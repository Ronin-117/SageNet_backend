from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import time
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
            # Try new grid class (2025/2026) -> Old grid -> List view
            items = soup.select("div[data-id]") or soup.select("div._1AtVbE")
            
            log.info(f"Flipkart Search Cards Found: {len(items)}")

            for item in items[:limit]:
                a = item.select_one("a")
                if a and a.has_attr('href') and a['href'].startswith("/"):
                    links.append("https://www.flipkart.com" + a['href'])

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

                    # Title
                    title = "Unknown"
                    t_el = p_soup.select_one("span.B_NuCI") or p_soup.select_one("h1")
                    if t_el: title = t_el.text.strip()

                    # Price
                    price = 0.0
                    p_el = p_soup.select_one("div.Nx9bqj") or p_soup.select_one("div._30jeq3")
                    if p_el: 
                        price = self.clean_price(p_el.text)
                    
                    # Rating (Robust Search)
                    rating = "N/A"
                    # 1. Look for the green star box
                    r_el = p_soup.select_one("div.XQDdHH") or p_soup.select_one("div._3LWZlK")
                    if r_el:
                        rating = r_el.text.strip()
                    else:
                        # 2. Fallback: Search for text pattern inside the header area
                        header = p_soup.select_one("div.C7fEHH") # Common header container
                        if header:
                             rating = self.clean_rating(header.text)

                    # Specs
                    specs = ""
                    # Table Strategy
                    rows = p_soup.select("tr._1s_Smc") or p_soup.select("tr.row")
                    if rows:
                        specs = " | ".join([f"{r.find_all('td')[0].text}: {r.find_all('td')[1].text}" for r in rows if len(r.find_all('td'))==2])
                    else:
                        # Highlights Strategy
                        lis = p_soup.select("div._2418kt ul li")
                        specs = " | ".join([li.text for li in lis])

                    if price > 0:
                        callback({
                            "name": title, "price": price, "rating": rating, 
                            "link": link, "specs": specs[:800], "source": "Flipkart"
                        })
                        count += 1

                except Exception as e:
                    log.error(f"Flipkart Item Error: {e}")

        except Exception as e:
            log.error(f"Flipkart Critical Error: {e}")
        finally:
            if driver: driver.quit()
        return count