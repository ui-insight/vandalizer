import pytest
from selenium import webdriver

@pytest.fixture(scope="class")
def driver(request):
    driver = webdriver.Firefox()
    request.cls.driver = driver
    yield driver
    driver.quit()