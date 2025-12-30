from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

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