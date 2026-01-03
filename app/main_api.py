from fastapi import FastAPI
from app.core.logger import setup_logger
from app.services.mqtt_svc import mqtt_svc
from app.api.v1.api import api_router

# 1. Setup Logging
log = setup_logger("API_Main")

# 2. Initialize FastAPI
app = FastAPI(
    title="Smart Energy API Pro",
    version="2.3.0",
    description="Enterprise-grade IoT Backend for SageNet Energy",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 3. Register Routers
app.include_router(api_router, prefix="/api/v1")

# 4. Lifecycle Events
@app.on_event("startup")
async def startup_event():
    """Start background services"""
    log.info("API Starting up...")
    mqtt_svc.start()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources"""
    log.info("API Shutting down...")
    # mqtt_svc.stop() # If you implement stop logic later

@app.get("/", tags=["Health"])
def health_check():
    # Change the version string to something unique
    return {"status": "healthy", "version": "2.3.0-AUTOMATED-TEST"}