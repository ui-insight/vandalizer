#!/usr/bin/env python3

import re
from playwright.sync_api import Page, expect


def test_homepage(page: Page) -> None:
    page.goto("http://localhost:5001/home/")
    expect(page.locator("#navbar-img").nth(1)).to_be_visible()
    expect(page.locator("#navbar-img").first).to_be_visible()

    expect(page.locator("#drag-area div").nth(1)).to_be_visible()
    expect(page.get_by_text("Select or Upload PDFs")).to_be_visible()
    expect(page.get_by_text("Chat")).to_be_visible()
    expect(page.get_by_role("listitem").filter(has_text="Workflows")).to_be_visible()
    expect(page.get_by_text("Select documents to begin")).to_be_visible()
    expect(page.get_by_text("Teach me how to use")).to_be_visible()
    expect(page.locator("#chat-suggestion-2")).to_be_visible()
    expect(page.get_by_text("How can I help?")).to_be_visible()
    expect(page.get_by_role("button", name='" / " Tasks')).to_be_visible()

    expect(page.locator("#file-input")).to_be_visible()

    expect(page.get_by_role("button", name="Add Folder")).to_be_visible()
    expect(page.locator("#space-select")).to_be_visible()
    expect(page.get_by_role("link", name="Support")).to_be_visible()
