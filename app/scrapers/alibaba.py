import re
import time
import urllib.parse
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.scrapers.base import BaseScraper


class Scraper(BaseScraper):
    BASE_URL = "https://www.alibaba.com"
    PAGE_LOAD_STRATEGY = "eager"
    SELECTORS = {
        # ── Search page ──────────────────────────────────────────────────────
        "search_input": "input.search-bar-input, input[name='SearchText'], input.ui-searchbar-keyword, input[type='text']",
        "search_submit": "input.search-bar-button, button.ui-searchbar-submit, .search-btn, input[type='submit']",

        "product_container": "div.fy23-search-card, div.m-gallery-product-item-v2, div[data-content='productItem'], .organic-list-offer-outter, .m-gallery-product-item",
        "title": "h2.search-card-e-title, .search-card-e-title a, h2.search-card-e-title span, .elements-title-normal__content, a.search-card-e-title, .organic-gallery-offer__title, h2.search-card-title",
        "link": "h2.search-card-e-title a, a.search-card-e-title, a.elements-title-normal, a.organic-gallery-offer__title-link, a[href*='/product-detail/'], a.search-card-title-link",
        "price": "div.search-card-e-price-main, .elements-offer-price-normal__price, .organic-gallery-offer__price, .price, span.price, div.price",
        "rating": "div.search-card-e-review, .elements-item-review__rating, .search-card-e-review span, .organic-gallery-offer__rating-val, span.rating-value",
        "reviews_count": "div.search-card-e-review, .elements-item-review__review-num, .search-card-e-review a, .organic-gallery-offer__reviews, span.review-count",
        "image": "div.search-card-e-slider-image img, img.search-card-e-photo, .elements-search-card-media-gallery__image img, img.organic-gallery-offer__img, img.search-card-photo",

        # ── Detail page ──────────────────────────────────────────────────────
        "detail_title": "h1",
        "detail_brand": "td.value, div.attribute-layout div.attribute-item",
        "detail_specs_table": "[data-testid='module-details-attribute'], #key-attributes, .module_attribute, div.do-entry-list, div.attribute-layout, div.product-spec-container",
        "detail_about": "div.product-description-content, .do-entry-list, div.attribute-item",
        "detail_description": "div.product-description, div#productDescription, .do-entry-list",
        "detail_price": "[data-testid='product-price'], [data-testid='range-price'], .module_price, span.pdp-price, div.pdp-price, .price-number, span.price, div.price",
        "detail_rating": "span.rating-value, .average-rating, .rating-star, span.rating",
        "detail_reviews_count": "span.review-count, .review-number, span.reviews",
        "detail_image": "img.pdp-image, .main-image img, .pdp-image-viewer img, img.product-image",
        "detail_seller": "a.company-name, .company-name, .supplier-name, .seller-name",
    }

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting Alibaba Scraper for query: '{search_query}' (limit: {limit})")
        results = self._custom_scrape_flow(self.BASE_URL, self.SELECTORS, search_query, limit)

        # Post-process each result with Alibaba-specific fixes
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
            
            # Form search URL directly to bypass homepage overlays and search box typing issues
            search_url = f"{base_url.rstrip('/')}/trade/search?SearchText={urllib.parse.quote(search_query)}"
            
            self.log(f"Navigating directly to search URL: {search_url}...")
            self.driver.get(search_url)
            time.sleep(3)
            
            # Attempt to dismiss standard popups & overlays
            try:
                self.close_popups()
            except Exception as e:
                self.log(f"Error handling overlays: {str(e)}")
            
            target_listings = self._collect_listings_with_pagination(selectors, search_query, limit)
            self.log(f"Selected {len(target_listings)} listings for detail page parsing.")
            
            # Detail Scraping phase
            for idx, item in enumerate(target_listings):
                self.check_cancelled(results)
                prod_idx = idx + 1
                self.log(f"[{prod_idx}/{len(target_listings)}] Navigating to details page: {item['title'][:40]}...")
                
                try:
                    self.driver.get(item["url"])
                    time.sleep(2.5)  # Delay between requests
                    
                    # Dismiss overlays on product detail page
                    try:
                        self.close_popups()
                    except Exception as e:
                        self.log(f"Error closing overlays on details page: {str(e)}")
                        
                    # Extract price on details page if missing or N/A
                    price = item.get("price")
                    if not price or price == "N/A":
                        for sel in selectors["detail_price"].split(","):
                            sel = sel.strip()
                            try:
                                price_elem = self.driver.find_element(By.CSS_SELECTOR, sel)
                                if price_elem and price_elem.text.strip():
                                    price = price_elem.text.strip()
                                    item["price"] = price
                                    self.log(f"Extracted price from details page using selector '{sel}': {price}")
                                    break
                            except Exception:
                                continue

                    # Extract description from dynamic LazyLoad iframe first
                    description = ""
                    try:
                        iframe_selectors = [
                            ".module_description iframe", 
                            ".module_product_specification iframe",
                            "#description-layout iframe",
                            "iframe[id*='desc']",
                            "iframe[src*='desc']"
                        ]
                        iframe_el = None
                        for sel in iframe_selectors:
                            try:
                                iframe_el = self.driver.find_element(By.CSS_SELECTOR, sel)
                                if iframe_el:
                                    break
                            except Exception:
                                continue
                        
                        if iframe_el:
                            self.log("Found description iframe. Switching context to read description...")
                            self.driver.switch_to.frame(iframe_el)
                            time.sleep(1.5)  # Allow iframe content to load
                            
                            iframe_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                            description = iframe_soup.get_text().strip()
                            
                            # Switch back to the main document context
                            self.driver.switch_to.default_content()
                            self.log("Successfully extracted description from iframe.")
                    except Exception as e:
                        self.log(f"Failed to read description from iframe: {str(e)}")
                        try:
                            self.driver.switch_to.default_content()
                        except:
                            pass

                    # Extract page source for BS4 details parsing
                    detail_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                    
                    # Fallback title extraction on details page if needed
                    detail_title_sel = selectors.get("detail_title")
                    if detail_title_sel:
                        title_elem = detail_soup.select_one(detail_title_sel)
                        if title_elem and title_elem.get_text().strip():
                            item["title"] = title_elem.get_text().strip()
                    
                    # Detailed specifications parsing
                    specs = {}
                    specs_containers = detail_soup.select(selectors["detail_specs_table"])
                    for container in specs_containers:
                        # 1. Parse standard list items (li)
                        for li in container.select("li"):
                            txt = li.get_text().strip()
                            if ":" in txt:
                                parts = txt.split(":", 1)
                                k = parts[0].strip().replace("\n", "").replace("\t", "")
                                v = parts[1].strip().replace("\n", "").replace("\t", "")
                                if 2 < len(k) < 30 and 1 < len(v) < 150:
                                    specs[k] = v
                        
                        # 2. Parse table rows (tr)
                        for tr in container.select("tr"):
                            cols = tr.select("th, td")
                            if len(cols) == 2:
                                k = cols[0].get_text().strip().rstrip(":").replace("\n", "").replace("\t", "")
                                v = cols[1].get_text().strip().replace("\n", "").replace("\t", "")
                                if k and v:
                                    specs[k] = v
                                    
                        # 3. Parse grid parameters (key-value class items)
                        for item_attr in container.select("div[class*='attribute-item'], div[class*='attr-item'], div[class*='parameter'], div[class*='property']"):
                            txt = item_attr.get_text().strip()
                            if ":" in txt:
                                parts = txt.split(":", 1)
                                k = parts[0].strip().replace("\n", "").replace("\t", "")
                                v = parts[1].strip().replace("\n", "").replace("\t", "")
                                if 2 < len(k) < 30 and 1 < len(v) < 150:
                                    specs[k] = v
                            else:
                                children = item_attr.find_all(recursive=False)
                                if len(children) == 2:
                                    k = children[0].get_text().strip().rstrip(":").replace("\n", "").replace("\t", "")
                                    v = children[1].get_text().strip().replace("\n", "").replace("\t", "")
                                    if k and v:
                                        specs[k] = v
                                        
                    # Fallback global table specifications parser
                    if len(specs) < 3:
                        for table in detail_soup.find_all("table"):
                            if any(x in str(table).lower() for x in ["desc", "footer", "recommend"]):
                                continue
                            for tr in table.find_all("tr"):
                                cols = tr.find_all(["th", "td"])
                                if len(cols) == 2:
                                    k = cols[0].get_text().strip().rstrip(":").replace("\n", "").replace("\t", "")
                                    v = cols[1].get_text().strip().replace("\n", "").replace("\t", "")
                                    if 2 < len(k) < 30 and 1 < len(v) < 120 and ":" not in v:
                                        specs[k] = v

                    # Extract brand
                    brand = None
                    for k, v in specs.items():
                        if k.lower() in ("brand", "brand name", "brand_name", "manufacturer"):
                            brand = v
                            break
                    if not brand:
                        brand_elem = detail_soup.select_one(selectors["detail_brand"])
                        if brand_elem:
                            brand = brand_elem.get_text().strip()
                        
                    # Extract Rating
                    rating = item.get("rating")
                    if not rating or rating == "N/A":
                        for sel in selectors["detail_rating"].split(","):
                            sel = sel.strip()
                            r_elem = detail_soup.select_one(sel)
                            if r_elem and r_elem.get_text().strip():
                                rating = r_elem.get_text().strip()
                                break
                                
                    # Extract Reviews Count
                    reviews_count = item.get("reviews_count")
                    if not reviews_count or reviews_count == "0":
                        for sel in selectors["detail_reviews_count"].split(","):
                            sel = sel.strip()
                            rc_elem = detail_soup.select_one(sel)
                            if rc_elem and rc_elem.get_text().strip():
                                reviews_count = rc_elem.get_text().strip()
                                break

                    # Parse about items (highlights)
                    about_items = []
                    bullets = detail_soup.select("div.product-description-content li, div.do-entry-list li, [data-testid='module-details-description'] li")
                    for b in bullets:
                        txt = b.get_text().strip()
                        if txt and 10 < len(txt) < 150:
                            about_items.append(txt)
                                
                    # Fallback Description
                    if not description:
                        desc_elem = detail_soup.select_one(selectors["detail_description"])
                        description = desc_elem.get_text().strip() if desc_elem else None
                    if not description:
                        paragraphs = [p.get_text().strip() for p in detail_soup.find_all("p")]
                        paragraphs = [p for p in paragraphs if len(p) > 50]
                        if paragraphs:
                            description = max(paragraphs, key=len)
                    
                    # Extract Seller
                    seller = None
                    seller_elem = detail_soup.select_one(selectors["detail_seller"])
                    if seller_elem:
                        seller = seller_elem.get_text().strip()
                    
                    item["brand"] = brand or "Unknown"
                    item["price"] = price or item.get("price")
                    item["rating"] = rating or item.get("rating") or "N/A"
                    item["reviews_count"] = reviews_count or item.get("reviews_count") or "0"
                    item["specifications"] = specs
                    item["about_items"] = about_items
                    item["description"] = description
                    item["seller"] = seller or "Alibaba Verified Supplier"
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
                    item["seller"] = "Alibaba Verified Supplier"
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

    def close_popups(self) -> None:
        self.log("Checking for Alibaba popups/overlays to close...")
        
        # Deactivate overlay backdrops via style edits to ensure clickable search elements
        try:
            self.driver.execute_script("""
                const selectors = [
                    '.next-overlay-backdrop', '.dialog-backdrop', '.modal-backdrop', 
                    '[class*="backdrop"]', '[class*="Backdrop"]', '[class*="overlay"]', '[class*="Overlay"]'
                ];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        if (el && el.style) {
                            el.style.display = 'none';
                            el.style.pointerEvents = 'none';
                        }
                    });
                });
            """)
            self.log("Hidden overlays/backdrops via DOM style manipulation.")
        except Exception as e:
            self.log(f"Failed to hide overlays via JS: {str(e)}")
            
        # Try clicking standard close X buttons
        popup_close_selectors = [
            "button.cookie-policy-close",
            ".cookie-close",
            ".cookie-btn-accept",
            "[aria-label='Close']",
            ".ui-dialog-close-link",
            ".close-button",
            ".icbu-close",
            ".next-dialog-close",
            "//div[contains(@class, 'close') or contains(@class, 'Close')]",
            "//button[contains(@class, 'close') or contains(@class, 'Close') or contains(@aria-label, 'close') or contains(@aria-label, 'Close')]",
            "//a[contains(@class, 'close') or contains(@class, 'Close')]",
            "//span[contains(@class, 'close') or contains(@class, 'Close')]"
        ]
        
        for sel in popup_close_selectors:
            try:
                if sel.startswith("//"):
                    btn = WebDriverWait(self.driver, 1.5).until(
                        EC.element_to_be_clickable((By.XPATH, sel))
                    )
                else:
                    btn = WebDriverWait(self.driver, 1.5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                    )
                if btn:
                    self.log(f"Closing popup using selector: '{sel}'")
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.5)
            except Exception:
                continue

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
                    rating_elem = soup.select_one("span.rating-value, .average-rating, .rating-star")
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
                    rc_elem = soup.select_one("span.review-count, .review-number")
                    if rc_elem:
                        rc = rc_elem.get_text()
                except Exception:
                    pass

        if rc:
            rc_str = str(rc).strip().lower()
            m = re.search(r'([\d,]+)', rc_str)
            if m:
                item["reviews_count"] = m.group(1).replace(",", "")
                return
        item["reviews_count"] = "0"

    def _fix_price(self, item: dict) -> None:
        price = item.get("price") or ""
        if price:
            m = re.search(r'(\$\s*\d+(?:\.\d{2})?(?:\s*-\s*\$\s*\d+(?:\.\d{2})?)?|₹\s*\d+(?:,\d{3})*(?:\.\d{2})?)', str(price))
            if m:
                item["price"] = m.group(1).replace(" ", "")
                return
            m_generic = re.search(r'(\d+(?:\.\d{2})?)', str(price))
            if m_generic:
                item["price"] = "$" + m_generic.group(1)
                return

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                price_elem = soup.select_one("span.pdp-price, div.pdp-price, .price-number")
                if price_elem:
                    price_text = price_elem.get_text().strip()
                    m = re.search(r'(\$\s*\d+(?:\.\d{2})?(?:\s*-\s*\$\s*\d+(?:\.\d{2})?)?|₹\s*\d+(?:,\d{3})*(?:\.\d{2})?)', price_text)
                    if m:
                        item["price"] = m.group(1).replace(" ", "")
                        return
            except Exception:
                pass

    def _fix_brand(self, item: dict) -> None:
        brand = item.get("brand") or ""
        if brand and brand != "Unknown":
            item["brand"] = re.sub(r'\s+', ' ', brand).strip()
            return

        specs = item.get("specifications") or {}
        for k, v in specs.items():
            if k.lower() in ("brand", "brand name", "brand_name", "manufacturer"):
                item["brand"] = v
                return

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                for item_attr in soup.select("div.attribute-item"):
                    text = item_attr.get_text().strip()
                    if ":" in text:
                        parts = text.split(":", 1)
                        if parts[0].strip().lower() in ("brand", "brand name", "manufacturer"):
                            item["brand"] = parts[1].strip()
                            return
            except Exception:
                pass

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
            item["seller"] = re.sub(r'\s+', ' ', seller).strip()
            return

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                seller_elem = soup.select_one("a.company-name, .company-name, .supplier-name")
                if seller_elem:
                    item["seller"] = seller_elem.get_text().strip()
                    return
            except Exception:
                pass

        item["seller"] = "Alibaba Verified Supplier"

    def _fix_warranty(self, item: dict) -> None:
        warranty = item.get("warranty") or ""
        if warranty and warranty != "N/A":
            return

        specs = item.get("specifications") or {}
        for k, v in specs.items():
            if "warranty" in k.lower():
                item["warranty"] = v
                return

        item["warranty"] = "N/A (Trade Assurance protection applies)"

    def _fix_specifications_and_about(self, item: dict) -> None:
        specs = item.get("specifications") or {}
        about_items = item.get("about_items") or []
        description = item.get("description") or ""

        item["specifications"] = specs
        if not about_items:
            about_items = ["Trade Assurance protects your Alibaba.com orders.", "Verified Supplier options available."]
        item["about_items"] = about_items[:10]
        if not description:
            description = "No description available."
        item["description"] = description
