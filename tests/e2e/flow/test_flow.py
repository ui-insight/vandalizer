"""
Test basic page flows for Vandalizer.
"""

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class TestLogin:
    def test_vandalizer_dev_login(self, driver, config):
        driver.get(config["base_url"])
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.LINK_TEXT, "SIGN IN"))
        )
        signInButton = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "SIGN IN"))
        )
        signInButton.click()
        WebDriverWait(driver, 10).until(EC.url_matches(config["home_url"]))


class TestNavigation:
    def test_loads_home_page(self, driver, config):
        driver.get(config["home_url"])
        WebDriverWait(driver, 10).until(EC.url_matches(config["home_url"]))
        assert driver.title == "Home | Vandalizer"

    def test_enters_directory(self, driver, config):
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    f"//span[contains(text(),'{config['examples_directory_name']}')]",
                )
            )
        )
        directory = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    f"//span[contains(text(),'{config['examples_directory_name']}')]",
                )
            )
        )
        directory.click()
        WebDriverWait(driver, 10).until(
            EC.url_contains(f"folder_id={config['examples_directory_id']}")
        )

    def test_enters_file(self, driver, config):
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//span[contains(text(),'{config['extract_file_name']}')]")
            )
        )
        file = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, f"//span[contains(text(),'{config['extract_file_name']}')]")
            )
        )
        file.click()
        WebDriverWait(driver, 10).until(
            EC.url_contains(f"docid={config['extract_file_id']}")
        )
