import time
import json
import urllib.parse
from typing import List, Dict, Any, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from app.scrapers.base import BaseScraper, ScrapeCancelledException


class Scraper(BaseScraper):
    """
    Google Maps business/places scraper.

    search_query is expected to be the full search string including location, e.g.:
        "Coffee shops in Seattle, Washington, USA"
    """

    BASE_URL = "https://www.google.com/maps/search/"

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting Google Maps Scraper for query: '{search_query}' (limit: {limit})")
        results: List[Dict[str, Any]] = []

        try:
            self.init_driver()
            encoded = urllib.parse.quote_plus(search_query)
            url = f"{self.BASE_URL}{encoded}"
            self.log(f"Navigating to {url}")
            self.driver.get(url)
            time.sleep(4)

            # Accept consent dialog if present
            self._dismiss_consent()

            # Scroll results feed to load up to `limit` cards
            card_urls = self._collect_card_links(limit)
            self.log(f"Collected {len(card_urls)} place links to process.")

            for idx, card_info in enumerate(card_urls):
                self.check_cancelled(results)
                self.log(f"[{idx + 1}/{len(card_urls)}] Scraping details for: {card_info['title']}")
                try:
                    detail = self._scrape_place_detail(card_info)
                    results.append(detail)
                except Exception as e:
                    self.log(f"WARNING: Failed to scrape details for '{card_info['title']}': {e}")
                    # Still add minimal info from card listing
                    results.append({
                        "title": card_info.get("title", "Unknown"),
                        "url": card_info.get("url", ""),
                        "rating": card_info.get("rating", ""),
                        "reviews_count": card_info.get("reviews_count", ""),
                        "image_url": card_info.get("image_url", ""),
                        "brand": "",
                        "price": "",
                        "specifications": {},
                        "about_items": [],
                        "description": "",
                        "seller": "",
                        "warranty": "",
                        "reviews": [],
                    })

        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None

        self.log(f"Google Maps scraping finished. Total places scraped: {len(results)}")
        return results

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _dismiss_consent(self) -> None:
        """Click 'Accept all' / 'I agree' consent dialogs if present."""
        try:
            buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(., 'Accept all') or contains(., 'I agree') or contains(., 'Agree')]"
            )
            if buttons:
                buttons[0].click()
                time.sleep(2)
                self.log("Dismissed consent dialog.")
        except Exception:
            pass

    def _collect_card_links(self, limit: int) -> List[Dict[str, Any]]:
        """Scroll the results feed and collect up to `limit` place cards."""
        cards_info: List[Dict[str, Any]] = []
        seen_titles = set()
        max_scroll_attempts = max(30, limit * 3)
        scroll_count = 0

        while len(cards_info) < limit and scroll_count < max_scroll_attempts:
            self.check_cancelled(cards_info)
            scroll_count += 1

            cards = self.driver.find_elements(By.CSS_SELECTOR, "div.Nv2PK")
            for card in cards:
                if len(cards_info) >= limit:
                    break
                try:
                    link_el = card.find_element(By.CSS_SELECTOR, "a.hfpxzc")
                    title = link_el.get_attribute("aria-label") or "Unknown"
                    url = link_el.get_attribute("href") or ""

                    if title in seen_titles:
                        continue
                    seen_titles.add(title)

                    rating = ""
                    reviews_count = ""
                    image_url = ""

                    try:
                        rating_el = card.find_elements(By.CSS_SELECTOR, "span.MW4etd")
                        if rating_el:
                            rating = rating_el[0].text.strip()
                    except Exception:
                        pass

                    try:
                        rev_el = card.find_elements(By.CSS_SELECTOR, "span.UY7F9")
                        if rev_el:
                            reviews_count = rev_el[0].text.strip().replace("(", "").replace(")", "")
                    except Exception:
                        pass

                    try:
                        img_el = card.find_elements(By.CSS_SELECTOR, "img")
                        if img_el:
                            image_url = img_el[0].get_attribute("src") or ""
                    except Exception:
                        pass

                    cards_info.append({
                        "title": title,
                        "url": url,
                        "rating": rating,
                        "reviews_count": reviews_count,
                        "image_url": image_url,
                        "_element": link_el,
                    })

                except Exception:
                    continue

            if len(cards_info) >= limit:
                break

            # Scroll the feed panel to load more results
            try:
                feed = self.driver.find_elements(By.CSS_SELECTOR, "div[role='feed']")
                if feed:
                    self.driver.execute_script(
                        "arguments[0].scrollTop = arguments[0].scrollHeight", feed[0]
                    )
                    time.sleep(1.5)
                else:
                    break
            except Exception:
                break

            # Check for "You've reached the end" message
            try:
                end_msg = self.driver.find_elements(By.CSS_SELECTOR, "div.HlvSq, p.fontBodyMedium")
                if any("end of results" in el.text.lower() or "no more results" in el.text.lower() for el in end_msg):
                    self.log("Reached end of results feed.")
                    break
            except Exception:
                pass

        # Trim to limit
        return cards_info[:limit]

    def _scrape_place_detail(self, card_info: Dict[str, Any]) -> Dict[str, Any]:
        """Click a place card and extract details from the detail panel."""
        title = card_info.get("title", "Unknown")
        url = card_info.get("url", "")
        rating = card_info.get("rating", "")
        reviews_count = card_info.get("reviews_count", "")
        image_url = card_info.get("image_url", "")

        # Navigate directly to the place URL for reliability
        if url:
            self.driver.get(url)
            time.sleep(3)

        # ── Place name ──────────────────────────────────────────────────────
        try:
            h1_els = self.driver.find_elements(By.CSS_SELECTOR, "h1.DUwDvf, h1")
            if h1_els:
                fetched_title = h1_els[0].text.strip()
                if fetched_title:
                    title = fetched_title
        except Exception:
            pass

        # ── Category ────────────────────────────────────────────────────────
        category = ""
        try:
            cat_els = self.driver.find_elements(By.CSS_SELECTOR, "button.DkEaL")
            if cat_els:
                category = cat_els[0].text.strip()
        except Exception:
            pass

        # ── Rating ──────────────────────────────────────────────────────────
        if not rating:
            try:
                r_el = self.driver.find_elements(By.CSS_SELECTOR, "div.F7nice span[aria-hidden='true'], span.ceNzKf")
                if r_el:
                    rating = r_el[0].text.strip()
            except Exception:
                pass

        # ── Reviews count ───────────────────────────────────────────────────
        if not reviews_count:
            try:
                rv_el = self.driver.find_elements(By.CSS_SELECTOR, "div.F7nice span[aria-label*='reviews'], span[aria-label*='reviews']")
                if rv_el:
                    reviews_count = rv_el[0].text.strip().replace("(", "").replace(")", "")
            except Exception:
                pass

        # ── Address ──────────────────────────────────────────────────────────
        address = ""
        try:
            addr_el = self.driver.find_elements(By.CSS_SELECTOR, "button[data-item-id='address']")
            if addr_el:
                aria = addr_el[0].get_attribute("aria-label") or ""
                address = aria.replace("Address: ", "").strip()
        except Exception:
            pass

        # ── Phone ────────────────────────────────────────────────────────────
        phone = ""
        try:
            ph_el = self.driver.find_elements(By.CSS_SELECTOR, "button[data-item-id*='phone']")
            if ph_el:
                aria = ph_el[0].get_attribute("aria-label") or ""
                phone = aria.replace("Phone: ", "").strip()
        except Exception:
            pass

        # ── Website ─────────────────────────────────────────────────────────
        website = ""
        try:
            web_el = self.driver.find_elements(By.CSS_SELECTOR, "a[data-item-id='authority']")
            if web_el:
                website = web_el[0].get_attribute("href") or ""
        except Exception:
            pass

        # ── Plus code ────────────────────────────────────────────────────────
        plus_code = ""
        try:
            oloc_el = self.driver.find_elements(By.CSS_SELECTOR, "button[data-item-id='oloc']")
            if oloc_el:
                aria = oloc_el[0].get_attribute("aria-label") or ""
                plus_code = aria.replace("Plus code: ", "").strip()
        except Exception:
            pass

        # ── Price level ──────────────────────────────────────────────────────
        price_level = ""
        try:
            p_el = self.driver.find_elements(By.CSS_SELECTOR, "span[aria-label*='Price:']")
            if p_el:
                price_level = p_el[0].get_attribute("aria-label") or ""
                price_level = price_level.replace("Price: ", "").strip()
        except Exception:
            pass

        # ── Hours / Open status ──────────────────────────────────────────────
        hours_text = ""
        try:
            hours_el = self.driver.find_elements(By.CSS_SELECTOR, "div.t39EBf, span.ZDu9vd")
            if hours_el:
                hours_text = hours_el[0].get_attribute("aria-label") or hours_el[0].text or ""
                hours_text = hours_text.strip()
        except Exception:
            pass

        # ── Image (detail) ──────────────────────────────────────────────────
        if not image_url:
            try:
                img_el = self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Photo'] img, img.A512qc")
                if img_el:
                    image_url = img_el[0].get_attribute("src") or ""
            except Exception:
                pass

        # ── Reviews ─────────────────────────────────────────────────────────
        reviews_list = []
        try:
            review_cards = self.driver.find_elements(By.CSS_SELECTOR, "div.jftiEf")
            for rev_card in review_cards[:5]:
                try:
                    author_el = rev_card.find_elements(By.CSS_SELECTOR, "div.d4r55")
                    stars_el = rev_card.find_elements(By.CSS_SELECTOR, "span.kvMYJc")
                    body_el = rev_card.find_elements(By.CSS_SELECTOR, "span.wiI7fc, div.MyEned")
                    date_el = rev_card.find_elements(By.CSS_SELECTOR, "span.rsqaWe")

                    author = author_el[0].text.strip() if author_el else "Anonymous"
                    stars = stars_el[0].get_attribute("aria-label") if stars_el else ""
                    body = body_el[0].text.strip() if body_el else ""
                    date = date_el[0].text.strip() if date_el else ""

                    reviews_list.append({
                        "author": author,
                        "rating": stars,
                        "text": body,
                        "date": date,
                        "title": "",
                    })
                except Exception:
                    continue
        except Exception:
            pass

        # ── Build specifications dict ────────────────────────────────────────
        specs = {}
        if address:
            specs["Address"] = address
        if phone:
            specs["Phone"] = phone
        if website:
            specs["Website"] = website
        if plus_code:
            specs["Plus Code"] = plus_code
        if hours_text:
            specs["Hours"] = hours_text
        if category:
            specs["Category"] = category

        return {
            "title": title,
            "url": url,
            "price": price_level,
            "rating": rating,
            "reviews_count": reviews_count,
            "image_url": image_url,
            "brand": category,        # Category acts as "brand" in the table
            "specifications": specs,
            "about_items": [],
            "description": address,   # Address in description for quick reference
            "seller": address,
            "warranty": phone,        # Phone in warranty field for compactness
            "reviews": reviews_list,
        }
