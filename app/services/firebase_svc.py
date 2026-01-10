import firebase_admin
from firebase_admin import credentials, firestore, auth
from app.core.config import settings
from app.core.logger import setup_logger
from datetime import datetime
from pytz import timezone

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

firebase_svc = FirebaseService()