from fastapi import APIRouter
from app.api.v1.endpoints import devices, analytics

api_router = APIRouter()

# 1. Device Control & Raw Data
api_router.include_router(devices.router, prefix="/devices", tags=["Devices"])

# 2. AI & Billing (New Module)
api_router.include_router(analytics.router, prefix="/analytics", tags=["Intelligence"])