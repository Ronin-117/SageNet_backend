from fastapi import Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.firebase_svc import firebase_svc
from app.core.exceptions import AuthError, AccessDenied, DeviceNotFound

security = HTTPBearer()

async def get_current_user(creds: HTTPAuthorizationCredentials = Security(security)) -> str:
    """
    Validates Firebase JWT and returns the User UID.
    Used as a dependency in routes.
    """
    token = creds.credentials
    uid = firebase_svc.verify_token(token)
    
    if not uid:
        raise AuthError("Invalid or expired authentication token")
    return uid

def verify_ownership(device_id: str, user_uid: str):
    """
    Business logic to ensure User owns Device.
    """
    owner = firebase_svc.get_device_owner(device_id)
    
    if not owner:
        raise DeviceNotFound(device_id)
        
    if owner != user_uid:
        raise AccessDenied("You do not own this device")
    
    return True