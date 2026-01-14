from selenium import webdriver
from bs4 import BeautifulSoup
import re
from app.core.logger import setup_logger

log = setup_logger("BaseScraper")

class BaseScraper:
    def __init__(self):
        self.selenium_url = "http://127.0.0.1:4444/wd/hub"

    def get_driver(self):
        """Creates a fresh, stealthy Chrome driver"""
        options = webdriver.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Block images/css for speed
        prefs = {
            "profile.managed_default_content_settings.images": 2, 
            "profile.managed_default_content_settings.stylesheets": 2
        }
        options.add_experimental_option("prefs", prefs)
        options.page_load_strategy = 'eager'
        
        driver = webdriver.Remote(command_executor=self.selenium_url, options=options)
        driver.set_page_load_timeout(30)
        return driver

    def clean_price(self, text):
        """Extracts number from string like '₹ 1,299.00'"""
        if not text: return 0.0
        try:
            # Regex to find number after ₹
            match = re.search(r'[\d,]+\.?\d*', text)
            if match:
                clean = match.group(0).replace(",", "").strip()
                return float(clean)
        except: pass
        return 0.0

    def clean_rating(self, text):
        """Extracts '4.5' from '4.5 out of 5 stars'"""
        if not text: return "N/A"
        match = re.search(r'(\d\.\d)', text)
        if match:
            val = float(match.group(1))
            if 1.0 <= val <= 5.0: return str(val)
        return "N/A"