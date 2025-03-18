"""
Test basic file management flows for Vandalizer.
"""

from urllib import parse as urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class TestFolderManagement:
    def test_get_home_page(self, driver, config):
        driver.get(config["home_url"])

    def test_click_add_folder(self, driver):
        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.ID, "add-folder-button"))
        )
        addFolderButton = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "add-folder-button"))
        )
        addFolderButton.click()

    def test_fill_in_folder_name(self, driver):
        folder_name_input = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.ID, "add-folder-field"))
        )

        folder_name_input.send_keys("auto-test-folder")

    def test_submit_folder_creation(self, driver):
        submit_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "add-folder-button"))
        )
        submit_button.click()

    def test_get_id_from_nav(self, driver, shared_state):
        WebDriverWait(driver, 10).until(EC.url_contains("folder_id="))
        shared_state["folder_id"] = urlparse.parse_qs(
            urlparse.urlparse(driver.current_url).query
        )["folder_id"][0]

        assert len(shared_state["folder_id"]) > 0

    def test_navigate_to_root(self, driver, config):
        driver.get(config["home_url"])

    def test_folder_exists(self, driver, shared_state):
        folder_button = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located(
                (By.XPATH, f'//button[@data-folder-id="{shared_state["folder_id"]}"]')
            )
        )

        # Check the title is included
        ancestor = folder_button.find_element(
            By.XPATH,
            "./ancestor::tr[contains(concat(' ',@class,' '),' folder ')]",
        )
        ancestor.find_element(By.XPATH, "//span[contains(text(), 'auto-test-folder')]")

        folder_button.click()

    def test_delete_button(self, driver):
        # Find a element with id `delete-option` in a div with id `file-popup-menu`, wait for visibility
        delete_button = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located(
                (By.XPATH, "//div[@id='file-popup-menu']//li[@id='delete-option']")
            )
        )
        delete_button.click()
        WebDriverWait(driver, 5).until(EC.alert_is_present())
        driver.switch_to.alert.accept()

    def test_folder_gone(self, driver, shared_state):
        WebDriverWait(driver, 10).until_not(
            EC.presence_of_element_located(
                (By.XPATH, f'//button[@data-folder-id="{shared_state["folder_id"]}"]')
            )
        )
