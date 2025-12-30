from pydantic import BaseModel, Field
from typing import List, Optional

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