import firebase_admin
from firebase_admin import credentials, firestore, auth,messaging
from app.core.config import settings
from app.core.logger import setup_logger
from datetime import datetime, timezone, timedelta


log = setup_logger("FirebaseService")

class FirebaseService:
    def __init__(self):
        if not firebase_admin._apps:
            try:
                cred = credentials.Certificate(settings.FIREBASE_CRED)
                firebase_admin.initialize_app(cred)
                log.info("Firebase Initialized Successfully")
            except Exception as e:
                log.error(f"Failed to init Firebase: {e}")
                raise e
        self.db = firestore.client()

    def get_device_owner(self, device_id: str):
        try:
            doc = self.db.collection('devices').document(device_id).get()
            if doc.exists:
                return doc.to_dict().get('owner_id')
            return None
        except Exception as e:
            log.error(f"Firestore Error for {device_id}: {e}")
            return None

    def verify_token(self, token: str):
        try:
            decoded_token = auth.verify_id_token(token)
            return decoded_token['uid']
        except Exception as e:
            log.warning(f"Auth Token Verification Failed: {e}")
            return None
    
    def claim_device(self, user_uid: str, device_id: str, name: str):
        try:
            # 1. Update the Device Document
            device_ref = self.db.collection('devices').document(device_id)
            device_ref.set({
                'owner_id': user_uid,
                'friendly_name': name,
                'claimed_at': firestore.SERVER_TIMESTAMP,
                'type': 'gateway',    # <--- Explicit
                'is_gateway': True,   # <--- Explicit
                'connected_satellites': [] # Init empty list
            }, merge=True) # merge=True prevents wiping existing stats

            # 2. Add to User's list (Optional, but good for fast lookups)
            user_ref = self.db.collection('users').document(user_uid)
            user_ref.set({
                'owned_devices': firestore.ArrayUnion([device_id])
            }, merge=True)

            log.info(f"Device {device_id} claimed by {user_uid}")
            return True
        except Exception as e:
            log.error(f"Claim Error: {e}")
            return False

    def update_device_state(self, device_id: str, new_states: list):
        """
        Updates live state AND tracks 'last_switched_on' time for warm-up logic.
        """
        try:
            doc_ref = self.db.collection('devices').document(device_id)
            
            # 1. Get current state to compare (needed to detect OFF->ON transition)
            doc = doc_ref.get()
            current_data = doc.to_dict() if doc.exists else {}
            old_states = current_data.get('live_state', [0]*4)
            last_switched = current_data.get('last_switched_on', [None]*4)

            # 2. Logic: If state changed from 0 to 1, update timestamp
            now_iso = datetime.now(timezone.utc).isoformat()
            
            updated_switched = []
            for i, state in enumerate(new_states):
                # Safety check for list length
                old_val = old_states[i] if i < len(old_states) else 0
                last_time = last_switched[i] if i < len(last_switched) else None
                
                if state == 1 and old_val == 0:
                    # Rising Edge (Turned ON) -> Update Time
                    updated_switched.append(now_iso)
                elif state == 0:
                    # Turned OFF -> Reset Time (Optional, or keep history)
                    updated_switched.append(None)
                else:
                    # No Change -> Keep old time
                    updated_switched.append(last_time)

            # 3. Save
            doc_ref.set({
                'live_state': new_states,
                'last_switched_on': updated_switched,
                'last_contact': firestore.SERVER_TIMESTAMP
            }, merge=True)
            
        except Exception as e:
            log.error(f"State Update Error: {e}")
    
    def update_ai_status(self, device_id: str, channel: int, status: str, training_end: datetime = None, threshold: float = None):
        """
        Updates the AI configuration for a specific channel.
        """
        try:
            data = {
                f"ai_config.{channel}.status": status
            }
            if training_end:
                data[f"ai_config.{channel}.training_end"] = training_end
            if threshold:
                data[f"ai_config.{channel}.threshold"] = threshold
            
            self.db.collection('devices').document(device_id).update(data)
            log.info(f"AI Config updated for {device_id} Ch {channel}: {status}")
            return True
        except Exception as e:
            log.error(f"AI Config Update Error: {e}")
            return False

    def get_device_full(self, device_id: str):
        """Helper to get full document for the Analytics Engine"""
        doc = self.db.collection('devices').document(device_id).get()
        return doc.to_dict() if doc.exists else None

    def register_fcm_token(self, user_uid: str, token: str):
        """
        Saves the phone's notification token to the user profile.
        Uses ArrayUnion to allow multiple devices (Phone + Tablet).
        """
        try:
            self.db.collection('users').document(user_uid).set({
                'fcm_tokens': firestore.ArrayUnion([token])
            }, merge=True)
            log.info(f"FCM Token registered for {user_uid}")
            return True
        except Exception as e:
            log.error(f"Token Reg Error: {e}")
            return False

    def send_alert(self, device_id: str, title: str, body: str, channel: int):
        """
        Sends a Push Notification using the modern 'send_each_for_multicast' API.
        """
        try:
            # 1. Get Device & Owner
            doc = self.db.collection('devices').document(device_id).get()
            if not doc.exists: return

            data = doc.to_dict()
            owner_id = data.get('owner_id')
            last_alert = data.get('last_alert_sent')

            # 2. Rate Limiting (Cool-down check)
            if last_alert:
                last_time = last_alert.replace(tzinfo=timezone.utc)
                diff_min = (datetime.now(timezone.utc) - last_time).total_seconds() / 60
                # Reduce cooldown to 1 minute for testing, set to 60 for production
                if diff_min < 1: 
                    log.info(f"Alert suppressed (Cool-down active for {device_id})")
                    return

            # 3. Get Owner's Tokens
            user_doc = self.db.collection('users').document(owner_id).get()
            if not user_doc.exists: return

            tokens = user_doc.to_dict().get('fcm_tokens', [])
            if not tokens:
                log.warning(f"No FCM tokens found for user {owner_id}")
                return

            # 4. Construct Message (Modern API)
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data={
                    "device_id": device_id,
                    "screen": "analytics", # Routing hint for App
                    "channel": str(channel), 
                }, 
                tokens=tokens
            )

            # 5. Send using the modern method
            # 'send_multicast' is legacy; 'send_each_for_multicast' is current
            try:
                response = messaging.send_each_for_multicast(message)
                log.info(f"Sent alert to {response.success_count} devices. (Failed: {response.failure_count})")
            except AttributeError:
                # Fallback for older libraries (just in case)
                response = messaging.send_multicast(message)
                log.info(f"Sent alert (Legacy) to {response.success_count} devices.")

            # 6. Update Last Alert Timestamp
            self.db.collection('devices').document(device_id).update({
                'last_alert_sent': firestore.SERVER_TIMESTAMP
            })

        except Exception as e:
            log.error(f"Notification Failed: {e}", exc_info=True)
            
    def save_alert(self, user_uid: str, alert_data: dict):
        """
        Saves an anomaly event to the user's history.
        Includes an 'expires_at' field for 3-month retention policies.
        """
        try:
            # 1. Calculate Expiration (90 Days from now)
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(days=90)

            # 2. Prepare Data
            doc_data = {
                "title": alert_data.get("title", "System Alert"),
                "body": alert_data.get("body", ""),
                "device_id": alert_data.get("device_id"),
                "channel": alert_data.get("channel"),
                "severity": alert_data.get("severity", "warning"), # 'warning' or 'critical'
                "timestamp": firestore.SERVER_TIMESTAMP,
                "expires_at": expires_at, # For TTL cleanup
                "read": False
            }

            # 3. Write to Sub-collection: users/{uid}/alerts/{auto_id}
            self.db.collection('users').document(user_uid).collection('alerts').add(doc_data)
            
            log.info(f"Alert saved for User {user_uid}: {alert_data.get('title')}")
            return True
        except Exception as e:
            log.error(f"Failed to save alert: {e}")
            return False

    def remove_fcm_token(self, user_uid: str, token: str):
        """
        Removes a specific FCM token on logout.
        """
        try:
            self.db.collection('users').document(user_uid).update({
                'fcm_tokens': firestore.ArrayRemove([token])
            })
            log.info(f"FCM Token removed for {user_uid}")
            return True
        except Exception as e:
            log.error(f"Token Removal Error: {e}")
            return False

    def save_search_results(self, job_id: str, results: list):
        try:
            self.db.collection('searches').document(job_id).set({
                'status': 'scraped',
                'raw_products': results,
                'scraped_at': firestore.SERVER_TIMESTAMP
            }, merge=True)
            log.info(f"Saved {len(results)} items to Firestore for Job {job_id}")
        except Exception as e:
            log.error(f"Firestore Save Error: {e}")

    def update_job_status(self, job_id: str, status: str):
        """Generic helper to move the progress bar in the UI."""
        try:
            self.db.collection('searches').document(job_id).update({
                'status': status,
                'last_updated': firestore.SERVER_TIMESTAMP
            })
        except Exception as e:
            log.error(f"Status Update Error [{job_id}]: {e}")

    def append_search_result(self, job_id: str, product: dict):
        """
        Adds a single product to the array. 
        FIXED: Removed 'status': 'processing' to prevent progress bar jumping.
        """
        try:
            self.db.collection('searches').document(job_id).set({
                'raw_products': firestore.ArrayUnion([product]),
                'last_updated': firestore.SERVER_TIMESTAMP
            }, merge=True)
        except Exception as e:
            log.error(f"Firestore Append Error: {e}")

    def mark_search_complete(self, job_id: str, count: int):
        """Finalizes the scraping phase."""
        try:
            self.db.collection('searches').document(job_id).update({
                'status': 'scraped', # Now at 70% progress
                'total_items': count,
                'completed_at': firestore.SERVER_TIMESTAMP
            })
        except Exception as e:
            log.error(f"Mark Complete Error: {e}")
    
    def save_analysis(self, job_id: str, analysis: dict):
        try:
            # This adds 'ai_analysis' field alongside 'raw_products'
            self.db.collection('searches').document(job_id).update({
                'ai_analysis': analysis,
                'status': 'analyzed'
            })
        except Exception as e:
            log.error(f"Analysis Save Error: {e}")

    def save_discovered_orphan(self, gateway_id: str, orphan_data: dict):
        """
        Updates the Gateway's 'discovered_orphans' map.
        UI listens to this field to show the "Scan" list.
        """
        try:
            mac = orphan_data.get('mac')
            if not mac: return

            # Structure: { "MAC_ADDR": { rssi: -60, type: "switch", last_seen: TIME } }
            update_payload = {
                f"discovered_orphans.{mac}": {
                    "rssi": orphan_data.get('rssi'),
                    "type": orphan_data.get('type', 'unknown'),
                    "last_seen": firestore.SERVER_TIMESTAMP
                }
            }
            
            self.db.collection('devices').document(gateway_id).update(update_payload)
            # log.info(f"Gateway {gateway_id} spotted {mac}") # Uncomment for verbose debug
        except Exception as e:
            # If doc doesn't exist yet, we might need to set it, but Gateway should exist by now
            log.error(f"Orphan Save Error: {e}")

    def register_satellite(self, mac_address: str, owner_id: str, gateway_id: str, name: str):
        """
        1. Creates Satellite Document.
        2. Links to User.
        3. Links to Gateway (Parent).
        4. Removes from Gateway's 'discovered_orphans' list.
        """
        try:
            batch = self.db.batch()

            # A. Create Satellite Doc
            sat_ref = self.db.collection('devices').document(mac_address)
            sat_data = {
                'owner_id': owner_id,
                'friendly_name': name,
                'type': 'satellite',
                'is_gateway': False,        # <--- UI Filter Flag
                'parent_gateway': gateway_id,
                'created_at': firestore.SERVER_TIMESTAMP,
                'live_state': [0, 0, 0, 0]
            }
            batch.set(sat_ref, sat_data)

            # B. Link to User
            user_ref = self.db.collection('users').document(owner_id)
            batch.set(user_ref, {
                'owned_devices': firestore.ArrayUnion([mac_address])
            }, merge=True)

            # C. Link to Gateway (Add to children, Remove from orphans)
            gateway_ref = self.db.collection('devices').document(gateway_id)
            batch.update(gateway_ref, {
                'connected_satellites': firestore.ArrayUnion([mac_address]),
                f'discovered_orphans.{mac_address}': firestore.DELETE_FIELD # Cleanup
            })

            batch.commit()
            log.info(f"Satellite {mac_address} fully adopted via {gateway_id}")
            return True
        except Exception as e:
            log.error(f"Satellite Reg Error: {e}")
            return False

    def set_device_as_gateway(self, device_id: str):
        """
        Helper to ensure a device is marked as a Gateway when it connects directly.
        Called by Bridge when 'telem' is received from a direct connection.
        """
        try:
            self.db.collection('devices').document(device_id).set({
                'type': 'gateway',
                'is_gateway': True
            }, merge=True)
        except: pass

    def create_or_update_user_profile(self, uid: str, data: dict) -> bool:
        """
        Upserts user profile data.
        """
        try:
            # 1. Add Metadata
            data['updated_at'] = firestore.SERVER_TIMESTAMP
            
            # 2. Write to Firestore
            # merge=True is CRITICAL. It ensures we don't wipe out 'fcm_tokens' or 'owned_devices'
            self.db.collection('users').document(uid).set(data, merge=True)
            
            log.info(f"User Profile updated for UID: {uid}")
            return True

        except Exception as e:
            log.error(f"🔥 Firestore Profile Write Error [UID: {uid}]: {e}", exc_info=True)
            return False

    def get_user_profile(self, uid: str) -> dict:
        """
        Fetches user document safely.
        """
        try:
            doc = self.db.collection('users').document(uid).get()
            if doc.exists:
                return doc.to_dict()
            
            log.warning(f"User Profile not found for UID: {uid}")
            return {}

        except Exception as e:
            log.error(f"🔥 Firestore Profile Read Error [UID: {uid}]: {e}", exc_info=True)
            return {}

    def sync_user_device_list(self, uid: str) -> int:
        """
        Repairs the 'owned_devices' array in the User Profile.
        It queries ALL devices owned by the user and overwrites the array.
        """
        try:
            # 1. Query all devices where owner_id == uid
            # Note: Admin SDK bypasses security rules, so this always works.
            docs = self.db.collection('devices').where('owner_id', '==', uid).stream()
            
            # 2. Extract IDs
            device_ids = [doc.id for doc in docs]
            
            # 3. Force Update the User Profile
            self.db.collection('users').document(uid).set({
                'owned_devices': device_ids,
                'last_synced': firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            log.info(f"Synced {len(device_ids)} devices for User {uid}")
            return len(device_ids)

        except Exception as e:
            log.error(f"Sync Devices Error: {e}")
            return -1

    def send_user_notification(self, user_uid: str, title: str, body: str, data: dict = None):
        """
        Sends a Push Notification to a specific User (all their logged-in devices).
        Used for async jobs like Shopping Results.
        """
        try:
            # 1. Get User's Tokens
            user_doc = self.db.collection('users').document(user_uid).get()
            if not user_doc.exists:
                log.warning(f"User {user_uid} not found for notification.")
                return

            tokens = user_doc.to_dict().get('fcm_tokens', [])
            if not tokens:
                log.info(f"No FCM tokens for user {user_uid}. Skipping alert.")
                return

            # 2. Prepare Payload
            payload_data = data if data else {}
            
            # 3. Construct Message
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data=payload_data, # Metadata for App routing
                tokens=tokens
            )

            # 4. Send
            try:
                response = messaging.send_each_for_multicast(message)
                log.info(f"Sent user alert to {response.success_count} devices.")
            except AttributeError:
                response = messaging.send_multicast(message) # Fallback
                log.info(f"Sent user alert (Legacy) to {response.success_count} devices.")

        except Exception as e:
            log.error(f"User Notification Failed: {e}", exc_info=True)

    def create_initial_search_job(self, job_id: str, uid: str, query: str, budget: float):
        """
        Creates the placeholder document immediately so it appears in the User's history.
        """
        try:
            self.db.collection('searches').document(job_id).set({
                'uid': uid,                # <--- The Field the App is looking for
                'query': query,
                'budget': budget,
                'status': 'queued',
                'created_at': firestore.SERVER_TIMESTAMP, # <--- Needed for Ordering
                'raw_products': []
            })
            log.info(f"Created initial search job {job_id} for user {uid}")
            return True
        except Exception as e:
            log.error(f"Failed to create search job: {e}")
            return False

firebase_svc = FirebaseService()