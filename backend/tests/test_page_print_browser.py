"""Opt-in Chromium PDF regression: PAGE_PRINT_BROWSER_TESTS=1 pytest -s tests/test_page_print_browser.py."""

import os

import pytest

from app.services.page_printing import render_page
from tests.test_page_printing import revision


@pytest.mark.skipif(os.environ.get("PAGE_PRINT_BROWSER_TESTS") != "1", reason="Requires local Playwright Chromium")
def test_default_print_keeps_bars_and_footer_and_trusted_controls_work(tmp_path):
    import fitz
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=os.environ.get("PAGE_PRINT_BROWSER_CHANNEL") or None)
        context = browser.new_context()
        page = context.new_page()
        # Exercise native printing under the sandbox; headless Chrome fires
        # beforeprint without presenting a system dialog.
        context.add_init_script("window.printCalls = 0; window.addEventListener('beforeprint', () => { window.printCalls++; });")
        for view in ("content", "full", "print"):
            html, csp = render_page(revision(), 4, view)
            # Even views with our trusted print script must reject authored JS.
            html = html.replace("</body>", "<script>window.untrustedRan = true;</script></body>")
            page.route(f"http://page-print.test/{view}", lambda route, request, html=html, csp=csp: route.fulfill(
                status=200, body=html, content_type="text/html", headers={"Content-Security-Policy": csp},
            ))
            page.goto(f"http://page-print.test/{view}")
            assert page.evaluate("window.untrustedRan") is None
            if view == "full":
                page.get_by_role("button", name="Print / Save as PDF").click()
                assert page.evaluate("window.printCalls") == 1
            elif view == "print":
                assert page.evaluate("window.printCalls") == 1
            else:
                assert page.locator("button").count() == 0
            pdf_path = tmp_path / f"page-{view}.pdf"
            page.pdf(path=str(pdf_path), print_background=False, format="Letter")
            with fitz.open(pdf_path) as pdf:
                assert len(pdf) == 2
                for sheet in pdf:
                    text = sheet.get_text()
                    assert "Version 4" in text and "2026-10-29 12:30 UTC" in text
                    assert "Print / Save as PDF" not in text
                    footer = sheet.search_for("Version 4")[0]
                    assert sheet.rect.height - 90 < footer.y0 < sheet.rect.height - 10
                colors = [drawing["fill"] for drawing in pdf[0].get_drawings() if drawing.get("fill")]
                def count_color(rgb):
                    return sum(all(abs(actual - wanted / 255) < .01 for actual, wanted in zip(color, rgb)) for color in colors)
                assert count_color((37, 99, 235)) >= 5  # Yearly totals, even with print_background=False.
                assert count_color((5, 150, 105)) >= 3  # Category breakdown.
                for index, sheet in enumerate(pdf):
                    sheet.get_pixmap(matrix=fitz.Matrix(1.2, 1.2)).save(str(tmp_path / f"{view}-{index + 1}.png"))
            if view == "full":
                page.screenshot(path=str(tmp_path / "screen.png"), full_page=True)
        browser.close()
    print(f"Print QA output: {tmp_path}")
