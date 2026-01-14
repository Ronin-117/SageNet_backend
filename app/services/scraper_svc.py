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
        
        # Block images aggressively
        prefs = {"profile.managed_default_content_settings.images": 2, "profile.managed_default_content_settings.stylesheets": 2}
        options.add_experimental_option("prefs", prefs)
        options.page_load_strategy = 'eager'
        
        driver = webdriver.Remote(command_executor=self.selenium_url, options=options)
        driver.set_page_load_timeout(20) # Strict 20s timeout per page
        return driver

    def scrape_all_stream(self, query: str, callback_func):
        """Scrapes Amazon then Flipkart. Returns total items found."""
        total_count = 0
        
        # Scrape Amazon
        total_count += self._scrape_site(query, "Amazon", callback_func, limit=3)
        
        # Scrape Flipkart
        total_count += self._scrape_site(query, "Flipkart", callback_func, limit=3)
            
        return total_count

    def _scrape_site(self, query, source, callback, limit):
        count = 0
        driver = None
        
        try:
            driver = self._get_driver()
            domain = "amazon.in" if source == "Amazon" else "flipkart.com"
            search_url = f"https://www.{domain}/search?q={query.replace(' ', '%20')}" if source == "Flipkart" else f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            
            log.info(f"🕷️ Scraping {source}: {query}")
            
            try:
                driver.get(search_url)
            except TimeoutException:
                log.warning(f"{source} Search Timeout. Attempting to parse anyway.")
            
            time.sleep(2)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # --- COLLECT LINKS ---
            links = []
            if source == "Amazon":
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
            
            driver.quit() # Close search driver
            
            # --- VISIT LINKS (Relentless Mode) ---
            for link in links:
                try:
                    # New Driver for EACH product (Prevent memory leaks/timeouts)
                    p_driver = self._get_driver()
                    log.info(f"   -> {source}: Visiting {link[:40]}...")
                    
                    try:
                        p_driver.get(link)
                    except TimeoutException:
                        log.warning(f"   -> Timeout on product page. Parsing loaded content.")
                        p_driver.execute_script("window.stop();")
                    
                    time.sleep(2)
                    page_soup = BeautifulSoup(p_driver.page_source, "html.parser")
                    
                    item_data = self._parse_product_page(page_soup, source, link)
                    
                    if item_data:
                        callback(item_data)
                        count += 1
                        
                    p_driver.quit()
                    
                except Exception as e:
                    log.error(f"   -> Failed {link[:20]}: {e}")
                    if 'p_driver' in locals(): p_driver.quit()
                    continue

        except Exception as e:
            log.error(f"{source} Fatal Error: {e}")
            if driver: driver.quit()
            
        return count

    def _parse_product_page(self, soup, source, link):
        try:
            # 1. TITLE
            if source == "Amazon":
                name_el = soup.select_one("#productTitle")
            else:
                name_el = soup.select_one("span.B_NuCI") or soup.select_one("h1")
            name = name_el.text.strip() if name_el else "Unknown"

            # 2. PRICE
            price = 0.0
            if source == "Amazon":
                price_el = soup.select_one(".a-price-whole")
            else:
                price_el = soup.select_one("div.Nx9bqj") or soup.select_one("div._30jeq3") or soup.select_one("div.CEmiEU")

            if price_el:
                txt = price_el.text.replace(",", "").replace("₹", "").strip()
                if txt.replace(".", "").isdigit(): price = float(txt)

            # 3. RATING (Specific Selectors)
            rating = "N/A"
            if source == "Amazon":
                # Amazon puts rating in Title of popover or text
                r_el = soup.select_one("#acrPopover") or soup.select_one("span.a-icon-alt")
                if r_el:
                    txt = r_el.get("title") or r_el.text
                    m = re.search(r'(\d\.\d)', txt)
                    if m: rating = m.group(1)
            else:
                # Flipkart uses specific div class
                r_el = soup.select_one("div._3LWZlK") or soup.select_one("div.XQDdHH")
                if r_el: rating = r_el.text.strip()

            # 4. SPECS
            specs_text = ""
            if source == "Amazon":
                table = soup.select_one("#productDetails_techSpec_section_1")
                if table:
                    specs_text = " | ".join([f"{row.find('th').text.strip()}: {row.find('td').text.strip()}" for row in table.find_all("tr") if row.find('th')])
                else:
                    bullets = soup.select("#detailBullets_feature_div li")
                    specs_text = " | ".join([li.text.strip().replace("\n", "") for li in bullets[:6]])
            else:
                # Flipkart Table
                rows = soup.select("tr._1s_Smc") or soup.select("tr.row")
                specs_list = []
                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) == 2: specs_list.append(f"{cols[0].text.strip()}: {cols[1].text.strip()}")
                specs_text = " | ".join(specs_list)

            if price > 0:
                return {
                    "name": name, "price": price, "rating": rating,
                    "link": link, "specs": specs_text[:800], "source": source
                }
            return None

        except: return None

scraper_svc = ScraperService()