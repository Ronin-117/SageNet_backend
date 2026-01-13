from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import re
from app.core.logger import setup_logger

log = setup_logger("ScraperService")

class ScraperService:
    def __init__(self):
        self.selenium_url = "http://127.0.0.1:4444/wd/hub"

    def _get_driver(self):
        options = webdriver.ChromeOptions()
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
            # Scrape Amazon
            results.extend(self._scrape_amazon(driver, query))
            # Scrape Flipkart
            results.extend(self._scrape_flipkart(driver, query))
        except Exception as e:
            log.error(f"Global Scraper Error: {e}")
        finally:
            if driver: driver.quit()
        return results

    def _scrape_amazon(self, driver, query):
        results = []
        try:
            log.info(f"🕷️ Scraping Amazon for: {query}")
            url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            driver.get(url)
            time.sleep(2)

            # Check for Captcha
            if "Robot" in driver.title or "Captcha" in driver.title:
                log.warning("⚠️ Amazon blocked us (Robot Check).")
                return []

            try:
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.s-main-slot")))
            except: pass

            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-component-type='s-search-result']")
            
            log.info(f"Amazon RAW items: {len(items)}")

            for item in items[:5]: 
                try:
                    # 1. Title (Multiple Strategies)
                    title_el = item.select_one("h2 span") or item.select_one("span.a-text-normal")
                    if not title_el: continue
                    name = title_el.text.strip()

                    # 2. Price (Regex Strategy - Robust)
                    price = 0.0
                    raw_text = item.text
                    # Find ₹ followed by numbers
                    match = re.search(r'₹\s?([0-9,]+)', raw_text)
                    if match:
                        price = float(match.group(1).replace(",", ""))
                    else:
                        # Fallback CSS
                        price_el = item.select_one(".a-price-whole")
                        if price_el:
                            price = float(price_el.text.replace(",", "").strip())

                    # 3. Rating (Regex Strategy)
                    rating = "N/A"
                    # Look for "4.5 out of 5 stars" pattern
                    rating_match = re.search(r'(\d\.\d)\s?out of 5 stars', item.text)
                    if rating_match:
                        rating = rating_match.group(1)

                    # 4. Link
                    link = "N/A"
                    link_el = item.select_one("h2 a")
                    if link_el and link_el.has_attr('href'):
                        link = "https://www.amazon.in" + link_el['href']

                    if price > 0:
                        results.append({
                            "name": name,
                            "price": price,
                            "rating": rating,
                            "link": link,
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

            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-id]")
            if not items: items = soup.select("div._1AtVbE")

            log.info(f"Flipkart RAW items: {len(items)}")

            for i, item in enumerate(items):
                if len(results) >= 5: break 
                try:
                    # 1. Title (Image Alt or Link Title)
                    name = None
                    img = item.select_one("img")
                    if img and img.has_attr("alt"): name = img["alt"]
                    if not name:
                        link = item.select_one("a.wjcEIp") or item.select_one("a.s1Q9rs")
                        if link: name = link.get("title") or link.text.strip()
                    
                    if not name: continue

                    # 2. Price (Regex Strategy)
                    price = 0.0
                    match = re.search(r'₹\s?([0-9,]+)', item.text)
                    if match:
                        price = float(match.group(1).replace(",", ""))

                    # 3. Rating (Regex Strategy)
                    rating = "N/A"
                    # Look for single digit dot digit (e.g. 4.3) 
                    # Often followed by star char or count in brackets
                    # This regex looks for a digit, dot, digit
                    r_match = re.search(r'\b([1-5]\.\d)\b', item.text)
                    if r_match:
                        rating = r_match.group(1)

                    # 4. Link
                    link = "N/A"
                    link_el = item.select_one("a")
                    if link_el and link_el.has_attr('href'):
                        href = link_el['href']
                        if href.startswith("/"): link = "https://www.flipkart.com" + href
                        else: link = href

                    if price > 0:
                        results.append({
                            "name": name,
                            "price": price,
                            "rating": rating,
                            "link": link,
                            "source": "Flipkart"
                        })
                except: continue
        except Exception as e:
            log.error(f"Flipkart Failed: {e}")
        return results

scraper_svc = ScraperService()