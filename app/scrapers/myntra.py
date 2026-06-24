import re
import urllib.parse
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from app.scrapers.base import BaseScraper


class Scraper(BaseScraper):
    BASE_URL = "https://www.myntra.com"
    SELECTORS = {
        # ── Search page ──────────────────────────────────────────────────────
        "search_input": "input.desktop-searchBar",
        "search_submit": "a.desktop-submit",  # Triggered via click or ENTER

        "product_container": "li.product-base",
        "title": "h4.product-product, h3.product-brand, .product-productName, div.product-product",
        "link": "a[target='_blank'], a[href*='/buy/'], a",
        "price": "span.product-discountedPrice, div.product-price, span.product-price",
        "rating": "div.product-ratingsContainer, div.product-ratings, span.product-ratings",
        "reviews_count": "div.product-ratingsContainer span.product-ratingsCount, .product-ratingsCount",
        "image": "img.img-responsive, picture.img-responsive img, img",

        # ── Detail page ──────────────────────────────────────────────────────
        "detail_title": "h1.pdp-name, h1",
        "detail_brand": "h1.pdp-title, h1.pdp-brand",
        "detail_specs_table": "div.index-row",  # Fallback row selector
        "detail_about": ".pdp-product-description-content, .pdp-product-detail",
        "detail_description": ".pdp-product-description-content, .pdp-product-detail",
        "detail_price": "span.pdp-price, strong.pdp-price, span[class*='pdp-price']",
        "detail_rating": "div.index-overallRating div, div.pdp-ratingsCount, div.index-overallRating",
        "detail_reviews_count": "div.index-ratingsCount, div.pdp-ratingsCount span",
        "detail_image": "img.pdp-image, div.image-grid-image, img[src*='myntra']",
        "detail_seller": ".pdp-seller-name, span[class*='seller']",
    }

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting Myntra Scraper for query: '{search_query}' (limit: {limit})")
        results = self._default_scrape_flow(self.BASE_URL, self.SELECTORS, search_query, limit)

        # Post-process each result with Myntra-specific fixes
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
                    # Try overall rating selector on pdp page
                    rating_elem = soup.select_one("div.index-overallRating div, div.pdp-ratingsCount")
                    if rating_elem:
                        rating = rating_elem.get_text()
                except Exception:
                    pass

        if rating and rating != "N/A":
            # Match e.g. 4.3 or 4
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
                    rc_elem = soup.select_one("div.index-ratingsCount, div.pdp-ratingsCount span")
                    if rc_elem:
                        rc = rc_elem.get_text()
                except Exception:
                    pass

        if rc:
            rc_str = str(rc).strip().lower()
            # Handle ratings/reviews counts like "1.2k" or "15"
            m_k = re.search(r'([\d\.]+)\s*k', rc_str)
            if m_k:
                try:
                    item["reviews_count"] = str(int(float(m_k.group(1)) * 1000))
                    return
                except ValueError:
                    pass

            # Match first series of digits (potentially with commas)
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
                # Look in pdp-price
                price_elem = soup.select_one("span.pdp-price, strong.pdp-price")
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
                brand_elem = soup.select_one("h1.pdp-title")
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

        item["seller"] = "Myntra Preferred Seller"

    def _fix_warranty(self, item: dict) -> None:
        # Apparel / footwear usually does not have electronic warranty.
        item["warranty"] = "N/A (Standard 14-day Myntra return policy applies)"

    def _fix_specifications_and_about(self, item: dict) -> None:
        specs = {}
        about_items = []
        description = ""

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                
                # Parse spec rows: div.index-row
                rows = soup.select("div.index-row")
                for row in rows:
                    key_el = row.select_one("div.index-rowKey")
                    val_el = row.select_one("div.index-rowValue")
                    if key_el and val_el:
                        k = key_el.get_text().strip()
                        v = val_el.get_text().strip()
                        if k and v:
                            specs[k] = v
                
                # Also check pdp-product-description-content or pdp-product-detail
                desc_container = soup.select_one(".pdp-product-description-content, .pdp-product-detail")
                if desc_container:
                    desc_text = desc_container.get_text().strip()
                    desc_text = re.sub(r'\s+', ' ', desc_text)
                    if not description:
                        description = desc_text
                    
                    # Extract list items/paragraphs for highlights
                    bullets = desc_container.select("li, p")
                    for b in bullets:
                        b_text = b.get_text().strip()
                        if b_text and len(b_text) > 10 and len(b_text) < 150:
                            about_items.append(b_text)
                        
                    if not about_items:
                        # Split description by period or newline
                        sentences = [s.strip() for s in re.split(r'\.|\n|•', desc_text) if len(s.strip()) > 15]
                        about_items = sentences[:5]
            except Exception as e:
                self.log(f"Error parsing specifications and about: {e}")
        
        # Clean brand if specified in specs
        for k, v in specs.items():
            if k.lower() == "brand" or k.lower() == "manufacturer":
                item["brand"] = v

        item["specifications"] = specs
        if not about_items:
            about_items = ["Standard fashion/lifestyle product from Myntra."]
        item["about_items"] = about_items[:10]  # Limit to 10 highlights
        if not description:
            description = "No description available."
        item["description"] = description
