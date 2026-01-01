import firebase_admin
from firebase_admin import credentials, firestore, auth
from app.core.config import settings
from app.core.logger import setup_logger

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

    def update_device_state(self, device_id: str, states: list):
        """
        Updates the 'live_state' field in Firestore.
        Used by the App to show Green/Grey buttons.
        """
        try:
            doc_ref = self.db.collection('devices').document(device_id)
            doc_ref.set({
                'live_state': states, # e.g. [1, 0, 0, 1]
                'last_contact': firestore.SERVER_TIMESTAMP
            }, merge=True)
            # log.info(f"State updated for {device_id}: {states}") # Optional log
        except Exception as e:
            log.error(f"Firestore State Update Failed: {e}")

firebase_svc = FirebaseService()