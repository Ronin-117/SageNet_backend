from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum


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

class PhaseType(str, Enum):
    SINGLE = "1"
    THREE = "3"

class TariffType(str, Enum):
    DOMESTIC = "domestic"
    COMMERCIAL = "commercial"

class ActivityPoint(BaseModel):
    time: str          # ISO Timestamp of the 30-min block
    value: float       # 0.0 to 1.0 (Percentage of time active)

class ActivityResponse(BaseModel):
    device_id: str
    resolution: str = "30m"
    # Returns a dictionary: "0": [points], "1": [points]
    channels: Dict[str, List[ActivityPoint]]

class AdoptionRequest(BaseModel):
    gateway_id: str  # The parent device ID
    orphan_mac: str  # The MAC address found via discovery
    name: str = "New Switch"

class LocationConfig(BaseModel):
    country: str = Field(..., min_length=2, max_length=2, description="ISO Country Code (e.g. IN)")
    state: str = Field(..., min_length=2, max_length=3, description="State Code (e.g. KL)")

class BillingConfig(BaseModel):
    cycle_start_day: int = Field(1, ge=1, le=28, description="Day of month bill resets")
    phase: PhaseType = Field(PhaseType.SINGLE, description="Connection Phase")
    type: TariffType = Field(TariffType.DOMESTIC, description="Tariff Category")
    monthly_budget: float = Field(3000.0, description="Target budget in INR")

# Request Model: Registration (Strict - All fields required)
class UserRegisterRequest(BaseModel):
    location: LocationConfig
    billing_config: BillingConfig

# Request Model: Update (Loose - All fields optional)
class UserUpdateRequest(BaseModel):
    location: Optional[LocationConfig] = None
    billing_config: Optional[BillingConfig] = None

# Response Model: Profile
class UserProfileResponse(BaseModel):
    uid: str
    location: Optional[LocationConfig] = None
    billing_config: Optional[BillingConfig] = None
    is_profile_complete: bool = False