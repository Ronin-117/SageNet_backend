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
        # options.add_argument("--headless") # Keep for server
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Performance prefs
        prefs = {
            "profile.managed_default_content_settings.images": 2, 
            "profile.managed_default_content_settings.stylesheets": 2
        }
        options.add_experimental_option("prefs", prefs)
        options.page_load_strategy = 'eager'
        
        driver = webdriver.Remote(
            command_executor=self.selenium_url,
            options=options
        )
        driver.set_page_load_timeout(30)
        return driver

    def scrape_all(self, query: str):
        results = []
        
        # 1. Scrape Amazon
        try:
            log.info("--- Starting Amazon Scrape ---")
            driver = self._get_driver()
            results.extend(self._scrape_amazon_deep(driver, query, limit=3))
            driver.quit()
        except Exception as e:
            log.error(f"Amazon Session Error: {e}")
            try: driver.quit()
            except: pass

        # 2. Scrape Flipkart
        try:
            log.info("--- Starting Flipkart Scrape ---")
            driver = self._get_driver()
            results.extend(self._scrape_flipkart_deep(driver, query, limit=3))
            driver.quit()
        except Exception as e:
            log.error(f"Flipkart Session Error: {e}")
            try: driver.quit()
            except: pass
            
        return results

    def _scrape_amazon_deep(self, driver, query, limit=3):
        results = []
        try:
            url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            driver.get(url)
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-component-type='s-search-result']")
            
            links = []
            for item in items[:limit]:
                link_el = item.find('a', href=re.compile(r'/(dp|gp)/'))
                if link_el:
                    href = link_el['href']
                    full = "https://www.amazon.in" + href if href.startswith("/") else href
                    links.append(full)
            
            log.info(f"Amazon: Found {len(links)} links. Visiting...")

            for i, link in enumerate(links):
                try:
                    log.info(f"   [{i}] Loading: {link[:60]}...")
                    driver.get(link)
                    time.sleep(3) # Increased wait for stability
                    
                    page_soup = BeautifulSoup(driver.page_source, "html.parser")
                    
                    # DEBUG TITLE
                    name_el = page_soup.select_one("#productTitle")
                    if not name_el:
                        log.warning(f"   [{i}] ❌ Title NOT Found (Check #productTitle)")
                        continue
                    name = name_el.text.strip()
                    log.info(f"   [{i}] ✅ Title: {name[:20]}...")

                    # DEBUG PRICE
                    price = 0.0
                    price_el = page_soup.select_one(".a-price-whole")
                    if price_el:
                        try:
                            price = float(price_el.text.replace(",", "").replace(".", "").strip())
                            log.info(f"   [{i}] ✅ Price: {price}")
                        except:
                            log.warning(f"   [{i}] ⚠️ Price Parse Fail: {price_el.text}")
                    else:
                        log.warning(f"   [{i}] ❌ Price Element (.a-price-whole) NOT Found")
                        # Don't skip yet, maybe specs are there

                    # DEBUG RATING
                    rating = "N/A"
                    r_el = page_soup.select_one("#acrPopover")
                    if r_el:
                        r_text = r_el.get("title") or r_el.text
                        m = re.search(r'(\d\.\d)', r_text)
                        if m: rating = m.group(1)
                    
                    # DEBUG SPECS
                    specs_data = []
                    table = page_soup.select_one("#productDetails_techSpec_section_1")
                    if table:
                        for row in table.find_all("tr"):
                            th = row.find("th")
                            td = row.find("td")
                            if th and td: specs_data.append(f"{th.text.strip()}: {td.text.strip()}")
                    else:
                        # Fallback bullets
                        bullets = page_soup.select("#detailBullets_feature_div li")
                        if bullets:
                             specs_data = [li.text.strip().replace("\n", " ") for li in bullets[:6]]
                    
                    log.info(f"   [{i}] Specs Found: {len(specs_data)} lines")

                    if price > 0:
                        results.append({
                            "name": name, "price": price, "rating": rating, 
                            "link": link, "specs": " | ".join(specs_data)[:500], "source": "Amazon"
                        })
                    else:
                        log.warning(f"   [{i}] SKIPPING: Price was 0.0")

                except Exception as e:
                    log.error(f"Amazon Item {i} Crash: {e}")

        except Exception as e:
            log.error(f"Amazon Logic Error: {e}")
        return results

    def _scrape_flipkart_deep(self, driver, query, limit=3):
        results = []
        try:
            url = f"https://www.flipkart.com/search?q={query.replace(' ', '%20')}"
            driver.get(url)
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            items = soup.select("div[data-id]") or soup.select("div._1AtVbE")
            
            links = []
            for item in items[:limit]:
                a = item.select_one("a")
                if a and a.has_attr('href') and a['href'].startswith("/"):
                    links.append("https://www.flipkart.com" + a['href'])
            
            log.info(f"Flipkart: Found {len(links)} links. Visiting...")

            for i, link in enumerate(links):
                try:
                    log.info(f"   [{i}] Loading: {link[:60]}...")
                    driver.get(link)
                    time.sleep(3) # Increased wait
                    
                    page_soup = BeautifulSoup(driver.page_source, "html.parser")
                    
                    # DEBUG TITLE
                    name_el = page_soup.select_one("span.B_NuCI") or page_soup.select_one("h1")
                    if not name_el:
                         log.warning(f"   [{i}] ❌ Title NOT Found")
                         continue
                    name = name_el.text.strip()
                    log.info(f"   [{i}] ✅ Title: {name[:20]}...")

                    # DEBUG PRICE
                    price = 0.0
                    price_el = page_soup.select_one("div.Nx9bqj") or page_soup.select_one("div._30jeq3")
                    if price_el:
                        try:
                            price = float(price_el.text.replace("₹", "").replace(",", "").strip())
                            log.info(f"   [{i}] ✅ Price: {price}")
                        except:
                            log.warning(f"   [{i}] ⚠️ Price Parse Fail: {price_el.text}")
                    else:
                        log.warning(f"   [{i}] ❌ Price Element NOT Found")

                    # DEBUG SPECS
                    specs_data = []
                    rows = page_soup.select("tr._1s_Smc")
                    if rows:
                        for row in rows:
                            cols = row.find_all("td")
                            if len(cols) == 2: specs_data.append(f"{cols[0].text}: {cols[1].text}")
                    else:
                        # Fallback Highlights
                        highlights = page_soup.select("div._2418kt ul li")
                        specs_data = [li.text for li in highlights]

                    log.info(f"   [{i}] Specs Found: {len(specs_data)} lines")

                    if price > 0:
                        results.append({
                            "name": name, "price": price, "rating": "N/A", # Fix rating logic later
                            "link": link, "specs": " | ".join(specs_data)[:500], "source": "Flipkart"
                        })
                    else:
                         log.warning(f"   [{i}] SKIPPING: Price was 0.0")

                except Exception as e:
                    log.error(f"Flipkart Item {i} Crash: {e}")

        except Exception as e:
            log.error(f"Flipkart Logic Error: {e}")
        return results

scraper_svc = ScraperService()