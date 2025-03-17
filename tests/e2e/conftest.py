import pytest
from selenium import webdriver
import os

@pytest.fixture(scope="class")
def driver(request):
    driver = webdriver.Firefox()
    request.cls.driver = driver
    yield driver
    driver.quit()

@pytest.fixture(scope="session")
def base_url():
    base_url = os.getenv("BASE_URL", False)
    if(base_url):
        return base_url.removesuffix('/')
    port = os.getenv("PORT", "5001")
    return f"http://localhost:{port}"
