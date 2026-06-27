import time
import re
import urllib.parse
import random
from typing import Dict, List, Any, Optional, Callable
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

from app.config import USER_AGENTS, SELENIUM_TIMEOUT, PAGE_LOAD_TIMEOUT

class ScrapeCancelledException(Exception):
    def __init__(self, message: str, results: list = None):
        super().__init__(message)
        self.results = results or []

class BaseScraper:
    PAGE_LOAD_STRATEGY = "normal"

    def __init__(self, job_id: str, headless: bool = True, log_callback: Optional[Callable[[str], None]] = None, is_cancelled_callback: Optional[Callable[[], bool]] = None):
        self.job_id = job_id
        self.headless = headless
        self.log_callback = log_callback or (lambda msg: print(f"[{job_id}] {msg}"))
        self.is_cancelled_callback = is_cancelled_callback
        self.driver = None

    def check_cancelled(self, results: list = None) -> None:
        if hasattr(self, "is_cancelled_callback") and self.is_cancelled_callback and self.is_cancelled_callback():
            raise ScrapeCancelledException("Scraping cancelled by user", results)

    def log(self, message: str) -> None:
        self.log_callback(message)

    def _get_domain(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc or parsed.path
        netloc = netloc.split(":")[0]  # Remove port if any
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc

    def _save_debug_screenshot(self, name: str) -> None:
        if self.driver:
            try:
                import os
                static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static")
                os.makedirs(static_path, exist_ok=True)
                file_path = os.path.join(static_path, f"{name}.png")
                self.driver.save_screenshot(file_path)
                self.log(f"Saved debug screenshot: static/{name}.png")
            except Exception as e:
                self.log(f"Failed to save debug screenshot: {str(e)}")

    def init_driver(self) -> None:
        self.log("Initializing ChromeDriver...")
        chrome_options = Options()
        chrome_options.page_load_strategy = getattr(self, "PAGE_LOAD_STRATEGY", "normal")
        
        if self.headless:
            chrome_options.add_argument("--headless=new")
        
        # Anti-bot detection measures
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        
        # Pick a random User-Agent
        user_agent = random.choice(USER_AGENTS)
        chrome_options.add_argument(f"user-agent={user_agent}")
        
        # Exclude switches to prevent detection
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            
            # Execute CDP command to override navigator.webdriver and user agent at network layer
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                }
            )
            self.driver.execute_cdp_cmd(
                "Network.setUserAgentOverride",
                {
                    "userAgent": user_agent
                }
            )
            
            self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            self.log("ChromeDriver initialized successfully.")
        except Exception as e:
            self.log(f"Failed to start ChromeDriver: {str(e)}")
            raise e

    def wait_for_element(self, selector: str, by=By.CSS_SELECTOR, timeout=SELENIUM_TIMEOUT) -> Any:
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        """Must be implemented by specific scraper subclasses."""
        raise NotImplementedError("Scraper subclass must implement scrape method")

    def close_popups(self) -> None:
        """Hook to close popups after loading the home page. Overridden by subclasses."""
        pass

    def _run_universal_heuristic(self, soup: BeautifulSoup, search_query: str) -> List[Dict[str, Any]]:
        self._save_debug_screenshot("universal_search_heuristic")
        all_links = soup.find_all("a", href=True)
        candidates = []
        
        # Extract query terms for relevance
        query_terms = [t.lower() for t in search_query.split()]
        
        for a in all_links:
            href = a["href"]
            # Skip common nav / non-product links
            if any(x in href.lower() for x in ["login", "signin", "signup", "register", "cart", "checkout", "account", "settings", "help", "faq", "about", "contact", "privacy", "terms", "javascript:", "logout"]):
                continue
                
            abs_url = urllib.parse.urljoin(self.driver.current_url, href)
            text = a.get_text().strip()
            
            # Parent element context
            parent = a.find_parent()
            parent_text = parent.get_text() if parent else ""
            
            # Heuristic score
            score = 0
            
            # 1. Contains search keywords
            if any(t in text.lower() or t in href.lower() for t in query_terms):
                score += 3
                
            # 2. Price nearby in parent text
            price_match = re.search(r'(?:[\$₹£€]\s?\d+(?:,\d{3})*(?:\.\d{2})?|\d+\s?(?:USD|EUR|INR|Rs))', parent_text)
            if price_match:
                score += 3
                
            # 3. Contains typical product link patterns
            if any(x in href.lower() for x in ["/product/", "/p/", "/item/", "/dp/", "/gp/", "/buy/", "/shop/"]):
                score += 2
                
            # 4. Length of text looks like title
            if 15 < len(text) < 120:
                score += 1
                
            # 5. Image nearby
            img_elem = None
            if parent:
                img_elem = parent.find("img") or (parent.find_parent() and parent.find_parent().find("img"))
            if img_elem:
                score += 2
                
            if score >= 3:
                # Extract price if found
                price = price_match.group(0) if price_match else None
                
                # Find image src
                img_url = None
                if img_elem:
                    img_url = img_elem.get("src") or img_elem.get("data-src")
                    img_url = urllib.parse.urljoin(self.driver.current_url, img_url) if img_url else None
                    
                candidates.append({
                    "title": text or "Product Link",
                    "url": abs_url,
                    "price": price,
                    "rating": "N/A",
                    "reviews_count": "0",
                    "image_url": img_url,
                    "score": score
                })
        
        # Sort candidates by score
        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        # Deduplicate based on URL
        seen_urls = set()
        listings = []
        for c in candidates:
            if c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                listings.append(c)
                
        return listings

    def _collect_listings_with_pagination(self, selectors: Dict[str, str], search_query: str, limit: int, initial_url: Optional[str] = None) -> List[Dict[str, Any]]:
        if initial_url:
            self.log(f"Navigating directly to search URL: {initial_url}...")
            self.driver.get(initial_url)
            time.sleep(3)
            
        listings = []
        page_num = 1
        max_pages = 5
        last_url = self.driver.current_url
        
        while len(listings) < limit and page_num <= max_pages:
            self.check_cancelled(listings)
            
            # Scroll down slowly to trigger lazy load elements
            self.log(f"Scrolling page {page_num} to load items...")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
            time.sleep(1.5)
            self.driver.execute_script("window.scrollTo(0, (document.body.scrollHeight / 3) * 2);")
            time.sleep(1.5)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
            
            self.check_cancelled(listings)
            # Parse search results page
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            self.log(f"Extracting product listings from page {page_num}...")
            
            page_listings = []
            containers = soup.select(selectors["product_container"])
            self.log(f"Found {len(containers)} raw product containers on page {page_num}.")
            
            # Fallback heuristic if no containers are found with predefined selectors
            if len(containers) == 0 or not any(container.select_one(selectors["title"]) for container in containers if container.select_one(selectors["title"])):
                self.log(f"Predefined selectors yielded 0 valid products on page {page_num}. Running universal search heuristic...")
                page_listings = self._run_universal_heuristic(soup, search_query)
            else:
                for container in containers:
                    try:
                        # Extract title and URL
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
                        product_url = urllib.parse.urljoin(self.driver.current_url, href)
                        
                        # Prevent duplicates
                        if any(l["url"] == product_url for l in page_listings):
                            continue
                        
                        # Extract price
                        price = None
                        if "price" in selectors:
                            price_elem = container.select_one(selectors["price"])
                            price = price_elem.get_text().strip() if price_elem else None
                        
                        # Extract rating
                        rating = None
                        if "rating" in selectors:
                            rating_elem = container.select_one(selectors["rating"])
                            rating = rating_elem.get_text().strip() if rating_elem else None
                        if not rating:
                            # Heuristic for rating in text
                            match = re.search(r'(\d\.\d)\s*(?:★|out of 5)', container.get_text())
                            if match:
                                rating = match.group(1)
                        
                        # Extract review count
                        reviews_count = None
                        if "reviews_count" in selectors:
                            reviews_elem = container.select_one(selectors["reviews_count"])
                            reviews_count = reviews_elem.get_text().strip() if reviews_elem else None
                        if not reviews_count:
                            # Heuristic for reviews count in text
                            match = re.search(r'(\d[\d,]*)\s*(?:Ratings|Reviews|\()', container.get_text())
                            if match:
                                reviews_count = match.group(1)
                        
                        # Extract image URL
                        image_url = None
                        if "image" in selectors:
                            image_elem = container.select_one(selectors["image"])
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
                        
                        brand = None
                        if "brand" in selectors:
                            brand_elem = container.select_one(selectors["brand"])
                            brand = brand_elem.get_text().strip() if brand_elem else None
                            
                        page_listings.append({
                            "title": title,
                            "url": product_url,
                            "price": price,
                            "rating": rating,
                            "reviews_count": reviews_count,
                            "image_url": image_url,
                            "brand": brand
                        })
                        
                    except Exception:
                        continue
            
            # Deduplicate across pages
            new_added = 0
            for item in page_listings:
                if not any(x["url"] == item["url"] for x in listings):
                    listings.append(item)
                    new_added += 1
            
            self.log(f"Collected {new_added} new items from page {page_num}. Total unique collected: {len(listings)}")
            
            if len(listings) >= limit:
                self.log(f"Target count {limit} reached or exceeded. Stopping search pagination.")
                break
                
            # Attempt next page navigation
            next_page_selectors = [
                "a.s-pagination-next", "a.s-pagination-item--next", "a[class*='s-pagination-next']", # Amazon
                "a._1LKq3z", "a[class*='_1LKq3z']", "a._3ANo7x", # Flipkart
                "a.next", "a[class*='next']", "li[class*='next'] a", # JioMart/Nykaa/Myntra/etc
                "a[aria-label*='Next']", "button[aria-label*='Next']",
                "//a[contains(text(), 'Next') or contains(text(), 'next') or contains(text(), 'NEXT')]",
                "//button[contains(text(), 'Next') or contains(text(), 'next') or contains(text(), 'NEXT')]",
                "//span[contains(text(), 'Next') or contains(text(), 'next') or contains(text(), 'NEXT')]/parent::a",
                "//span[contains(text(), 'Next') or contains(text(), 'next') or contains(text(), 'NEXT')]/parent::button"
            ]
            
            found_next = False
            for sel in next_page_selectors:
                try:
                    if sel.startswith("//"):
                        next_page_btn = self.driver.find_element(By.XPATH, sel)
                    else:
                        next_page_btn = self.driver.find_element(By.CSS_SELECTOR, sel)
                        
                    if next_page_btn and next_page_btn.is_displayed() and next_page_btn.is_enabled():
                        self.log(f"Found next page button via selector '{sel}'. Clicking...")
                        self.driver.execute_script("arguments[0].click();", next_page_btn)
                        found_next = True
                        page_num += 1
                        
                        # Wait for URL to change or wait for new container elements
                        try:
                            WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selectors["product_container"]))
                            )
                        except Exception:
                            time.sleep(3)
                            
                        if self.driver.current_url == last_url:
                            self.log("URL didn't change immediately, waiting extra 2s...")
                            time.sleep(2)
                            
                        last_url = self.driver.current_url
                        break
                except Exception:
                    continue
            
            if not found_next:
                self.log("No next page button found. Attempting additional scroll for infinite scroll...")
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2.5)
                page_num += 1

        # Score and limit results
        keywords = [kw.lower() for kw in search_query.split()]
        scored_listings = []
        for item in listings:
            score = sum(1 for kw in keywords if kw in item["title"].lower())
            scored_listings.append((score, item))
        
        # Sort by relevance score descending
        scored_listings.sort(key=lambda x: x[0], reverse=True)
        candidate_listings = [item for _, item in scored_listings]
        target_listings = candidate_listings[:limit]
        return target_listings

    def _default_scrape_flow(self, base_url: str, selectors: Dict[str, str], search_query: str, limit: int) -> List[Dict[str, Any]]:
        results = []
        try:
            self.check_cancelled(results)
            self.init_driver()
            
            url = base_url
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            
            domain = self._get_domain(url)
            
            self.log(f"Navigating to {url} (domain: {domain})...")
            self.driver.get(url)
            
            # Allow page to settle
            time.sleep(2)
            
            # Check for CAPTCHA
            page_source = self.driver.page_source
            if any(x in page_source.lower() for x in ["captcha", "robot check", "sorry, we just need to make sure you're not a robot"]):
                self.log("WARNING: CAPTCHA / robot check detected. Target website is blocking the headless request.")
                self._save_debug_screenshot("captcha_block")
                self.log("To solve this, try unchecking 'Headless Mode' in parameters.")
                time.sleep(5)
            
            # Close any popups before searching
            try:
                self.close_popups()
            except Exception as e:
                self.log(f"Error closing popups: {str(e)}")

            # Find and enter search query
            self.check_cancelled(results)
            self.log(f"Looking for search input using selector: '{selectors['search_input']}'")
            search_input = None
            for sel in selectors["search_input"].split(","):
                sel = sel.strip()
                try:
                    search_input = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                    )
                    if search_input:
                        break
                except Exception:
                    continue
            
            if not search_input:
                self.log("Search input not found using primary selectors. Trying fallback to any input type text/search...")
                try:
                    search_input = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//input[@type='text' or @type='search']"))
                    )
                except Exception:
                    self._save_debug_screenshot("no_search_input_found")
                    raise Exception("Could not locate search bar input on page.")

            self.log(f"Entering search query: '{search_query}'")
            search_input.clear()
            search_input.send_keys(search_query)
            time.sleep(1)
            
            self.check_cancelled(results)
            self.log("Submitting search form...")
            submit_btn = None
            for sel in selectors["search_submit"].split(","):
                sel = sel.strip()
                try:
                    submit_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                    )
                    if submit_btn:
                        break
                except Exception:
                    continue
            
            if submit_btn:
                submit_btn.click()
            else:
                self.log("Submit button not found. Sending Enter key...")
                search_input.send_keys(Keys.ENTER)
            
            # Wait for results to load
            self.log("Waiting for search results...")
            time.sleep(3)
            
            # Retrieve target listings using multi-page pagination / scrolling
            target_listings = self._collect_listings_with_pagination(selectors, search_query, limit)
            self.log(f"Selected {len(target_listings)} listings matching search criteria for detail scraping.")
            
            if not target_listings:
                self.log("No matching items found.")
                return []
            
            # Detail Scraping phase
            for idx, item in enumerate(target_listings):
                self.check_cancelled(results)
                prod_idx = idx + 1
                self.log(f"[{prod_idx}/{len(target_listings)}] Navigating to details page: {item['title'][:40]}...")
                
                try:
                    self.driver.get(item["url"])
                    time.sleep(2)  # Delay between requests
                    
                    detail_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                    
                    # Detailed specifications parsing
                    specs = {}
                    tables = detail_soup.select(selectors["detail_specs_table"])
                    for table in tables:
                        for row in table.select("tr"):
                            cols = row.select("th, td")
                            if len(cols) >= 2:
                                key = cols[0].get_text().strip().replace("\n", "").replace("\t", "")
                                val = cols[1].get_text().strip().replace("\n", "").replace("\t", "")
                                key = re.sub(r'\s+', ' ', key)
                                val = re.sub(r'\s+', ' ', val)
                                if key and val:
                                    specs[key] = val
                    
                    # Fallback universal specs parser
                    if len(specs) < 3:
                        self.log("Fewer than 3 specs found via selectors. Running universal key-value parsing fallback...")
                        # Sibling key-value match for css-grid specifications (essential for Flipkart's div-based specs tables)
                        labels = detail_soup.select("div.col-3-12, div._2H3t1s, div[class*='label'], td[class*='label']")
                        for lbl in labels:
                            k = lbl.get_text().strip()
                            sibling = lbl.find_next_sibling()
                            if sibling:
                                v = sibling.get_text().strip()
                                if 2 < len(k) < 50 and 1 < len(v) < 250:
                                    k_clean = re.sub(r'\s+', ' ', k).rstrip(":")
                                    v_clean = re.sub(r'\s+', ' ', v)
                                    specs[k_clean] = v_clean

                        for dl in detail_soup.find_all("dl"):
                            dts = dl.find_all("dt")
                            dds = dl.find_all("dd")
                            for k_elem, v_elem in zip(dts, dds):
                                k = k_elem.get_text().strip().rstrip(":")
                                v = v_elem.get_text().strip()
                                if 2 < len(k) < 30 and 1 < len(v) < 120 and ":" not in v:
                                    specs[k] = v
                                    
                        for li in detail_soup.find_all("li"):
                            litext = li.get_text().strip()
                            if ":" in litext and not litext.startswith("http"):
                                parts = litext.split(":", 1)
                                k = parts[0].strip()
                                v = parts[1].strip()
                                if 2 < len(k) < 35 and 1 < len(v) < 150:
                                    specs[k] = v
                                    
                        for table in detail_soup.find_all("table"):
                            for tr in table.find_all("tr"):
                                cols = tr.find_all(["th", "td"])
                                if len(cols) == 2:
                                    k = cols[0].get_text().strip().rstrip(":")
                                    v = cols[1].get_text().strip()
                                    if 2 < len(k) < 35 and 1 < len(v) < 150 and ":" not in v:
                                        specs[k] = v
                    
                    # Extract brand
                    brand = None
                    for k, v in specs.items():
                        if k.lower() == "brand" or k.lower() == "manufacturer":
                            brand = v
                            break
                    
                    if not brand:
                        brand_byline = detail_soup.select_one("a#bylineInfo, a#brand")
                        if brand_byline:
                            brand_text = brand_byline.get_text().strip()
                            brand_text = re.sub(r'(?i)visit the\s+', '', brand_text)
                            brand_text = re.sub(r'(?i)\s+store', '', brand_text)
                            brand_text = re.sub(r'(?i)brand:\s*', '', brand_text)
                            brand = brand_text
                    
                    # Bullet points
                    about_items = []
                    bullets = detail_soup.select(selectors["detail_about"])
                    for bullet in bullets:
                        txt = bullet.get_text().strip()
                        if txt and len(txt) > 5:
                            about_items.append(txt)
                            
                    if len(about_items) == 0:
                        for li in detail_soup.find_all("li"):
                            txt = li.get_text().strip()
                            if len(txt) > 15 and not txt.startswith("http") and ":" not in txt:
                                about_items.append(txt)
                            if len(about_items) >= 5:
                                break
                    
                    # Description
                    desc_elem = detail_soup.select_one(selectors["detail_description"])
                    description = desc_elem.get_text().strip() if desc_elem else None
                    if not description:
                        paragraphs = [p.get_text().strip() for p in detail_soup.find_all("p")]
                        paragraphs = [p for p in paragraphs if len(p) > 50]
                        if paragraphs:
                            description = max(paragraphs, key=len)
                    
                    # Fallback details extraction (price, rating, reviews_count, image_url, title, brand)
                    if not item.get("price"):
                        price_sel = selectors.get("detail_price")
                        if price_sel:
                            price_elem = detail_soup.select_one(price_sel)
                            if price_elem:
                                item["price"] = price_elem.get_text().strip()
                                self.log(f"Extracted price from details page: {item['price']}")
                    
                    if not item.get("rating") or item.get("rating") == "N/A":
                        rating_sel = selectors.get("detail_rating")
                        if rating_sel:
                            rating_elem = detail_soup.select_one(rating_sel)
                            if rating_elem:
                                item["rating"] = rating_elem.get_text().strip()
                                self.log(f"Extracted rating from details page: {item['rating']}")
                        if not item.get("rating") or item.get("rating") == "N/A":
                            # Regex fallback on detail text
                            text_match = re.search(r'(\d\.\d)\s*★', detail_soup.get_text())
                            if text_match:
                                item["rating"] = text_match.group(1)
                                self.log(f"Extracted rating from detail page text: {item['rating']}")
                                
                    if not item.get("reviews_count") or item.get("reviews_count") == "0":
                        reviews_sel = selectors.get("detail_reviews_count")
                        if reviews_sel:
                            reviews_elem = detail_soup.select_one(reviews_sel)
                            if reviews_elem:
                                item["reviews_count"] = reviews_elem.get_text().strip()
                                self.log(f"Extracted reviews count from details page: {item['reviews_count']}")
                        if not item.get("reviews_count") or item.get("reviews_count") == "0":
                            # Regex fallback on detail text
                            text_match = re.search(r'(\d[\d,]*)\s*(?:Reviews|Ratings)', detail_soup.get_text(), re.IGNORECASE)
                            if text_match:
                                item["reviews_count"] = text_match.group(1)
                                self.log(f"Extracted reviews count from detail page text: {item['reviews_count']}")

                    if not item.get("image_url"):
                        img_sel = selectors.get("detail_image")
                        if img_sel:
                            img_elem = detail_soup.select_one(img_sel)
                            if img_elem:
                                img_url = None
                                for attr in ["src", "data-src", "data-original", "srcset"]:
                                    val = img_elem.get(attr)
                                    if val:
                                        if attr == "srcset":
                                            val = val.split(",")[0].strip().split(" ")[0]
                                        if not val.startswith("data:image/"):
                                            img_url = val
                                            break
                                if not img_url and img_elem.has_attr("src"):
                                    img_url = img_elem["src"]
                                if img_url:
                                    item["image_url"] = urllib.parse.urljoin(item["url"], img_url)
                                    self.log("Extracted image URL from details page.")

                    detail_title_sel = selectors.get("detail_title")
                    if detail_title_sel:
                        title_elem = detail_soup.select_one(detail_title_sel)
                        if title_elem:
                            d_title = title_elem.get_text().strip()
                            if d_title and (not item.get("title") or item["title"].endswith("...") or len(item["title"]) < len(d_title) - 10):
                                item["title"] = d_title
                                self.log(f"Updated title from details page: {d_title[:40]}...")

                    if (not brand or brand == "Unknown") and item.get("title"):
                        first_word = item["title"].split()[0]
                        if len(first_word) > 1 and first_word.isalnum():
                            brand = first_word

                    # Extract Seller
                    seller = None
                    seller_sel = selectors.get("detail_seller")
                    if seller_sel:
                        for s_sel in seller_sel.split(","):
                            s_sel = s_sel.strip()
                            try:
                                seller_elem = detail_soup.select_one(s_sel)
                                if seller_elem:
                                    seller = seller_elem.get_text().strip()
                                    if seller:
                                        break
                            except Exception:
                                continue
                    # Fallback for Seller
                    if not seller:
                        try:
                            # Use string instead of text to avoid deprecation warnings
                            seller_label = detail_soup.find(string=re.compile(r'Seller:?|Sold by:?', re.IGNORECASE))
                            if seller_label:
                                parent = seller_label.parent
                                parent_text = parent.get_text().strip()
                                match = re.search(r'(?:Seller|Sold by)\s*:?\s*([^.\n\r]+)', parent_text, re.IGNORECASE)
                                if match:
                                    seller_val = match.group(1).strip()
                                    # Clean up trailing "and fulfilled by..." or similar common suffixes
                                    seller_val = re.sub(r'(?i)\s+and\s+(?:fulfilled|ships|sent).*', '', seller_val)
                                    seller = seller_val.strip()
                                else:
                                    sibling = seller_label.find_next_sibling()
                                    if sibling:
                                        seller = sibling.get_text().strip()
                        except Exception:
                            pass
                    
                    # Extract Warranty
                    warranty = None
                    warranty_sel = selectors.get("detail_warranty")
                    if warranty_sel:
                        for w_sel in warranty_sel.split(","):
                            w_sel = w_sel.strip()
                            try:
                                w_elem = detail_soup.select_one(w_sel)
                                if w_elem:
                                    warranty = w_elem.get_text().strip()
                                    if warranty:
                                        break
                            except Exception:
                                continue
                    # Fallback for Warranty from specs
                    if not warranty and specs:
                        for k, v in specs.items():
                            if "warranty" in k.lower():
                                if k.lower() in ["warranty summary", "warranty", "domestic warranty"]:
                                    warranty = v
                                    break
                        if not warranty:
                            for k, v in specs.items():
                                if "warranty" in k.lower():
                                    warranty = f"{k}: {v}"
                                    break
                    # Fallback for Warranty from page text
                    if not warranty:
                        try:
                            warranty_label = detail_soup.find(string=re.compile(r'\b\d+\s*(?:year|month|yr|mon)s?\s*(?:manufacturer|brand)?\s*warranty\b', re.IGNORECASE))
                            if warranty_label:
                                warranty = warranty_label.strip()
                        except Exception:
                            pass

                    # Extract Reviews
                    reviews_list = []
                    reviews_container_sel = selectors.get("detail_reviews_container")
                    if reviews_container_sel:
                        try:
                            review_blocks = detail_soup.select(reviews_container_sel)
                            for block in review_blocks[:5]:  # Top 5 reviews
                                r_rating = "N/A"
                                r_rating_sel = selectors.get("detail_review_rating")
                                if r_rating_sel:
                                    r_rating_elem = block.select_one(r_rating_sel)
                                    if r_rating_elem:
                                        r_rating = r_rating_elem.get_text().strip()
                                
                                r_title = ""
                                r_title_sel = selectors.get("detail_review_title")
                                if r_title_sel:
                                    r_title_elem = block.select_one(r_title_sel)
                                    if r_title_elem:
                                        r_title = r_title_elem.get_text().strip()
                                
                                r_text = ""
                                r_text_sel = selectors.get("detail_review_text")
                                if r_text_sel:
                                    r_text_elem = block.select_one(r_text_sel)
                                    if r_text_elem:
                                        r_text = r_text_elem.get_text().strip()
                                
                                r_author = "Anonymous"
                                r_author_sel = selectors.get("detail_review_author")
                                if r_author_sel:
                                    r_author_elem = block.select_one(r_author_sel)
                                    if r_author_elem:
                                        r_author = r_author_elem.get_text().strip()
                                
                                r_date = ""
                                r_date_sel = selectors.get("detail_review_date")
                                if r_date_sel:
                                    r_date_elem = block.select_one(r_date_sel)
                                    if r_date_elem:
                                        r_date = r_date_elem.get_text().strip()
                                
                                # Fallback/adjust author & date for list structures
                                if r_author == "Anonymous" or not r_date:
                                    try:
                                        meta_elems = block.select("p._2sc7ZR, p[class*='author'], p[class*='name'], p[class*='date']")
                                        if len(meta_elems) >= 1 and r_author == "Anonymous":
                                            r_author = meta_elems[0].get_text().strip()
                                        if len(meta_elems) >= 2 and not r_date:
                                            r_date = meta_elems[1].get_text().strip()
                                    except Exception:
                                        pass
                                
                                if r_text or r_title:
                                    reviews_list.append({
                                        "rating": r_rating,
                                        "title": r_title,
                                        "text": r_text,
                                        "author": r_author,
                                        "date": r_date
                                    })
                        except Exception as e:
                            self.log(f"Error parsing reviews list: {str(e)}")

                    # Fallback review scraping (generic search for review cards)
                    if not reviews_list:
                        try:
                            # Search for elements with class containing 'review' or 'comment'
                            for block in detail_soup.select("div[class*='review'], div[class*='comment']"):
                                if len(reviews_list) >= 5:
                                    break
                                txt_elem = block.select_one("div[class*='text'], p[class*='text'], span[class*='text']")
                                if txt_elem:
                                    r_text = txt_elem.get_text().strip()
                                    if len(r_text) > 10 and not any(r["text"] == r_text for r in reviews_list):
                                        # Extract rating
                                        r_rating = "N/A"
                                        r_rating_elem = block.select_one("div[class*='rating'], span[class*='rating']")
                                        if r_rating_elem:
                                            r_rating = r_rating_elem.get_text().strip()
                                        reviews_list.append({
                                            "rating": r_rating,
                                            "title": "",
                                            "text": r_text,
                                            "author": "Anonymous",
                                            "date": ""
                                        })
                        except Exception:
                            pass

                    # Merge data
                    item["brand"] = brand or "Unknown"
                    item["specifications"] = specs
                    item["about_items"] = about_items
                    item["description"] = description
                    item["seller"] = seller or "Unknown"
                    item["warranty"] = warranty or "N/A"
                    item["reviews"] = reviews_list
                    item["_html"] = str(detail_soup)
                    
                    results.append(item)
                    self.log(f"[{prod_idx}/{len(target_listings)}] Successfully scraped item details.")
                    
                except Exception as ex:
                    self.log(f"Error scraping detail page {item['url']}: {str(ex)}")
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
