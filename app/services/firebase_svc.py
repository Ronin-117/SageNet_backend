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

firebase_svc = FirebaseService()