import time
import re
from typing import List, Dict, Any
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from app.scrapers.base import BaseScraper


class Scraper(BaseScraper):
    BASE_URL = "https://www.flipkart.com"
    SELECTORS = {
        # ── Search page ──────────────────────────────────────────────────────
        "search_input": "input[name='q'], input.Pke_EE, input[title*='Search']",
        "search_submit": "button[type='submit'], button._2iLD__, svg.r4151t",

        # Product card containers on search results page
        "product_container": (
            "div._1AtVbE, div._7573G2, div.CGtC98, div.yKfJKb, "
            "div.slAV3a, div.gJG47c, [data-id], div[class*='productCard']"
        ),

        # Title: prefer the dedicated title div; avoid the bare <a> that
        # also matches "Add to Compare" links
        "title": (
            "div._4rR01T, div.KzDlHZ, div._2WkVRV, "
            "a.s1Q9rs[title], a.wjcE2[title], a.IRpwTa[title]"
        ),

        "link":  "a[href*='/p/'], a.CGtC98, a._1fQZEK, a.s1Q9rs, a.rleRzy",

        # Price
        "price": (
            "div._30jeq3, div.Nx93Qx, div._25b18c, "
            "div.hl05eU, div.DyC4OI, [class*='price']"
        ),

        # Rating — Flipkart obfuscates class names; use a broad sweep +
        # text-pattern fallback in the base flow
        "rating": (
            "div._3LWZlK, span.X1uhqq, div.X1uhqq, "
            "span.Y1tV3b, div[class*='rating']"
        ),

        # Reviews count  (Wyu63M / _2_R_DZ are known FK classes)
        "reviews_count": (
            "span._2_R_DZ, span.Wyu63M, "
            "span[class*='rating-reviews'], span[class*='count']"
        ),

        "image": (
            "img._396csY, img._53u2t-, img.DByoEF, "
            "img._2r43zH, img.szzFBx, img[src*='rukminim']"
        ),

        # ── Detail page ──────────────────────────────────────────────────────
        # Full product title shown at top of product page
        "detail_title": "span.B_NuCI, h1.G6XhYL, span.VU-ZEz, h1",

        # Brand / Manufacturer
        "detail_brand": (
            "span.byline, div._1V6C56, span.G1u1ci, "
            "div._2rdyvV, div._3_6Uyw span, span._2b4HkV"
        ),
        "detail_brand_xpath": (
            "//td[normalize-space(text())='Brand']/following-sibling::td | "
            "//th[normalize-space(text())='Brand']/..//td[2]"
        ),

        # Specs table  (Flipkart renders specs as a CSS-grid table)
        "detail_specs_table": (
            "table._14cfVK, div._1xp1A4, div.SpecificationTable, "
            "div.RygUYn, div._3k-BhJ, table"
        ),

        # "Highlights" bullet list
        "detail_about": (
            "div._2418aC ul li, li._21A30U, "
            "div._2o14nN ul li, div._2o14nN, "
            "div.yN-eZT ul li, .x3G5OL li, "
            "ul._2G6jTc li"
        ),

        # Product description section
        # Flipkart wraps the main description in a div with class _4gvKMe or
        # inside section.x3G5OL or div[class*='description']
        "detail_description": (
            "div._4gvKMe, "
            "div.cPHDOP div._2o14nN, "
            "section._3msved div, "
            "div[class*='description']:not([class*='spec']):not([class*='rating']), "
            "div._1mXVIV div._2o14nN"
        ),

        # ── Seller ───────────────────────────────────────────────────────────
        # Flipkart shows the sold-by name in:
        #   div#sellerName > span > span
        # Broader fallback chain follows
        "detail_seller": (
            "div#sellerName span span, "
            "div#sellerName span, "
            "div._3enr8x span, span._3SGgDu, "
            "a._1RLNHA, div.tn7TLd, "
            "div._27MIqn span, div[id*='seller'] span"
        ),

        # ── Warranty ─────────────────────────────────────────────────────────
        # Flipkart usually puts warranty in the specs table; keep the
        # CSS selectors as a secondary attempt.
        "detail_warranty": (
            "div.x3G5OL li:contains('Warranty'), "
            "li[class*='warranty'], "
            "div[class*='warranty'], "
            "div.x3G5OL"
        ),

        # ── Customer reviews ─────────────────────────────────────────────────
        "detail_reviews_container": (
            "div.col._2w1f9X, div.col._2ZG37Z, div.col.EPCm5O, "
            "div._1AtVbE div[class*='review'], "
            "div[class*='col'] div[class*='review']"
        ),
        "detail_review_rating":  "div._3LWZlK, div.X1uhqq, span.Y1tV3b, div[class*='rating']",
        "detail_review_title":   "p._2-N1P8, p.z3A1nd, p.title, p[class*='title']",
        "detail_review_text":    "div.t-y302, div._1gX497, div.ZmyZ1b, div[class*='review-text'], div.t-y302 div",
        "detail_review_author":  "p._2sc7ZR, p._2sc7ZR._2V3Cno, p[class*='author'], p[class*='name']",
        "detail_review_date":    "p._2sc7ZR:nth-child(2), p._2sc7ZR + p._2sc7ZR, p[class*='date']",

        # ── Detail fallbacks ─────────────────────────────────────────────────
        "detail_price":         "div.Nx93Qx, div._30jeq3, div.hl05eU, div.U1u1ci, div[class*='price']",
        "detail_rating":        "div._3LWZlK, span.X1uhqq, div.X1uhqq, span.Y1tV3b, [class*='rating']",
        "detail_reviews_count": "span._2_R_DZ, span.Wyu63M, [class*='rating-reviews']",
        "detail_image":         "img.DByoEF, img._396csY, img._2r43zH, img.szzFBx, img[src*='rukminim']",
    }

    # ── Popup handling ────────────────────────────────────────────────────────

    def close_popups(self) -> None:
        self.log("Checking for Flipkart login popup...")

        # Method 1: ESC key
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.ESCAPE)
            time.sleep(1)
        except Exception as e:
            self.log(f"Failed to send ESCAPE key: {e}")

        # Method 2: Click explicit close button
        popup_selectors = [
            (By.XPATH, "//button[contains(text(), '✕')]"),
            (By.XPATH, "//span[contains(text(), '✕')]"),
            (By.CSS_SELECTOR, "button._2KpZ6l._2doB4z"),
            (By.CSS_SELECTOR, "span._30XB9F"),
            (By.XPATH, "//button[text()='✕']"),
            (By.XPATH, "//span[text()='✕']"),
            (By.CSS_SELECTOR, "button[class*='_2doB4z']"),
        ]
        for by, sel in popup_selectors:
            try:
                element = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((by, sel))
                )
                if element:
                    self.log(f"Closing login popup via: {sel}")
                    element.click()
                    time.sleep(1)
                    return
            except Exception:
                continue

        self.log("No login popup found or already closed.")

    # ── Entry point ───────────────────────────────────────────────────────────

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting Flipkart Scraper for query: '{search_query}' (limit: {limit})")
        results = self._default_scrape_flow(self.BASE_URL, self.SELECTORS, search_query, limit)

        # Post-process each result with Flipkart-specific fixes
        for item in results:
            self._fix_title(item)
            self._fix_highlights(item)
            self._fix_specifications(item)
            self._fix_rating(item)
            self._fix_reviews_count(item)
            self._fix_seller(item)
            self._fix_warranty(item)
            self._fix_description(item)
            # Remove temporary page HTML string to keep clean DB records
            item.pop("_html", None)

        return results

    # ── Post-processing helpers ───────────────────────────────────────────────

    def _fix_title(self, item: dict) -> None:
        """Remove junk suffixes that Flipkart sometimes appends to titles."""
        title = item.get("title", "")
        # Strip trailing "(X Ratings & X Reviews)"  or  "₹XX,XXX" noise
        title = re.sub(r'\s*\(\d[\d,]*\s*(?:Ratings?|Reviews?).*?\)\s*$', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s+', ' ', title).strip()
        if title:
            item["title"] = title

    def _fix_rating(self, item: dict) -> None:
        """
        Keep only the numeric part of the rating, e.g.
        '4.2★' → '4.2'  or  '4.2 out of 5' → '4.2'
        If rating is N/A or missing, extract it using HTML helpers.
        """
        rating = item.get("rating") or ""
        
        # If rating is N/A or empty, try to extract it using page source
        if not rating or rating == "N/A":
            html_str = item.get("_html")
            if html_str:
                try:
                    soup = BeautifulSoup(html_str, "html.parser")
                    # Heuristic 1: Look for common rating elements
                    rating_selectors = [
                        "div._3LWZlK", "span.X1uhqq", "div.X1uhqq", 
                        "span.Y1tV3b", "div.cg31wB", "div._2d4h3g", "span.Wyu63M"
                    ]
                    for sel in rating_selectors:
                        elem = soup.select_one(sel)
                        if elem:
                            text = elem.get_text().strip()
                            m = re.search(r'([1-5]\.[0-9])', text)
                            if m:
                                rating = m.group(1)
                                break
                    
                    if not rating or rating == "N/A":
                        # Heuristic 2: Scan for element with class containing rating or star
                        for elem in soup.find_all(class_=re.compile(r'rating|star', re.IGNORECASE)):
                            text = elem.get_text().strip()
                            m = re.search(r'^([1-5]\.[0-9])\s*★?$', text)
                            if m:
                                rating = m.group(1)
                                break
                                
                    if not rating or rating == "N/A":
                        # Heuristic 3: Check regex fallback on page text
                        page_text = soup.get_text()
                        matches = re.findall(r'(\b[1-5]\.[0-9]\b)\s*(?:★|out of 5|ratings|reviews)', page_text, re.IGNORECASE)
                        if matches:
                            rating = matches[0]
                        else:
                            matches = re.findall(r'(\b[1-5]\.[0-9]\b)[\d,\s]*(?:ratings|reviews)', page_text, re.IGNORECASE)
                            if matches:
                                rating = matches[0]
                except Exception:
                    pass

        if not rating or rating == "N/A":
            return
            
        m = re.search(r'(\d(?:\.\d)?)', rating)
        if m:
            item["rating"] = m.group(1)

    def _fix_reviews_count(self, item: dict) -> None:
        """
        Flipkart shows ratings and reviews as '1,234 Ratings & 567 Reviews'.
        Extract only the reviews number; fall back to the ratings number.
        """
        rc = item.get("reviews_count") or ""
        if not rc or rc in ("0", "N/A"):
            return

        # e.g. "1,234 Ratings & 567 Reviews"
        m_both = re.search(
            r'([\d,]+)\s*Ratings?\s*[&and]+\s*([\d,]+)\s*Reviews?',
            rc, re.IGNORECASE
        )
        if m_both:
            item["reviews_count"] = m_both.group(2).replace(",", "")
            return

        # e.g. "1,234 Ratings"  or  "567 Reviews"
        m_single = re.search(r'([\d,]+)\s*(?:Ratings?|Reviews?)', rc, re.IGNORECASE)
        if m_single:
            item["reviews_count"] = m_single.group(1).replace(",", "")
            return

        # Plain number already
        m_plain = re.search(r'([\d,]+)', rc)
        if m_plain:
            item["reviews_count"] = m_plain.group(1).replace(",", "")

    def _fix_seller(self, item: dict) -> None:
        """
        Flipkart's seller name lives inside #sellerName or adjacent to 'Seller' label.
        Clean up rating tags appended next to the seller.
        """
        seller = item.get("seller") or ""
        if seller and seller not in ("Unknown", "N/A", ""):
            seller = re.sub(r'\s*[\d\.]+\s*★?\s*$', '', seller)
            seller = re.sub(r'\s*\(\s*[\d\.]+\s*★?\s*\)\s*$', '', seller)
            item["seller"] = seller.strip()
            return

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                seller_selectors = [
                    "div#sellerName", "div#sellerName span", "span._3SGgDu",
                    "div._3enr8x", "a._1RLNHA", "div.tn7TLd", "div._27MIqn"
                ]
                for sel in seller_selectors:
                    elem = soup.select_one(sel)
                    if elem:
                        text = elem.get_text().strip()
                        text = re.sub(r'(?i)^seller\s*:\s*', '', text)
                        text = re.sub(r'\s*[\d\.]+\s*★?\s*$', '', text)
                        text = re.sub(r'\s*\(\s*[\d\.]+\s*★?\s*\)\s*$', '', text)
                        if text and len(text) < 100:
                            item["seller"] = text.strip()
                            return

                seller_label = soup.find(string=re.compile(r'^Seller\s*$', re.IGNORECASE))
                if not seller_label:
                    seller_label = soup.find(string=re.compile(r'^Seller\s*:', re.IGNORECASE))
                
                if seller_label:
                    parent = seller_label.parent
                    label_text = parent.get_text().strip()
                    m = re.search(r'(?i)seller\s*:\s*([^0-9\(\★]+)', label_text)
                    if m:
                        val = m.group(1).strip()
                        if val:
                            item["seller"] = val
                            return
                    
                    sibling = parent.find_next_sibling()
                    if sibling:
                        sibling_text = sibling.get_text().strip()
                        sibling_text = re.sub(r'\s*[\d\.]+\s*★?\s*$', '', sibling_text)
                        sibling_text = re.sub(r'\s*\(\s*[\d\.]+\s*★?\s*\)\s*$', '', sibling_text)
                        if sibling_text and len(sibling_text) < 80:
                            item["seller"] = sibling_text
                            return

                    curr = parent
                    for _ in range(3):
                        if curr:
                            siblings = curr.find_next_siblings()
                            for sib in siblings:
                                sib_text = sib.get_text().strip()
                                if sib_text and "seller" not in sib_text.lower() and len(sib_text) < 80:
                                    sib_text = re.sub(r'\s*[\d\.]+\s*★?\s*$', '', sib_text)
                                    sib_text = re.sub(r'\s*\(\s*[\d\.]+\s*★?\s*\)\s*$', '', sib_text)
                                    item["seller"] = sib_text
                                    return
                            curr = curr.parent
            except Exception:
                pass

        # Try to recover from specifications dict
        specs = item.get("specifications") or {}
        for k, v in specs.items():
            if "sold by" in k.lower() or "seller" in k.lower():
                item["seller"] = v
                return

        if not item.get("seller"):
            item["seller"] = "Unknown"

    def _fix_warranty(self, item: dict) -> None:
        """
        Extract warranty from specs table or about_items if the CSS
        selector didn't capture it.
        """
        warranty = item.get("warranty") or ""
        if warranty and warranty not in ("N/A", ""):
            warranty_clean = warranty.split("\n")[0].strip()
            m = re.search(
                r'(\d+[\w\s]*(?:year|month|yr|mon)s?\s*(?:manufacturer|brand|domestic)?\s*warranty)',
                warranty_clean, re.IGNORECASE
            )
            if m:
                item["warranty"] = m.group(0).strip().title()
            else:
                item["warranty"] = warranty_clean[:120]  # cap length
            return

        # Fallback 1: specs dict
        specs = item.get("specifications") or {}
        for k, v in specs.items():
            if "warranty" in k.lower():
                item["warranty"] = v
                return

        # Fallback 2: scan about_items
        for bullet in (item.get("about_items") or []):
            if re.search(r'warranty', bullet, re.IGNORECASE):
                item["warranty"] = bullet.strip()
                return

        # Fallback 3: description text
        desc = item.get("description") or ""
        m = re.search(
            r'(\d+[\w\s]*(?:year|month|yr|mon)s?\s*(?:manufacturer|brand|domestic)?\s*warranty)',
            desc, re.IGNORECASE
        )
        if m:
            item["warranty"] = m.group(0).strip().title()
            return

        item["warranty"] = "N/A"

    def _fix_highlights(self, item: dict) -> None:
        """
        Flipkart highlights are shown as "Product highlights" section.
        Extract these and update item['about_items'].
        """
        html_str = item.get("_html")
        if not html_str:
            return
            
        try:
            soup = BeautifulSoup(html_str, "html.parser")
            about = item.get("about_items") or []
            
            # Find the header element with text "Product highlights"
            header = soup.find(string=re.compile(r'Product\s+highlights', re.IGNORECASE))
            if header:
                parent = header.parent
                container = None
                curr = parent
                for _ in range(5):
                    if curr:
                        grid_items = curr.select("div.grid-formation")
                        if grid_items:
                            container = curr
                            break
                        curr = curr.parent
                
                if container:
                    new_about = []
                    for grid_item in container.select("div.grid-formation"):
                        # Extract the text of the leaf node (i.e. the highlight text)
                        divs = [
                            d for d in grid_item.find_all(True)
                            if d.name in ("div", "span") and d.get_text(strip=True) and not d.find(True)
                        ]
                        if divs:
                            text = divs[-1].get_text(strip=True)
                            if text and len(text) > 3 and text not in new_about:
                                new_about.append(text)
                    if new_about:
                        about = new_about
            
            item["about_items"] = about
        except Exception as e:
            self.log(f"Error in _fix_highlights: {e}")

    def _fix_specifications(self, item: dict) -> None:
        """
        Flipkart uses a grid-based CSS layout (e.g. grid-formation-dynamic)
        for specifications in modern pages, which standard table parsers miss.
        Extract these and add them to item['specifications'].
        """
        html_str = item.get("_html")
        if not html_str:
            return
            
        try:
            soup = BeautifulSoup(html_str, "html.parser")
            specs = item.get("specifications") or {}
            
            # Find grid-based specifications
            grid_items = soup.select("div.grid-formation-dynamic")
            for grid_item in grid_items:
                divs = [
                    d for d in grid_item.find_all(True)
                    if d.name in ("div", "span") and d.get_text(strip=True) and not d.find(True)
                ]
                if len(divs) >= 2:
                    k = divs[0].get_text(strip=True)
                    v = divs[1].get_text(strip=True)
                    k = re.sub(r'\s+', ' ', k).rstrip(":")
                    v = re.sub(r'\s+', ' ', v)
                    if 2 < len(k) < 50 and 1 < len(v) < 250:
                        specs[k] = v
                        
            item["specifications"] = specs
        except Exception as e:
            self.log(f"Error in _fix_specifications: {e}")

    def _fix_description(self, item: dict) -> None:
        """
        Build a meaningful description from specifications and highlights.
        This provides a rich product profile.
        """
        specs = item.get("specifications") or {}
        about = item.get("about_items") or []
        
        desc_parts = []
        if about:
            highlights_str = " | ".join(about)
            desc_parts.append(f"Highlights: {highlights_str}")
        if specs:
            specs_str = " | ".join(f"{k}: {v}" for k, v in specs.items())
            desc_parts.append(f"Specifications: {specs_str}")
            
        if desc_parts:
            item["description"] = "\n\n".join(desc_parts)
        else:
            desc = (item.get("description") or "").strip()
            if desc and "flipkart plus" not in desc.lower():
                item["description"] = re.sub(r'\s{2,}', ' ', desc).strip()
            else:
                item["description"] = "N/A"