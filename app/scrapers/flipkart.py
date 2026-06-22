import time
from typing import List, Dict, Any
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.scrapers.base import BaseScraper

class Scraper(BaseScraper):
    BASE_URL = "https://www.flipkart.com"
    SELECTORS = {
        "search_input": "input[name='q'], input.Pke_EE, input[title*='Search']",
        "search_submit": "button[type='submit'], button._2iLD__, svg.r4151t",
        "product_container": "div._1AtVbE, div._7573G2, div.CGtC98, div.yKfJKb, div.slAV3a, div.gJG47c, [data-id], div[class*='productCard']",
        "title": "div._4rR01T, a.s1Q9rs, div.KzDlHZ, a[title], div._2WkVRV, a.wjcE2, a.IRpwTa",
        "link": "a[href*='/p/'], a.CGtC98, a._1fQZEK, a.s1Q9rs, a.rleRzy",
        "price": "div._30jeq3, div.Nx93Qx, div._25b18c, div.hl05eU, div.DyC4OI, [class*='price']",
        "rating": "div._3LWZlK, span.X1uhqq, div.X1uhqq, span.Y1tV3b, [class*='rating']",
        "reviews_count": "span._2_R_DZ, span.Wyu63M, span.Wyu63M, [class*='rating-reviews']",
        "image": "img._396csY, img._53u2t-, img.DByoEF, img._2r43zH, img",
        
        # Detail Page Selectors
        "detail_title": "span.B_NuCI, h1.G6XhYL, span.VU-ZEz",
        "detail_brand": "span.byline, div._1V6C56, tr.brand td, td:contains('Brand'), span.G1u1ci",
        "detail_specs_table": "table._14cfVK, div._1xp1A4, div.SpecificationTable, div.RygUYn, div._3k-BhJ",
        "detail_about": "div._2418aC ul li, li._21A30U, div._2o14nN ul li, div._2o14nN, div.description, div.yN-eZT, .x3G5OL li",
        "detail_description": "div._1mXVIV, div._2o14nN, div.description, div.yN-eZT, div._3la3Ad, div[class*='description']",
        
        # Seller and Warranty Details
        "detail_seller": "div#sellerName, span._3SGgDu, a._1RLNHA, div._3enr8x",
        "detail_warranty": "div.x3G5OL, div[class*='warranty']",
        
        # Customer Reviews Selectors
        "detail_reviews_container": "div.col._2w1f9X, div.col._2ZG37Z, div.col.EPCm5O, div._1AtVbE div[class*='review'], div[class*='col'] div[class*='review']",
        "detail_review_rating": "div._3LWZlK, div.X1uhqq, span.Y1tV3b, div[class*='rating']",
        "detail_review_title": "p._2-N1P8, p.z3A1nd, p.title, p[class*='title']",
        "detail_review_text": "div.t-y302, div._1gX497, div.ZmyZ1b, div[class*='review-text'], div.t-y302 div",
        "detail_review_author": "p._2sc7ZR, p._2sc7ZR._2V3Cno, p[class*='author'], p[class*='name']",
        "detail_review_date": "p._2sc7ZR:nth-child(2), p._2sc7ZR + p._2sc7ZR, p[class*='date']",
        
        # Detail Page Fallbacks
        "detail_price": "div.Nx93Qx, div._30jeq3, div.hl05eU, div.U1u1ci, div[class*='price']",
        "detail_rating": "div._3LWZlK, span.X1uhqq, div.X1uhqq, span.Y1tV3b, [class*='rating']",
        "detail_reviews_count": "span._2_R_DZ, span.Wyu63M, [class*='rating-reviews']",
        "detail_image": "img.DByoEF, img._396csY, img._2r43zH, img"
    }

    def close_popups(self) -> None:
        self.log("Checking for Flipkart login popup...")
        
        # Method 1: Send ESCAPE key to body
        try:
            self.log("Attempting to close login popup by sending ESCAPE key...")
            body = self.driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.ESCAPE)
            time.sleep(1)
        except Exception as e:
            self.log(f"Failed to send ESCAPE key to body: {e}")

        # Method 2: Click the close button if it exists using common xpath / css patterns
        popup_selectors = [
            (By.XPATH, "//button[contains(text(), '✕')]"),
            (By.XPATH, "//span[contains(text(), '✕')]"),
            (By.CSS_SELECTOR, "button._2KpZ6l._2doB4z"),
            (By.CSS_SELECTOR, "span._30XB9F"),
            (By.XPATH, "//button[text()='✕']"),
            (By.XPATH, "//span[text()='✕']"),
            (By.CSS_SELECTOR, "button[class*='_2doB4z']")
        ]
        
        for by, sel in popup_selectors:
            try:
                # Use a very short timeout since the popup is either already loaded or not there
                element = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((by, sel))
                )
                if element:
                    self.log(f"Found login popup close button via: {sel}")
                    element.click()
                    time.sleep(1)
                    return  # Success
            except Exception:
                continue
                
        self.log("No explicit login popup close button found/clicked, or already closed.")

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting Flipkart Scraper for query: '{search_query}' (limit: {limit})")
        return self._default_scrape_flow(self.BASE_URL, self.SELECTORS, search_query, limit)
