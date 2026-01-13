from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from app.core.logger import setup_logger

log = setup_logger("ScraperService")

class ScraperService:
    def __init__(self):
        # Localhost works because we are in Host Mode
        self.selenium_url = "http://127.0.0.1:4444/wd/hub"

    def _get_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # Fake User Agent to prevent blocking
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        driver = webdriver.Remote(
            command_executor=self.selenium_url,
            options=options
        )
        return driver

    def scrape_all(self, query: str):
        """Orchestrator to scrape both and combine"""
        results = []
        driver = None
        
        try:
            driver = self._get_driver()
            
            # 1. Scrape Amazon
            amazon_data = self._scrape_amazon(driver, query)
            results.extend(amazon_data)
            
            # 2. Scrape Flipkart
            flipkart_data = self._scrape_flipkart(driver, query)
            results.extend(flipkart_data)
            
        except Exception as e:
            log.error(f"Global Scraper Error: {e}")
        finally:
            if driver:
                driver.quit()
        
        return results

    def _scrape_amazon(self, driver, query):
        results = []
        try:
            log.info(f"🕷️ Scraping Amazon for: {query}")
            url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            driver.get(url)
            
            # Wait for results
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.s-main-slot"))
            )
            
            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-component-type='s-search-result']")

            for item in items[:4]: # Top 4
                try:
                    title = item.select_one("h2 a span").text.strip()
                    price = item.select_one(".a-price-whole").text.replace(",", "").strip()
                    rating_el = item.select_one("span.a-icon-alt")
                    rating = rating_el.text.split(" ")[0] if rating_el else "N/A"
                    
                    results.append({
                        "name": title,
                        "price": float(price) if price.isdigit() else 0,
                        "rating": rating,
                        "source": "Amazon"
                    })
                except: continue
        except Exception as e:
            log.error(f"Amazon Failed: {e}")
        
        return results

    def _scrape_flipkart(self, driver, query):
        results = []
        try:
            log.info(f"🕷️ Scraping Flipkart for: {query}")
            url = f"https://www.flipkart.com/search?q={query.replace(' ', '%20')}"
            driver.get(url)
            
            # Wait for results (Flipkart uses different classes often, checking generic)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Try finding cards by data-id (Robust method from your old code)
            items = soup.select("div[data-id]")
            
            for item in items[:4]: # Top 4
                try:
                    # Selectors based on your provided code
                    title_el = item.select_one("div.RG5Slk") or item.select_one("div._4rR01T") or item.select_one("a.s1Q9rs")
                    price_el = item.select_one("div.hZ3P6w") or item.select_one("div._30jeq3") or item.select_one("div.Nx9bqj")
                    rating_el = item.select_one("div.MKiFS6") or item.select_one("div._3LWZlK")
                    
                    if title_el and price_el:
                        price_text = price_el.text.replace("₹", "").replace(",", "").strip()
                        results.append({
                            "name": title_el.text.strip(),
                            "price": float(price_text) if price_text.isdigit() else 0,
                            "rating": rating_el.text.strip() if rating_el else "N/A",
                            "source": "Flipkart"
                        })
                except: continue
        except Exception as e:
            log.error(f"Flipkart Failed: {e}")
            
        return results

scraper_svc = ScraperService()