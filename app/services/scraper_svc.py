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
            # Scrape Amazon (Limit 5)
            results.extend(self._scrape_amazon(driver, query))
            # Scrape Flipkart (Limit 5)
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

            if "Robot" in driver.title: return []

            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-component-type='s-search-result']")
            
            log.info(f"Amazon RAW items: {len(items)}")

            for item in items[:5]: 
                try:
                    # 1. Title
                    title_el = item.select_one("h2 span") or item.select_one("span.a-text-normal")
                    if not title_el: continue
                    name = title_el.text.strip()

                    # 2. Price
                    price = 0.0
                    price_el = item.select_one(".a-price-whole")
                    if price_el:
                        price = float(price_el.text.replace(",", "").strip())

                    # 3. Rating
                    rating = "N/A"
                    r_match = re.search(r'(\d\.\d)\s?out of 5 stars', item.text)
                    if r_match: rating = r_match.group(1)

                    # 4. Link
                    link = "N/A"
                    link_el = item.select_one("h2 a")
                    if link_el and link_el.has_attr('href'):
                        link = "https://www.amazon.in" + link_el['href']

                    # 5. Specs (Best Effort from Search Card)
                    # Amazon often puts specs in rows with 'a-color-secondary'
                    specs_list = []
                    # Try finding the specific feature rows
                    rows = item.select("div.a-row")
                    for row in rows:
                        text = row.text.strip()
                        # Filter out Price, Rating, and Junk
                        if len(text) > 3 and "₹" not in text and "stars" not in text and "delivery" not in text.lower():
                            specs_list.append(text)
                    
                    specs_text = " | ".join(specs_list[:3]) if specs_list else "See Link"

                    if price > 0:
                        results.append({
                            "name": name,
                            "price": price,
                            "rating": rating,
                            "link": link,
                            "specs": specs_text,
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
                    # 1. Title
                    name = None
                    img = item.select_one("img")
                    if img and img.has_attr("alt"): name = img["alt"]
                    if not name:
                        # Try Link Title
                        link = item.select_one("a.wjcEIp") or item.select_one("a.s1Q9rs")
                        if link: name = link.get("title") or link.text.strip()
                    
                    if not name: continue

                    # 2. Price
                    price = 0.0
                    match = re.search(r'₹\s?([0-9,]+)', item.text)
                    if match:
                        price = float(match.group(1).replace(",", ""))

                    # 3. Rating
                    rating = "N/A"
                    r_match = re.search(r'\b([1-5]\.\d)\b', item.text)
                    if r_match: rating = r_match.group(1)

                    # 4. Link
                    link = "N/A"
                    link_el = item.select_one("a")
                    if link_el and link_el.has_attr('href'):
                        href = link_el['href']
                        if href.startswith("/"): link = "https://www.flipkart.com" + href
                        else: link = href

                    # 5. Specs (From Search Card)
                    # Flipkart List View often has a UL
                    specs_text = "See Link"
                    ul_list = item.select_one("ul")
                    if ul_list:
                        lis = ul_list.find_all("li")
                        specs_text = " | ".join([li.text.strip() for li in lis])
                    else:
                        # Grid View: Specs are often mixed in subtitles
                        # Look for gray text (often class _13oc-S or similar, but generic is safer)
                        # We grab text that ISN'T the name or price
                        all_text = item.text
                        # Simple heuristic: If text is long and not the name
                        if len(all_text) > len(name) + 20:
                            specs_text = "Check Product Page Details" 

                    if price > 0:
                        results.append({
                            "name": name,
                            "price": price,
                            "rating": rating,
                            "link": link,
                            "specs": specs_text,
                            "source": "Flipkart"
                        })
                except: continue
        except Exception as e:
            log.error(f"Flipkart Failed: {e}")
        return results

scraper_svc = ScraperService()