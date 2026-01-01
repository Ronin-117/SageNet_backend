from pydantic import BaseModel, Field
from typing import List, Optional, Dict


# ================= INPUT MODELS (REQUESTS) =================

class RelayCommand(BaseModel):
    """
    Payload for controlling a switch.
    """
    index: int = Field(
        ..., 
        ge=0, 
        le=3, 
        description="The relay channel index (0 to 3)"
    )
    state: bool = Field(
        ..., 
        description="Target state: True (ON) or False (OFF)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "index": 0,
                "state": True
            }
        }

# ================= OUTPUT MODELS (RESPONSES) =================

class GeneralResponse(BaseModel):
    """Standard generic response"""
    status: str
    message: Optional[str] = None

class CommandResponse(BaseModel):
    """Response after toggling a switch"""
    status: str = "success"
    device: str
    action: str

class HistoryPoint(BaseModel):
    """A single data point for graphs"""
    time: str
    voltage: float
    power: float

class HistoryResponse(BaseModel):
    """Response for historical data queries"""
    device: str
    count: int
    data: List[HistoryPoint]

class DeviceStatus(BaseModel):
    """Current state of the device (Optional for future use)"""
    device_id: str
    online: bool
    last_seen: str

class DailyUsagePoint(BaseModel):
    date: str
    avg_voltage: float
    total_energy_kwh: float
    
class LongHistoryResponse(BaseModel):
    device_id: str
    days: int
    data: List[DailyUsagePoint]

class DeviceClaimRequest(BaseModel):
    device_id: str
    friendly_name: str = "Smart Switch"

class ActivityPoint(BaseModel):
    time: str          # ISO Timestamp of the 30-min block
    value: float       # 0.0 to 1.0 (Percentage of time active)

class ActivityResponse(BaseModel):
    device_id: str
    resolution: str = "30m"
    # Returns a dictionary: "0": [points], "1": [points]
    channels: Dict[str, List[ActivityPoint]]