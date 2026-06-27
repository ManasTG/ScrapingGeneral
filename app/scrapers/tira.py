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
    BASE_URL = "https://www.tirabeauty.com"
    SELECTORS = {
        # ── Search page ──────────────────────────────────────────────────────
        "product_container": ".gridItem--yQFgq",
        "title": ".productName--Ys8wX, h3",
        "link": "a[href*='/product/']",
        "price": ".productCartPrice--vLCUm, .discountPrice--G5FvG",
        "rating": ".avgRating--wH8mU",
        "reviews_count": ".ratingCount--RAu2n",
        "image": "img.image--tXts_",

        # ── Detail page ──────────────────────────────────────────────────────
        "detail_title": ".productTitleContainer--XeDzj h1, h1",
        "detail_brand": ".productBrand--_gf_p, .brandName--Wv_F8",
        "detail_specs_table": ".pdpTable--fOX8q",
        "detail_about": ".accordionContent--Mioyy.productDescription--aYlfh .htmlContent--eDD85",
        "detail_description": ".accordionContent--Mioyy.productDescription--aYlfh .htmlContent--eDD85",
        "detail_price": ".productPrice--i0c7o .currentAmount--BpSjQ, .priceContainer--j_xK4 .sellingPrice--p93n2",
        "detail_rating": ".tira-feedback-service-average-rating-section",
        "detail_reviews_count": ".tira-feedback-service-average-rating-total-reviews",
        "detail_image": ".pdpImage--TIFEB, img.image--tXts_",
        "detail_seller": ".soldByWrapper--ASa1S",
    }

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting Tira Scraper for query: '{search_query}' (limit: {limit})")
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
            search_url = f"{url.rstrip('/')}/products/?q={urllib.parse.quote(search_query)}"
            
            # Close popups on initial load if any
            try:
                self.close_popups()
            except Exception as e:
                self.log(f"Error closing popups: {str(e)}")

            target_listings = self._collect_listings_with_pagination(selectors, search_query, limit, initial_url=search_url)
            self.log(f"Selected {len(target_listings)} listings for details page parsing.")
            
            # Detail Scraping phase
            for idx, item in enumerate(target_listings):
                self.check_cancelled(results)
                prod_idx = idx + 1
                self.log(f"[{prod_idx}/{len(target_listings)}] Navigating to details page: {item['title'][:40]}...")
                
                try:
                    self.driver.get(item["url"])
                    time.sleep(2.5)  # Delay between requests
                    
                    # Expand accordions (Product Description, Details, etc.)
                    try:
                        headers = self.driver.find_elements(By.CSS_SELECTOR, "button[class*='accordionHeaderWrapper']")
                        for header in headers:
                            try:
                                self.driver.execute_script("arguments[0].click();", header)
                            except Exception:
                                pass
                        time.sleep(0.5)
                    except Exception as e:
                        self.log(f"Could not expand accordion: {str(e)}")
                    
                    # Save HTML
                    detail_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                    
                    # Specs table parsing
                    specs = {}
                    tables = detail_soup.select(selectors["detail_specs_table"])
                    for table in tables:
                        key_el = table.select_one(".prop--etp3L")
                        val_el = table.select_one(".val--WS0aD")
                        if key_el and val_el:
                            key = key_el.get_text().strip().rstrip(":")
                            val = val_el.get_text().strip()
                            if key and val:
                                specs[key] = val
                                
                    # General sibling key-value fallback
                    if len(specs) < 2:
                        for tr in detail_soup.find_all("tr"):
                            cols = tr.find_all(["td", "th"])
                            if len(cols) == 2:
                                k = cols[0].get_text().strip().rstrip(":")
                                v = cols[1].get_text().strip()
                                if k and v:
                                    specs[k] = v
                                    
                    # Extract brand
                    brand = None
                    brand_elem = detail_soup.select_one(selectors["detail_brand"])
                    if brand_elem:
                        brand = brand_elem.get_text().strip()
                        
                    # About / Highlights
                    about_items = []
                    about_content = detail_soup.select_one(selectors["detail_about"])
                    if about_content:
                        # Extract list items if present
                        bullets = about_content.select("li, p")
                        for bullet in bullets:
                            txt = bullet.get_text().strip()
                            if txt and 10 < len(txt) < 150:
                                about_items.append(txt)
                                
                    # Description
                    desc_elem = detail_soup.select_one(selectors["detail_description"])
                    description = desc_elem.get_text().strip() if desc_elem else None
                    
                    # Seller
                    seller = None
                    seller_elem = detail_soup.select_one(selectors["detail_seller"])
                    if seller_elem:
                        seller = seller_elem.get_text().strip()
                        
                    item["brand"] = brand or "Unknown"
                    item["specifications"] = specs
                    item["about_items"] = about_items
                    item["description"] = description
                    item["seller"] = seller or "Unknown"
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
            # Match number in ratings/reviews string
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

        html_str = item.get("_html")
        if html_str:
            try:
                soup = BeautifulSoup(html_str, "html.parser")
                sold_by_el = soup.select_one(self.SELECTORS["detail_seller"])
                if sold_by_el:
                    txt = sold_by_el.get_text().strip()
                    item["seller"] = re.sub(r'(?i)^sold\s+by\s*:\s*', '', txt).strip()
                    return
            except Exception:
                pass

        item["seller"] = "RELIANCE RETAIL LIMITED"

    def _fix_warranty(self, item: dict) -> None:
        item["warranty"] = "N/A (Standard cosmetic/personal care product return policy apply)"

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
                        key_el = row.select_one(".prop--etp3L")
                        val_el = row.select_one(".val--WS0aD")
                        if key_el and val_el:
                            k = key_el.get_text().strip().rstrip(":")
                            v = val_el.get_text().strip()
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
            about_items = ["Standard personal care product from Tira."]
        item["about_items"] = about_items[:10]
        if not description:
            description = "No description available."
        item["description"] = re.sub(r'\s+', ' ', description).strip()
