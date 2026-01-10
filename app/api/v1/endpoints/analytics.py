from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_current_user, verify_ownership
from app.models.analytics_schemas import BillPrediction, AnalyticsResponse, TrainRequest, AIStatusResponse
from app.services.analytics_svc import analytics_svc
from app.services.firebase_svc import firebase_svc
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/{device_id}/bill", response_model=BillPrediction)
def get_live_bill(
    device_id: str,
    uid: str = Depends(get_current_user)
):
    """
    Get real-time billing estimation.
    """
    verify_ownership(device_id, uid)
    
    try:
        data = analytics_svc.calculate_bill(device_id)
        return BillPrediction(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Calculation Error")

@router.get("/{device_id}/insights", response_model=AnalyticsResponse)
def get_ai_insights(
    device_id: str,
    uid: str = Depends(get_current_user)
):
    """
    Get Bill + Anomalies in one request.
    """
    verify_ownership(device_id, uid)
    
    bill = analytics_svc.calculate_bill(device_id)
    anomalies = analytics_svc.check_anomalies(device_id)
    
    return AnalyticsResponse(
        device_id=device_id,
        bill=bill,
        recent_anomalies=anomalies
    )

@router.post("/{device_id}/train", response_model=AIStatusResponse)
def trigger_training(
    device_id: str,
    payload: TrainRequest,
    uid: str = Depends(get_current_user)
):
    """
    Start the Learning Phase for a specific appliance (Channel).
    """
    verify_ownership(device_id, uid)
    
    # Calculate end time
    end_time = datetime.utcnow() + timedelta(hours=payload.duration_hours)
    
    # Update DB to "learning"
    success = firebase_svc.update_ai_status(
        device_id=device_id,
        channel=payload.channel_index,
        status="learning",
        training_end=end_time
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update AI config")

    # Return updated status (Mocking the fetch for speed)
    # In real app, you might re-fetch the full config
    return get_ai_status(device_id, uid)

@router.get("/{device_id}/ai/status", response_model=AIStatusResponse)
def get_ai_status(
    device_id: str,
    uid: str = Depends(get_current_user)
):
    """
    Check if devices are Learning, Training, or Monitoring.
    """
    verify_ownership(device_id, uid)
    
    data = firebase_svc.get_device_full(device_id)
    if not data:
        raise HTTPException(status_code=404, detail="Device not found")
        
    ai_config = data.get("ai_config", {})
    
    return AIStatusResponse(
        device_id=device_id,
        channels=ai_config
    )