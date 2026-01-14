from app.services.scrapers.amazon import AmazonScraper
from app.services.scrapers.flipkart import FlipkartScraper
from app.core.logger import setup_logger

log = setup_logger("ScraperOrchestrator")

class ScraperService:
    def __init__(self):
        self.amazon = AmazonScraper()
        self.flipkart = FlipkartScraper()

    def scrape_all_stream(self, query: str, callback_func):
        """
        Main Entry Point used by Worker.
        """
        count = 0
        
        # 1. Run Amazon
        count += self.amazon.scrape(query, callback_func, limit=3)
        
        # 2. Run Flipkart
        count += self.flipkart.scrape(query, callback_func, limit=3)
        
        return count

scraper_svc = ScraperService()