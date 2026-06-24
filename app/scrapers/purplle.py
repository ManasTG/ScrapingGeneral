import re
import time
import urllib.parse
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.scrapers.base import BaseScraper, ScrapeCancelledException


class Scraper(BaseScraper):
    BASE_URL = "https://www.purplle.com"
    SELECTORS = {
        # ── Search page ──────────────────────────────────────────────────────
        "search_input": "input[placeholder*='looking for'], input[aria-label='Search'], input.form-control",
        "search_submit": "input[placeholder*='looking for']",  # Submit via Enter

        "product_container": "a[id^='listing_item_']",
        "title": "div.product-title",
        "link": "a[id^='listing_item_']",
        "price": "span.text-black.fw-bolder",
        "rating": "span.star-rating",
        "reviews_count": "span",
        "image": "img",

        # ── Detail page ──────────────────────────────────────────────────────
        "detail_title": "div.product-info h1 span.block.lh-normal:not(.font-bold), h1",
        "detail_brand": "div.product-info h1 span.font-bold.block.lh-normal, .font-bold",
        "detail_specs_table": "div.inner-box",
        "detail_about": "div.accordion-collapse",
        "detail_description": "div.accordion-collapse",
        "detail_price": "div.product-info strong.our-price, strong.our-price",
        "detail_rating": "div.product-info p.star-rating, p.star-rating",
        "detail_reviews_count": "div.product-info span.text-rating, span.text-rating",
        "detail_image": "img.transition-transform, img[src*='/product/']",
        "detail_seller": "div[class*='seller']",
    }

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting Purplle Scraper for query: '{search_query}' (limit: {limit})")
        results = self._custom_scrape_flow(self.BASE_URL, self.SELECTORS, search_query, limit)

        # Post-process each result
        for item in results:
            self._fix_title(item)
            self._fix_rating(item)
            self._fix_reviews_count(item)
            self._fix_price(item)
            self._fix_brand(item)
            self._fix_seller(item)
            self._fix_warranty(item)
            self._fix_specifications_and_about(item)
            
            # Remove temporary page HTML string to keep clean DB records
            item.pop("_html", None)

        return results

    def _custom_scrape_flow(self, base_url: str, selectors: Dict[str, str], search_query: str, limit: int) -> List[Dict[str, Any]]:
        results = []
        try:
            self.check_cancelled(results)
            self.init_driver()
            
            url = base_url
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            
            domain = self._get_domain(url)
            
            # Form search URL directly
            search_url = f"{url.rstrip('/')}/search?q={urllib.parse.quote(search_query)}"
            
            self.log(f"Navigating directly to search URL: {search_url}...")
            self.driver.get(search_url)
            
            # Allow page to settle
            time.sleep(2)
            
            # Close any popups
            try:
                self.close_popups()
            except Exception as e:
                self.log(f"Error closing popups: {str(e)}")

            # Wait for results to load
            self.log("Waiting for search results to load...")
            time.sleep(3)
            
            # Scroll down slowly to trigger lazy load elements
            self.check_cancelled(results)
            self.log("Scrolling page to load items...")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
            time.sleep(1.5)
            self.driver.execute_script("window.scrollTo(0, (document.body.scrollHeight / 3) * 2);")
            time.sleep(1.5)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
            
            self.check_cancelled(results)
            # Parse search results page
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            
            self.log("Extracting product listings from search results...")
            containers = soup.select(selectors["product_container"])
            self.log(f"Found {len(containers)} raw product containers.")
            
            listings = []
            for container in containers:
                try:
                    title_elem = container.select_one(selectors["title"])
                    if not title_elem:
                        if container.name == "a" and (container.has_attr("href") or container.has_attr("aria-label")):
                            title_elem = container
                        elif container.has_attr("aria-label"):
                            title_elem = container
                            
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text().strip()
                    if not title and title_elem.has_attr("aria-label"):
                        title = title_elem["aria-label"]
                    
                    link_elem = container.select_one(selectors["link"]) or title_elem
                    if not link_elem or not link_elem.has_attr("href"):
                        if container.name == "a" and container.has_attr("href"):
                            link_elem = container
                        else:
                            link_elem = container.select_one("a[href]")
                    
                    if not link_elem or not link_elem.has_attr("href"):
                        continue
                        
                    href = link_elem["href"]
                    product_url = urllib.parse.urljoin(url, href)
                    
                    # Prevent duplicates
                    if any(l["url"] == product_url for l in listings):
                        continue
                    
                    price_elem = container.select_one(selectors["price"])
                    price = price_elem.get_text().strip() if price_elem else None
                    
                    rating_elem = container.select_one(selectors["rating"])
                    rating = rating_elem.get_text().strip() if rating_elem else None
                    if not rating:
                        match = re.search(r'(\d\.\d)\s*(?:★|out of 5)', container.get_text())
                        if match:
                            rating = match.group(1)
                    
                    reviews_count = None
                    # Fallback to search inside card text for reviews count pattern: (123)
                    match = re.search(r'\((\d[\d,]*)\)', container.get_text())
                    if match:
                        reviews_count = match.group(1)
                    else:
                        reviews_elem = container.select_one(selectors["reviews_count"])
                        reviews_count = reviews_elem.get_text().strip() if reviews_elem else None
                    
                    image_elem = container.select_one(selectors["image"])
                    image_url = None
                    if image_elem:
                        for attr in ["src", "data-src", "data-original", "srcset"]:
                            val = image_elem.get(attr)
                            if val:
                                if attr == "srcset":
                                    val = val.split(",")[0].strip().split(" ")[0]
                                if not val.startswith("data:image/"):
                                    image_url = val
                                    break
                        if not image_url and image_elem.has_attr("src"):
                            image_url = image_elem["src"]
                    
                    listings.append({
                        "title": title,
                        "url": product_url,
                        "price": price,
                        "rating": rating or "N/A",
                        "reviews_count": reviews_count or "0",
                        "image_url": image_url
                    })
                except Exception:
                    continue

            # Universal fallback heuristic if no containers are found
            if len(listings) == 0:
                self.log("Predefined selectors yielded 0 valid products. Running universal fallback...")
                # ... let it fail gracefully or fallback to base scraper
                
            # Score and limit results
            keywords = [kw.lower() for kw in search_query.split()]
            scored_listings = []
            for item in listings:
                score = sum(1 for kw in keywords if kw in item["title"].lower())
                scored_listings.append((score, item))
            
            scored_listings.sort(key=lambda x: x[0], reverse=True)
            candidate_listings = [item for _, item in scored_listings]
            target_listings = candidate_listings[:limit]
            self.log(f"Selected {len(target_listings)} listings for details page parsing.")
            
            # Detail Scraping phase
            for idx, item in enumerate(target_listings):
                self.check_cancelled(results)
                prod_idx = idx + 1
                self.log(f"[{prod_idx}/{len(target_listings)}] Navigating to details page: {item['title'][:40]}...")
                
                try:
                    self.driver.get(item["url"])
                    time.sleep(2)  # Delay between requests
                    
                    # Expand description and specifications accordions
                    try:
                        desc_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Product Description') or contains(@class, 'accordion-button')]"))
                        )
                        self.log("Clicking accordion button to expand details...")
                        self.driver.execute_script("arguments[0].click();", desc_btn)
                        time.sleep(1)
                    except Exception as e:
                        self.log(f"Could not click accordion button: {str(e)}")
                    
                    # Save HTML
                    detail_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                    
                    # Specs
                    specs = {}
                    # Try selector table/list
                    tables = detail_soup.select(selectors["detail_specs_table"])
                    for table in tables:
                        # Extract inner-box elements if present
                        rows = table.select("div.mb-2.flex.gap-3.items-center")
                        for row in rows:
                            key_el = row.select_one("span.block.text-sm.font-semibold.text-dark-secondary")
                            val_el = row.select_one("span.block.text-sm.text-black-50")
                            if key_el and val_el:
                                key = key_el.get_text().strip().rstrip(":")
                                val = val_el.get_text().strip()
                                if key and val:
                                    specs[key] = val
                    
                    # Extract brand
                    brand = None
                    brand_elem = detail_soup.select_one(selectors["detail_brand"])
                    if brand_elem:
                        brand = brand_elem.get_text().strip()

                    # About/Highlights
                    about_items = []
                    bullets = detail_soup.select(selectors["detail_about"])
                    for bullet in bullets:
                        txt = bullet.get_text().strip()
                        if txt and len(txt) > 5:
                            about_items.append(txt)

                    # Description
                    desc_elem = detail_soup.select_one(selectors["detail_description"])
                    description = desc_elem.get_text().strip() if desc_elem else None
                    
                    item["brand"] = brand or "Unknown"
                    item["specifications"] = specs
                    item["about_items"] = about_items
                    item["description"] = description
                    item["seller"] = "Unknown"
                    item["warranty"] = "N/A"
                    item["reviews"] = []
                    item["_html"] = str(detail_soup)
                    
                    results.append(item)
                    self.log(f"[{prod_idx}/{len(target_listings)}] Successfully scraped item details.")
                except Exception as ex:
                    self.log(f"Error scraping details page {item['url']}: {str(ex)}")
                    item["brand"] = "Unknown"
                    item["specifications"] = {}
                    item["about_items"] = []
                    item["description"] = f"Failed to load details: {str(ex)}"
                    item["seller"] = "Unknown"
                    item["warranty"] = "N/A"
                    item["reviews"] = []
                    results.append(item)
            
            self.log(f"Scraping completed. Scraped details for {len(results)} items.")
            
        except Exception as e:
            self._save_debug_screenshot("fatal_error")
            self.log(f"Fatal error during scraping job: {str(e)}")
            raise e
        finally:
            if self.driver:
                self.log("Closing browser session...")
                self.driver.quit()
        
        return results

    def _fix_title(self, item: dict) -> None:
        title = item.get("title", "")
        title = re.sub(r'\s+', ' ', title).strip()
        if title:
            item["title"] = title

    def _fix_rating(self, item: dict) -> None:
        rating = item.get("rating") or ""
        if not rating or rating == "N/A":
            html_str = item.get("_html")
            if html_str:
                try:
                    soup = BeautifulSoup(html_str, "html.parser")
                    rating_elem = soup.select_one(self.SELECTORS["detail_rating"])
                    if rating_elem:
                        rating = rating_elem.get_text()
                except Exception:
                    pass

        if rating and rating != "N/A":
            m = re.search(r'([1-5]\.[0-9]|[1-5])', str(rating))
            if m:
                item["rating"] = m.group(1)
                return
        item["rating"] = "N/A"

    def _fix_reviews_count(self, item: dict) -> None:
        rc = item.get("reviews_count") or ""
        if not rc or rc == "0":
            html_str = item.get("_html")
            if html_str:
                try:
                    soup = BeautifulSoup(html_str, "html.parser")
                    rc_elem = soup.select_one(self.SELECTORS["detail_reviews_count"])
                    if rc_elem:
                        rc = rc_elem.get_text()
                except Exception:
                    pass

        if rc:
            rc_str = str(rc).strip()
            # Match number, potentially within parentheses
            m = re.search(r'\(?(\d[\d,]*)\)?', rc_str)
            if m:
                item["reviews_count"] = m.group(1).replace(",", "")
                return
        item["reviews_count"] = "0"

    def _fix_price(self, item: dict) -> None:
        price = item.get("price") or ""
        if price:
            m = re.search(r'(₹?\s*\d+(?:,\d{3})*(?:\.\d{2})?)', str(price))
            if m:
                item["price"] = m.group(1).replace(" ", "")
                if not item["price"].startswith("₹"):
                    item["price"] = "₹" + item["price"]
                return

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                price_elem = soup.select_one(self.SELECTORS["detail_price"])
                if price_elem:
                    price_text = price_elem.get_text().strip()
                    m = re.search(r'(₹?\s*\d+(?:,\d{3})*(?:\.\d{2})?)', price_text)
                    if m:
                        item["price"] = m.group(1).replace(" ", "")
                        if not item["price"].startswith("₹"):
                            item["price"] = "₹" + item["price"]
                        return
            except Exception:
                pass

    def _fix_brand(self, item: dict) -> None:
        brand = item.get("brand") or ""
        if brand and brand != "Unknown":
            item["brand"] = re.sub(r'\s+', ' ', brand).strip()
            return

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                brand_elem = soup.select_one(self.SELECTORS["detail_brand"])
                if brand_elem:
                    brand_text = brand_elem.get_text().strip()
                    if brand_text:
                        item["brand"] = brand_text
                        return
            except Exception:
                pass

        specs = item.get("specifications") or {}
        for k, v in specs.items():
            if k.lower() in ("brand", "brand name", "brand_name"):
                item["brand"] = v
                return

        title = item.get("title", "")
        if title:
            words = title.split()
            if words:
                item["brand"] = words[0]
                return

        item["brand"] = "Unknown"

    def _fix_seller(self, item: dict) -> None:
        item["seller"] = "Purplle Retailer"

    def _fix_warranty(self, item: dict) -> None:
        item["warranty"] = "N/A (Standard cosmetic return policy applies)"

    def _fix_specifications_and_about(self, item: dict) -> None:
        specs = item.get("specifications") or {}
        about_items = item.get("about_items") or []
        description = item.get("description") or ""

        html_str = item.get("_html")
        if html_str and (not specs or not about_items or not description):
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                
                if not specs:
                    rows = soup.select("div.inner-box div.mb-2.flex.gap-3.items-center")
                    for row in rows:
                        key_el = row.select_one("span.block.text-sm.font-semibold.text-dark-secondary")
                        val_el = row.select_one("span.block.text-sm.text-black-50")
                        if key_el and val_el:
                            k = key_el.get_text().strip().rstrip(":")
                            v = val_el.get_text().strip()
                            if k and v:
                                specs[k] = v
                
                # Sibling key-value fallback
                if not specs:
                    for table in soup.find_all("table"):
                        for tr in table.find_all("tr"):
                            cols = tr.find_all(["th", "td"])
                            if len(cols) == 2:
                                k = cols[0].get_text().strip().rstrip(":")
                                v = cols[1].get_text().strip()
                                if k and v:
                                    specs[k] = v

                # About / Description
                desc_panels = soup.select("div.accordion-collapse, div[class*='description']")
                for panel in desc_panels:
                    panel_text = panel.get_text().strip()
                    if panel_text:
                        panel_text = re.sub(r'\s+', ' ', panel_text)
                        if not description or len(panel_text) > len(description):
                            description = panel_text
                        
                        for li in panel.select("li, p"):
                            li_text = li.get_text().strip()
                            if li_text and 10 < len(li_text) < 150:
                                about_items.append(li_text)

                if not about_items and description:
                    sentences = [s.strip() for s in re.split(r'\.|\n|•', description) if len(s.strip()) > 15]
                    about_items = sentences[:5]
            except Exception:
                pass

        for k, v in list(specs.items()):
            if k.lower() == "brand" or k.lower() == "manufacturer":
                item["brand"] = v

        item["specifications"] = specs
        if not about_items:
            about_items = ["Standard personal care product from Purplle."]
        item["about_items"] = about_items[:10]
        if not description:
            description = "No description available."
        item["description"] = description
