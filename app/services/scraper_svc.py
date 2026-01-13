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
            results.extend(self._scrape_amazon(driver, query))
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

            if "Robot" in driver.title:
                return []

            try:
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.s-main-slot")))
            except: pass

            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-component-type='s-search-result']")
            
            for item in items[:5]: 
                try:
                    # 1. Title
                    title_el = item.select_one("h2 a span")
                    if not title_el: continue
                    name = title_el.text.strip()

                    # 2. Price
                    price_el = item.select_one(".a-price-whole")
                    if not price_el: continue
                    price = float(price_el.text.replace(",", "").strip())

                    # 3. Rating (NEW)
                    rating = "N/A"
                    rating_el = item.select_one("span.a-icon-alt")
                    if rating_el:
                        # Text is like "4.5 out of 5 stars" -> Get "4.5"
                        rating = rating_el.text.split(" ")[0]

                    # 4. Link (NEW)
                    link = "N/A"
                    link_el = item.select_one("h2 a")
                    if link_el and link_el.has_attr('href'):
                        link = "https://www.amazon.in" + link_el['href']

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

            for i, item in enumerate(items):
                if len(results) >= 5: break 
                try:
                    # 1. Title
                    name = None
                    img = item.select_one("img")
                    if img and img.has_attr("alt"): name = img["alt"]
                    if not name:
                        title_div = item.select_one("div.KzDlHZ") or item.select_one("div._4rR01T") or item.select_one("a.s1Q9rs")
                        if title_div: name = title_div.text.strip()

                    # 2. Price (Regex)
                    price = 0.0
                    raw_text = item.text
                    match = re.search(r'₹\s?([0-9,]+)', raw_text)
                    if match:
                        price = float(match.group(1).replace(",", ""))

                    # 3. Rating (NEW)
                    # Flipkart uses these classes for the green star box
                    rating = "N/A"
                    rating_el = item.select_one("div.XQDdHH") or item.select_one("div._3LWZlK")
                    if rating_el:
                        rating = rating_el.text.strip()

                    # 4. Link (NEW)
                    # Find any anchor tag with an href inside the card
                    link = "N/A"
                    link_el = item.select_one("a")
                    if link_el and link_el.has_attr('href'):
                        href = link_el['href']
                        if href.startswith("/"):
                            link = "https://www.flipkart.com" + href
                        else:
                            link = href

                    if name and price > 0:
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