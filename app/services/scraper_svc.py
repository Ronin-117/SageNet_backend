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
        
        # Performance: Block images/css
        prefs = {
            "profile.managed_default_content_settings.images": 2, 
            "profile.managed_default_content_settings.stylesheets": 2
        }
        options.add_experimental_option("prefs", prefs)
        options.page_load_strategy = 'eager'
        
        driver = webdriver.Remote(command_executor=self.selenium_url, options=options)
        driver.set_page_load_timeout(30)
        return driver

    def scrape_all_stream(self, query: str, callback_func):
        driver = None
        count = 0
        try:
            driver = self._get_driver()
            
            # Scrape Amazon (Working Logic)
            count += self._scrape_site(driver, query, "Amazon", callback_func)
            
            # Scrape Flipkart (Fixed Logic)
            count += self._scrape_site(driver, query, "Flipkart", callback_func)
            
        except Exception as e:
            log.error(f"Global Scraper Error: {e}")
        finally:
            if driver: driver.quit()
        return count

    def _scrape_site(self, driver, query, source, callback):
        count = 0
        try:
            domain = "amazon.in" if source == "Amazon" else "flipkart.com"
            search_url = f"https://www.{domain}/search?q={query.replace(' ', '%20')}" if source == "Flipkart" else f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            
            log.info(f"🕷️ Scraping {source}: {query}")
            
            # --- SEARCH PAGE LOAD ---
            try:
                driver.get(search_url)
            except TimeoutException:
                log.warning(f"{source} Search Timeout. Stopping load to parse.")
                driver.execute_script("window.stop();") # CRITICAL FIX for Flipkart
            
            time.sleep(2) # Wait for DOM to settle

            soup = BeautifulSoup(driver.page_source, "html.parser")
            links = []

            # --- LINK COLLECTION ---
            if source == "Amazon":
                # Existing working logic for Amazon
                if "Robot" in driver.title:
                    log.warning("Amazon Robot Check Detected.")
                    return 0
                items = soup.select("div[data-component-type='s-search-result']")
                for item in items[:2]:
                    link_el = item.find('a', href=re.compile(r'/(dp|gp)/'))
                    if link_el:
                        href = link_el['href']
                        full = "https://www.amazon.in" + href if href.startswith("/") else href
                        links.append(full)
            else:
                # --- FLIPKART LINK FIX ---
                # Strategy: Don't rely on div classes. Look for 'href' containing product pattern '/p/'
                # This finds links even if the grid layout CSS is broken/changed
                raw_links = soup.find_all('a', href=re.compile(r'/p/itm'))
                seen_urls = set()
                
                for a in raw_links:
                    if len(links) >= 2: break
                    href = a['href']
                    if href not in seen_urls:
                        full = "https://www.flipkart.com" + href if href.startswith("/") else href
                        links.append(full)
                        seen_urls.add(href)
                
                if not links:
                    # Fallback: Try generic classes if regex failed
                    items = soup.select("div[data-id]") or soup.select("div._1AtVbE")
                    for item in items[:2]:
                        a = item.select_one("a")
                        if a and a.has_attr('href'):
                             links.append("https://www.flipkart.com" + a['href'])

            log.info(f"{source} found {len(links)} links. Visiting...")

            # --- DEEP VISIT ---
            for i, link in enumerate(links):
                try:
                    log.info(f"   -> {source}: Visiting {link[:40]}...")
                    
                    try:
                        driver.get(link)
                    except TimeoutException:
                        log.warning(f"   -> {source} Product Page Timeout. Parsing partial content.")
                        driver.execute_script("window.stop();")
                    
                    time.sleep(2)
                    page_soup = BeautifulSoup(driver.page_source, "html.parser")
                    
                    name, price, rating, specs = "Unknown", 0.0, "N/A", ""

                    # 1. TITLE
                    if source == "Amazon":
                        name_el = page_soup.select_one("#productTitle")
                        if name_el: name = name_el.text.strip()
                    else:
                        name_el = page_soup.select_one("span.B_NuCI") or page_soup.select_one("h1")
                        if name_el: name = name_el.text.strip()

                    # 2. PRICE (Regex for both)
                    # Search entire body for price pattern if specific selector fails
                    body_text = page_soup.get_text()
                    # Look for ₹ followed by numbers, but prioritize specific elements
                    
                    if source == "Amazon":
                        price_el = page_soup.select_one(".a-price-whole")
                    else:
                        price_el = page_soup.select_one("div.Nx9bqj") or page_soup.select_one("div._30jeq3") or page_soup.select_one("div.CEmiEU")

                    if price_el:
                         # CSS found
                         clean = price_el.text.replace(",", "").replace("₹", "").strip()
                         if clean.replace(".", "").isdigit(): price = float(clean)
                    
                    if price == 0.0:
                        # Regex Fallback
                        p_match = re.search(r'₹\s?([0-9,]+)', body_text)
                        if p_match:
                            val = float(p_match.group(1).replace(",", ""))
                            if val > 100: price = val

                    # 3. RATING
                    if source == "Amazon":
                        r_el = page_soup.select_one("#acrPopover") or page_soup.select_one("span.a-icon-alt")
                        if r_el:
                            txt = r_el.get("title") or r_el.text
                            m = re.search(r'(\d\.\d)', txt)
                            if m: rating = m.group(1)
                    else:
                        r_el = page_soup.select_one("div.XQDdHH") or page_soup.select_one("div._3LWZlK")
                        if r_el: rating = r_el.text.strip()

                    # 4. SPECS
                    if source == "Amazon":
                        table = page_soup.select_one("#productDetails_techSpec_section_1")
                        if table:
                            specs = " | ".join([f"{r.find('th').text.strip()}: {r.find('td').text.strip()}" for r in table.find_all("tr") if r.find('th')])
                        else:
                            bullets = page_soup.select("#detailBullets_feature_div li")
                            specs = " | ".join([li.text.strip().replace("\n", "") for li in bullets[:6]])
                    else:
                        # Flipkart Tables
                        rows = page_soup.select("tr._1s_Smc") or page_soup.select("tr.row")
                        if rows:
                            specs_list = []
                            for row in rows:
                                cols = row.find_all("td")
                                if len(cols) == 2:
                                    specs_list.append(f"{cols[0].text.strip()}: {cols[1].text.strip()}")
                            specs = " | ".join(specs_list)
                        else:
                            # Highlights fallback
                            lis = page_soup.select("div._2418kt ul li")
                            specs = " | ".join([li.text for li in lis])

                    # SAVE
                    if price > 0:
                        item_data = {
                            "name": name, "price": price, "rating": rating,
                            "link": link, "specs": specs[:800], "source": source
                        }
                        callback(item_data)
                        count += 1
                        
                except Exception as e:
                    log.error(f"   -> Failed {link[:20]}: {e}")
                    continue

        except Exception as e:
            log.error(f"{source} Fatal Error: {e}")
        return count

scraper_svc = ScraperService()