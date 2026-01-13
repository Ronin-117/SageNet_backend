from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
from app.core.logger import setup_logger

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
            
            # 1. Find Product Cards (Grid view confirmed by logs)
            items = soup.select("div[data-id]")
            if not items:
                items = soup.select("div._1AtVbE")

            log.info(f"Flipkart RAW items: {len(items)}")

            for i, item in enumerate(items):
                if len(results) >= 5: break 
                
                try:
                    # --- TITLE STRATEGIES ---
                    name = None
                    
                    # Strategy 1: Image Alt Text (Very reliable for Grid View)
                    img_el = item.select_one("img.UCc1lI")
                    if img_el and img_el.has_attr("alt"):
                        name = img_el["alt"]
                    
                    # Strategy 2: Link Text (Fallback)
                    if not name:
                        link_el = item.select_one("a.wjcEIp") or item.select_one("a.s1Q9rs")
                        if link_el:
                            name = link_el.get("title") or link_el.text.strip()

                    # --- PRICE STRATEGIES ---
                    price_el = (
                        item.select_one("div.Nx9bqj") or  # New 2025 Price Class
                        item.select_one("div._30jeq3")    # Old Price Class
                    )
                    
                    # Fallback: Look for ₹ symbol manually
                    if not price_el:
                        for div in item.find_all("div"):
                            if "₹" in div.text:
                                price_el = div
                                break

                    # --- PARSING ---
                    if name and price_el:
                        p_text = price_el.text.replace("₹", "").replace(",", "").strip()
                        
                        # Remove "onwards" or other text noise
                        p_text = p_text.split()[0] 

                        if p_text.isdigit():
                            results.append({
                                "name": name,
                                "price": float(p_text),
                                "source": "Flipkart"
                            })
                        else:
                            # log.warning(f"Flipkart Price Parse Error: {p_text}")
                            pass
                            
                except Exception as e:
                    # log.error(f"Item Error: {e}")
                    continue
            
        except Exception as e:
            log.error(f"Flipkart Failed: {e}")
            
        return results

scraper_svc = ScraperService()