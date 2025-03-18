import os

import pytest
from selenium import webdriver


@pytest.fixture(scope="class")
def driver(request):
    if os.getenv("TEST_BROWSER", "").lower() == "chrome":
        options = webdriver.ChromeOptions()
        if os.getenv("TEST_BROWSER_HEADLESS", False):
            options.add_argument("--headless=new")  # Run in headless mode
    else:
        options = webdriver.FirefoxOptions()
        if os.getenv("TEST_BROWSER_HEADLESS", False):
            options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")  # Disable GPU acceleration
    options.add_argument("--no-sandbox")  # Disable sandboxing
    options.add_argument("--window-size=1920,1080")  # Set window size
    if os.getenv("TEST_BROWSER") == "chrome":
        driver = webdriver.Chrome(options)
    else:
        driver = webdriver.Firefox(options)
    request.cls.driver = driver
    yield driver
    driver.quit()


@pytest.fixture(scope="session")
def base_url():
    base_url = os.getenv("BASE_URL", False)
    if base_url:
        return base_url.removesuffix("/")
    port = os.getenv("PORT", "5001")
    return f"http://localhost:{port}"
