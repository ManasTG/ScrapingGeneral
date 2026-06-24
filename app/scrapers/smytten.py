import re
import time
import urllib.parse
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.scrapers.base import BaseScraper, ScrapeCancelledException


class Scraper(BaseScraper):
    BASE_URL = "https://smytten.com"
    SELECTORS = {
        # ── Search page ──────────────────────────────────────────────────────
        "search_input": "input[type='search'], input[placeholder*='Search']",
        "search_submit": "input[type='search']",

        # Product containers matching Trial, Shop or general cards
        "product_container": "div.css-112gu2v, div.css-7a2h6w, div[class*='ProductCard'], div[class*='product-card'], a[href*='/product/']",
        "title": "h3.css-1bxfed, h6.css-1wae67p, h3, h6, [class*='title'], [class*='name']",
        "brand": ".css-19rulb3, h4.css-mtys0e, h4, [class*='brand']",
        "link": "a[href*='/product/'], a[href*='/shop/product/'], a[href*='/trial/product/']",
        "price": ".css-1nr9wgh, h6.css-4azlf7, .price, [class*='price']",
        "rating": "p.css-pzp4ha, p.css-jv1d3j, [class*='rating'], .rating",
        "reviews_count": ".reviews-count, .rating-count, [class*='reviews']",
        "image": "img.css-1shpo1e, img.css-12256vw, img",

        # ── Detail page ──────────────────────────────────────────────────────
        "detail_title": "h1#product-heading, h1.css-d2y0ky, h1.css-wutisi, h1",
        "detail_brand": "a[href^='/brand/'], a.css-yybu5f, [class*='brand']",
        "detail_specs_table": ".specs-table, table, .specifications, [class*='specsTable']",
        "detail_about": ".product-about, .highlights, [class*='highlights'], .ant-tabs-content-holder",
        "detail_description": ".product-description, .description, [class*='description'], .ant-tabs-content-holder",
        "detail_price": "div.css-k3moiz, .css-1yo9tud, [class*='price']",
        "detail_rating": ".css-76wsh, [class*='rating']",
        "detail_reviews_count": ".css-3nonjq, [class*='reviewsCount']",
        "detail_image": "img[src*='/product/'], img[class*='product'], img[class*='detail']",
        "detail_seller": "[class*='seller'], .seller-info",
    }

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting Smytten Scraper for query: '{search_query}' (limit: {limit})")
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
            
            # Form search URL directly
            search_url = f"{url.rstrip('/')}/search-product?search={urllib.parse.quote(search_query)}"
            
            self.log(f"Navigating directly to search URL: {search_url}...")
            self.driver.get(search_url)
            
            # Allow page to settle
            time.sleep(3)
            
            # Close any popups if applicable
            try:
                self.close_popups()
            except Exception as e:
                self.log(f"Error closing popups: {str(e)}")

            # Scroll down slowly to trigger infinite scroll load elements
            self.check_cancelled(results)
            self.log("Scrolling page to load items...")
            for i in range(3):
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
                    reviews_elem = container.select_one(selectors["reviews_count"])
                    if reviews_elem:
                        reviews_count = reviews_elem.get_text().strip()
                    
                    if not reviews_count:
                        # Fallback to search inside card text for reviews count pattern
                        match = re.search(r'\(?(\d[\d,]*)\)?\s*(?:Ratings|Reviews)', container.get_text(), re.IGNORECASE)
                        if match:
                            reviews_count = match.group(1)
                    
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
                    
                    # Extract brand
                    brand_elem = container.select_one(selectors["brand"])
                    brand = brand_elem.get_text().strip() if brand_elem else None
                    if not brand:
                        # Check if first word of title can be brand
                        words = title.split()
                        brand = words[0] if words else "Unknown"

                    listings.append({
                        "title": title,
                        "url": product_url,
                        "price": price,
                        "brand": brand,
                        "rating": rating or "N/A",
                        "reviews_count": reviews_count or "0",
                        "image_url": image_url
                    })
                except Exception:
                    continue
                
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
                    time.sleep(2.5)  # Delay between requests
                    
                    # Try to expand description tabs (click all tabs trigger to load spec/description details)
                    try:
                        tabs = self.driver.find_elements(By.CSS_SELECTOR, ".ant-tabs-tab-btn")
                        for tab in tabs:
                            tab_text = tab.text.strip()
                            if tab_text:
                                self.driver.execute_script("arguments[0].click();", tab)
                                self.log(f"Clicked tab: {tab_text}")
                                time.sleep(0.3)
                    except Exception as e:
                        self.log(f"Could not click info tabs: {str(e)}")
                    
                    # Save HTML
                    detail_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                    
                    # Specs parsing
                    specs = {}
                    tables = detail_soup.select(selectors["detail_specs_table"])
                    for table in tables:
                        for row in table.select("tr"):
                            cols = row.select("th, td")
                            if len(cols) == 2:
                                k = cols[0].get_text().strip().rstrip(":")
                                v = cols[1].get_text().strip()
                                if k and v:
                                    specs[k] = v
                                    
                    # Sibling key-value fallback
                    if len(specs) < 2:
                        for tr in detail_soup.find_all("tr"):
                            cols = tr.find_all(["td", "th"])
                            if len(cols) == 2:
                                k = cols[0].get_text().strip().rstrip(":")
                                v = cols[1].get_text().strip()
                                if k and v:
                                    specs[k] = v

                    # Smytten-specific specifications parser (inside tabs/panes)
                    active_panes = detail_soup.select(".ant-tabs-tabpane, [class*='tabpane']")
                    for pane in active_panes:
                        for div in pane.select("div, p, li"):
                            text = div.get_text().strip()
                            if ":" in text and "\n" not in text and 3 < len(text) < 150:
                                parts = text.split(":", 1)
                                k = parts[0].strip()
                                v = parts[1].strip()
                                if 2 < len(k) < 30 and v:
                                    specs[k] = v
                                    
                    # Extract brand
                    brand = item.get("brand")
                    brand_elem = detail_soup.select_one(selectors["detail_brand"])
                    if brand_elem:
                        brand = brand_elem.get_text().strip()
                        
                    # About / Highlights
                    about_items = []
                    about_content = detail_soup.select_one(selectors["detail_about"])
                    if about_content:
                        bullets = about_content.select("li, p")
                        for bullet in bullets:
                            txt = bullet.get_text().strip()
                            if txt and 10 < len(txt) < 150:
                                about_items.append(txt)
                                
                    # Description
                    desc_elem = detail_soup.select_one(selectors["detail_description"])
                    description = desc_elem.get_text().strip() if desc_elem else None
                    
                    item["brand"] = brand or "Unknown"
                    item["specifications"] = specs
                    item["about_items"] = about_items
                    item["description"] = description
                    item["seller"] = "Smytten"
                    item["warranty"] = "N/A"
                    item["reviews"] = []
                    item["_html"] = str(detail_soup)
                    
                    results.append(item)
                    self.log(f"[{prod_idx}/{len(target_listings)}] Successfully scraped item details.")
                except Exception as ex:
                    self.log(f"Error scraping details page {item['url']}: {str(ex)}")
                    item["brand"] = item.get("brand") or "Unknown"
                    item["specifications"] = {}
                    item["about_items"] = []
                    item["description"] = f"Failed to load details: {str(ex)}"
                    item["seller"] = "Smytten"
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
                    else:
                        text_match = re.search(r'([1-5]\.[0-9]|[1-5])\s*★', soup.get_text())
                        if text_match:
                            rating = text_match.group(1)
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
                    else:
                        text_match = re.search(r'([\d,]+)\s*(?:Reviews|Ratings)', soup.get_text(), re.IGNORECASE)
                        if text_match:
                            rc = text_match.group(1)
                except Exception:
                    pass

        if rc:
            rc_str = str(rc).strip()
            m = re.search(r'([\d,]+)', rc_str)
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
        seller = item.get("seller") or ""
        if seller and seller != "Unknown":
            item["seller"] = re.sub(r'(?i)^sold\s+by\s*:\s*', '', seller).strip()
            return
        item["seller"] = "Smytten"

    def _fix_warranty(self, item: dict) -> None:
        item["warranty"] = "N/A (Standard cosmetic/personal care product policy)"

    def _fix_specifications_and_about(self, item: dict) -> None:
        specs = item.get("specifications") or {}
        about_items = item.get("about_items") or []
        description = item.get("description") or ""

        html_str = item.get("_html")
        if html_str and (not specs or not about_items or not description):
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                
                if not specs:
                    rows = soup.select(self.SELECTORS["detail_specs_table"])
                    for row in rows:
                        for tr in row.select("tr"):
                            cols = tr.select("td, th")
                            if len(cols) == 2:
                                k = cols[0].get_text().strip().rstrip(":")
                                v = cols[1].get_text().strip()
                                if k and v:
                                    specs[k] = v
                
                if not description:
                    desc_elem = soup.select_one(self.SELECTORS["detail_description"])
                    if desc_elem:
                        description = desc_elem.get_text().strip()
                        
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
            about_items = ["Discovery and trial pack from Smytten."]
        item["about_items"] = about_items[:10]
        if not description:
            description = "No description available."
        item["description"] = re.sub(r'\s+', ' ', description).strip()
