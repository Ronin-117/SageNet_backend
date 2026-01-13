import time
import json
import redis
from app.core.config import settings
from app.core.logger import setup_logger
from app.services.scraper_svc import scraper_svc
from app.services.firebase_svc import firebase_svc

log = setup_logger("ScraperWorker")

# Connect to Global Redis
r = redis.Redis(
    host=settings.REDIS_HOST, 
    port=settings.REDIS_PORT, 
    password=settings.REDIS_PASS, 
    decode_responses=True
)

QUEUE_NAME = "scraper_jobs"

def process_jobs():
    log.info("🕷️ Scraper Worker Started. Waiting for jobs...")
    
    while True:
        # Blocking Pop: Waits here until a job arrives
        # Result: ('scraper_jobs', '{"job_id": "123", "query": "Fan"}')
        task = r.blpop(QUEUE_NAME, timeout=30)
        
        if task:
            _, data_str = task
            try:
                job_data = json.loads(data_str)
                job_id = job_data['job_id']
                query = job_data['query']
                uid = job_data['uid']
                
                log.info(f"Processing Job {job_id}: {query}")
                
                # 1. Scrape Both Sites
                results = scraper_svc.scrape_all(query)
                
                log.info(f"Scraping finished. Found {len(results)} items.")
                
                # 2. Save Raw Results to Firestore
                # (We will implement this save method next, for now just log)
                firebase_svc.save_search_results(job_id, results)
                
                # 3. Trigger AI Analysis (Future Step)
                # We will push this to an 'ai_jobs' queue later
                
                log.info(f"Job {job_id} Completed. Found {len(results)} items.")
                
            except Exception as e:
                log.error(f"Job Failed: {e}")

if __name__ == "__main__":
    process_jobs()