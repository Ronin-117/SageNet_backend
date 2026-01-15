from pydantic import BaseModel
from typing import List, Optional, Dict, Literal
from datetime import datetime
from pydantic import Field

class BillPrediction(BaseModel):
    device_id: str
    currency: str = "INR"
    current_usage_kwh: float
    current_bill_amt: float
    predicted_month_end_amt: float
    billing_cycle_start: datetime
    billing_cycle_end: datetime

class AnomalyEvent(BaseModel):
    timestamp: datetime
    severity: str  # "LOW", "MEDIUM", "CRITICAL"
    description: str
    detected_value: float
    threshold: float

class AnalyticsResponse(BaseModel):
    device_id: str
    bill: BillPrediction
    recent_anomalies: List[AnomalyEvent]


# Input: What the App sends to start training
class TrainRequest(BaseModel):
    channel_index: int = Field(..., ge=0, le=3, description="Relay Channel (0-3)")
    duration_hours: int = Field(24, ge=1, le=720, description="How long to collect data (Hours)")

# Storage: What we save in Firestore (per channel)
class AIChannelConfig(BaseModel):
    status: Literal["disabled", "learning", "training", "monitoring"] = "disabled"
    training_end: Optional[datetime] = None
    threshold: Optional[float] = None
    last_trained: Optional[datetime] = None

# Output: What the App sees
class AIStatusResponse(BaseModel):
    device_id: str
    channels: Dict[str, AIChannelConfig]

class ShopRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Product name (e.g., 'BLDC Fan')")
    budget: float = Field(..., gt=0, description="Max price in INR")

class ShopResponse(BaseModel):
    job_id: str
    status: str
    message: str

class BillPredictionResponse(BaseModel):
    device_id: str
    currency: str = "INR"
    units_consumed: float
    units_forecasted: float
    bill_current: float
    bill_forecasted: float
    tariff_plan: str # "KSEB Domestic LT-1A"