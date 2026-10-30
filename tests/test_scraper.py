import pytest
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup
from app.scrapers.base import BaseScraper
from app.scrapers.amazon import Scraper as AmazonScraper
from app.scrapers.flipkart import Scraper as FlipkartScraper
from app.scrapers.nykaa import Scraper as NykaaScraper
from app.scrapers.purplle import Scraper as PurplleScraper
from app.scrapers.tira import Scraper as TiraScraper
from app.scrapers.kult import Scraper as KultScraper
from app.scrapers.smytten import Scraper as SmyttenScraper
from app.scrapers.zepto import Scraper as ZeptoScraper
from app.scrapers.alibaba import Scraper as AlibabaScraper

# Mock HTML sample for search listing
SEARCH_PAGE_HTML = """
<div data-component-type="s-search-result" class="s-result-item">
    <div>
        <h2>
            <a class="a-link-normal" href="/dp/B0CXMSQ427">
                <span class="a-size-medium">Dell Inspiron 3520 Laptop, Intel Core i5-1235U</span>
            </a>
        </h2>
        <span class="a-price-whole">48,990</span>
        <span class="a-icon-alt">4.1 out of 5 stars</span>
        <span class="a-size-base s-underline-text">154</span>
        <img class="s-image" src="https://m.media-amazon.com/images/I/71c5W90xL.jpg" />
    </div>
</div>
<div data-component-type="s-search-result" class="s-result-item">
    <div>
        <h2>
            <a class="a-link-normal" href="/dp/B0C89P5K56">
                <span class="a-size-medium">Dell 14 Thin & Light Laptop, 12th Gen Intel Core i3</span>
            </a>
        </h2>
        <span class="a-price-whole">35,990</span>
        <span class="a-icon-alt">3.9 out of 5 stars</span>
        <span class="a-size-base s-underline-text">88</span>
        <img class="s-image" src="https://m.media-amazon.com/images/I/61H4hMhN.jpg" />
    </div>
</div>
"""

# Mock HTML sample for product detail page
DETAIL_PAGE_HTML = """
<span id="productTitle">Dell Inspiron 3520 Laptop, Intel Core i5-1235U</span>
<a id="bylineInfo" href="/Dell/pages/default">Brand: Dell</a>
<div id="sellerName"><span>Sold by: Appario Retail Private Ltd</span></div>
<table id="productDetails_techSpec_section_1">
    <tr>
        <th>Brand</th>
        <td>Dell</td>
    </tr>
    <tr>
        <th>Processor Type</th>
        <td>Core i5</td>
    </tr>
    <tr>
        <th>RAM Size</th>
        <td>8 GB</td>
    </tr>
    <tr>
        <th>Warranty Summary</th>
        <td>1 Year Manufacturer Warranty</td>
    </tr>
</table>
<div id="feature-bullets">
    <ul>
        <li><span class="a-list-item">Processor: Intel Core i5-1235U 12th Gen</span></li>
        <li><span class="a-list-item">RAM & Storage: 8GB DDR4, 512GB SSD</span></li>
    </ul>
</div>
<div id="productDescription">
    <p>This is a high performance Dell laptop suitable for study and daily usage.</p>
</div>
<div class="EPCm5O">
    <div class="_3LWZlK">5 ★</div>
    <p class="_2-N1P8">Excellent laptop</p>
    <div class="t-y302">Very fast boot times and good battery backup.</div>
    <p class="_2sc7ZR _2V3Cno">Sumit Kumar</p>
    <p class="_2sc7ZR">2 months ago</p>
</div>
"""

@patch.object(BaseScraper, "_find_firefox_binary", return_value="/usr/bin/firefox-esr")
@patch("selenium.webdriver.Firefox")
def test_firefox_driver_initialization(mock_firefox, mock_find_binary):
    """Test that Firefox ESR driver is initialized as primary browser with low-memory settings."""
    scraper = BaseScraper("test-job-123", headless=True)
    scraper._init_firefox_driver()
    
    assert mock_firefox.called
    options = mock_firefox.call_args[1]["options"]
    assert "-headless" in options.arguments
    assert options.preferences.get("permissions.default.image") == 2
    assert options.preferences.get("dom.ipc.processCount") == 1
    assert options.preferences.get("browser.cache.disk.enable") is False

@patch("selenium.webdriver.Chrome")
def test_driver_fallback_to_chrome(mock_chrome):
    """Test that when Firefox fails or is missing, it automatically falls back to Chrome."""
    scraper = BaseScraper("test-job-123", headless=True)
    scraper.init_driver()
    
    assert mock_chrome.called
    options = mock_chrome.call_args[1]["options"]
    assert "--headless=new" in options.arguments
    assert "--no-sandbox" in options.arguments

def test_scraper_url_and_selectors():
    """Test that individual scrapers are properly configured."""
    amazon = AmazonScraper("job-1")
    flipkart = FlipkartScraper("job-2")
    nykaa = NykaaScraper("job-3")
    purplle = PurplleScraper("job-4")
    tira = TiraScraper("job-5")
    kult = KultScraper("job-6")
    smytten = SmyttenScraper("job-7")
    zepto = ZeptoScraper("job-8")
    alibaba = AlibabaScraper("job-9")
    
    assert amazon.BASE_URL == "https://www.amazon.in"
    assert flipkart.BASE_URL == "https://www.flipkart.com"
    assert nykaa.BASE_URL == "https://www.nykaa.com"
    assert purplle.BASE_URL == "https://www.purplle.com"
    assert tira.BASE_URL == "https://www.tirabeauty.com"
    assert kult.BASE_URL == "https://kult.app"
    assert smytten.BASE_URL == "https://smytten.com"
    assert zepto.BASE_URL == "https://www.zepto.com"
    assert alibaba.BASE_URL == "https://www.alibaba.com"
    
    assert "search_input" in amazon.SELECTORS
    assert "search_input" in flipkart.SELECTORS
    assert "search_input" in nykaa.SELECTORS
    assert "search_input" in purplle.SELECTORS
    assert "product_container" in tira.SELECTORS
    assert "product_container" in kult.SELECTORS
    assert "product_container" in smytten.SELECTORS
    assert "product_container" in zepto.SELECTORS
    assert "product_container" in alibaba.SELECTORS

@patch("selenium.webdriver.Chrome")
def test_scraper_extracts_listings(mock_chrome):
    """Test that the listings extraction logic parses search result HTML correctly."""
    # Configure mock driver
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    driver_instance.page_source = SEARCH_PAGE_HTML
    driver_instance.current_url = "https://www.amazon.in"
    
    scraper = AmazonScraper("test-job-456", headless=True)
    
    # Run the scrape method using mocks for navigation and interaction
    with patch.object(scraper, "init_driver") as mock_init:
        scraper.driver = driver_instance
        
        # Mock navigation and explicit wait findings
        scraper.driver.get = MagicMock()
        scraper.wait_for_element = MagicMock()
        
        def mock_get(url):
            if "/dp/" in str(url) or "/gp/" in str(url) or "product" in str(url):
                driver_instance.page_source = DETAIL_PAGE_HTML
            else:
                driver_instance.page_source = SEARCH_PAGE_HTML
            
        driver_instance.get.side_effect = mock_get
        
        results = scraper.scrape("Dell Laptops", limit=2)
        
        assert len(results) == 2
        
        # Verify first item
        assert "Dell Inspiron 3520" in results[0]["title"]
        assert results[0]["price"] == "48,990"
        assert results[0]["rating"] == "4.1 out of 5 stars"
        assert results[0]["reviews_count"] == "154"
        assert results[0]["image_url"] == "https://m.media-amazon.com/images/I/71c5W90xL.jpg"
        
        # Verify second item
        assert "Dell 14 Thin" in results[1]["title"]
        
        # Verify parsed details specs
        assert results[0]["brand"] == "Dell"
        assert results[0]["specifications"]["Processor Type"] == "Core i5"
        assert results[0]["specifications"]["RAM Size"] == "8 GB"
        assert len(results[0]["about_items"]) == 2
        assert "Processor: Intel Core i5-1235U" in results[0]["about_items"][0]
        assert "daily usage" in results[0]["description"]
        
        # Verify newly added fields
        assert results[0]["seller"] == "Appario Retail Private Ltd"
        assert results[0]["warranty"] == "1 Year Manufacturer Warranty"
        assert len(results[0]["reviews"]) == 1
        assert results[0]["reviews"][0]["rating"] == "5 ★"
        assert results[0]["reviews"][0]["title"] == "Excellent laptop"
        assert results[0]["reviews"][0]["text"] == "Very fast boot times and good battery backup."
        assert results[0]["reviews"][0]["author"] == "Sumit Kumar"
        assert results[0]["reviews"][0]["date"] == "2 months ago"

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

@patch("selenium.webdriver.Chrome")
def test_flipkart_scraper_closes_popup(mock_chrome):
    """Test that Flipkart scraper attempts to close the login popup."""
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    # Mock finding elements and page source
    body_element = MagicMock()
    driver_instance.find_element.return_value = body_element
    driver_instance.page_source = "<html></html>"
    
    scraper = FlipkartScraper("test-job-789", headless=True)
    scraper.driver = driver_instance
    
    # Patch WebDriverWait so we don't actually wait or fail
    with patch("app.scrapers.flipkart.WebDriverWait") as mock_wait:
        # Mock element to be clickable to return a mock close button element
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        close_btn_elem = MagicMock()
        mock_wait_instance.until.return_value = close_btn_elem
        
        # Call close_popups directly
        scraper.close_popups()
        
        # Verify it tries to send ESCAPE key to body
        driver_instance.find_element.assert_called_with(By.TAG_NAME, "body")
        body_element.send_keys.assert_called_with(Keys.ESCAPE)
        
        # Verify it tries to find popup close button
        mock_wait.assert_called()
        close_btn_elem.click.assert_called()


@patch("selenium.webdriver.Chrome")
def test_scraper_cancellation(mock_chrome):
    """Test that scraper stops executing and raises ScrapeCancelledException when is_cancelled_callback returns True."""
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    # cancellation condition: first call False, subsequent calls True
    cancellation_states = [False, True]
    def check_cancel():
        return cancellation_states.pop(0) if cancellation_states else True
        
    scraper = AmazonScraper("test-job-cancel", headless=True, is_cancelled_callback=check_cancel)
    
    with patch.object(scraper, "init_driver") as mock_init:
        scraper.driver = driver_instance
        scraper.driver.get = MagicMock()
        scraper.wait_for_element = MagicMock()
        
        from app.scrapers.base import ScrapeCancelledException
        with pytest.raises(ScrapeCancelledException) as excinfo:
            scraper.scrape("Dell Laptops", limit=2)
            
        assert "cancelled by user" in str(excinfo.value)


FLIPKART_DETAIL_HTML = """
<div>
  <!-- Product Highlights Header -->
  <div>Product highlights</div>
  <div class="grid-formation">
    <div>AMD Ryzen 5 Quad Core</div>
  </div>
  <div class="grid-formation">
    <div>8 GB | 512 GB</div>
  </div>

  <!-- Dynamic Specs -->
  <div class="grid-formation-dynamic">
    <div>Processor Brand</div>
    <div>AMD</div>
  </div>
  <div class="grid-formation-dynamic">
    <div>Processor Name</div>
    <div>Ryzen 5 Quad Core</div>
  </div>

  <!-- Rating -->
  <div class="cg31wB">4.3 ★</div>

  <!-- Seller -->
  <div id="sellerName"><span>RetailNet</span></div>
</div>
"""

@patch("selenium.webdriver.Chrome")
def test_flipkart_scraper_extracts_correct_fields(mock_chrome):
    """Test that FlipkartScraper post-processing extracts and cleans up rating, seller, warranty, specifications and description."""
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    scraper = FlipkartScraper("test-job-fk-extract", headless=True)
    
    item = {
        "title": "DELL Laptop (8 Ratings & 3 Reviews)",
        "url": "https://www.flipkart.com/dell-laptop/p/itme",
        "price": "₹45,990",
        "rating": "N/A",
        "reviews_count": "N/A",
        "image_url": "img.png",
        "_html": FLIPKART_DETAIL_HTML
    }
    
    scraper._fix_title(item)
    scraper._fix_highlights(item)
    scraper._fix_specifications(item)
    scraper._fix_rating(item)
    scraper._fix_reviews_count(item)
    scraper._fix_seller(item)
    scraper._fix_warranty(item)
    scraper._fix_description(item)
    
    assert item["title"] == "DELL Laptop"
    assert "AMD Ryzen 5 Quad Core" in item["about_items"]
    assert "8 GB | 512 GB" in item["about_items"]
    assert item["specifications"]["Processor Brand"] == "AMD"
    assert item["specifications"]["Processor Name"] == "Ryzen 5 Quad Core"
    assert item["rating"] == "4.3"
    assert item["seller"] == "RetailNet"
    assert "Highlights:" in item["description"]
    assert "Specifications:" in item["description"]
    assert "Processor Brand: AMD" in item["description"]


NYKAA_DETAIL_HTML = """
<div id="content-details">
  This is an amazing sunscreen with SPF 50. Use daily for best protection.
  Ingredients: Niacinamide, Zinc PCA, CICA, Ceramides.
  How to Use: Apply on face.
</div>
"""

@patch("selenium.webdriver.Chrome")
def test_nykaa_scraper_extracts_correct_fields(mock_chrome):
    """Test that NykaaScraper post-processing extracts and cleans up rating, seller, warranty, specifications and description."""
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    scraper = NykaaScraper("test-job-nykaa-extract", headless=True)
    
    item = {
        "title": "WishCare Niacinamide Sunscreen (14611 ratings & 3096 reviews)",
        "url": "https://www.nykaa.com/wishcare-sunscreen/p/123",
        "price": "₹399",
        "rating": "4.3/5",
        "reviews_count": "14611 ratings & 3096 reviews",
        "image_url": "img.jpg",
        "specifications": {
            "Country of Origin": "India"
        },
        "_html": NYKAA_DETAIL_HTML
    }
    
    scraper._fix_title(item)
    scraper._fix_rating(item)
    scraper._fix_reviews_count(item)
    scraper._fix_price(item)
    scraper._fix_brand(item)
    scraper._fix_seller(item)
    scraper._fix_warranty(item)
    scraper._fix_about_items_and_description(item)
    
    assert item["title"] == "WishCare Niacinamide Sunscreen"
    assert item["rating"] == "4.3"
    assert item["reviews_count"] == "3096"
    assert item["price"] == "₹399"
    assert item["brand"] == "WishCare"
    assert item["seller"] == "Nykaa E Retail Limited"
    assert "Standard cosmetic" in item["warranty"]
    assert "sunscreen with SPF 50" in item["description"]
    assert "sunscreen with SPF 50" in item["about_items"][0]


PURPLLE_DETAIL_HTML = """
<div class="product-info">
    <h1>
        <span class="font-bold block lh-normal">DermDoc</span>
        <span class="block lh-normal">4% Niacinamide Sunscreen</span>
    </h1>
    <strong class="our-price">374</strong>
    <p class="star-rating">4.3★</p>
    <span class="text-rating">11576 Ratings</span>
</div>
<div class="inner-box">
    <div class="mb-2 flex gap-3 items-center">
        <span class="block text-sm font-semibold text-dark-secondary">Country of Origin</span>
        <span class="block text-sm text-black-50">India</span>
    </div>
</div>
<div class="accordion-collapse">
    This sunscreen offers broad spectrum protection. It is enriched with niacinamide.
    <ul>
        <li>Broad Spectrum SPF 50</li>
        <li>Prevents sun damage</li>
    </ul>
</div>
"""

@patch("selenium.webdriver.Chrome")
def test_purplle_scraper_extracts_correct_fields(mock_chrome):
    """Test that PurplleScraper post-processing extracts and cleans up rating, seller, warranty, specifications and description."""
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    scraper = PurplleScraper("test-job-purplle-extract", headless=True)
    
    item = {
        "title": "DermDoc 4% Niacinamide Sunscreen (11576 Ratings)",
        "url": "https://www.purplle.com/wishcare-sunscreen/p/123",
        "price": "₹374",
        "rating": "N/A",
        "reviews_count": "11576 Ratings",
        "image_url": "img.jpg",
        "specifications": {},
        "_html": PURPLLE_DETAIL_HTML
    }
    
    scraper._fix_title(item)
    scraper._fix_rating(item)
    scraper._fix_reviews_count(item)
    scraper._fix_price(item)
    scraper._fix_brand(item)
    scraper._fix_seller(item)
    scraper._fix_warranty(item)
    scraper._fix_specifications_and_about(item)
    
    assert item["title"] == "DermDoc 4% Niacinamide Sunscreen (11576 Ratings)"
    assert item["rating"] == "4.3"
    assert item["reviews_count"] == "11576"
    assert item["price"] == "₹374"
    assert item["brand"] == "DermDoc"
    assert item["seller"] == "Purplle Retailer"
    assert "Standard cosmetic" in item["warranty"]
    assert "Broad Spectrum SPF 50" in item["about_items"]
    assert "broad spectrum protection" in item["description"]


TIRA_DETAIL_HTML = """
<div class="productBrand--_gf_p">Tira</div>
<div class="productTitleContainer--XeDzj">
    <h1>Tira Deep Cleansing Mini Wipes (8 Pcs)</h1>
</div>
<div class="productPrice--i0c7o">
    <span class="currentAmount--BpSjQ">₹75</span>
</div>
<div class="tira-feedback-service-average-rating-section">3.9/5</div>
<div class="tira-feedback-service-average-rating-total-reviews">215 Ratings</div>
<img class="pdpImage--TIFEB" src="img.jpg" />
<div class="soldByWrapper--ASa1S">Sold by : RELIANCE RETAIL LIMITED</div>
<div class="pdpTable--fOX8q">
    <div class="prop--etp3L">Country of Origin</div>
    <div class="val--WS0aD">India</div>
</div>
<div class="accordionContent--Mioyy productDescription--aYlfh">
    <div class="htmlContent--eDD85">
        These wet wipes helps to remove dirt, excess oil and impurities.
        They cleanse, purify and refresh skin.
    </div>
</div>
"""

@patch("selenium.webdriver.Chrome")
def test_tira_scraper_extracts_correct_fields(mock_chrome):
    """Test that TiraScraper post-processing extracts and cleans up rating, seller, warranty, specifications and description."""
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    scraper = TiraScraper("test-job-tira-extract", headless=True)
    
    item = {
        "title": "Tira Deep Cleansing Mini Wipes (8 Pcs) (215 Ratings)",
        "url": "https://www.tirabeauty.com/product/123",
        "price": "₹75",
        "rating": "N/A",
        "reviews_count": "215 Ratings",
        "image_url": "img.jpg",
        "specifications": {},
        "_html": TIRA_DETAIL_HTML
    }
    
    scraper._fix_title(item)
    scraper._fix_rating(item)
    scraper._fix_reviews_count(item)
    scraper._fix_price(item)
    scraper._fix_brand(item)
    scraper._fix_seller(item)
    scraper._fix_warranty(item)
    scraper._fix_specifications_and_about(item)
    
    assert item["title"] == "Tira Deep Cleansing Mini Wipes (8 Pcs) (215 Ratings)"
    assert item["rating"] == "3.9"
    assert item["reviews_count"] == "215"
    assert item["price"] == "₹75"
    assert item["brand"] == "Tira"
    assert item["seller"] == "RELIANCE RETAIL LIMITED"
    assert "Standard cosmetic" in item["warranty"]
    assert "These wet wipes helps to remove dirt" in item["about_items"][0]
    assert "These wet wipes helps to remove dirt" in item["description"]


KULT_DETAIL_HTML = """
<div class="brand">Kult Brand</div>
<h1 class="product-detail-title">Kult Matte Lipstick</h1>
<div class="detail-price">₹450</div>
<div class="detail-rating">4.2</div>
<div class="detail-reviews-count">98 Ratings</div>
<img class="main-image" src="lipstick.jpg" />
<div class="sold-by">Sold by : KULT E-COMMERCE PRIVATE LIMITED</div>
<table class="specs-table">
    <tr>
        <th>Country of Origin</th>
        <td>India</td>
    </tr>
</table>
<div class="product-description">
    This is an amazing matte lipstick that lasts all day. Easy application and smooth finish.
</div>
"""

@patch("selenium.webdriver.Chrome")
def test_kult_scraper_extracts_correct_fields(mock_chrome):
    """Test that KultScraper post-processing extracts and cleans up rating, seller, warranty, specifications and description."""
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    scraper = KultScraper("test-job-kult-extract", headless=True)
    
    item = {
        "title": "Kult Matte Lipstick (98 Ratings)",
        "url": "https://kult.app/product/123",
        "price": "₹450",
        "rating": "N/A",
        "reviews_count": "98 Ratings",
        "image_url": "lipstick.jpg",
        "specifications": {},
        "_html": KULT_DETAIL_HTML
    }
    
    scraper._fix_title(item)
    scraper._fix_rating(item)
    scraper._fix_reviews_count(item)
    scraper._fix_price(item)
    scraper._fix_brand(item)
    scraper._fix_seller(item)
    scraper._fix_warranty(item)
    scraper._fix_specifications_and_about(item)
    
    assert item["title"] == "Kult Matte Lipstick (98 Ratings)"
    assert item["rating"] == "4.2"
    assert item["reviews_count"] == "98"
    assert item["price"] == "₹450"
    assert item["brand"] == "Kult Brand"
    assert item["seller"] == "KULT E-COMMERCE PRIVATE LIMITED"
    assert "Standard cosmetic" in item["warranty"]
    assert "amazing matte lipstick" in item["about_items"][0]
    assert "amazing matte lipstick" in item["description"]


SMYTTEN_DETAIL_HTML = """
<a class="css-yybu5f" href="/brand/dot-key">DOT & KEY</a>
<h1 id="product-heading">Smytten Sunscreen SPF 50</h1>
<div class="css-k3moiz">₹399</div>
<div class="css-76wsh">4.3</div>
<div class="css-qxtsom">
    <div class="css-3nonjq">125 Ratings</div>
    <div class="css-3nonjq">42 Reviews</div>
</div>
<div class="ant-tabs-tabpane-active">
    <div>Country of Origin: India</div>
    <div>Expiry Date: 2028-12-31</div>
</div>
<div class="product-description">
    This is an amazing sunscreen with broad spectrum protection. It prevents sun damage.
</div>
"""

@patch("selenium.webdriver.Chrome")
def test_smytten_scraper_extracts_correct_fields(mock_chrome):
    """Test that SmyttenScraper post-processing extracts and cleans up rating, seller, warranty, specifications and description."""
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    scraper = SmyttenScraper("test-job-smytten-extract", headless=True)
    
    item = {
        "title": "Smytten Sunscreen SPF 50 (125 Ratings)",
        "url": "https://smytten.com/product/123",
        "price": "₹399",
        "rating": "N/A",
        "reviews_count": "125 Ratings",
        "image_url": "sunscreen.jpg",
        "specifications": {},
        "_html": SMYTTEN_DETAIL_HTML
    }
    
    scraper._fix_title(item)
    scraper._fix_rating(item)
    scraper._fix_reviews_count(item)
    scraper._fix_price(item)
    scraper._fix_brand(item)
    scraper._fix_seller(item)
    scraper._fix_warranty(item)
    scraper._fix_specifications_and_about(item)
    
    assert item["title"] == "Smytten Sunscreen SPF 50 (125 Ratings)"
    assert item["rating"] == "4.3"
    assert item["reviews_count"] == "125"
    assert item["price"] == "₹399"
    assert item["brand"] == "DOT & KEY"
    assert item["seller"] == "Smytten"
    assert "Standard personal care" in item["warranty"]
    assert item["specifications"]["Country of Origin"] == "India"
    assert item["specifications"]["Expiry Date"] == "2028-12-31"
    assert "amazing sunscreen with broad" in item["about_items"][0]
    assert "amazing sunscreen with broad" in item["description"]


ZEPTO_DETAIL_HTML = """
<div class="brand">Dot & Key</div>
<h1 class="product-title">Zepto Sunscreen SPF 50</h1>
<div class="price">₹399</div>
<div class="rating">4.3</div>
<div class="reviews-count">125 Ratings</div>
<table class="specs-table">
    <tr>
        <th>Country of Origin</th>
        <td>India</td>
    </tr>
    <tr>
        <th>Expiry Date</th>
        <td>2028-12-31</td>
    </tr>
</table>
<div class="product-description">
    This is an amazing sunscreen with broad spectrum protection. It prevents sun damage.
</div>
"""

@patch("selenium.webdriver.Chrome")
def test_zepto_scraper_extracts_correct_fields(mock_chrome):
    """Test that ZeptoScraper post-processing extracts and cleans up rating, seller, warranty, specifications and description."""
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    scraper = ZeptoScraper("test-job-zepto-extract", headless=True)
    
    item = {
        "title": "Zepto Sunscreen SPF 50 (125 Ratings)",
        "url": "https://www.zepto.com/pn/zepto-sunscreen-spf-50/pvid/123",
        "price": "₹399",
        "rating": "N/A",
        "reviews_count": "125 Ratings",
        "image_url": "sunscreen.jpg",
        "specifications": {},
        "_html": ZEPTO_DETAIL_HTML
    }
    
    scraper._fix_title(item)
    scraper._fix_rating(item)
    scraper._fix_reviews_count(item)
    scraper._fix_price(item)
    scraper._fix_brand(item)
    scraper._fix_seller(item)
    scraper._fix_warranty(item)
    scraper._fix_specifications_and_about(item)
    
    assert item["title"] == "Zepto Sunscreen SPF 50 (125 Ratings)"
    assert item["rating"] == "4.3"
    assert item["reviews_count"] == "125"
    assert item["price"] == "₹399"
    assert item["brand"] == "Dot & Key"
    assert item["seller"] == "Zepto"
    assert "Standard personal care" in item["warranty"]
    assert item["specifications"]["Country of Origin"] == "India"
    assert item["specifications"]["Expiry Date"] == "2028-12-31"
    assert "amazing sunscreen with broad" in item["about_items"][0]
    assert "amazing sunscreen with broad" in item["description"]


@patch("selenium.webdriver.Chrome")
def test_scraper_collects_with_pagination(mock_chrome):
    """Test that `_collect_listings_with_pagination` navigates to next pages and collects items up to the limit."""
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    PAGE1_HTML = """
    <div data-component-type="s-search-result" class="s-result-item">
        <div>
            <h2><a class="a-link-normal" href="/dp/ITEM1"><span class="a-size-medium">Laptop Item 1</span></a></h2>
            <span class="a-price-whole">50,000</span>
        </div>
    </div>
    <a class="s-pagination-next" href="/next-page-url">Next</a>
    """
    
    PAGE2_HTML = """
    <div data-component-type="s-search-result" class="s-result-item">
        <div>
            <h2><a class="a-link-normal" href="/dp/ITEM2"><span class="a-size-medium">Laptop Item 2</span></a></h2>
            <span class="a-price-whole">60,000</span>
        </div>
    </div>
    """
    
    driver_instance.page_source = PAGE1_HTML
    driver_instance.current_url = "https://www.amazon.in/s?k=laptop"
    
    mock_next_button = MagicMock()
    mock_next_button.is_displayed.return_value = True
    mock_next_button.is_enabled.return_value = True
    
    def mock_find_element(by, value):
        if "s-pagination-next" in value or "next" in value:
            return mock_next_button
        raise Exception("Element not found")
        
    driver_instance.find_element.side_effect = mock_find_element
    
    scraper = AmazonScraper("test-job-pagination", headless=True)
    scraper.driver = driver_instance
    
    def mock_execute_script(script, *args):
        if "click" in script:
            driver_instance.page_source = PAGE2_HTML
            driver_instance.current_url = "https://www.amazon.in/s?k=laptop&page=2"
            return None
        return None
        
    driver_instance.execute_script.side_effect = mock_execute_script
    
    results = scraper._collect_listings_with_pagination(
        selectors=scraper.SELECTORS,
        search_query="Laptop",
        limit=2
    )
    
    assert len(results) == 2
    assert results[0]["title"] == "Laptop Item 1"
    assert results[1]["title"] == "Laptop Item 2"


ALIBABA_DETAIL_HTML = """
<div class="product-title">
    <h1>Alibaba Professional Laptop 15.6 Inch</h1>
</div>
<div class="price-number">$450.00 - $480.00</div>
<span class="rating-value">4.8</span>
<span class="review-count">(12 reviews)</span>
<div class="attribute-layout">
    <div class="attribute-item">Brand Name: OEM/Alibaba</div>
    <div class="attribute-item">Country of Origin: China</div>
    <div class="attribute-item">Warranty: 1 Year Manufacturer Warranty</div>
</div>
<div class="product-description">
    High quality business laptop for office work. Equipped with high-speed SSD and reliable CPU.
</div>
<a class="company-name" href="/company_profile">Shenzhen Technology Co., Ltd.</a>
"""


@patch("selenium.webdriver.Chrome")
def test_alibaba_scraper_extracts_correct_fields(mock_chrome):
    """Test that AlibabaScraper post-processing extracts and cleans up rating, seller, warranty, specifications and description."""
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    scraper = AlibabaScraper("test-job-alibaba-extract", headless=True)
    
    item = {
        "title": "Alibaba Professional Laptop 15.6 Inch",
        "url": "https://www.alibaba.com/product-detail/123.html",
        "price": "$450.00 - $480.00",
        "rating": "N/A",
        "reviews_count": "N/A",
        "image_url": "laptop.jpg",
        "specifications": {},
        "_html": ALIBABA_DETAIL_HTML
    }
    
    scraper._fix_title(item)
    scraper._fix_rating(item)
    scraper._fix_reviews_count(item)
    scraper._fix_price(item)
    scraper._fix_brand(item)
    scraper._fix_seller(item)
    scraper._fix_warranty(item)
    scraper._fix_specifications_and_about(item)
    
    assert item["title"] == "Alibaba Professional Laptop 15.6 Inch"
    assert item["rating"] == "4.8"
    assert item["reviews_count"] == "12"
    assert item["price"] == "$450.00-$480.00"
    assert item["brand"] == "OEM/Alibaba"
    assert item["seller"] == "Shenzhen Technology Co., Ltd."
    assert "1 Year Manufacturer Warranty" in item["warranty"]
    assert item["specifications"]["Country of Origin"] == "China"
    assert item["specifications"]["Brand Name"] == "OEM/Alibaba"
    assert "High quality business laptop" in item["description"]





