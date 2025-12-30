from fastapi import APIRouter, Depends
from typing import List

# Import Core Components
from app.dependencies import get_current_user, verify_ownership
from app.models.schemas import (
    RelayCommand, 
    CommandResponse, 
    HistoryResponse, 
    HistoryPoint
)
from app.services.mqtt_svc import mqtt_svc
from app.services.influx_svc import influx_svc
from app.core.exceptions import MqttPublishError, InfluxQueryError

# Initialize Router
router = APIRouter(
    prefix="/devices",
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