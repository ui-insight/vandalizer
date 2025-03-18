import os
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from selenium import webdriver


@pytest.fixture(scope="class")
def shared_state():
    return {}


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
def config():
    base_url = os.getenv("BASE_URL", False)
    if not base_url:
        port = os.getenv("PORT", "5001")
        base_url = f"http://localhost:{port}"
    base_url = base_url.removesuffix("/") + "/"
    home_url = base_url + "home"
    id = uuid.uuid4()
    extract_file_id = "16366A017B6144A2B2A9E02956F22339"
    return {
        "base_url": base_url,
        "home_url": home_url + "/",
        "create_folder_name": f"auto_test_folder_{id}",
        "create_file_source": "auto_test_example.pdf",
        "create_file_name": f"auto_test_example_{id}.pdf",
        "examples_directory_name": "auto_test_examples",
        "examples_directory_id": "58111be9429948b6894636805bbf75ed",
        "extract_file_name": "example.pdf",
        "extract_file_id": extract_file_id,
        "extract_file_url": f"{home_url}?docid={extract_file_id}",
        "extract_workflow_id": "67d9ca885037b4497daf9be2",
        "extract_workflow_name": "auto_test_workflow",
    }


@pytest.fixture(scope="class")
def temp_dir():
    with TemporaryDirectory() as temp_dir_object:
        yield Path(temp_dir_object)
