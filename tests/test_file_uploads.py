#!/usr/bin/env python3

import re
from playwright.sync_api import Page, expect

from pathlib import Path
import os


def test_file_input_upload(page: Page) -> None:
    page.goto("http://localhost:5001/home/")

    # with open("temp_file.txt", "w") as f:
    #     f.write("This is a test file.")

    # file_path = Path.cwd() / "temp_file.txt"
    # page.locator("#file-input").set_input_files(file_path)

    # page.wait_for_timeout(500)

    # expect(page.get_by_role("cell", name='" / " temp_file.txt')).to_be_visible()

    # os.remove("temp_file.txt")
