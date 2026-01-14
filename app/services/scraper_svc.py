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
            # We limit to Top 2 from each site to save time (Deep scraping is slow)
            results.extend(self._scrape_amazon(driver, query, limit=2))
            results.extend(self._scrape_flipkart(driver, query, limit=2))
        except Exception as e:
            log.error(f"Global Scraper Error: {e}")
        finally:
            if driver: driver.quit()
        return results

    def _scrape_amazon(self, driver, query, limit=2):
        results = []
        try:
            log.info(f"🕷️ Scraping Amazon for: {query}")
            url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            driver.get(url)
            time.sleep(2)

            if "Robot" in driver.title: return []

            # 1. Gather Links from Search Page first
            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-component-type='s-search-result']")
            product_urls = []

            for item in items[:limit]:
                # Find Link
                link_el = item.select_one("h2 a")
                if link_el and link_el.has_attr('href'):
                    full_link = "https://www.amazon.in" + link_el['href']
                    product_urls.append(full_link)

            # 2. Deep Scrape Each Product
            for link in product_urls:
                try:
                    log.info(f"   -> Visiting: {link[:40]}...")
                    driver.get(link)
                    time.sleep(2) # Wait for details to load
                    
                    # Extract Data from Product Page
                    page_soup = BeautifulSoup(driver.page_source, "html.parser")
                    
                    # Title
                    name_el = page_soup.select_one("#productTitle")
                    name = name_el.text.strip() if name_el else "Unknown"

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

                    # SPECS: Extract the Technical Details Table
                    specs_text = ""
                    # Look for the standard tech table
                    table = page_soup.select_one("#productDetails_techSpec_section_1")
                    if not table:
                        # Fallback to list style details
                        table = page_soup.select_one("#detailBullets_feature_div")
                    
                    if table:
                        rows = table.find_all("tr")
                        spec_list = []
                        for row in rows:
                            th = row.find("th")
                            td = row.find("td")
                            if th and td:
                                key = th.text.strip().replace("\u200e", "") # Remove invisible chars
                                val = td.text.strip().replace("\u200e", "")
                                if key and val:
                                    spec_list.append(f"{key}: {val}")
                        # If list style
                        if not spec_list:
                            lis = table.find_all("li")
                            for li in lis:
                                txt = li.text.strip().replace("\n", " ")
                                spec_list.append(txt)
                                
                        specs_text = " | ".join(spec_list)
                    
                    if not specs_text:
                        specs_text = "See Product Link"

                    if price > 0:
                        results.append({
                            "name": name,
                            "price": price,
                            "rating": rating,
                            "link": driver.current_url, # Guaranteed correct link
                            "specs": specs_text[:500], # Limit length
                            "source": "Amazon"
                        })

                except Exception as e:
                    log.error(f"Amazon Item Error: {e}")
                    continue

        except Exception as e:
            log.error(f"Amazon Failed: {e}")
        return results

    def _scrape_flipkart(self, driver, query, limit=2):
        results = []
        try:
            log.info(f"🕷️ Scraping Flipkart for: {query}")
            url = f"https://www.flipkart.com/search?q={query.replace(' ', '%20')}"
            driver.get(url)
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-id]") or soup.select("div._1AtVbE")
            
            product_urls = []
            for item in items[:limit]:
                # Find Link
                link_el = item.select_one("a")
                if link_el and link_el.has_attr('href'):
                    href = link_el['href']
                    if href.startswith("/"):
                        product_urls.append("https://www.flipkart.com" + href)

            # Deep Scrape
            for link in product_urls:
                try:
                    log.info(f"   -> Visiting: {link[:40]}...")
                    driver.get(link)
                    time.sleep(2)
                    
                    page_soup = BeautifulSoup(driver.page_source, "html.parser")
                    
                    # Title
                    name_el = page_soup.select_one("span.B_NuCI") # Specific FK Product Page Class
                    if not name_el: name_el = page_soup.select_one("h1")
                    name = name_el.text.strip() if name_el else "Unknown"

                    # Price
                    price = 0.0
                    price_el = page_soup.select_one("div._30jeq3._16Jk6d") # FK Detail Price Class
                    if price_el:
                        price = float(price_el.text.replace("₹", "").replace(",", "").strip())

                    # Rating
                    rating = "N/A"
                    rating_el = page_soup.select_one("div._3LWZlK")
                    if rating_el: rating = rating_el.text.strip()

                    # SPECS: Extract the Table
                    specs_text = ""
                    # FK usually has a div with class _1UhVsV or _3k-BhJ for specs
                    # We look for rows named _1s_Smc (Key) and _21Ahn- (Value)
                    spec_rows = page_soup.select("div._1s_Smc") # Common row class
                    spec_vals = page_soup.select("div._21Ahn-") # Common value class
                    
                    # If classes change, try generic table approach
                    if not spec_rows:
                        # Find div containing "Specifications" text
                        headers = page_soup.find_all(string="Specifications")
                        if headers:
                            # Try to grab the parent container text content simply
                            container = headers[0].find_parent("div").find_parent("div")
                            if container:
                                # Clean up text
                                raw_text = container.get_text(separator="|").replace("Specifications|", "")
                                specs_text = raw_text
                    else:
                        # Structured Extraction
                        spec_list = []
                        # Zip keys and values (hope they match order, usually do in FK HTML)
                        # Actually safer to look for tr if it's a table, or row divs
                        rows = page_soup.select("tr._1s_Smc") 
                        if rows:
                            for row in rows:
                                cols = row.find_all("td")
                                if len(cols) == 2:
                                    spec_list.append(f"{cols[0].text}: {cols[1].text}")
                        specs_text = " | ".join(spec_list)

                    if not specs_text:
                        # Fallback: Just grab the Highlights section
                        highlights = page_soup.select("div._2418kt ul li")
                        if highlights:
                            specs_text = " | ".join([li.text for li in highlights])

                    if price > 0:
                        results.append({
                            "name": name,
                            "price": price,
                            "rating": rating,
                            "link": driver.current_url, # Guaranteed correct link
                            "specs": specs_text[:500],
                            "source": "Flipkart"
                        })

                except Exception as e:
                    log.error(f"FK Item Error: {e}")
                    continue

        except Exception as e:
            log.error(f"Flipkart Failed: {e}")
        return results

scraper_svc = ScraperService()