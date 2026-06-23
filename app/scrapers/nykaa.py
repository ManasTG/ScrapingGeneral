import re
import urllib.parse
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from app.scrapers.base import BaseScraper


class Scraper(BaseScraper):
    BASE_URL = "https://www.nykaa.com"
    SELECTORS = {
        # ── Search page ──────────────────────────────────────────────────────
        "search_input": "input[name='search-suggestions-nykaa']",
        "search_submit": "input[name='search-suggestions-nykaa']",  # Pressed via ENTER fallback

        "product_container": (
            ".productWrapper, div[class*='productWrapper'], div.css-d5z3ih"
        ),
        "title": (
            ".productWrapper h2, .productWrapper h2.css-xrzmfa, "
            "div.css-xrzmfa, .productWrapper div[class*='title']"
        ),
        "link": (
            ".productWrapper a, .productWrapper a.css-qlopj4, "
            ".productWrapper a[href*='/p/']"
        ),
        "price": (
            ".productWrapper .css-111z9ua, .productWrapper .css-17x46n5, "
            ".productWrapper span[class*='price']"
        ),
        "rating": (
            ".productWrapper [aria-label*='rating'], "
            ".productWrapper div[class*='rating']"
        ),
        "reviews_count": (
            ".productWrapper [aria-label*='reviews'], "
            ".productWrapper span[class*='reviews']"
        ),
        "image": (
            ".productWrapper a img.css-11gn9r6, .productWrapper img, "
            ".productWrapper img[src*='catalog']"
        ),

        # ── Detail page ──────────────────────────────────────────────────────
        "detail_title": "h1.css-1gc4qee, h1",
        "detail_brand": "a[href*='/brands/'], .css-1d5wdox",
        "detail_specs_table": "table, .css-z3x9b4, table[class*='spec']",
        "detail_about": ".css-3k9ukm, #content-details, div[class*='description']",
        "detail_description": ".css-3k9ukm, #content-details, div[class*='description']",
        "detail_price": ".css-17yghil, .css-1jczs1a, span[class*='price']",
        "detail_rating": ".css-u2f8dr, [aria-label*='rating'], div[class*='rating']",
        "detail_reviews_count": ".css-u2f8dr, [aria-label*='reviews'], span[class*='review']",
        "detail_image": (
            ".productSelectedImage img, img[src*='/catalog/product/'], "
            "img[class*='product']"
        ),
        "detail_seller": ".css-1d5wdox, div[class*='seller']",

        # Reviews List selectors
        "detail_reviews_container": ".css-z7l7ua",
        "detail_review_rating": ".css-1132h24",
        "detail_review_title": ".css-tm4hnq",
        "detail_review_text": ".css-1n0nrdk",
        "detail_review_author": ".css-amd8cf",
        "detail_review_date": ".css-3zk3jq",
    }

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting Nykaa Scraper for query: '{search_query}' (limit: {limit})")
        results = self._default_scrape_flow(self.BASE_URL, self.SELECTORS, search_query, limit)

        # Post-process each result with Nykaa-specific fixes
        for item in results:
            self._fix_title(item)
            self._fix_rating(item)
            self._fix_reviews_count(item)
            self._fix_price(item)
            self._fix_brand(item)
            self._fix_seller(item)
            self._fix_warranty(item)
            self._fix_about_items_and_description(item)
            
            # Remove temporary page HTML string to keep clean DB records
            item.pop("_html", None)

        return results

    def _fix_title(self, item: dict) -> None:
        title = item.get("title", "")
        # Clean extra whitespace
        title = re.sub(r'\s+', ' ', title).strip()
        if title:
            item["title"] = title

    def _fix_rating(self, item: dict) -> None:
        rating = item.get("rating") or ""
        if not rating or rating == "N/A":
            # Extract from HTML if missing
            html_str = item.get("_html")
            if html_str:
                try:
                    soup = BeautifulSoup(html_str, "html.parser")
                    rating_elem = soup.select_one(".css-u2f8dr")
                    if rating_elem:
                        rating = rating_elem.get_text()
                except Exception:
                    pass

        if rating and rating != "N/A":
            # Match 4.3/5 or 4.3 out of 5 stars or just 4.3
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
                    rc_elem = soup.select_one(".css-u2f8dr")
                    if rc_elem:
                        rc = rc_elem.get_text()
                except Exception:
                    pass

        if rc:
            # Extract reviews count number, e.g. "14611 ratings & 3096 reviews"
            # Prefer matching reviews number
            m_rev = re.search(r'([\d,]+)\s*reviews?', str(rc), re.IGNORECASE)
            if m_rev:
                item["reviews_count"] = m_rev.group(1).replace(",", "")
                return
            m_rat = re.search(r'([\d,]+)\s*ratings?', str(rc), re.IGNORECASE)
            if m_rat:
                item["reviews_count"] = m_rat.group(1).replace(",", "")
                return
            # Match any first digit series
            m_digits = re.search(r'([\d,]+)', str(rc))
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
                for price_sel in [".css-17yghil", ".css-1jczs1a", ".css-111z9ua"]:
                    price_elem = soup.select_one(price_sel)
                    if price_elem:
                        price_text = price_elem.get_text().strip()
                        m = re.search(r'(₹\s*\d+(?:,\d{3})*(?:\.\d{2})?)', price_text)
                        if m:
                            item["price"] = m.group(1).replace(" ", "")
                            return
            except Exception:
                pass

    def _fix_brand(self, item: dict) -> None:
        # Default brand name parsing from title if not set
        brand = item.get("brand") or ""
        if brand and brand != "Unknown":
            # Remove any unwanted characters/lines
            brand = re.sub(r'\s+', ' ', brand).strip()
            item["brand"] = brand
            return

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                brand_link = soup.select_one("a[href*='/brands/']")
                if brand_link:
                    brand_text = brand_link.get_text().strip()
                    if brand_text:
                        item["brand"] = brand_text
                        return
            except Exception:
                pass

        # Specs lookup
        specs = item.get("specifications") or {}
        for k, v in specs.items():
            if k.lower() in ("brand", "brand name"):
                item["brand"] = v
                return

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
            item["seller"] = re.sub(r'(?i)^sold\s+by\s*:\s*', '', seller).strip()
            return

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                # Look for sold by text in the page
                sold_by_el = soup.find(string=re.compile(r'sold\s+by\s*:', re.IGNORECASE))
                if sold_by_el:
                    parent_text = sold_by_el.parent.get_text().strip()
                    m = re.search(r'(?i)sold\s+by\s*:\s*(.*)', parent_text)
                    if m:
                        item["seller"] = m.group(1).strip()
                        return
            except Exception:
                pass

        item["seller"] = "Nykaa E Retail Limited"

    def _fix_warranty(self, item: dict) -> None:
        # Cosmetics usually don't have warranties
        item["warranty"] = "N/A (Standard cosmetic/personal care product return policy apply)"

    def _fix_about_items_and_description(self, item: dict) -> None:
        about = item.get("about_items") or []
        description = item.get("description") or ""

        # Clean highlights/about list
        cleaned_about = []
        for line in about:
            line_clean = re.sub(r'\s+', ' ', line).strip()
            if line_clean and len(line_clean) > 8 and "javascript:" not in line_clean:
                cleaned_about.append(line_clean)

        # Clean description
        if description:
            description = re.sub(r'\s+', ' ', description).strip()

        # If empty description or about, extract from HTML if possible
        html_str = item.get("_html")
        if html_str and (not cleaned_about or not description):
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                content_details = soup.find(id="content-details")
                if content_details:
                    details_text = content_details.get_text().strip()
                    details_text = re.sub(r'\s+', ' ', details_text)
                    
                    if not description:
                        description = details_text
                    
                    if not cleaned_about:
                        # Split by period or bullet-points to populate highlights
                        sentences = [
                            s.strip() for s in re.split(r'\.|\n|•', details_text)
                            if len(s.strip()) > 15
                        ]
                        cleaned_about = sentences[:5]
            except Exception:
                pass

        if not cleaned_about:
            cleaned_about = ["Standard beauty care product from Nykaa."]

        if not description:
            description = "No description available."

        item["about_items"] = cleaned_about
        item["description"] = description
