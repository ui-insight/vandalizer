import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class TestLogin:
    def test_vandalizer_dev_login(self, driver):
        driver.get("https://vandalizer-dev.nkn.uidaho.edu/")
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.LINK_TEXT, "SIGN IN"))
        )
        signInButton = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "SIGN IN"))
        )
        signInButton.click()
        WebDriverWait(driver, 10).until(
            EC.url_matches("https://vandalizer-dev.nkn.uidaho.edu/home/")
        )

class TestNavigation:
    def test_loads_home_page(self, driver):
        driver.get("https://vandalizer-dev.nkn.uidaho.edu/home/")
        WebDriverWait(driver, 10).until(
            EC.url_matches("https://vandalizer-dev.nkn.uidaho.edu/home/")
        )
        assert driver.title == "Home | Vandalizer"

    def test_enters_directory(self, driver):
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//span[contains(text(),'test')]"))
        )
        directory = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'test')]"))
        )
        directory.click()
        WebDriverWait(driver, 10).until(
            EC.url_contains("folder_id=18d04abb0c2c4194bba3b69a175bdcab")
        )
    
    def test_enters_file(self, driver):
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//span[contains(text(),'L19AC00167.pdf')]"))
        )
        file = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'L19AC00167.pdf')]"))
        )
        file.click()
        WebDriverWait(driver, 10).until(
            EC.url_contains("docid=0B1EF085C7724C8481BCB450211C916C")
        )

if __name__ == "__main__":
    pytest.main([__file__])