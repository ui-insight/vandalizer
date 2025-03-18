"""
Test basic file management flows for Vandalizer.
"""

from pathlib import Path
from shutil import copyfile
from urllib import parse as urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class TestFileManagement:
    def test_get_home_page(self, driver, config):
        driver.get(config["home_url"])

    def test_click_upload_file(self, driver):
        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.XPATH, "//label[@for='file-input']"))
        )
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//label[@for='file-input']"))
        )
        # For automation purposes, we don't click

    def test_create_file(self, config, shared_state, temp_dir):
        shared_state["target_file_path"] = temp_dir / config["create_file_name"]
        copyfile(
            str(
                Path(__file__).parent.absolute()
                / "example_pdfs"
                / config["create_file_source"]
            ),
            str(temp_dir / config["create_file_name"]),
        )

    def test_fill_in_file_name(self, driver, shared_state):
        file_name_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "file-input"))
        )

        file_name_input.send_keys(str(shared_state["target_file_path"]))

    def test_get_id_from_nav(self, driver, shared_state):
        WebDriverWait(driver, 60).until(EC.url_contains("docid="))
        shared_state["doc_id"] = urlparse.parse_qs(
            urlparse.urlparse(driver.current_url).query
        )["docid"][0]

        assert len(shared_state["doc_id"]) > 0

    def test_navigate_to_root(self, driver, config):
        driver.get(config["home_url"])

    def test_file_exists(self, driver, shared_state, config):
        file_button = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located(
                (By.XPATH, f'//button[@data-doc-id="{shared_state["doc_id"]}"]')
            )
        )

        # Check the title is included
        ancestor = file_button.find_element(
            By.XPATH,
            "./ancestor::tr[contains(concat(' ',@class,' '),' file ')]",
        )
        ancestor.find_element(
            By.XPATH, f"//span[contains(text(), '{config['create_file_name']}')]"
        )

        file_button.click()

    def test_delete_button(self, driver):
        # Find a element with id `delete-option` in a div with id `file-popup-menu`, wait for visibility
        delete_button = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located(
                (By.XPATH, "//div[@id='file-popup-menu']//li[@id='delete-option']")
            )
        )
        delete_button.click()

    def test_file_gone(self, driver, shared_state):
        WebDriverWait(driver, 10).until_not(
            EC.presence_of_element_located(
                (By.XPATH, f'//button[@data-doc-id="{shared_state["doc_id"]}"]')
            )
        )
