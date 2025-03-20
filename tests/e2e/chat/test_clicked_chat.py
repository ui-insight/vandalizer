from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class TestClickedChat:
    def test_get_page(self, driver, config):
        chat_url = config["extract_file_url"] + "&section=Chat"
        driver.get(chat_url)

    def test_verify_title(self, driver, config):
        title_element = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.ID, "document-title"))
        )

        assert config["extract_file_name"] in title_element.text

    def test_click_chat(self, driver):
        summarize_suggestion = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.ID, "chat-suggestion-1"))
        )
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(summarize_suggestion))
        summarize_suggestion.click()

    def test_has_throbber(self, driver):
        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.CLASS_NAME, "chat-loader"))
        )

    def test_throbber_ends(self, driver):
        WebDriverWait(driver, 60).until_not(
            EC.visibility_of_element_located((By.CLASS_NAME, "chat-loader"))
        )

    def test_response_has_body(self, driver):
        response_body = WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CLASS_NAME, "message-response-body"))
        )
        assert "PDF" in response_body.get_attribute("innerHTML")
