import pytest
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup
from app.scrapers.base import BaseScraper
from app.scrapers.amazon import Scraper as AmazonScraper
from app.scrapers.flipkart import Scraper as FlipkartScraper

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

@patch("selenium.webdriver.Chrome")
def test_driver_initialization(mock_chrome):
    """Test that ChromeDriver is initialized with proper arguments."""
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
    
    assert amazon.BASE_URL == "https://www.amazon.in"
    assert flipkart.BASE_URL == "https://www.flipkart.com"
    
    assert "search_input" in amazon.SELECTORS
    assert "search_input" in flipkart.SELECTORS

@patch("selenium.webdriver.Chrome")
def test_scraper_extracts_listings(mock_chrome):
    """Test that the listings extraction logic parses search result HTML correctly."""
    # Configure mock driver
    driver_instance = MagicMock()
    mock_chrome.return_value = driver_instance
    
    driver_instance.page_source = SEARCH_PAGE_HTML
    
    scraper = AmazonScraper("test-job-456", headless=True)
    
    # Run the scrape method using mocks for navigation and interaction
    with patch.object(scraper, "init_driver") as mock_init:
        scraper.driver = driver_instance
        
        # Mock navigation and explicit wait findings
        scraper.driver.get = MagicMock()
        scraper.wait_for_element = MagicMock()
        
        def mock_get(url):
            driver_instance.page_source = DETAIL_PAGE_HTML
            
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
