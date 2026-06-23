"""
Run this standalone (no app imports needed) to see exactly what
Flipkart's search results page looks like to the scraper.

Usage:
    python flipkart_debug.py "laptop"
"""
import sys
import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

QUERY = sys.argv[1] if len(sys.argv) > 1 else "laptop"

# ---- Selectors to test ----
CONTAINER_SEL = (
    "div._1AtVbE, div._7573G2, div.CGtC98, div.yKfJKb, "
    "div.slAV3a, div.gJG47c, div[data-id], div[class*='productCard']"
)
TITLE_SEL = "div._4rR01T, a.s1Q9rs, div.KzDlHZ, div._2WkVRV, a.wjcE2, a.IRpwTa"
LINK_SEL  = "a[href*='/p/']"

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

driver = webdriver.Chrome(options=options)
driver.execute_cdp_cmd(
    "Page.addScriptToEvaluateOnNewDocument",
    {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
)

try:
    print(f"[1] Loading flipkart.com ...")
    driver.get("https://www.flipkart.com")
    time.sleep(2)

    # Dismiss popup
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.ESCAPE)
        time.sleep(0.8)
    except Exception:
        pass
    for by, sel in [
        (By.XPATH, "//button[contains(text(),'✕')]"),
        (By.CSS_SELECTOR, "button._2KpZ6l._2doB4z"),
        (By.CSS_SELECTOR, "button[class*='_2doB4z']"),
    ]:
        try:
            el = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((by, sel)))
            el.click()
            time.sleep(0.5)
            break
        except Exception:
            continue

    print(f"[2] Searching for '{QUERY}' ...")
    inp = WebDriverWait(driver, 8).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='q']"))
    )
    inp.clear()
    inp.send_keys(QUERY)
    inp.send_keys(Keys.ENTER)
    time.sleep(3)

    # Scroll
    for pct in (0.33, 0.66, 1.0):
        driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {pct});")
        time.sleep(1.2)

    driver.save_screenshot("/home/claude/debug_listing.png")
    print("[3] Screenshot saved: debug_listing.png")

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # ----- Test container selector -----
    containers = soup.select(CONTAINER_SEL)
    print(f"\n[4] Containers matched: {len(containers)}")

    # ----- Show which individual selectors matched -----
    for single_sel in CONTAINER_SEL.split(","):
        single_sel = single_sel.strip()
        n = len(soup.select(single_sel))
        print(f"     {single_sel!r:45s} → {n} matches")

    # ----- For the first 5 containers show title/link hits -----
    print(f"\n[5] Title selector hits inside containers:")
    title_hits = 0
    for i, c in enumerate(containers[:10]):
        t_el = c.select_one(TITLE_SEL)
        l_el = c.select_one(LINK_SEL)
        title_txt = t_el.get_text(strip=True)[:60] if t_el else "—"
        link_href = (l_el.get("href") or "")[:60] if l_el else "—"
        if t_el:
            title_hits += 1
        print(f"  Container {i+1}: title={title_txt!r}  link={link_href!r}")
    print(f"  Title selector matched in {title_hits}/10 containers")

    # ----- Dump first product link found anywhere on page -----
    all_product_links = soup.select("a[href*='/p/']")
    print(f"\n[6] Total a[href*='/p/'] links on page: {len(all_product_links)}")
    for a in all_product_links[:5]:
        parent_classes = " ".join(a.get("class") or [])
        txt = a.get_text(strip=True)[:50]
        print(f"  href={a['href'][:60]!r}  text={txt!r}  classes={parent_classes!r}")

    # ----- Dump classes of all divs that contain /p/ links -----
    print(f"\n[7] Parent div classes of first 5 product links:")
    for a in all_product_links[:5]:
        p = a.find_parent("div")
        if p:
            print(f"  div.class={p.get('class')}")

    # ----- Page source snippet -----
    page_text = driver.page_source
    print(f"\n[8] Page source length: {len(page_text)} chars")
    print(f"     Contains 'captcha': {'captcha' in page_text.lower()}")
    print(f"     Contains 'robot':   {'robot' in page_text.lower()}")
    print(f"     First 500 chars of <body>:")
    body_start = page_text.find("<body")
    print(page_text[body_start:body_start+500])

finally:
    driver.quit()
    print("\n[DONE]")
