from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.dependencies import get_current_user
from app.services.firebase_svc import firebase_svc
from app.models.schemas import UserRegisterRequest, GeneralResponse

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

@router.post("/register", response_model=GeneralResponse)
def register_user_profile(
    payload: UserRegisterRequest,
    uid: str = Depends(get_current_user)
):
    """
    Call this immediately after Firebase Login to set Location & Billing Config.
    """
    # Convert Pydantic model to dict (nested)
    data = payload.model_dump() # For Pydantic v2. Use .dict() if on v1.
    
    success = firebase_svc.create_or_update_user_profile(uid, data)
    
    if not success:
        raise HTTPException(status_code=500, detail="Database Write Failed")

    return GeneralResponse(
        status="success", 
        message="User profile created successfully"
    )