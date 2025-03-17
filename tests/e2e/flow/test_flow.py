import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

@pytest.fixture(scope="class")
def setup_driver(request):
    driver = webdriver.Firefox()
    request.cls.driver = driver
    yield 
    driver.quit()

@pytest.mark.usefixtures("setup_driver")
class TestLogin:
    def test_vandalizer_dev_login(self):
        self.driver.get("https://vandalizer-dev.nkn.uidaho.edu/")
        # Wait for the sign-in button to be clickable
        signInButton = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "SIGN IN"))
        )
        signInButton.click()
        # Wait for the navigation to complete
        WebDriverWait(self.driver, 10).until(
            EC.url_matches("https://vandalizer-dev.nkn.uidaho.edu/home/")
        )
        # Optionally, you can add assertions to verify if the home page elements are present
        homePageElement = self.driver.find_element(By.TAG_NAME, "body")
        assert homePageElement

@pytest.mark.usefixtures("setup_driver")
class TestNavigation:
    def loads_home_page(self):
        self.driver.get("https://vandalizer-dev.nkn.uidaho.edu/home/")
        title = self.driver.title
        assert title == "Home | Vandalizer"
        # Check URL matches
        WebDriverWait(self.driver, 10).until(
            EC.url_matches("https://vandalizer-dev.nkn.uidaho.edu/home/")
        )

    def enters_directory(self):
        directory = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'test')]"))
        )
        directory.click()
        # Wait until the URL has the specified value
        WebDriverWait(self.driver, 10).until(
            EC.url_contains("/folder_id=18d04abb0c2c4194bba3b69a175bdcab")
        )
        file = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'L19AC00167.pdf')]"))
        )
        file.click()
        # Wait until the URL has the specified value
        WebDriverWait(self.driver, 10).until(
            EC.url_contains("/folder_id=18d04abb0c2c4194bba3b69a175bdcab&docid=0B1EF085C7724C8481BCB450211C916C")
        )

if __name__ == "__main__":
    pytest.main([__file__])