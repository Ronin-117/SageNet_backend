from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
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
        
        # Optimize: Block images/css to make deep scraping faster
        prefs = {
            "profile.managed_default_content_settings.images": 2, 
            "profile.managed_default_content_settings.stylesheets": 2
        }
        options.add_experimental_option("prefs", prefs)
        options.page_load_strategy = 'eager'
        
        driver = webdriver.Remote(command_executor=self.selenium_url, options=options)
        # Set a strict timeout so one stuck page doesn't kill the whole job
        driver.set_page_load_timeout(20) 
        return driver

    def scrape_all_stream(self, query: str, callback_func):
        """
        Scrapes and calls 'callback_func(item)' immediately for each found item.
        """
        driver = None
        count = 0
        try:
            driver = self._get_driver()
            
            # Amazon (Limit 3 deep visits)
            count += self._scrape_deep(driver, query, "Amazon", callback_func, limit=3)
            
            # Restart driver between sites to clear RAM/Cache
            driver.quit()
            driver = self._get_driver()

            # Flipkart (Limit 3 deep visits)
            count += self._scrape_deep(driver, query, "Flipkart", callback_func, limit=3)
            
        except Exception as e:
            log.error(f"Global Scraper Error: {e}")
        finally:
            if driver: driver.quit()
        return count

    def _scrape_deep(self, driver, query, source, callback, limit=3):
        count = 0
        try:
            domain = "amazon.in" if source == "Amazon" else "flipkart.com"
            search_url = f"https://www.{domain}/search?q={query.replace(' ', '%20')}" if source == "Flipkart" else f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            
            log.info(f"🕷️ Scraping {source}: {query}")
            
            try:
                driver.get(search_url)
            except TimeoutException:
                log.warning(f"{source} Search Timeout. Attempting to parse loaded content.")

            time.sleep(2)
            
            soup = BeautifulSoup(driver.page_source, "html.parser")
            links = []
            
            # --- LINK COLLECTION ---
            if source == "Amazon":
                if "Robot" in driver.title:
                    log.warning("Amazon Robot Check Detected.")
                    return 0
                items = soup.select("div[data-component-type='s-search-result']")
                for item in items[:limit]: 
                    link_el = item.find('a', href=re.compile(r'/(dp|gp)/'))
                    if link_el: links.append("https://www.amazon.in" + link_el['href'])
            else:
                items = soup.select("div[data-id]") or soup.select("div._1AtVbE")
                for item in items[:limit]: 
                    link_el = item.select_one("a")
                    if link_el and link_el.has_attr('href') and link_el['href'].startswith("/"):
                        links.append("https://www.flipkart.com" + link_el['href'])

            # --- DEEP VISIT ---
            for link in links:
                try:
                    log.info(f"   -> {source}: Visiting {link[:40]}...")
                    
                    try:
                        driver.get(link)
                        time.sleep(2)
                    except TimeoutException:
                        log.warning(f"   -> {source} Product Page Timeout. Parsing partial content.")
                        driver.execute_script("window.stop();") # Stop loading, try to parse
                    
                    page_soup = BeautifulSoup(driver.page_source, "html.parser")
                    
                    # 1. TITLE
                    name = "Unknown"
                    if source == "Amazon":
                        name_el = page_soup.select_one("#productTitle")
                        if name_el: name = name_el.text.strip()
                    else:
                        name_el = page_soup.select_one("span.B_NuCI") or page_soup.select_one("h1")
                        if name_el: name = name_el.text.strip()

                    # 2. PRICE
                    price = 0.0
                    price_el = None
                    if source == "Amazon":
                        price_el = page_soup.select_one(".a-price-whole")
                    else:
                        price_el = page_soup.select_one("div.Nx9bqj") or page_soup.select_one("div._30jeq3") or page_soup.select_one("div.CEmiEU")

                    if price_el:
                        # Clean currency symbols
                        price_text = price_el.text.replace(",", "").replace("₹", "").strip()
                        if price_text.replace(".", "").isdigit():
                            price = float(price_text)
                    
                    # 3. RATING (FIXED)
                    rating = "N/A"
                    if source == "Amazon":
                        # Strategy A: Popover Title
                        r_el = page_soup.select_one("#acrPopover")
                        if r_el:
                             txt = r_el.get("title") or r_el.text
                             m = re.search(r'(\d\.\d)', txt)
                             if m: rating = m.group(1)
                        
                        # Strategy B: Icon Alt Text (Backup)
                        if rating == "N/A":
                            r_el = page_soup.select_one("span.a-icon-alt")
                            if r_el:
                                m = re.search(r'(\d\.\d)', r_el.text)
                                if m: rating = m.group(1)
                    else:
                        # Flipkart specific green box
                        r_el = page_soup.select_one("div.XQDdHH") or page_soup.select_one("div._3LWZlK")
                        if r_el: 
                            rating = r_el.text.strip()

                    # 4. SPECS (FULL TABLE)
                    specs_text = ""
                    if source == "Amazon":
                        table = page_soup.select_one("#productDetails_techSpec_section_1")
                        if table:
                            specs_list = []
                            for row in table.find_all("tr"):
                                th = row.find("th")
                                td = row.find("td")
                                if th and td: 
                                    key = th.text.strip().replace("\u200e", "")
                                    val = td.text.strip().replace("\u200e", "")
                                    specs_list.append(f"{key}: {val}")
                            specs_text = " | ".join(specs_list)
                        else:
                            # Bullet fallback
                            bullets = page_soup.select("#detailBullets_feature_div li")
                            specs_text = " | ".join([li.text.strip().replace("\n", " ") for li in bullets[:10]])
                    else:
                        # Flipkart Tables
                        rows = page_soup.select("tr._1s_Smc") or page_soup.select("tr.row")
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
                            "rating": rating,
                            "link": link, # Use the link we visited
                            "specs": specs_text, # Full specs
                            "source": source
                        }
                        # CALL THE CALLBACK (Save immediately)
                        callback(item_data)
                        count += 1
                        
                except Exception as e:
                    log.error(f"Item Visit Error ({link[:20]}): {e}")
                    continue

        except Exception as e:
            log.error(f"{source} Logic Error: {e}")
        return count

scraper_svc = ScraperService()