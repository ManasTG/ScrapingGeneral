import os

# Database Config
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASES_DIR = os.path.join(BASE_DIR, "Databases")
os.makedirs(DATABASES_DIR, exist_ok=True)

# Auto-migrate existing database files from root to Databases/ if they exist
for file_name in os.listdir(BASE_DIR):
    if file_name.endswith(".db"):
        old_path = os.path.join(BASE_DIR, file_name)
        new_path = os.path.join(DATABASES_DIR, file_name)
        if os.path.isfile(old_path):
            try:
                import shutil
                if os.path.exists(new_path):
                    # Remove the blank new file if it exists to allow overwriting with the populated old DB
                    os.remove(new_path)
                shutil.move(old_path, new_path)
                print(f"Successfully migrated {file_name} to Databases/ folder")
            except Exception as e:
                print(f"Failed to migrate database file {file_name}: {e}")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(DATABASES_DIR, 'scraper.db')}")


# Selenium Config
DEFAULT_HEADLESS = True
SELENIUM_TIMEOUT = 15  # seconds
PAGE_LOAD_TIMEOUT = 30  # seconds

# User Agent Rotation Pool
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
]

# Website Selectors (Legacy Fallback)
WEBSITE_SELECTORS = {
    "amazon": {
        "product_container": "div[data-component-type='s-search-result'], div.s-result-item",
        "title": "h2 a, h2 span, h3 a, h3 span",
        "link": "h2 a, h3 a, a[href*='/dp/']",
        "price": ".a-price-whole, span.a-price-whole",
        "rating": "span.a-icon-alt",
        "reviews_count": "span.a-size-base.s-underline-text, span.a-size-base",
        "image": "img.s-image"
    },
    "generic": {
        "product_container": "div[class*='product'], div[class*='item'], div[class*='card']",
        "title": "h2, h3, h4, a[class*='title'], [class*='name']",
        "link": "a[href*='/product/'], a[href*='/p/'], a[href*='/item/'], a[href*='/dp/']",
        "price": "[class*='price'], span[class*='price']",
        "rating": "[class*='rating'], span[class*='rating']",
        "reviews_count": "[class*='review'], span[class*='review']",
        "image": "img[class*='image'], img[class*='product']"
    }
}

