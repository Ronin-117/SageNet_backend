from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import time
import re
from app.services.scrapers.base_scraper import BaseScraper
from app.core.logger import setup_logger

log = setup_logger("AmazonScraper")

class AmazonScraper(BaseScraper):
    def scrape(self, query, callback, limit=2):
        driver = None
        count = 0
        try:
            driver = self.get_driver()
            url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            log.info(f"🕷️ Amazon Search: {url}")
            
            try:
                driver.get(url)
            except TimeoutException:
                log.warning("Amazon Search Timeout. Stopping load.")
                driver.execute_script("window.stop();")
            
            time.sleep(2)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # --- 1. GET LINKS ---
            links = []
            items = soup.select("div[data-component-type='s-search-result']")
            
            # If standard selector fails, try generic
            if not items:
                log.warning("Standard Amazon selector failed. Trying generic.")
                items = soup.select("div.s-result-item")

            log.info(f"Amazon Search Cards Found: {len(items)}")

            for item in items[:limit]:
                # Look for link in h2 (Title) or generic link
                link_el = item.select_one("h2 a") or item.find('a', href=re.compile(r'/(dp|gp)/'))
                if link_el:
                    href = link_el['href']
                    full = "https://www.amazon.in" + href if href.startswith("/") else href
                    links.append(full)

            # --- 2. DEEP DIVE ---
            for link in links:
                try:
                    log.info(f"   -> Amazon Visit: {link[:50]}...")
                    try:
                        driver.get(link)
                    except TimeoutException:
                        driver.execute_script("window.stop();")
                    
                    time.sleep(2)
                    p_soup = BeautifulSoup(driver.page_source, "html.parser")

                    # Title
                    title = "Unknown"
                    t_el = p_soup.select_one("#productTitle")
                    if t_el: title = t_el.text.strip()

                    # Price
                    price = 0.0
                    p_el = p_soup.select_one(".a-price-whole")
                    if p_el: 
                        price = self.clean_price(p_el.text)
                    
                    # Rating
                    rating = "N/A"
                    r_el = p_soup.select_one("#acrPopover") or p_soup.select_one("#averageCustomerReviews")
                    if r_el:
                        rating = self.clean_rating(r_el.get("title") or r_el.text)

                    # Specs
                    specs = ""
                    table = p_soup.select_one("#productDetails_techSpec_section_1")
                    if table:
                        specs = " | ".join([f"{r.find('th').text.strip()}: {r.find('td').text.strip()}" for r in table.find_all("tr") if r.find('th')])
                    else:
                        bullets = p_soup.select("#detailBullets_feature_div li")
                        specs = " | ".join([li.text.strip().replace("\n", " ") for li in bullets[:6]])

                    if price > 0:
                        callback({
                            "name": title, "price": price, "rating": rating, 
                            "link": link, "specs": specs[:800], "source": "Amazon"
                        })
                        count += 1
                        
                except Exception as e:
                    log.error(f"Amazon Item Error: {e}")
                    
        except Exception as e:
            log.error(f"Amazon Critical Error: {e}")
        finally:
            if driver: driver.quit()
        return count