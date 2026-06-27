from typing import List, Dict, Any
from app.scrapers.base import BaseScraper

class Scraper(BaseScraper):
    BASE_URL = "https://www.amazon.in"
    SELECTORS = {
        "search_input": "input#twotabsearchtextbox, input[name='field-keywords']",
        "search_submit": "input#nav-search-submit-button, input[type='submit']",
        "product_container": "div[data-component-type='s-search-result'], div[data-asin]:not([data-asin='']), div.s-result-item",
        "title": "h2 a, h2 span, h3 a, h3 span, a.a-link-normal span.a-size-medium, a.a-link-normal span.a-size-base-plus",
        "link": "h2 a, h3 a, a[href*='/dp/'], a[href*='/gp/']",
        "price": ".a-price-whole, span.a-price-whole, .a-price span.a-offscreen",
        "rating": "span.a-icon-alt, i.a-icon-star span",
        "reviews_count": "span.a-size-base.s-underline-text, span.a-size-base, a.a-link-normal.s-underline-text",
        "image": "img.s-image, img[data-image-latency]",
        
        # Detail Page Selectors
        "detail_title": "span#productTitle, h1#title",
        "detail_brand": "a#bylineInfo, tr.brand td.value, #bylineInfo",
        "detail_specs_table": "table#productDetails_techSpec_section_1, div#prodDetails table, table.prodDetSectionEntry, table[class*='spec']",
        "detail_about": "div#feature-bullets ul li span.a-list-item, #feature-bullets ul li",
        "detail_description": "div#productDescription p, div#productDescription span, #productDescription",
        "detail_seller": "#sellerProfileTriggerId, #merchant-info a, div#merchant-info, [data-field='merchant-name'] a, [data-field='merchant-name']"
    }

    def scrape(self, search_query: str, limit: int) -> List[Dict[str, Any]]:
        self.log(f"Starting Amazon Scraper for query: '{search_query}' (limit: {limit})")
        return self._default_scrape_flow(self.BASE_URL, self.SELECTORS, search_query, limit)
