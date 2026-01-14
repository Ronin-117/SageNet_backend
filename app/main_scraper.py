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
    log.info("🕷️ Scraper Worker Started...")
    
    while True:
        task = r.blpop(QUEUE_NAME, timeout=30)
        
        if task:
            _, data_str = task
            try:
                job_data = json.loads(data_str)
                job_id = job_data['job_id']
                query = job_data['query']
                
                log.info(f"Processing Job {job_id}: {query}")
                
                # Define the callback function
                def on_item_found(item):
                    firebase_svc.append_search_result(job_id, item)

                # Execute
                total_count = scraper_svc.scrape_all_stream(query, on_item_found)
                
                # Mark Done
                firebase_svc.mark_search_complete(job_id, total_count)
                log.info(f"Job {job_id} Completed. Found {total_count} items.")
                
            except Exception as e:
                log.error(f"Job Failed: {e}")

if __name__ == "__main__":
    process_jobs()