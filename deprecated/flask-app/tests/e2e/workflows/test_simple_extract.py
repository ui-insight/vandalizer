from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class TestWorkflowRun:
    def test_get_page(self, driver, config) -> None:
        workflow_url = f"{config['extract_file_url']}&workflow_id={config['extract_workflow_id']}&section=Workflows"
        driver.get(workflow_url)

    def test_verify_doc_title(self, driver, config) -> None:
        title_element = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.ID, "document-title")),
        )

        assert config["extract_file_name"] in title_element.text

    def test_verify_workflow_title(self, driver, config) -> None:
        title_element = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.ID, "workflowTitle")),
        )

        assert config["extract_workflow_name"] in title_element.text

    def test_has_step(self, driver) -> None:
        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located(
                (By.XPATH, "//span[contains(text(), 'Extract title')]"),
            ),
        )

    def test_click_run(self, driver) -> None:
        run_workflow_button = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.CLASS_NAME, "run-workflow")),
        )
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(run_workflow_button))
        run_workflow_button.click()

    def test_has_throbber(self, driver) -> None:
        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.CLASS_NAME, "workflow-output")),
        )

    def test_response_has_body(self, driver) -> None:
        response_body = WebDriverWait(driver, 180).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".workflow-output-section>div"),
            ),
        )
        assert "pdf test file" in response_body.get_attribute("innerHTML").lower()
