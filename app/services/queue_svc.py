import redis
import json
import uuid
from app.core.config import settings
from app.core.logger import setup_logger
import time 

log = setup_logger("QueueService")

class QueueService:
    def __init__(self):
        try:
            self.redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASS,
                decode_responses=True
            )
            # Test connection
            self.redis.ping()
            log.info("✅ Connected to Global Redis")
        except Exception as e:
            log.error(f"❌ Redis Connection Failed: {e}")
            self.redis = None

    def push_scraper_job(self, query: str, budget: float, uid: str) -> str:
        if not self.redis: return None

        job_id = str(uuid.uuid4())
        
        job_data = {
            "job_id": job_id,
            "query": query,
            "budget": budget,
            "uid": uid,
            "status": "queued",
            "timestamp": time.time()
        }

        try:
            self.redis.rpush("scraper_jobs", json.dumps(job_data))
            log.info(f"Job {job_id} pushed to queue")
            return job_id
        except Exception as e:
            log.error(f"Failed to push job: {e}")
            return None


queue_svc = QueueService()