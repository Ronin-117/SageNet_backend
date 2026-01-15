import firebase_admin
from firebase_admin import credentials, firestore, auth,messaging
from app.core.config import settings
from app.core.logger import setup_logger
from datetime import datetime, timezone

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
                'type': '4ch_switch' # Default type
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

    def send_alert(self, device_id: str, title: str, body: str):
        """
        Sends a Push Notification to the device owner.
        Includes Rate Limiting (Max 1 alert per hour per device).
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
                # Convert Firestore timestamp to datetime
                last_time = last_alert.replace(tzinfo=timezone.utc)
                diff_min = (datetime.now(timezone.utc) - last_time).total_seconds() / 60
                
                if diff_min < 60: # 1 Hour Cool-down
                    log.info(f"Alert suppressed (Cool-down active for {device_id})")
                    return

            # 3. Get Owner's Tokens
            user_doc = self.db.collection('users').document(owner_id).get()
            if not user_doc.exists: return
            
            tokens = user_doc.to_dict().get('fcm_tokens', [])
            if not tokens:
                log.warning(f"No FCM tokens found for user {owner_id}")
                return

            # 4. Construct Message
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data={"device_id": device_id}, # Metadata for app click action
                tokens=tokens
            )

            # 5. Send
            response = messaging.send_multicast(message)
            log.info(f"Sent alert to {response.success_count} devices.")

            # 6. Update Last Alert Timestamp
            self.db.collection('devices').document(device_id).update({
                'last_alert_sent': firestore.SERVER_TIMESTAMP
            })

        except Exception as e:
            log.error(f"Notification Failed: {e}")

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

    def append_search_result(self, job_id: str, product: dict):
        """
        Adds a single product to the 'raw_products' array in Firestore.
        Uses arrayUnion to append without overwriting.
        """
        try:
            self.db.collection('searches').document(job_id).set({
                'status': 'processing',
                'raw_products': firestore.ArrayUnion([product]),
                'last_updated': firestore.SERVER_TIMESTAMP
            }, merge=True)
            log.info(f"Appended 1 item to Job {job_id}")
        except Exception as e:
            log.error(f"Firestore Append Error: {e}")
            
    def mark_search_complete(self, job_id: str, count: int):
        try:
            self.db.collection('searches').document(job_id).update({
                'status': 'scraped',
                'total_items': count,
                'completed_at': firestore.SERVER_TIMESTAMP
            })
        except: pass
    
    def save_analysis(self, job_id: str, analysis: dict):
        try:
            # This adds 'ai_analysis' field alongside 'raw_products'
            self.db.collection('searches').document(job_id).update({
                'ai_analysis': analysis,
                'status': 'analyzed'
            })
        except Exception as e:
            log.error(f"Analysis Save Error: {e}")

firebase_svc = FirebaseService()