import time
import re
import urllib.parse
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from app.scrapers.base import BaseScraper


class Scraper(BaseScraper):
    BASE_URL = "https://www.bigbasket.com"
    SELECTORS = {
        # ── Search page ──────────────────────────────────────────────────────
        "search_input": (
            "header:not(.fixed) input[placeholder='Search for Products...'], "
            "header.fixed input[placeholder='Search for Products...'], "
            "div:has(use[href*='search']) input, "
            "div.sc-bJBgwP.bnLeCx input, "
            "svg + input[placeholder='Search for Products...'], "
            "input[placeholder='Search for Products...']"
        ),
        "search_submit": (
            "button[type='submit'], button[aria-label*='Search']"
        ),
        "product_container": (
            "div[class*='SKUDeck___StyledDiv'], "
            "li:has(div[class*='SKUDeck']), div[class*='product-card']"
        ),
        "title": "h3.line-clamp-2, h3, h4",
        "link": "a[href*='/pd/']",
        "price": (
            "div[class*='gap-0.5'] span:not([class*='Pricing___StyledLabel'])"
            ":not([class*='Tags___StyledLabel']), span[class*='Pricing___StyledLabel']"
        ),
        "rating": "div:has(span[class*='ReviewsAndRatings___StyledLabel']) span:first-child",
        "reviews_count": "span[class*='ReviewsAndRatings___StyledLabel']",
        "image": "img[class*='DeckImage___StyledImage'], img[class*='Image']",

        # ── Detail page ──────────────────────────────────────────────────────
        "detail_title": "h1",
        "detail_brand": "section a[href*='/pb/'], a[href*='/pb/']",
        "detail_specs_table": "table",  # Fallback
        "detail_about": "div[class*='sc-fbKhjd']",
        "detail_description": "div[class*='sc-fbKhjd']",
        "detail_price": (
            "section table tr[class*='font-bold'] td:first-child, "
            "span[class*='Pricing___StyledLabel']"
        ),
        "detail_rating": "div:has(span[class*='ReviewsAndRatings___StyledLabel']) span:first-child",
        "detail_reviews_count": "span[class*='ReviewsAndRatings___StyledLabel']",
        "detail_image": (
            "section[class*='Image___StyledSection'] > div.w-full.flex.relative "
            "> div:nth-child(2) img, section[class*='Image___StyledSection'] img"
        ),
    }

    def init_driver(self) -> None:
        super().init_driver()
        if self.driver:
            try:
                self.log("Maximizing browser window to desktop size...")
                self.driver.maximize_window()
                self.driver.set_window_size(1920, 1080)
            except Exception as e:
                self.log(f"Failed to set window size: {e}")

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting BigBasket Scraper for query: '{search_query}' (limit: {limit})")
        results = self._default_scrape_flow(self.BASE_URL, self.SELECTORS, search_query, limit)

        # Post-process each result with BigBasket-specific fixes
        for item in results:
            self._fix_title(item)
            self._fix_brand(item)
            self._fix_price(item)
            self._fix_rating_and_reviews(item)
            self._fix_image(item)
            self._fix_specifications_and_about(item)
            self._fix_seller_and_warranty(item)
            
            # Explicitly remove/set rating, reviews_count, and warranty to None
            item["rating"] = None
            item["reviews_count"] = None
            item["warranty"] = None
            
            # Remove temporary page HTML string to keep clean DB records
            item.pop("_html", None)

        return results

    def _fix_title(self, item: dict) -> None:
        title = item.get("title", "")
        # Remove any leading/trailing whitespace and clean up double spaces
        title = re.sub(r'\s+', ' ', title).strip()
        if title:
            item["title"] = title

    def _fix_brand(self, item: dict) -> None:
        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                # Look for brand link containing /pb/ (product brand)
                brand_link = soup.select_one('a[href*="/pb/"]')
                if brand_link:
                    brand_text = brand_link.get_text().strip()
                    if brand_text:
                        item["brand"] = brand_text
                        return
            except Exception as e:
                self.log(f"Error in _fix_brand: {e}")

        # Fallback to first word of title if brand is still empty or Unknown
        if not item.get("brand") or item["brand"] == "Unknown":
            title = item.get("title", "")
            if title:
                words = title.split()
                if words:
                    item["brand"] = words[0]

    def _fix_price(self, item: dict) -> None:
        price = item.get("price") or ""
        # Clean price string
        if price:
            # Extract rupee symbol and numbers
            m = re.search(r'(₹\s*\d+(?:,\d{3})*(?:\.\d{2})?)', price)
            if m:
                item["price"] = m.group(1).replace(" ", "")
                return

        # Fallback to detail page parsing
        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                # Check for detailed price element
                price_elem = soup.select_one('section table tr[class*="font-bold"] td')
                if price_elem:
                    price_text = price_elem.get_text().strip()
                    m = re.search(r'(₹\s*\d+(?:,\d{3})*(?:\.\d{2})?)', price_text)
                    if m:
                        item["price"] = m.group(1).replace(" ", "")
                        return

                # Check any span containing ₹
                for span in soup.find_all("span"):
                    txt = span.get_text().strip()
                    if "₹" in txt:
                        parent_classes = "".join(span.parent.get("class", [])) if span.parent else ""
                        classes = "".join(span.get("class", []))
                        if "line-through" not in classes and "line-through" not in parent_classes:
                            m = re.search(r'(₹\s*\d+(?:,\d{3})*(?:\.\d{2})?)', txt)
                            if m:
                                item["price"] = m.group(1).replace(" ", "")
                                return
            except Exception as e:
                self.log(f"Error in _fix_price: {e}")

    def _fix_rating_and_reviews(self, item: dict) -> None:
        rating = item.get("rating") or "N/A"
        reviews_count = item.get("reviews_count") or "0"

        # Try to parse from detail page HTML
        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")

                # Look for span containing "Ratings"
                rating_label = soup.find(string=re.compile(r'\bRatings\b', re.IGNORECASE))
                if rating_label:
                    parent = rating_label.parent
                    # On BB, parent has ratings and reviews counts
                    parent_text = parent.get_text().strip()

                    # Rating value: decimal number (e.g. 4.1) inside parent siblings or parent itself
                    m_val = re.search(r'([1-5]\.[0-9])', parent_text)
                    if m_val:
                        rating = m_val.group(1)
                    else:
                        # try to find first child span of parent
                        first_span = parent.find("span")
                        if first_span:
                            m_val = re.search(r'([1-5]\.[0-9])', first_span.get_text())
                            if m_val:
                                rating = m_val.group(1)

                    # Reviews count: e.g. "10326 Ratings & 562 Reviews"
                    m_rev = re.search(r'([\d,]+)\s*Reviews?', parent_text, re.IGNORECASE)
                    if m_rev:
                        reviews_count = m_rev.group(1).replace(",", "")
                    else:
                        # Fallback to ratings count
                        m_rat = re.search(r'([\d,]+)\s*Ratings?', parent_text, re.IGNORECASE)
                        if m_rat:
                            reviews_count = m_rat.group(1).replace(",", "")
            except Exception as e:
                self.log(f"Error in _fix_rating_and_reviews: {e}")

        # Clean rating
        if rating and rating != "N/A":
            m = re.search(r'([1-5]\.[0-9]|[1-5])', str(rating))
            if m:
                item["rating"] = m.group(1)
            else:
                item["rating"] = "N/A"
        else:
            item["rating"] = "N/A"

        # Clean reviews count
        if reviews_count:
            m = re.search(r'(\d+)', str(reviews_count).replace(",", ""))
            if m:
                item["reviews_count"] = m.group(1)
            else:
                item["reviews_count"] = "0"
        else:
            item["reviews_count"] = "0"

    def _fix_image(self, item: dict) -> None:
        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                img_elem = soup.select_one('section[class*="Image___StyledSection"] img')
                if img_elem:
                    img_url = img_elem.get("src") or img_elem.get("data-src")
                    if img_url:
                        item["image_url"] = urllib.parse.urljoin(item["url"], img_url)
            except Exception as e:
                self.log(f"Error in _fix_image: {e}")

    def _fix_specifications_and_about(self, item: dict) -> None:
        specs = {}
        about_items = []
        description = ""

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")

                # BigBasket uses accordion components like div[class*="sc-fbKhjd"]
                # Loop through spans that act as headers
                section_headers = [
                    "About the Product", "Nutritional Facts", "How to Use",
                    "Other Product Info", "Storage and Uses", "Benefits",
                    "Ingredients"
                ]

                for span in soup.find_all("span"):
                    text = span.get_text().strip()
                    if text in section_headers:
                        # Find closest parent container div
                        parent = span.find_parent("div")
                        if parent:
                            # Content div is a child of parent that does not contain title span itself, or next sibling div
                            content_div = None
                            for child in parent.children:
                                if child.name == "div" and span not in child.find_all(True) and child != span:
                                    content_div = child
                                    break

                            if not content_div:
                                # Fallback to sibling of parent
                                content_div = parent.find_next_sibling("div")

                            if content_div:
                                content_text = content_div.get_text().strip()
                                # Clean up CSS import references or script junk
                                content_text = re.sub(r'@import url\("[^\"]+"\);\s*', '', content_text)
                                content_text = re.sub(r'\s+', ' ', content_text).strip()

                                if text == "About the Product":
                                    description = content_text
                                    # Split by sentence to make bullet points
                                    sentences = [
                                        s.strip() for s in re.split(r'\.|\n', content_text)
                                        if len(s.strip()) > 10
                                    ]
                                    about_items.extend(sentences[:5])
                                else:
                                    specs[text] = content_text

            except Exception as e:
                self.log(f"Error in _fix_specifications_and_about: {e}")

        # Set values
        item["specifications"] = specs
        item["about_items"] = about_items if about_items else ["Premium grocery product from BigBasket."]
        item["description"] = description if description else "No description available."

    def _fix_seller_and_warranty(self, item: dict) -> None:
        item["seller"] = "BigBasket (Supermarket Grocery Supplies)"
        item["warranty"] = "N/A (FMCG / Grocery product)"
