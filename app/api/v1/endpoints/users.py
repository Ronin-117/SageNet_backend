from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from app.core.logger import setup_logger
from app.dependencies import get_current_user
from app.services.firebase_svc import firebase_svc
from app.models.schemas import UserRegisterRequest, GeneralResponse, UserProfileResponse, UserUpdateRequest

router = APIRouter()

log = setup_logger("UserRouter")

class TokenRequest(BaseModel):
    token: str

# ==========================================
# 1. FCM TOKEN REGISTRATION
# ==========================================
@router.post("/fcm", status_code=status.HTTP_200_OK)
def register_fcm_token(
    payload: TokenRequest,
    uid: str = Depends(get_current_user)
):
    """
    Registers the mobile device FCM token for push notifications.
    Idempotent operation (safe to call multiple times).
    """
    log.info(f"Registering FCM token for User: {uid}")
    
    success = firebase_svc.register_fcm_token(uid, payload.token)
    
    if not success:
        # Log is already handled in service, throw specific HTTP error
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Database unavailable, could not save token."
        )

    return {"status": "registered"}

@router.delete("/fcm", status_code=status.HTTP_200_OK)
def unregister_fcm_token(
    payload: TokenRequest, # Re-using the same schema { token: str }
    uid: str = Depends(get_current_user)
):
    """
    Call this on LOGOUT. Removes the token so the device stops receiving alerts 
    for this account.
    """
    success = firebase_svc.remove_fcm_token(uid, payload.token)
    
    if not success:
        # Non-critical error, but good to report
        log.warning(f"Failed to unregister token for {uid}")
    
    return {"status": "unregistered"}

# ==========================================
# 2. USER REGISTRATION (Profile Setup)
# ==========================================
@router.post("/register", response_model=GeneralResponse, status_code=status.HTTP_201_CREATED)
def register_user_profile(
    payload: UserRegisterRequest,
    uid: str = Depends(get_current_user)
):
    """
    Initializes the user profile with Location and Billing Config.
    Call this immediately after Firebase Auth Sign-Up.
    """
    log.info(f"Initializing Profile for User: {uid}")

    # Convert Pydantic model to Dict
    data = payload.model_dump()
    
    # Mark profile as complete for UI logic
    data['is_profile_complete'] = True

    success = firebase_svc.create_or_update_user_profile(uid, data)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to initialize user profile."
        )

    return GeneralResponse(
        status="success", 
        message="User profile created successfully"
    )

# ==========================================
# 3. GET PROFILE
# ==========================================
@router.get("/profile", response_model=UserProfileResponse)
def get_profile(uid: str = Depends(get_current_user)):
    """
    Retrieves current user settings.
    """
    user_data = firebase_svc.get_user_profile(uid)
    
    if not user_data:
        # Instead of 404, we return an empty profile structure so the UI doesn't crash
        # The 'is_profile_complete' flag tells UI to show the Setup Screen
        return UserProfileResponse(uid=uid, is_profile_complete=False)

    return UserProfileResponse(
        uid=uid,
        location=user_data.get("location"),
        billing_config=user_data.get("billing_config"),
        is_profile_complete=user_data.get("is_profile_complete", False)
    )

# ==========================================
# 4. UPDATE PROFILE (PATCH)
# ==========================================
@router.patch("/profile", response_model=GeneralResponse)
def update_profile(
    payload: UserUpdateRequest, 
    uid: str = Depends(get_current_user)
):
    """
    Partial update of user settings. 
    Only fields sent in the body will be updated.
    """
    # 1. Filter out None values (exclude_unset=True)
    # This prevents overwriting existing data with Nulls if the field wasn't sent
    update_data = payload.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="No valid fields provided for update."
        )

    log.info(f"User {uid} updating fields: {list(update_data.keys())}")

    # 2. Perform Update
    success = firebase_svc.create_or_update_user_profile(uid, update_data)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to update profile."
        )

    return GeneralResponse(
        status="success", 
        message="Profile updated successfully"
    )

@router.post("/sync_devices", response_model=GeneralResponse)
def sync_devices(uid: str = Depends(get_current_user)):
    """
    Force-updates the User's 'owned_devices' list by scanning the device registry.
    Fixes 'missing device' issues.
    """
    count = firebase_svc.sync_user_device_list(uid)
    
    if count == -1:
        raise HTTPException(status_code=500, detail="Sync failed")
        
    return GeneralResponse(
        status="success",
        message=f"Synced {count} devices."
    )