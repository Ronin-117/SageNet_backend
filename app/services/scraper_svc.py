from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import random
from app.core.logger import setup_logger

log = setup_logger("ScraperService")

class ScraperService:
    def __init__(self):
        self.selenium_url = "http://127.0.0.1:4444/wd/hub"

    def _get_driver(self):
        options = webdriver.ChromeOptions()
        # options.add_argument("--headless") # Comment out if debugging locally, but keep for server
        
        # --- STEALTH FLAGS ---
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080") # Look like a Desktop
        options.add_argument("--disable-blink-features=AutomationControlled") # Hide Selenium
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        driver = webdriver.Remote(
            command_executor=self.selenium_url,
            options=options
        )
        return driver

    def scrape_all(self, query: str):
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
            
            # DEBUG: What page are we actually on?
            time.sleep(2) # Wait for redirects
            log.info(f"Amazon Page Title: {driver.title}")

            if "Robot" in driver.title:
                log.warning("⚠️ Amazon blocked us (CAPTCHA detected).")
                return []

            # Wait for results
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.s-main-slot"))
                )
            except:
                log.warning("Amazon Timeout: Product grid not found")

            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-component-type='s-search-result']")
            
            log.info(f"Amazon RAW items found: {len(items)}")

            for item in items[:4]: 
                try:
                    title = item.select_one("h2 a span").text.strip()
                    price_el = item.select_one(".a-price-whole")
                    price = price_el.text.replace(",", "").strip() if price_el else "0"
                    
                    results.append({
                        "name": title,
                        "price": float(price) if price.isdigit() else 0,
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
            
            time.sleep(2)
            log.info(f"Flipkart Page Title: {driver.title}")

            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Try generic class for product cards if data-id fails
            items = soup.select("div[data-id]")
            if not items:
                # Fallback selector for grid view
                items = soup.select("div._1AtVbE")

            log.info(f"Flipkart RAW items found: {len(items)}")

            for item in items[:4]:
                try:
                    # Updated Generic Selectors
                    title_el = item.select_one("div.RG5Slk") or item.select_one("div._4rR01T") or item.select_one("a.s1Q9rs")
                    price_el = item.select_one("div.hZ3P6w") or item.select_one("div._30jeq3") or item.select_one("div.Nx9bqj")
                    
                    if title_el and price_el:
                        price_text = price_el.text.replace("₹", "").replace(",", "").strip()
                        results.append({
                            "name": title_el.text.strip(),
                            "price": float(price_text) if price_text.isdigit() else 0,
                            "source": "Flipkart"
                        })
                except: continue
        except Exception as e:
            log.error(f"Flipkart Failed: {e}")
            
        return results

scraper_svc = ScraperService()