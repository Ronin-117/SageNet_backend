from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.dependencies import get_current_user
from app.services.firebase_svc import firebase_svc

router = APIRouter()

class TokenRequest(BaseModel):
    token: str

@router.post("/fcm", status_code=200)
def register_token(
    payload: TokenRequest,
    uid: str = Depends(get_current_user)
):
    """
    Mobile App calls this on startup to register for notifications.
    """
    success = firebase_svc.register_fcm_token(uid, payload.token)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save token")
    
    return {"status": "registered"}