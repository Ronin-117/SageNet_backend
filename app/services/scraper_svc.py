from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
from app.core.logger import setup_logger
import re

log = setup_logger("ScraperService")

class ScraperService:
    def __init__(self):
        self.selenium_url = "http://127.0.0.1:4444/wd/hub"

    def _get_driver(self):
        options = webdriver.ChromeOptions()
        # options.add_argument("--headless") # Keep commented for server use logic
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
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
            results.extend(self._scrape_amazon(driver, query))
            # 2. Scrape Flipkart
            results.extend(self._scrape_flipkart(driver, query))
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
            time.sleep(2)

            if "Robot" in driver.title:
                log.warning("⚠️ Amazon blocked us.")
                return []

            # Wait for grid
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.s-main-slot"))
                )
            except: pass

            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-component-type='s-search-result']")
            
            log.info(f"Amazon RAW items: {len(items)}")

            for i, item in enumerate(items[:5]): 
                try:
                    # Strategy 1: Standard Title
                    title_el = item.select_one("h2 span") or item.select_one("span.a-text-normal")
                    if not title_el:
                        log.warning(f"Amazon Item {i}: No Title")
                        continue

                    # Strategy 2: Price (Whole part)
                    price_el = item.select_one(".a-price-whole")
                    if not price_el:
                        log.warning(f"Amazon Item {i}: No Price")
                        continue

                    results.append({
                        "name": title_el.text.strip(),
                        "price": float(price_el.text.replace(",", "").strip()),
                        "source": "Amazon"
                    })
                except Exception as e:
                    log.error(f"Amazon Parse Error item {i}: {e}")
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

            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            items = soup.select("div[data-id]")
            if not items:
                items = soup.select("div._1AtVbE")

            log.info(f"Flipkart RAW items found: {len(items)}")

            for i, item in enumerate(items):
                if len(results) >= 5: break 
                
                try:
                    # 1. GET TITLE (Your logs proved Strategy A works!)
                    name = None
                    img = item.select_one("img")
                    if img and img.has_attr("alt"):
                        name = img["alt"]
                    
                    if not name:
                        title_div = item.select_one("div.KzDlHZ") or item.select_one("div._4rR01T") or item.select_one("a.s1Q9rs")
                        if title_div:
                            name = title_div.text.strip()

                    # 2. GET PRICE (The Regex Fix)
                    price = 0.0
                    
                    # Try specific class first (Cleanest)
                    price_div = item.select_one("div.Nx9bqj") or item.select_one("div._30jeq3")
                    if price_div:
                        raw_price = price_div.text
                    else:
                        # Fallback: Get ALL text and search for ₹ pattern
                        raw_price = item.text

                    # Regex Logic: Find '₹' followed by numbers/commas
                    # Example: "Mouse ₹219 ₹1,299" -> Finds "219"
                    match = re.search(r'₹\s?([0-9,]+)', raw_price)
                    
                    if match:
                        clean_price = match.group(1).replace(",", "")
                        if clean_price.isdigit():
                            price = float(clean_price)

                    # 3. VALIDATE & SAVE
                    if name and price > 0:
                        results.append({
                            "name": name,
                            "price": price,
                            "source": "Flipkart"
                        })
                    else:
                        # Only log warnings if we really missed data
                        pass 

                except Exception as e:
                    # log.error(f"Item {i} Error: {e}")
                    continue
            
        except Exception as e:
            log.error(f"Flipkart Failed: {e}")
            
        return results

scraper_svc = ScraperService()