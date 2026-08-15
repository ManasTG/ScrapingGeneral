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
