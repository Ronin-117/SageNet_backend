from selenium import webdriver
from selenium.webdriver.common.by import By
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
        
        # Optimize: Block images/css
        prefs = {"profile.managed_default_content_settings.images": 2, "profile.managed_default_content_settings.stylesheets": 2}
        options.add_experimental_option("prefs", prefs)
        options.page_load_strategy = 'eager'
        
        driver = webdriver.Remote(command_executor=self.selenium_url, options=options)
        driver.set_page_load_timeout(30)
        return driver

    def scrape_all_stream(self, query: str, callback_func):
        """
        Scrapes and calls 'callback_func(item)' immediately for each found item.
        """
        driver = None
        count = 0
        try:
            driver = self._get_driver()
            
            # Amazon
            count += self._scrape_deep(driver, query, "Amazon", callback_func)
            
            # Flipkart
            count += self._scrape_deep(driver, query, "Flipkart", callback_func)
            
        except Exception as e:
            log.error(f"Global Scraper Error: {e}")
        finally:
            if driver: driver.quit()
        return count

    def _scrape_deep(self, driver, query, source, callback):
        count = 0
        try:
            domain = "amazon.in" if source == "Amazon" else "flipkart.com"
            search_url = f"https://www.{domain}/search?q={query.replace(' ', '%20')}" if source == "Flipkart" else f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            
            log.info(f"🕷️ Scraping {source}: {query}")
            driver.get(search_url)
            time.sleep(2)
            
            soup = BeautifulSoup(driver.page_source, "html.parser")
            links = []
            
            # --- LINK COLLECTION ---
            if source == "Amazon":
                items = soup.select("div[data-component-type='s-search-result']")
                for item in items[:2]: # Limit 2
                    link_el = item.find('a', href=re.compile(r'/(dp|gp)/'))
                    if link_el: links.append("https://www.amazon.in" + link_el['href'])
            else:
                items = soup.select("div[data-id]") or soup.select("div._1AtVbE")
                for item in items[:2]: # Limit 2
                    link_el = item.select_one("a")
                    if link_el and link_el.has_attr('href') and link_el['href'].startswith("/"):
                        links.append("https://www.flipkart.com" + link_el['href'])

            # --- DEEP VISIT ---
            for link in links:
                try:
                    log.info(f"   -> {source}: Visiting {link[:40]}...")
                    driver.get(link)
                    time.sleep(2)
                    
                    page_soup = BeautifulSoup(driver.page_source, "html.parser")
                    
                    # 1. TITLE
                    if source == "Amazon":
                        name_el = page_soup.select_one("#productTitle")
                    else:
                        name_el = page_soup.select_one("span.B_NuCI") or page_soup.select_one("h1")
                    
                    name = name_el.text.strip() if name_el else "Unknown"

                    # 2. PRICE (Regex Strategy for both)
                    price = 0.0
                    # Try specific selectors first
                    if source == "Amazon":
                        price_el = page_soup.select_one(".a-price-whole")
                    else:
                        price_el = page_soup.select_one("div.Nx9bqj") or page_soup.select_one("div._30jeq3") or page_soup.select_one("div.CEmiEU")

                    if price_el:
                        price_text = price_el.text.replace(",", "").replace("₹", "").strip()
                        if price_text.replace(".", "").isdigit():
                            price = float(price_text)
                    
                    # Fallback: Regex Search in whole body if selector failed
                    if price == 0.0:
                         # Look for ₹ 500 pattern, take the first valid one
                         matches = re.findall(r'₹\s?([0-9,]+)', page_soup.get_text())
                         for m in matches:
                             val = float(m.replace(",", ""))
                             if val > 100: # Filter out tiny EMI amounts
                                 price = val
                                 break

                    # 3. SPECS (Full Text)
                    specs_text = ""
                    if source == "Amazon":
                        table = page_soup.select_one("#productDetails_techSpec_section_1")
                        if table:
                            specs_text = " | ".join([f"{row.find('th').text.strip()}: {row.find('td').text.strip()}" for row in table.find_all("tr") if row.find('th')])
                        else:
                            # Bullet fallback
                            specs_text = " | ".join([li.text.strip() for li in page_soup.select("#detailBullets_feature_div li")])
                    else:
                        # Flipkart Tables
                        rows = page_soup.select("tr._1s_Smc") # Common FK row
                        if not rows:
                            rows = page_soup.select("tr.row") # Newer FK row
                        
                        specs_list = []
                        for row in rows:
                            cols = row.find_all("td")
                            if len(cols) == 2:
                                specs_list.append(f"{cols[0].text.strip()}: {cols[1].text.strip()}")
                        specs_text = " | ".join(specs_list)

                    if price > 0:
                        item_data = {
                            "name": name,
                            "price": price,
                            "rating": "N/A", # Keep simple for now
                            "link": link,
                            "specs": specs_text, # NO TRUNCATION
                            "source": source
                        }
                        # CALL THE CALLBACK (Save immediately)
                        callback(item_data)
                        count += 1
                        
                except Exception as e:
                    log.error(f"Item Visit Error: {e}")
                    continue

        except Exception as e:
            log.error(f"{source} Logic Error: {e}")
        return count

scraper_svc = ScraperService()