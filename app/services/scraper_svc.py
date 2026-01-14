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
            # Limit to Top 3 items per site to keep scraping time under 1 minute
            results.extend(self._scrape_amazon_deep(driver, query, limit=3))
            results.extend(self._scrape_flipkart_deep(driver, query, limit=3))
        except Exception as e:
            log.error(f"Global Scraper Error: {e}")
        finally:
            if driver: driver.quit()
        return results

    def _scrape_amazon_deep(self, driver, query, limit=3):
        results = []
        try:
            log.info(f"🕷️ Scraping Amazon (Deep Mode) for: {query}")
            url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            driver.get(url)
            time.sleep(2)

            if "Robot" in driver.title:
                log.warning("Amazon Robot Check detected on search page.")
                return []

            # 1. Collect Links from Search Page
            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-component-type='s-search-result']")
            product_links = []

            for item in items[:limit]:
                # Find Link using generic strategy
                link_el = item.find('a', href=re.compile(r'/(dp|gp)/'))
                if link_el:
                    href = link_el['href']
                    if href.startswith("/"):
                        product_links.append("https://www.amazon.in" + href)
                    else:
                        product_links.append(href)

            # 2. Visit Each Product
            for link in product_links:
                try:
                    log.info(f"   -> Visiting Amazon Product: {link[:50]}...")
                    driver.get(link)
                    time.sleep(2) # Allow specs to load
                    
                    page_soup = BeautifulSoup(driver.page_source, "html.parser")

                    # -- Extract Details --
                    # Title
                    name_el = page_soup.select_one("#productTitle")
                    name = name_el.text.strip() if name_el else "Unknown Product"

                    # Price
                    price = 0.0
                    price_el = page_soup.select_one(".a-price-whole")
                    if price_el:
                        price = float(price_el.text.replace(",", "").replace(".", "").strip())

                    # Rating
                    rating = "N/A"
                    rating_el = page_soup.select_one("#acrPopover")
                    if rating_el:
                        r_text = rating_el.get("title") or rating_el.text
                        match = re.search(r'(\d\.\d)', r_text)
                        if match: rating = match.group(1)

                    # SPECS (The Table)
                    # Strategy: Look for the specific table ID you provided
                    specs_data = []
                    table = page_soup.select_one("#productDetails_techSpec_section_1")
                    
                    if table:
                        rows = table.find_all("tr")
                        for row in rows:
                            th = row.find("th")
                            td = row.find("td")
                            if th and td:
                                key = th.text.strip().replace("\u200e", "")
                                val = td.text.strip().replace("\u200e", "")
                                specs_data.append(f"{key}: {val}")
                    else:
                        # Fallback: Detail Bullets
                        bullets = page_soup.select("#detailBullets_feature_div li")
                        for li in bullets:
                            specs_data.append(li.text.strip().replace("\n", " "))

                    specs_text = " | ".join(specs_data) if specs_data else "Details not found in table"

                    if price > 0:
                        results.append({
                            "name": name,
                            "price": price,
                            "rating": rating,
                            "link": link,
                            "specs": specs_text[:1000], # Limit text size for DB
                            "source": "Amazon"
                        })
                        
                except Exception as e:
                    log.error(f"Amazon Product Visit Error: {e}")
                    continue

        except Exception as e:
            log.error(f"Amazon Failed: {e}")
        return results

    def _scrape_flipkart_deep(self, driver, query, limit=3):
        results = []
        try:
            log.info(f"🕷️ Scraping Flipkart (Deep Mode) for: {query}")
            url = f"https://www.flipkart.com/search?q={query.replace(' ', '%20')}"
            driver.get(url)
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-id]")
            if not items: items = soup.select("div._1AtVbE")

            product_links = []
            for item in items[:limit]:
                link_el = item.select_one("a")
                if link_el and link_el.has_attr('href'):
                    href = link_el['href']
                    if href.startswith("/"):
                        product_links.append("https://www.flipkart.com" + href)

            # 2. Visit Each Product
            for link in product_links:
                try:
                    log.info(f"   -> Visiting Flipkart Product: {link[:50]}...")
                    driver.get(link)
                    time.sleep(2)
                    
                    page_soup = BeautifulSoup(driver.page_source, "html.parser")

                    # Title (Try new and old classes)
                    name_el = page_soup.select_one("span.B_NuCI") or page_soup.select_one("span.VU-ZEz") or page_soup.select_one("h1")
                    name = name_el.text.strip() if name_el else "Unknown Product"

                    # Price
                    price = 0.0
                    price_el = page_soup.select_one("div.Nx9bqj") or page_soup.select_one("div._30jeq3")
                    if price_el:
                         price = float(price_el.text.replace("₹", "").replace(",", "").strip())

                    # Rating
                    rating = "N/A"
                    rating_el = page_soup.select_one("div.XQDdHH") or page_soup.select_one("div._3LWZlK")
                    if rating_el: rating = rating_el.text.strip()

                    # SPECS (Based on your HTML snippet)
                    # Structure: div.d2eo1M > table.n7infM > tr.row
                    specs_data = []
                    
                    # Find all tables with class n7infM (Your snippet had this)
                    # Or generic table search inside spec container
                    tables = page_soup.select("table.n7infM")
                    if not tables:
                        tables = page_soup.select("table._14cfVK") # Old class fallback

                    for table in tables:
                        rows = table.find_all("tr")
                        for row in rows:
                            # Your snippet: td.col-3-12 (Key), td.col-9-12 (Value)
                            cols = row.find_all("td")
                            if len(cols) >= 2:
                                key = cols[0].text.strip()
                                val = cols[1].text.strip()
                                specs_data.append(f"{key}: {val}")
                    
                    specs_text = " | ".join(specs_data) if specs_data else "Specifications not found"

                    if price > 0:
                        results.append({
                            "name": name,
                            "price": price,
                            "rating": rating,
                            "link": link,
                            "specs": specs_text[:1000],
                            "source": "Flipkart"
                        })

                except Exception as e:
                    log.error(f"Flipkart Product Visit Error: {e}")
                    continue

        except Exception as e:
            log.error(f"Flipkart Failed: {e}")
            
        return results

scraper_svc = ScraperService()