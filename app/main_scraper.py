import time
import json
import redis
from app.core.config import settings
from app.core.logger import setup_logger
from app.services.scraper_svc import scraper_svc
from app.services.firebase_svc import firebase_svc
from app.services.llm_svc import llm_svc

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
                uid = job_data.get('uid') # Needed for notification
                query = job_data['query']
                
                log.info(f"Processing Job {job_id}: {query}")

                # Capture items
                collected_items = []

                def on_item_found(item):
                    collected_items.append(item)
                    firebase_svc.append_search_result(job_id, item)

                # Execute Scraping
                scraper_svc.scrape_all_stream(query, on_item_found)

                # --- AI ANALYSIS ---
                if collected_items:
                    log.info("🔍 Running AI Analysis...")
                    # Pass budget if available
                    analysis = llm_svc.analyze_products(query, job_data.get('budget', 0), collected_items)

                    if analysis:
                        firebase_svc.save_analysis(job_id, analysis)
                        log.info("✅ AI Analysis Saved.")

                # Mark Done
                firebase_svc.mark_search_complete(job_id, len(collected_items))
                
                # --- NEW: SEND NOTIFICATION ---
                if uid:
                    item_count = len(collected_items)
                    msg_body = f"Found {item_count} items."
                    if item_count > 0:
                        msg_body += " Tap to view AI recommendations."
                    else:
                        msg_body += " Try a different search term."

                    firebase_svc.send_user_notification(
                        user_uid=uid,
                        title="Shopping Search Complete",
                        body=msg_body,
                        data={
                            "screen": "shopping_result", # Hint for Frontend Routing
                            "job_id": job_id
                        }
                    )
                # ------------------------------

                log.info(f"Job {job_id} Completed.")

            except Exception as e:
                log.error(f"Job Failed: {e}", exc_info=True)

if __name__ == "__main__":
    process_jobs()