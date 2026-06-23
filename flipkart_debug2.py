"""
Drill into div[data-id] > a.k7wcnx to find the exact title, price,
rating, image child elements with their current class names.
"""
import sys, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

QUERY = sys.argv[1] if len(sys.argv) > 1 else "laptop"

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
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
    {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"})

try:
    driver.get("https://www.flipkart.com")
    time.sleep(2)
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.5)
    except: pass
    for by, sel in [
        (By.XPATH, "//button[contains(text(),'✕')]"),
        (By.CSS_SELECTOR, "button[class*='_2doB4z']"),
    ]:
        try:
            WebDriverWait(driver, 2).until(EC.element_to_be_clickable((by, sel))).click()
            time.sleep(0.5); break
        except: continue

    inp = WebDriverWait(driver, 8).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='q']")))
    inp.clear(); inp.send_keys(QUERY); inp.send_keys(Keys.ENTER)
    time.sleep(3)
    for pct in (0.33, 0.66, 1.0):
        driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight*{pct});")
        time.sleep(1.2)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    containers = soup.select("div[data-id]")
    print(f"Containers (div[data-id]): {len(containers)}\n")

    for i, c in enumerate(containers[:3]):
        print(f"{'='*60}")
        print(f"CONTAINER {i+1}  data-id={c.get('data-id')}")
        print(f"  Container classes: {c.get('class')}")

        # All direct child divs with their classes
        print(f"  --- All child elements (tag + class) ---")
        for child in c.descendants:
            if hasattr(child, 'get') and child.get('class'):
                cls = ' '.join(child.get('class'))
                txt = child.get_text(strip=True)[:60]
                tag = child.name
                print(f"    <{tag} class='{cls}'> text={txt!r}")

        # Images
        print(f"  --- Images ---")
        for img in c.find_all("img"):
            print(f"    src={img.get('src','')[:80]!r}  data-src={img.get('data-src','')[:80]!r}  class={img.get('class')}")

        print()

finally:
    driver.quit()
    print("[DONE]")
