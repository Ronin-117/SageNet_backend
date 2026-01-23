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
        # 1. Wait for Job (UI is currently in 'queued' state from API)
        task = r.blpop(QUEUE_NAME, timeout=30)

        if task:
            _, data_str = task
            try:
                job_data = json.loads(data_str)
                job_id = job_data['job_id']
                uid = job_data.get('uid')
                query = job_data['query']
                budget = job_data.get('budget', 0.0)
                
                log.info(f"Processing Job {job_id}: {query}")

                # --- STEP 1: PROCESSING (UI: 40%) ---
                # "Analyzing energy requirements..."
                firebase_svc.update_job_status(job_id, 'processing')

                collected_items = []
                def on_item_found(item):
                    collected_items.append(item)
                    firebase_svc.append_search_result(job_id, item)

                # --- STEP 2: SCRAPED (UI: 70%) ---
                # "Gathering deals from Amazon & Flipkart..."
                # We set this BEFORE the heavy scraping starts
                firebase_svc.update_job_status(job_id, 'scraped')

                # Perform actual Selenium work
                scraper_svc.scrape_all_stream(query, on_item_found)

                # Update the final item count (status remains 'scraped')
                firebase_svc.mark_search_complete(job_id, len(collected_items))

                # --- STEP 3: ANALYZED (UI: 100%) ---
                # "Analysis complete. Best matches found!"
                if collected_items:
                    log.info("🔍 Running AI Analysis...")
                    
                    analysis = llm_svc.analyze_products(query, budget, collected_items)

                    if analysis:
                        # This method sets status to 'analyzed'
                        firebase_svc.save_analysis(job_id, analysis)
                        log.info("✅ AI Analysis Saved.")
                else:
                    log.warning("No items found to analyze.")
                    # Optional: Move to a 'failed' or 'empty' state if desired

                # --- STEP 4: NOTIFY ---
                if uid:
                    firebase_svc.send_user_notification(
                        user_uid=uid,
                        title="Search Complete",
                        body=f"Found {len(collected_items)} alternatives for '{query}'.",
                        data={"screen": "shopping_result", "job_id": job_id}
                    )

                log.info(f"Job {job_id} Completed successfully.")

            except Exception as e:
                log.error(f"Job {job_id} Failed: {e}", exc_info=True)
                firebase_svc.update_job_status(job_id, 'failed')

if __name__ == "__main__":
    process_jobs()