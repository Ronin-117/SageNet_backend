from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import time
import re
from app.services.scrapers.base_scraper import BaseScraper
from app.core.logger import setup_logger

log = setup_logger("FlipkartScraper")

class FlipkartScraper(BaseScraper):
    def scrape(self, query, callback, limit=2):
        driver = None
        count = 0
        try:
            driver = self.get_driver()
            url = f"https://www.flipkart.com/search?q={query.replace(' ', '%20')}"
            log.info(f"🕷️ Flipkart Search: {url}")
            
            try:
                driver.get(url)
            except TimeoutException:
                log.warning("Flipkart Search Timeout. Stopping load.")
                driver.execute_script("window.stop();")
            
            time.sleep(2)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # --- 1. GET LINKS ---
            links = []
            # Grid view (div[data-id]) or fallback
            items = soup.select("div[data-id]") or soup.select("div._1AtVbE")
            
            # Collect unique links
            seen = set()
            for item in items:
                if len(links) >= limit: break
                a = item.select_one("a")
                if a and a.has_attr('href'):
                    href = a['href']
                    if href.startswith("/"):
                        full_link = "https://www.flipkart.com" + href
                        if full_link not in seen:
                            links.append(full_link)
                            seen.add(full_link)

            log.info(f"Flipkart Search Cards Found: {len(items)} -> Selected {len(links)} links")

            # --- 2. DEEP DIVE ---
            for link in links:
                try:
                    log.info(f"   -> Flipkart Visit: {link[:50]}...")
                    try:
                        driver.get(link)
                    except TimeoutException:
                        driver.execute_script("window.stop();")
                    
                    time.sleep(2)
                    p_soup = BeautifulSoup(driver.page_source, "html.parser")

                    # TITLE STRATEGIES
                    # 1. New Class (B_NuCI / VU-ZEz)
                    # 2. Generic H1
                    name_el = (p_soup.select_one("span.B_NuCI") or 
                               p_soup.select_one("span.VU-ZEz") or 
                               p_soup.select_one("h1"))
                    
                    name = name_el.text.strip() if name_el else "Unknown Product"
                    if name == "Unknown Product":
                        log.warning(f"   ⚠️ Title not found for {link[:20]}")

                    # PRICE STRATEGIES
                    price = 0.0
                    # 1. Specific Class (Nx9bqj is current 2025 standard)
                    price_el = (p_soup.select_one("div.Nx9bqj") or 
                                p_soup.select_one("div._30jeq3") or 
                                p_soup.select_one("div.CEmiEU"))
                    
                    if price_el:
                        price = self.clean_price(price_el.text)
                    
                    # 2. Fallback: Regex Search in Page Text (CRITICAL FIX)
                    if price == 0.0:
                        # Look for ₹ followed by digits
                        # We take the text of the main container to avoid header/footer noise
                        main_content = p_soup.select_one("div._1AtVbE") or p_soup
                        match = re.search(r'₹\s?([0-9,]+)', main_content.get_text())
                        if match:
                            clean = match.group(1).replace(",", "")
                            price = float(clean)

                    if price == 0.0:
                        log.warning(f"   ⚠️ Price not found for {link[:20]}")

                    # RATING
                    rating = "N/A"
                    r_el = p_soup.select_one("div.XQDdHH") or p_soup.select_one("div._3LWZlK")
                    if r_el: rating = r_el.text.strip()

                    # SPECS
                    specs = ""
                    rows = p_soup.select("tr._1s_Smc") or p_soup.select("tr.row")
                    if rows:
                        specs = " | ".join([f"{r.find_all('td')[0].text}: {r.find_all('td')[1].text}" for r in rows if len(r.find_all('td'))==2])
                    else:
                        # Highlights fallback
                        lis = p_soup.select("div._2418kt ul li")
                        specs = " | ".join([li.text for li in lis])

                    # SAVE
                    if price > 0:
                        callback({
                            "name": name, "price": price, "rating": rating, 
                            "link": link, "specs": specs[:800], "source": "Flipkart"
                        })
                        count += 1
                        # log.info(f"   ✅ Saved Flipkart Item: {name[:20]}")

                except Exception as e:
                    log.error(f"Flipkart Item Error: {e}")

        except Exception as e:
            log.error(f"Flipkart Critical Error: {e}")
        finally:
            if driver: driver.quit()
        return count