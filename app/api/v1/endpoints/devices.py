from fastapi import APIRouter, Depends
from typing import List

# Import Core Components
from app.dependencies import get_current_user, verify_ownership
from app.models.schemas import (
    RelayCommand, 
    CommandResponse, 
    HistoryResponse, 
    HistoryPoint,
    LongHistoryResponse,
    DailyUsagePoint,
    DeviceClaimRequest,
    ActivityResponse,
    ActivityPoint
)
from app.services.mqtt_svc import mqtt_svc
from app.services.influx_svc import influx_svc
from app.services.firebase_svc import firebase_svc
from app.core.exceptions import MqttPublishError, InfluxQueryError


# Initialize Router
router = APIRouter(
    tags=["Devices"],
    responses={404: {"description": "Not found"}},
)

@router.post("/{device_id}/control", response_model=CommandResponse)
def control_device(
    device_id: str, 
    cmd: RelayCommand, 
    uid: str = Depends(get_current_user)
):
    """
    Send a remote command to the ESP32 via MQTT.
    """
    # 1. Security Check
    verify_ownership(device_id, uid)

    # 2. Execute Logic (MQTT)
    success = mqtt_svc.publish_command(device_id, cmd.index, cmd.state)
    
    if not success:
        raise MqttPublishError("Device did not acknowledge the command")

    return CommandResponse(
        device=device_id,
        action=f"Relay {cmd.index} {'ON' if cmd.state else 'OFF'}"
    )

@router.get("/{device_id}/history", response_model=HistoryResponse)
def get_device_history(
    device_id: str, 
    uid: str = Depends(get_current_user)
):
    """
    Fetch last 1 hour of voltage/power data for graphs.
    """
    # 1. Security Check
    verify_ownership(device_id, uid)

    # 2. Execute Logic (InfluxDB)
    try:
        data = influx_svc.get_history(device_id)
        
        # Convert raw dicts to Pydantic models for validation
        formatted_data = [HistoryPoint(**point) for point in data]
        
        return HistoryResponse(
            device=device_id,
            count=len(formatted_data),
            data=formatted_data
        )
    except Exception as e:
        raise InfluxQueryError(str(e))

@router.post("/claim", response_model=CommandResponse)
def claim_device(
    payload: DeviceClaimRequest,
    uid: str = Depends(get_current_user)
):
    """
    Links a device to the logged-in user.
    Called when User scans QR code in App.
    """
    # We do NOT verify ownership here because the user doesn't own it YET.
    # We verify the device simply exists or trust the ID provided.
    
    success = firebase_svc.claim_device(uid, payload.device_id, payload.friendly_name)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to register device")

    return CommandResponse(
        device=payload.device_id, 
        action="Device Successfully Claimed", 
        status="success"
    )

@router.get("/{device_id}/history/daily", response_model=LongHistoryResponse)
def get_daily_history(
    device_id: str,
    days: int = 7,
    uid: str = Depends(get_current_user)
):
    """
    Get aggregated history for last N days (Max 30).
    """
    # 1. Validation
    if days > 30:
        raise HTTPException(status_code=400, detail="Max history is 30 days")
        
    # 2. Security
    verify_ownership(device_id, uid)

    # 3. Logic
    try:
        data = influx_svc.get_long_history(device_id, days)
        
        # Convert to Pydantic
        formatted = [DailyUsagePoint(**p) for p in data]
        
        return LongHistoryResponse(
            device_id=device_id,
            days=days,
            data=formatted
        )
    except Exception as e:
        raise InfluxQueryError(str(e))

@router.get("/{device_id}/activity", response_model=ActivityResponse)
def get_device_activity(
    device_id: str,
    days: int = 7,
    uid: str = Depends(get_current_user)
):
    """
    Get ON/OFF patterns for the last N days (Max 30).
    Resolution: 30 minutes.
    Values: 0.0 (Off) to 1.0 (On).
    """
    if days > 30:
        raise HTTPException(status_code=400, detail="Max history is 30 days")
        
    verify_ownership(device_id, uid)

    try:
        data = influx_svc.get_activity_patterns(device_id, days)
        
        return ActivityResponse(
            device_id=device_id,
            channels=data
        )
    except Exception as e:
        raise InfluxQueryError(str(e))