"""The PyMuPDF fallback keeps a borderless table's rows on one line.

Support ticket: asked for "Total Revenue Actuals Fiscal YTD", extraction
returned the Current Month figure. The fallback reader emitted the table one
cell per line, so the label was followed by the leftmost number and the
column headers sat far above it.
"""

import pymupdf
import pytest

from app.services.document_readers import _page_text_with_table_rows, _pymupdf_extract_with_pages
from app.services.extraction_sources import find_quote_offset

COLS = [40, 260, 360, 460, 560, 660]
HEADER = ["Current Month", "Fiscal YTD", "Prior YTD", "Budget", "Remaining"]
ROWS = [
    ("Tuition Revenue", "12,004", "301,220.10", "280,114.00", "400,000.00", "98,779.90"),
    ("Total Revenue Actuals", "35,767", "724,298.58", "670,119.12", "900,000.00", "175,701.42"),
    ("Salaries", "20,110", "410,332.00", "398,221.00", "520,000.00", "109,668.00"),
]


def _report_page(doc):
    page = doc.new_page(width=792, height=612)
    page.insert_text((40, 40), "Monthly Financial Report")
    for x, h in zip(COLS[1:], HEADER):
        page.insert_text((x, 80), h, fontsize=9)
    y = 100
    for row in ROWS:
        for x, v in zip(COLS, row):
            page.insert_text((x, y), v, fontsize=9)
        y += 16
    page.insert_text((40, y + 20), "Figures are unaudited.")
    return page


def _lines(text: str) -> list[list[str]]:
    return [line.split("\t") for line in text.splitlines()]


@pytest.fixture
def report_pdf(tmp_path):
    doc = pymupdf.open()
    _report_page(doc)
    path = tmp_path / "report.pdf"
    doc.save(path)
    return str(path)


def test_row_label_sits_with_its_numbers_under_their_headers(report_pdf):
    text, _ = _pymupdf_extract_with_pages(report_pdf)
    lines = _lines(text)
    header = next(cells for cells in lines if "Fiscal YTD" in cells)
    row = next(cells for cells in lines if cells[0] == "Total Revenue Actuals")
    assert row == list(ROWS[1])
    assert header == ["", *HEADER]
    assert row[header.index("Fiscal YTD")] == "724,298.58"
    assert row[header.index("Current Month")] == "35,767"


def test_text_around_the_table_is_unchanged(report_pdf):
    text, _ = _pymupdf_extract_with_pages(report_pdf)
    lines = text.splitlines()
    assert lines[0] == "Monthly Financial Report"
    assert lines[-1] == "Figures are unaudited."


def test_quote_from_the_old_one_cell_per_line_text_still_verifies(report_pdf):
    text, _ = _pymupdf_extract_with_pages(report_pdf)
    assert find_quote_offset(text, "Total Revenue Actuals\n35,767\n724,298.58") is not None
    assert find_quote_offset(text, "Total Revenue Actuals 35,767 724,298.58") is not None


def test_prose_page_is_byte_identical_to_plain_text():
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate([
        "The award period is 2024 to 2027 and the total is 485,000.",
        "Cost share of 12,500 is committed by the department.",
        "Indirect costs are charged at 56.5% of modified total direct costs.",
    ]):
        page.insert_text((60, 80 + 18 * i), line)
    assert _page_text_with_table_rows(page) == page.get_text("text")


def test_two_column_article_keeps_reading_order():
    doc = pymupdf.open()
    page = doc.new_page()
    for i in range(12):
        page.insert_text((50, 80 + 16 * i), f"Left column sentence {i} runs on.")
        page.insert_text((320, 80 + 16 * i), f"Right column sentence {i} runs on.")
    assert _page_text_with_table_rows(page) == page.get_text("text")


def test_page_markers_still_point_at_each_page(tmp_path):
    doc = pymupdf.open()
    _report_page(doc)
    doc.new_page().insert_text((60, 80), "Second page narrative.")
    path = tmp_path / "two.pdf"
    doc.save(path)
    text, markers = _pymupdf_extract_with_pages(str(path))
    second = next(m for m in markers if m["value"] == 2)
    # The offset lands on the "\n" that joins pages (unchanged by this fix).
    assert text[second["char_offset"]:].lstrip("\n").startswith("Second page narrative.")
