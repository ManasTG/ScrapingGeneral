import time
import re
import urllib.parse
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.scrapers.base import BaseScraper


class Scraper(BaseScraper):
    BASE_URL = "https://www.jiomart.com"
    
    # Selector dictionary to drive the search listing and details crawl
    SELECTORS = {
        # ── Search page ──────────────────────────────────────────────────────
        "search_input": "input#autocomplete-0, input#search, input[name='q'], input[type='search'], input[placeholder*='search']",
        "search_submit": "button.search-btn, button[type='submit'], span.search-icon, i.jds-icon-search",

        # Product containers on PLP
        "product_container": "div.plp-card-container, div.jm-col-3, div.jm-col-4, div.product-grid-item, .product-card, div.plp-card",
        "title": "span.plp-card-title, div.plp-card-title, .name, .product-name, .title, a[class*='title'], [class*='card-title']",
        "link": "a[href*='/p/'], a.plp-card-wrapper, a.product-image-container, a",
        "price": "span.jm-heading-xxs, .plp-card-price, .price, .final-price, span[class*='price'], div[class*='price']",
        "rating": "span.plp-card-details-rating, div.rating-star, span.rating, .plp-card-details-rating-val",
        "reviews_count": "span.plp-card-details-reviews, .rating-count, span.rating-count, .reviews-count",
        "image": "img.plp-card-image-normal, img.plp-card-image, img.product-image, img",

        # ── Detail page ──────────────────────────────────────────────────────
        "detail_title": "h1#pdp-name, h1.pdp-name, h1.product-title, h1.jm-mb-xs, h1",
        "detail_brand": "a#pdp-brand, .pdp-brand, .product-brand, span.pdp-brand-name, a.brand-link, td.brand-value",
        "detail_specs_table": "table.pdp-specs-table, .pdp-specifications-table, div.pdp-specs, table",
        "detail_about": "ul.pdp-highlights li, .pdp-product-highlights li, ul.jm-list li, li",
        "detail_description": "div.pdp-product-description, #pdp-description, .pdp-desc-text, .product-description, p",
        "detail_price": "span.jm-heading-xs, span.pdp-price, span.pdp-selling-price, .pdp-price-box, span.jm-heading-m",
        "detail_rating": "span.pdp-rating, .rating-value, div[class*='rating']",
        "detail_reviews_count": "span.pdp-reviews-count, .reviews-value",
        "detail_image": "img.pdp-image, img#pdp-main-image, img[src*='jiomart']",
        "detail_seller": ".pdp-seller-name, .seller-name, span[class*='seller']",
    }

    def close_popups(self) -> None:
        """
        Handle location setup prior to initiating searches on JioMart.
        Selects 'Delhi, India' from the location suggestion dropdown.
        """
        self.log("Handling JioMart location overlay/popup...")
        try:
            # Check for standard AllowLocation overlay
            overlay = self.driver.find_elements(By.CSS_SELECTOR, '.AllowLocation__overlay, div[class*="AllowLocation"]')
            if overlay:
                self.log("AllowLocation popup detected. Trying to click manual/enter pin button to open search...")
                clicked = self.driver.execute_script("""
                    var overlay = document.querySelector('.AllowLocation__overlay, div[class*="AllowLocation"]');
                    if (overlay) {
                        var buttons = overlay.querySelectorAll('button, div, span, a');
                        for (var i = 0; i < buttons.length; i++) {
                            var txt = buttons[i].innerText || '';
                            if (txt.toLowerCase().includes('manual') || txt.toLowerCase().includes('enter pin') || txt.toLowerCase().includes('select location')) {
                                buttons[i].click();
                                return true;
                            }
                        }
                    }
                    return false;
                """)
                if clicked:
                    self.log("Clicked manual/enter pin button on popup.")
                    time.sleep(2)
                else:
                    self.log("Could not find manual button. Dismissing overlay using close button/remove...")
                    self.driver.execute_script("""
                        var overlay = document.querySelector('.AllowLocation__overlay, div[class*="AllowLocation"]');
                        if (overlay) {
                            var closeBtn = document.querySelector('.AllowLocation__close, button[class*="close"], span[class*="close"]');
                            if (closeBtn) {
                                closeBtn.click();
                            } else {
                                overlay.remove();
                            }
                        }
                    """)
                    time.sleep(1.5)
        except Exception as e:
            self.log(f"AllowLocation popup handler error/not needed: {str(e)}")

        location_input_selector = "input#pincode, input[name='pincode'], input[placeholder*='pincode'], input[placeholder*='Pin'], input[placeholder*='pin'], input[type='text'][placeholder*='pincode'], input[placeholder*='location'], input[placeholder*='search']"
        
        # Check if the location input is already open (visible)
        input_field = None
        try:
            input_field = self.driver.find_element(By.CSS_SELECTOR, location_input_selector)
            if not input_field.is_displayed():
                input_field = None
        except Exception:
            pass

        # If not open, click the header location trigger
        if not input_field:
            self.log("Location input field not visible. Clicking header location button to open modal...")
            location_selectors = [
                ".DeliverySection__deliveryTitle",
                "span.DeliverySection__deliveryTitle",
                "#delivery_details",
                ".delivery-pin",
                ".lbl-delivery-pin",
                ".header-pincode",
                "div.delivery-address",
                "div[class*='delivery-pin']",
                "div[class*='pincode']",
                "div[class*='location']",
                "span[class*='delivery-pin']",
                "span[class*='pincode']",
                "button[class*='delivery-pin']",
            ]
            for sel in location_selectors:
                try:
                    element = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                    )
                    if element:
                        self.log(f"Clicking location trigger button: {sel}")
                        element.click()
                        time.sleep(1.5)
                        break
                except Exception:
                    continue

        # Enter location "Delhi, India" and confirm
        try:
            input_field = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, location_input_selector))
            )
            self.log("Location input field located. Entering 'Delhi, India'...")
            input_field.clear()
            input_field.send_keys("Delhi, India")
            time.sleep(3) # Wait for suggestion box to populate
            
            suggestion_found = False
            suggestion_selectors = [
                "//li[contains(text(), 'Delhi') or contains(text(), 'delhi') or contains(text(), 'DELHI')]",
                "//div[contains(text(), 'Delhi') or contains(text(), 'delhi') or contains(text(), 'DELHI')]",
                "//span[contains(text(), 'Delhi') or contains(text(), 'delhi') or contains(text(), 'DELHI')]",
                "//a[contains(text(), 'Delhi') or contains(text(), 'delhi') or contains(text(), 'DELHI')]",
                "//li[contains(translate(text(), 'DELHI', 'delhi'), 'delhi')]",
                "//div[contains(translate(text(), 'DELHI', 'delhi'), 'delhi')]",
                "//span[contains(translate(text(), 'DELHI', 'delhi'), 'delhi')]"
            ]
            
            for xpath in suggestion_selectors:
                try:
                    suggestion = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    self.log(f"Found location suggestion matching XPATH '{xpath}': '{suggestion.text}'. Clicking it...")
                    suggestion.click()
                    suggestion_found = True
                    break
                except Exception:
                    continue

            if suggestion_found:
                time.sleep(2)
                self._click_apply_button()
                self.log("Location confirmed. Waiting for a moment (3s) to reload and settle...")
                time.sleep(3)
            else:
                self.log("No specific 'Delhi' suggestion found. Trying to press Enter/click Apply...")
                input_field.send_keys(Keys.ENTER)
                time.sleep(1.5)
                self._click_apply_button()
                time.sleep(3)
        except Exception as e:
            self.log(f"Could not interact with location popup: {str(e)}")

    def _click_apply_button(self) -> None:
        """Helper to click the apply/submit button on the pincode modal if present."""
        apply_selectors = [
            "button[class*='apply']",
            "span[class*='apply']",
            "button[type='submit']",
            ".pincode-apply",
            "div.apply-btn",
            "button.apply-btn",
            "span.apply-btn",
            "button.btn-pincode-apply",
        ]
        for asel in apply_selectors:
            try:
                apply_btn = self.driver.find_element(By.CSS_SELECTOR, asel)
                if apply_btn.is_displayed() and apply_btn.is_enabled():
                    self.log(f"Clicking pincode apply button: {asel}")
                    apply_btn.click()
                    break
            except Exception:
                continue

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting JioMart Scraper for query: '{search_query}' (limit: {limit})")
        results = self._default_scrape_flow(self.BASE_URL, self.SELECTORS, search_query, limit)

        # Post-process each result with JioMart-specific fixes
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
                    # Try selectors
                    rating_elem = soup.select_one("span.pdp-rating, .rating-value")
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
                    rc_elem = soup.select_one("span.pdp-reviews-count, .reviews-value")
                    if rc_elem:
                        rc = rc_elem.get_text()
                except Exception:
                    pass

        if rc:
            rc_str = str(rc).strip().lower()
            m_k = re.search(r'([\d\.]+)\s*k', rc_str)
            if m_k:
                try:
                    item["reviews_count"] = str(int(float(m_k.group(1)) * 1000))
                    return
                except ValueError:
                    pass

            m_digits = re.search(r'([\d,]+)', rc_str)
            if m_digits:
                item["reviews_count"] = m_digits.group(1).replace(",", "")
                return

        item["reviews_count"] = "0"

    def _fix_price(self, item: dict) -> None:
        price = item.get("price") or ""
        if price:
            m = re.search(r'(₹\s*\d+(?:,\d{3})*(?:\.\d{2})?)', str(price))
            if m:
                item["price"] = m.group(1).replace(" ", "")
                return

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                price_elem = soup.select_one("span.jm-heading-xs, span.pdp-price, span.pdp-selling-price, .pdp-price-box")
                if price_elem:
                    price_text = price_elem.get_text().strip()
                    m = re.search(r'(₹\s*\d+(?:,\d{3})*(?:\.\d{2})?)', price_text)
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

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                brand_elem = soup.select_one("a#pdp-brand, .pdp-brand, span.pdp-brand-name, a.brand-link")
                if brand_elem:
                    brand_text = brand_elem.get_text().strip()
                    if brand_text:
                        item["brand"] = brand_text
                        return
            except Exception:
                pass

        # Fallback to first word of title
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
            item["seller"] = re.sub(r'(?i)^seller\s*:\s*', '', seller).strip()
            return

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                seller_el = soup.find(string=re.compile(r'sold\s+by\s*:', re.IGNORECASE))
                if not seller_el:
                    seller_el = soup.find(string=re.compile(r'seller\s*:', re.IGNORECASE))
                if seller_el:
                    parent_text = seller_el.parent.get_text().strip()
                    m = re.search(r'(?i)(?:sold\s+by|seller)\s*:\s*(.*)', parent_text)
                    if m:
                        item["seller"] = m.group(1).strip()
                        return
            except Exception:
                pass

        item["seller"] = "JioMart Retailer"

    def _fix_warranty(self, item: dict) -> None:
        # Check specs
        specs = item.get("specifications") or {}
        for k, v in specs.items():
            if "warranty" in k.lower():
                item["warranty"] = v
                return
        
        # Check highlights/description
        about_items = item.get("about_items") or []
        for bullet in about_items:
            if "warranty" in bullet.lower():
                item["warranty"] = bullet
                return
                
        item["warranty"] = "Standard manufacturer warranty if applicable"

    def _fix_specifications_and_about(self, item: dict) -> None:
        specs = {}
        about_items = []
        description = ""

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                
                # Check for specs tables
                tables = soup.select("table.pdp-specs-table, .pdp-specifications-table, table")
                for table in tables:
                    for row in table.select("tr"):
                        cols = row.select("th, td")
                        if len(cols) >= 2:
                            k = cols[0].get_text().strip()
                            v = cols[1].get_text().strip()
                            k = re.sub(r'\s+', ' ', k).rstrip(":")
                            v = re.sub(r'\s+', ' ', v)
                            if k and v and len(k) < 50 and len(v) < 250:
                                specs[k] = v
                
                # highlights
                bullets = soup.select("ul.pdp-highlights li, .pdp-product-highlights li, ul.jm-list li")
                for b in bullets:
                    b_text = b.get_text().strip()
                    if b_text and len(b_text) > 10 and len(b_text) < 200:
                        about_items.append(b_text)
                        
                desc_container = soup.select_one("div.pdp-product-description, #pdp-description, .pdp-desc-text, .product-description")
                if desc_container:
                    description = desc_container.get_text().strip()
            except Exception as e:
                self.log(f"Error parsing specifications and about: {e}")
        
        # Clean brand if specified in specs
        for k, v in specs.items():
            if k.lower() == "brand" or k.lower() == "manufacturer":
                item["brand"] = v

        item["specifications"] = specs
        if not about_items:
            about_items = ["Standard product quality guaranteed by JioMart."]
        item["about_items"] = about_items[:10]
        if not description:
            description = "No description available."
        item["description"] = description
