import os
import sys
import shutil
import random
import time
import re
import urllib.parse
from typing import Dict, List, Any, Optional, Callable
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Backward compatibility aliases
Service = ChromeService
Options = ChromeOptions
from app.config import WEBSITE_SELECTORS, USER_AGENTS, SELENIUM_TIMEOUT, PAGE_LOAD_TIMEOUT

class ScrapeCancelledException(Exception):
    def __init__(self, message: str, results: list = None):
        super().__init__(message)
        self.results = results or []

class ProductScraper:
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

    def _get_selectors(self, url: str) -> Dict[str, str]:
        # Match Amazon or other domains
        for key in WEBSITE_SELECTORS:
            if key in url:
                return WEBSITE_SELECTORS[key]
        return WEBSITE_SELECTORS["generic"]

    def _save_debug_screenshot(self, name: str) -> None:
        if self.driver:
            try:
                import os
                static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
                os.makedirs(static_path, exist_ok=True)
                file_path = os.path.join(static_path, f"{name}.png")
                self.driver.save_screenshot(file_path)
                self.log(f"Saved debug screenshot: static/{name}.png")
            except Exception as e:
                self.log(f"Failed to save debug screenshot: {str(e)}")

    def _find_firefox_binary(self) -> Optional[str]:
        candidates = [
            "/usr/bin/firefox-esr",
            "/usr/bin/firefox",
            "/opt/firefox/firefox",
            shutil.which("firefox-esr"),
            shutil.which("firefox"),
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Mozilla Firefox\firefox.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Mozilla Firefox\firefox.exe"),
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    def _find_geckodriver(self) -> Optional[str]:
        candidates = [
            "/usr/local/bin/geckodriver",
            "/usr/bin/geckodriver",
            shutil.which("geckodriver"),
            r"C:\Program Files\Mozilla Firefox\geckodriver.exe",
            r"C:\geckodriver\geckodriver.exe",
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    def _find_chrome_binary(self) -> Optional[str]:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/opt/chrome-linux64/chrome",
            "/opt/chrome/chrome",
            shutil.which("google-chrome"),
            shutil.which("chrome"),
            shutil.which("chromium"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    def _find_chromedriver(self) -> Optional[str]:
        candidates = [
            "/usr/bin/chromedriver",
            "/usr/local/bin/chromedriver",
            "/opt/chromedriver-linux64/chromedriver",
            shutil.which("chromedriver"),
            r"C:\chromedriver\chromedriver.exe",
            r"C:\Program Files\Google\Chrome\Application\chromedriver.exe",
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    def _init_firefox_driver(self) -> None:
        self.log("Checking for lightweight Firefox ESR (Gecko) browser...")
        
        # Immediate pre-check: ensure binary exists to prevent selenium-manager network hang
        firefox_binary = self._find_firefox_binary()
        if not firefox_binary:
            raise FileNotFoundError("Firefox/Firefox-ESR is not installed on this system.")
            
        self.log(f"Found Firefox binary at: {firefox_binary}")
        
        is_headless = self.headless
        if sys.platform.startswith("linux") and "DISPLAY" not in os.environ:
            is_headless = True

        # Set environment variables BEFORE creating the driver — critical for containers
        if is_headless:
            os.environ["MOZ_HEADLESS"] = "1"  # More reliable than -headless arg in ESR
        # Prevent crash reporter from hanging the process in headless/container envs
        os.environ["MOZ_CRASHREPORTER_DISABLE"] = "1"
        # Disable IPC shared-memory transport when /dev/shm is too small (common in containers)
        os.environ.setdefault("MOZ_DISABLE_CONTENT_SANDBOX", "1")
            
        firefox_options = FirefoxOptions()
        firefox_options.binary_location = firefox_binary
        firefox_options.page_load_strategy = "normal"
        
        if is_headless:
            firefox_options.add_argument("-headless")

        # Container-critical flags (fixes "Failed to read marionette port" in Docker/cloud)
        firefox_options.add_argument("--no-remote")     # Prevent IPC clashes in containers
        firefox_options.add_argument("--disable-gpu")   # No GPU in headless containers

        # Explicit tmp profile directory to avoid /tmp permission issues in some cloud envs
        import tempfile
        profile_dir = tempfile.mkdtemp(prefix="ff_profile_")
        firefox_options.add_argument(f"-profile")
        firefox_options.add_argument(profile_dir)
            
        # Low-memory optimizations for < 512MB RAM environments
        # 1. Block images at engine level to save ~60-70% RAM
        firefox_options.set_preference("permissions.default.image", 2)
        # 2. Block media streams, notifications, audio, geolocation
        firefox_options.set_preference("permissions.default.media_stream", 2)
        firefox_options.set_preference("permissions.default.desktop-notification", 2)
        firefox_options.set_preference("permissions.default.geo", 2)
        firefox_options.set_preference("media.autoplay.default", 5)
        firefox_options.set_preference("media.volume_scale", "0.0")
        
        # 3. Limit content processes (single IPC content process significantly saves RAM)
        firefox_options.set_preference("dom.ipc.processCount", 1)
        firefox_options.set_preference("browser.tabs.remote.separatePrivilegedContentProcess", False)
        # Disable Fission (site-isolation) to save memory and avoid multi-process issues
        firefox_options.set_preference("fission.autostart", False)
        
        # 4. Aggressive memory & cache management
        firefox_options.set_preference("browser.cache.disk.enable", False)
        firefox_options.set_preference("browser.cache.memory.enable", True)
        firefox_options.set_preference("browser.cache.memory.capacity", 4096)  # 4MB memory cache
        firefox_options.set_preference("browser.sessionhistory.max_entries", 2)
        firefox_options.set_preference("image.mem.decode_bytes_at_a_time", 4096)
        
        # 5. Disable WebGL & hardware acceleration
        firefox_options.set_preference("webgl.disabled", True)
        firefox_options.set_preference("layers.acceleration.disabled", True)
        firefox_options.set_preference("gfx.direct2d.disabled", True)

        # 6. Marionette connection stability — longer timeout for slow container starts
        firefox_options.set_preference("marionette.port", 0)  # Let OS pick a free port
        firefox_options.set_preference("toolkit.startup.max_resumed_crashes", -1)
        
        # Stealth & Anti-bot detection
        user_agent = random.choice(USER_AGENTS)
        firefox_options.set_preference("general.useragent.override", user_agent)
        firefox_options.set_preference("dom.webdriver.enabled", False)
        firefox_options.set_preference("useAutomationExtension", False)
        
        # Window size
        firefox_options.add_argument("--width=1280")
        firefox_options.add_argument("--height=720")
            
        # Detect pre-installed Geckodriver executable
        geckodriver_path = self._find_geckodriver()

        # Build Geckodriver service with extended connection timeout
        service_args = ["--log", "warn"]
        if geckodriver_path:
            self.log(f"Using pre-installed Geckodriver: {geckodriver_path}")
            service = FirefoxService(
                executable_path=geckodriver_path,
                service_args=service_args
            )
        else:
            service = FirefoxService(service_args=service_args)

        try:
            self.driver = webdriver.Firefox(service=service, options=firefox_options)
        except Exception as e:
            # Clean up temp profile on failure
            import shutil as _shutil
            try:
                _shutil.rmtree(profile_dir, ignore_errors=True)
            except Exception:
                pass
            raise e
            
        self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        self.log("Firefox ESR (Gecko) initialized successfully as primary browser.")

    def _init_chrome_driver(self) -> None:
        self.log("Initializing ChromeDriver (Chrome fallback)...")
        
        # Enforce headless mode in Linux environments without a display server
        is_headless = self.headless
        if sys.platform.startswith("linux") and "DISPLAY" not in os.environ:
            is_headless = True

        chrome_options = ChromeOptions()
        
        if is_headless:
            chrome_options.add_argument("--headless=new")
        
        # Anti-bot detection and container compatibility measures
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--window-size=1280,720")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--disable-infobars")
        
        # Memory-reduction optimizations for 512MB RAM environments
        chrome_options.add_argument("--js-flags=--max-old-space-size=128")
        chrome_options.add_argument("--renderer-process-limit=2")
        chrome_options.add_argument("--disk-cache-size=4096")
        chrome_options.add_argument("--media-cache-size=4096")
        chrome_options.add_argument("--disable-application-cache")
        chrome_options.add_argument("--aggressive-cache-discard")
        chrome_options.add_argument("--disable-features=Translate,OptimizationHints,MediaRouter,CalculateNativeWinOcclusion,InterestFeedContentSuggestions")

        # Block images and unnecessary media at browser engine level (saves 60-70% RAM)
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_setting_values.media_stream": 2,
            "profile.default_content_setting_values.geolocation": 2,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        # Pick a random User-Agent
        user_agent = random.choice(USER_AGENTS)
        chrome_options.add_argument(f"user-agent={user_agent}")
        
        # Exclude switches to prevent detection
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        # Detect Chrome binary if available
        chrome_binary = self._find_chrome_binary()
        if chrome_binary:
            self.log(f"Using Chrome binary at: {chrome_binary}")
            chrome_options.binary_location = chrome_binary

        # Detect pre-installed ChromeDriver executable
        chromedriver_path = self._find_chromedriver()

        try:
            if chromedriver_path:
                self.log(f"Using pre-installed ChromeDriver: {chromedriver_path}")
                service = ChromeService(executable_path=chromedriver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
            
            # Execute CDP command to override navigator.webdriver and user agent at network layer
            try:
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

                # Block heavy network resources (images, fonts, ads, trackers) via CDP Network blocking
                self.driver.execute_cdp_cmd("Network.enable", {})
                self.driver.execute_cdp_cmd("Network.setBlockedURLs", {
                    "urls": [
                        "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.svg", "*.ico",
                        "*.woff", "*.woff2", "*.ttf", "*.otf", "*.eot",
                        "*doubleclick.net*", "*google-analytics.com*", "*googletagmanager.com*",
                        "*facebook.net*", "*criteo.net*", "*amazon-adsystem.com*",
                        "*adnxs.com*", "*advertising*", "*analytics*", "*video*"
                    ]
                })
            except Exception:
                pass
            
            self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            self.log("ChromeDriver initialized successfully.")
        except Exception as e:
            self.log(f"Failed to start ChromeDriver: {str(e)}")
            raise e

    def init_driver(self) -> None:
        try:
            self._init_firefox_driver()
            return
        except Exception as fe:
            self.log(f"Firefox ESR not available or initialization skipped ({str(fe)}). Falling back immediately to Chrome...")
        
        try:
            self._init_chrome_driver()
        except Exception as ce:
            self.log(f"All browser initializations failed. Last error: {str(ce)}")
            raise ce

    def wait_for_element(self, selector: str, by=By.CSS_SELECTOR, timeout=SELENIUM_TIMEOUT) -> Any:
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_element_located((by, selector)) if hasattr(EC, 'presence_of_element_element_located') 
            else EC.presence_of_element_located((by, selector))
        )

    def scrape(self, website: str, search_query: str, limit: int) -> List[Dict[str, Any]]:
        results = []
        try:
            self.check_cancelled(results)
            self.init_driver()
            
            # Clean URL input
            url = website
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            
            domain = self._get_domain(url)
            selectors = self._get_selectors(url)
            
            self.log(f"Navigating to {url} (domain: {domain})...")
            self.driver.get(url)
            
            # Allow page to settle
            time.sleep(2)
            
            # Check for CAPTCHA
            page_source = self.driver.page_source
            if "captcha" in page_source.lower() or "robot check" in page_source.lower() or "sorry, we just need to make sure you're not a robot" in page_source.lower():
                self.log("WARNING: CAPTCHA / robot check detected. Amazon is blocking the headless request.")
                self._save_debug_screenshot("captcha_block")
                self.log("To solve this, try unchecking 'Headless Mode' in parameters, so you can solve the captcha in the window.")
                time.sleep(5)  # Wait in case of auto-solve or user solving in headful mode
            
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
                from selenium.webdriver.common.keys import Keys
                search_input.send_keys(Keys.ENTER)
            
            # Wait for results to load
            self.log("Waiting for search results...")
            time.sleep(3)
            
            # Scroll down slowly to trigger lazy load elements
            self.check_cancelled(results)
            self.log("Scrolling page to load items...")
            if "google" in domain and "maps" in url:
                self.log("Detected Google Maps. Scrolling the left-side feed sidebar...")
                for i in range(1, 6):
                    self.driver.execute_script(f"var feed = document.querySelector('div[role=\"feed\"]'); if(feed) feed.scrollTop = feed.scrollHeight * {i/5};")
                    time.sleep(1.5)
            else:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
                time.sleep(1.5)
                self.driver.execute_script("window.scrollTo(0, (document.body.scrollHeight / 3) * 2);")
                time.sleep(1.5)
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)
            
            self.check_cancelled(results)
            # Parse search results page
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            
            self.log("Extracting product listings from search results...")
            containers = soup.select(selectors["product_container"])
            self.log(f"Found {len(containers)} raw product containers.")
            
            listings = []
            
            # Fallback heuristic if no containers are found with predefined selectors
            if len(containers) == 0 or not any(container.select_one(selectors["title"]) for container in containers if container.select_one(selectors["title"])):
                self.log("Predefined selectors yielded 0 valid products. Initiating universal search heuristic...")
                self._save_debug_screenshot("universal_search_heuristic")
                
                # Get all links
                all_links = soup.find_all("a", href=True)
                candidates = []
                
                # Extract query terms for relevance
                query_terms = [t.lower() for t in search_query.split()]
                
                for a in all_links:
                    href = a["href"]
                    # Skip common nav / non-product links
                    if any(x in href.lower() for x in ["login", "signin", "signup", "register", "cart", "checkout", "account", "settings", "help", "faq", "about", "contact", "privacy", "terms", "javascript:", "logout"]):
                        continue
                        
                    abs_url = urllib.parse.urljoin(url, href)
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
                            img_url = urllib.parse.urljoin(url, img_url) if img_url else None
                            
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
                for c in candidates:
                    if c["url"] not in seen_urls:
                        seen_urls.add(c["url"])
                        listings.append(c)
                
                self.log(f"Universal heuristic identified {len(listings)} product candidate links.")
            else:
                for container in containers:
                    try:
                        # Skip sponsored listings on Amazon if possible, or scrape everything
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
                                # Try to find any link inside the container
                                link_elem = container.select_one("a[href]")
                        
                        if not link_elem or not link_elem.has_attr("href"):
                            continue
                            
                        href = link_elem["href"]
                        # Clean up URL
                        product_url = urllib.parse.urljoin(url, href)
                        
                        # Prevent duplicates
                        if any(l["url"] == product_url for l in listings):
                            continue
                        
                        # Extract price
                        price_elem = container.select_one(selectors["price"])
                        price = price_elem.get_text().strip() if price_elem else None
                        
                        # Extract rating
                        rating_elem = container.select_one(selectors["rating"])
                        rating = rating_elem.get_text().strip() if rating_elem else None
                        
                        # Extract review count
                        reviews_elem = container.select_one(selectors["reviews_count"])
                        reviews_count = reviews_elem.get_text().strip() if reviews_elem else None
                        
                        # Extract image URL
                        image_elem = container.select_one(selectors["image"])
                        image_url = None
                        if image_elem:
                            if image_elem.has_attr("src"):
                                image_url = image_elem["src"]
                            elif image_elem.has_attr("data-src"):
                                image_url = image_elem["data-src"]
                        
                        listings.append({
                            "title": title,
                            "url": product_url,
                            "price": price,
                            "rating": rating,
                            "reviews_count": reviews_count,
                            "image_url": image_url
                        })
                        
                    except Exception as e:
                        # Log error inside list extraction, but continue
                        continue

            
            # Select top results (matching the search query keyword e.g. "Dell")
            # Simple relevance scoring
            keywords = [kw.lower() for kw in search_query.split()]
            scored_listings = []
            for item in listings:
                score = sum(1 for kw in keywords if kw in item["title"].lower())
                scored_listings.append((score, item))
            
            # Sort by relevance score descending
            scored_listings.sort(key=lambda x: x[0], reverse=True)
            candidate_listings = [item for _, item in scored_listings]
            
            # Slice top candidate listings
            target_listings = candidate_listings[:limit]
            self.log(f"Selected {len(target_listings)} listings matching search criteria for detail scraping.")
            
            if not target_listings:
                self.log("No matching items found. Checking fallback selectors...")
                # If we couldn't parse listings properly, return empty or try a generic parse
                return []
            
            # Detail Scraping phase
            for idx, item in enumerate(target_listings):
                self.check_cancelled(results)
                prod_idx = idx + 1
                self.log(f"[{prod_idx}/{len(target_listings)}] Navigating to details page: {item['title'][:40]}...")
                
                try:
                    self.driver.get(item["url"])
                    
                    if "google" in domain and "maps" in item["url"]:
                        self.log("Waiting for Google Maps detail page to load...")
                        try:
                            # Wait for the Google Maps detail title or address button to be present
                            WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "h1.DUwDvf, button[data-item-id='address']"))
                            )
                        except Exception:
                            self.log("Timeout waiting for Google Maps detail page to load.")
                    
                    time.sleep(2)  # Delay between requests
                    
                    detail_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                    
                    if "google" in domain and "maps" in item["url"]:
                        self.log("Parsing place details for Google Maps...")
                        specs = {}
                        
                        # Extract Address
                        address_btn = detail_soup.select_one("button[data-item-id='address']")
                        if address_btn and address_btn.has_attr("aria-label"):
                            specs["Address"] = address_btn["aria-label"].replace("Address: ", "")
                        elif address_btn:
                            specs["Address"] = address_btn.get_text().strip()
                            
                        # Extract Phone Number
                        phone_btn = detail_soup.select_one("button[data-item-id*='phone:tel:']")
                        if phone_btn and phone_btn.has_attr("aria-label"):
                            specs["Phone"] = phone_btn["aria-label"].replace("Phone: ", "")
                        elif phone_btn:
                            specs["Phone"] = phone_btn.get_text().strip()
                            
                        # Extract Website
                        website_a = detail_soup.select_one("a[data-item-id='authority']")
                        if website_a and website_a.has_attr("href"):
                            specs["Website"] = website_a["href"]
                        elif website_a:
                            specs["Website"] = website_a.get_text().strip()
                            
                        # Extract Category (use as brand)
                        brand = "Unknown"
                        cat_elem = detail_soup.select_one("span.D72iN, button[class*='D72iN']")
                        if cat_elem:
                            brand = cat_elem.get_text().strip()
                            
                        about_items = []
                        description = "Google Maps Place Listing"
                    else:
                        # Detailed specifications parsing
                        specs = {}
                        tables = detail_soup.select(selectors["detail_specs_table"])
                        for table in tables:
                            for row in table.select("tr"):
                                cols = row.select("th, td")
                                if len(cols) >= 2:
                                    key = cols[0].get_text().strip().replace("\n", "").replace("\t", "")
                                    val = cols[1].get_text().strip().replace("\n", "").replace("\t", "")
                                    # Remove excessive spaces
                                    key = re.sub(r'\s+', ' ', key)
                                    val = re.sub(r'\s+', ' ', val)
                                    if key and val:
                                        specs[key] = val
                        
                        # Fallback universal specs parser (lists, dl, divs with colons)
                        if len(specs) < 3:
                            self.log("Fewer than 3 specs found via selectors. Running universal key-value parsing fallback...")
                            
                            # 1. Parse description lists dl
                            for dl in detail_soup.find_all("dl"):
                                dts = dl.find_all("dt")
                                dds = dl.find_all("dd")
                                for k_elem, v_elem in zip(dts, dds):
                                    k = k_elem.get_text().strip().rstrip(":")
                                    v = v_elem.get_text().strip()
                                    if 2 < len(k) < 30 and 1 < len(v) < 120 and ":" not in v:
                                        specs[k] = v
                                        
                            # 2. Parse list items (li) containing colons
                            for li in detail_soup.find_all("li"):
                                litext = li.get_text().strip()
                                if ":" in litext and not litext.startswith("http"):
                                    parts = litext.split(":", 1)
                                    k = parts[0].strip()
                                    v = parts[1].strip()
                                    # Length constraints to verify it's a metadata property row
                                    if 2 < len(k) < 35 and 1 < len(v) < 150:
                                        specs[k] = v
                                        
                            # 3. Parse tables generically (if they didn't match the selector)
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
                        # Try from specs first
                        for k, v in specs.items():
                            if k.lower() == "brand" or k.lower() == "manufacturer":
                                brand = v
                                break
                        
                        if not brand:
                            # Try selector
                            brand_elem = detail_soup.select_one(selectors["detail_title"])
                            brand_byline = detail_soup.select_one("a#bylineInfo, a#brand")
                            if brand_byline:
                                brand_text = brand_byline.get_text().strip()
                                # Clean "Brand: Dell" or "Visit the Dell Store"
                                brand_text = re.sub(r'(?i)visit the\s+', '', brand_text)
                                brand_text = re.sub(r'(?i)\s+store', '', brand_text)
                                brand_text = re.sub(r'(?i)brand:\s*', '', brand_text)
                                brand = brand_text
                        
                        # "About this item" bullet points
                        about_items = []
                        bullets = detail_soup.select(selectors["detail_about"])
                        for bullet in bullets:
                            txt = bullet.get_text().strip()
                            if txt and len(txt) > 5 and txt not in about_items:
                                about_items.append(txt)
                                
                        # Fallback bullet details from lists if empty
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
                            # Fallback to the longest paragraph in the page
                            paragraphs = [p.get_text().strip() for p in detail_soup.find_all("p")]
                            paragraphs = [p for p in paragraphs if len(p) > 50]
                            if paragraphs:
                                description = max(paragraphs, key=len)

                    
                    # Merge data
                    item["brand"] = brand or "Unknown"
                    item["specifications"] = specs
                    item["about_items"] = about_items
                    item["description"] = description
                    
                    results.append(item)
                    self.log(f"[{prod_idx}/{len(target_listings)}] Successfully scraped item details.")
                    
                except Exception as ex:
                    self.log(f"Error scraping detail page {item['url']}: {str(ex)}")
                    # Append item with whatever details we already have
                    item["brand"] = "Unknown"
                    item["specifications"] = {}
                    item["about_items"] = []
                    item["description"] = f"Failed to load details: {str(ex)}"
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
