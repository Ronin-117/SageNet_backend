from fastapi import APIRouter, Depends
from typing import List
from typing import Optional

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
    ActivityPoint,
    AdoptionRequest
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
    minutes: int = 60,       # Default 1 hour
    channel: Optional[int] = None, # Default None (Whole Board)
    uid: str = Depends(get_current_user)
):
    """
    Fetch history.
    - minutes: 5, 30, 60, 720 (12h), 1440 (24h)
    - channel: 0-3 (Relay specific) or leave empty for Total Board
    """
    verify_ownership(device_id, uid)

    try:
        data = influx_svc.get_history(device_id, minutes, channel)
        
        # Note: We reuse HistoryPoint but "voltage" might be missing if channel is selected.
        # Pydantic might complain if voltage is missing. 
        # Let's clean the data to ensure 0.0 defaults if missing.
        cleaned_data = []
        for d in data:
            cleaned_data.append({
                "time": d["time"],
                "voltage": d.get("voltage", 0.0), # Default to 0 if relay view
                "power": d.get("power", 0.0)
            })

        formatted_data = [HistoryPoint(**point) for point in cleaned_data]

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


@router.post("/adopt", response_model=CommandResponse)
def adopt_device(
    payload: AdoptionRequest,
    uid: str = Depends(get_current_user)
):
    """
    1. Verify user owns the Gateway.
    2. Register the Orphan in DB.
    3. Send MQTT command to Gateway to transmit credentials.
    """
    # 1. Security Check (User must own the Gateway to use it for adoption)
    verify_ownership(payload.gateway_id, uid)

    # 2. Register in Database
    db_success = firebase_svc.register_satellite(
        payload.orphan_mac, 
        uid, 
        payload.gateway_id, 
        payload.name
    )
    
    if not db_success:
        raise HTTPException(status_code=500, detail="Database Registration Failed")

    # 3. Send Command to Gateway
    mqtt_success = mqtt_svc.send_adoption_command(
        payload.gateway_id, 
        payload.orphan_mac, 
        uid
    )

    if not mqtt_success:
        # Rollback DB? Or just let user retry.
        raise HTTPException(status_code=500, detail="Failed to send command to Gateway")

    return CommandResponse(
        device=payload.orphan_mac,
        action="Adoption Signal Sent",
        status="success"
    )