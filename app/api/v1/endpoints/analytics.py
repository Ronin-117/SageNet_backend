from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_current_user, verify_ownership
from app.models.analytics_schemas import BillPrediction, AnalyticsResponse
from app.services.analytics_svc import analytics_svc

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