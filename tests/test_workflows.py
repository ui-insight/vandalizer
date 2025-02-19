#!/usr/bin/env python3

import re
from playwright.sync_api import Page, expect


def test_example(page: Page) -> None:
    page.goto("http://localhost:5001/home/")
    page.get_by_role("listitem").filter(has_text="Workflows").click()
    page.get_by_role("button", name='+" / " New Workflow').click()
    page.get_by_role("textbox", name="Name your workflow").click()
    page.get_by_role("textbox", name="Name your workflow").fill("My Workflow")
    page.get_by_role("textbox", name="A one sentence description of").click()
    page.get_by_role("textbox", name="A one sentence description of").fill(
        "A basic workflow "
    )
    page.get_by_role("button", name="Create Workflow").click()
    page.get_by_role("listitem").filter(has_text="Workflows").click()
    page.locator("#workflows-panel").get_by_text("My Workflow").click()
    page.get_by_role("button", name="+ ADD STEP").click()
    page.get_by_role("textbox", name="Briefly describe the purpose").click()
    page.get_by_role("textbox", name="Briefly describe the purpose").fill("Extraction")
    page.get_by_role("button", name="Begin Building Step").click()
    page.get_by_text("ADD YOUR FIRST TASK").click()
    page.locator("a").filter(has_text="Extractions Extract").first.click()
    page.get_by_role("button", name="Enter Manually").click()
    page.get_by_role("textbox", name="Enter extractions (comma-").click()
    page.get_by_role("textbox", name="Enter extractions (comma-").fill(
        "Name, Budget, Salary, Year, Amount, Email"
    )
    page.get_by_role("button", name="Add Extractions").click()
    page.get_by_role("button", name="+ ADD STEP").click()
    page.get_by_role("textbox", name="Briefly describe the purpose").click()
    page.get_by_role("textbox", name="Briefly describe the purpose").fill("Summary")
    page.get_by_role("button", name="Begin Building Step").click()
    page.get_by_text("ADD YOUR FIRST TASK").click()
    page.locator("a").filter(has_text="Prompts Ask questions, build").first.click()
    page.get_by_role("button", name="Enter Manually").click()
    page.get_by_role("textbox", name="Enter prompt:").click()
    page.get_by_role("textbox", name="Enter prompt:").fill(
        "Summarize the provided text"
    )
    page.get_by_role("button", name="Add Prompt").click()
    page.get_by_role("button", name="+ ADD STEP").click()
    page.get_by_role("textbox", name="Briefly describe the purpose").click()
    page.get_by_role("textbox", name="Briefly describe the purpose").fill("Format")
    page.get_by_role("button", name="Begin Building Step").click()
    page.get_by_text("ADD YOUR FIRST TASK").click()
    page.locator("a").filter(has_text="Format Format your data,").first.click()
    page.get_by_role("button", name="Enter Manually").click()
    page.get_by_role("textbox", name="Enter formatter:").click()
    page.get_by_role("textbox", name="Enter formatter:").fill("Format as markdown")
    page.get_by_role("button", name="Add Formatter").click()
