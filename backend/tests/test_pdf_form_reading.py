"""A form whose content stream keeps labels apart from their values is read
in visual order, so each label and its value share a line.

On the BLM Notice of Award both PDF readers listed budget lines a–n in one
block and their figures in another, out of order: every extraction run
swapped Travel and Supplies, and one read Total Direct Costs from the award
total.
"""

from collections import Counter
from types import SimpleNamespace

import pymupdf
import pytest

from app.services.document_readers import (
    _fast_path_page_texts,
    _form_page_reading,
    _pairs_kept,
    _pymupdf_extract_with_pages,
)
from app.services.extraction_sources import find_quote_offset

LEFT_ROWS = [  # (y, item letter, label, value)
    (360, "a.", "Salaries and Wages", "57,030.00"),
    (373, "b.", "Fringe Benefits", "20,679.30"),
    (386, "e.", "Supplies", "1,000.00"),
    (399, "f.", "Travel", "3,566.00"),
]
BOXED_ROWS = [  # label box | value box, a drawn rule between them
    (412, "j.", "TOTAL DIRECT COSTS", "82,275.30"),
    (425, "k.", "INDIRECT COSTS", "14,398.18"),
]
RIGHT_ROWS = [
    (365, "a. Amount of Federal Financial Assistance", "96,673.48"),
    (392, "13. Total Federal Funds Awarded to Date", "96,673.48"),
]


def _noa_page(doc, *, in_order: bool = False):
    """A two-column award form. Unless ``in_order``, the stream is written the
    way the BLM form is: every label first, then every figure."""
    page = doc.new_page(width=612, height=792)
    for y in (330, 560):
        page.draw_line((32, y), (591, y))
    page.draw_line((307, 330), (307, 560))
    for y in (403, 416, 429):
        page.draw_line((32, y), (216, y))
    page.draw_line((216, 403), (216, 429))

    def label(row):
        y, letter, name = row[0], row[1], row[2]
        page.insert_text((46, y), letter, fontsize=8)
        page.insert_text((60, y), name, fontsize=8)
        if row in LEFT_ROWS:
            page.insert_text((130, y), "..........$", fontsize=8)
        else:
            page.insert_text((220, y), "$", fontsize=8)

    def value(row):
        page.insert_text((262, row[0]), row[3], fontsize=8)

    page.insert_text((40, 340), "11. APPROVED BUDGET", fontsize=8)
    page.insert_text((312, 345), "12. AWARD COMPUTATION", fontsize=8)
    if in_order:
        for row in LEFT_ROWS + BOXED_ROWS:
            label(row)
            value(row)
        for y, name, figure in RIGHT_ROWS:
            page.insert_text((312, y), name, fontsize=8)
            page.insert_text((520, y), "$ " + figure, fontsize=8)
        return page
    for row in BOXED_ROWS + LEFT_ROWS:
        label(row)
    for y, name, _ in RIGHT_ROWS:
        page.insert_text((312, y), name, fontsize=8)
    for row in reversed(LEFT_ROWS + BOXED_ROWS):
        value(row)
    for y, _, figure in RIGHT_ROWS:
        page.insert_text((520, y), "$ " + figure, fontsize=8)
    return page


@pytest.fixture
def noa_pdf(tmp_path):
    doc = pymupdf.open()
    _noa_page(doc)
    doc.new_page().insert_text((72, 72), "Special conditions follow on this page.")
    path = tmp_path / "noa.pdf"
    doc.save(path)
    return str(path)


def _cells(text: str) -> list[list[str]]:
    return [line.split("\t") for line in text.splitlines()]


def test_each_budget_line_keeps_its_own_figure(noa_pdf):
    text, _ = _pymupdf_extract_with_pages(noa_pdf)
    for _, letter, name, figure in LEFT_ROWS:
        cells = next(c for c in _cells(text) if c[0] == letter)
        assert name in cells[1] and cells[-1] == figure
    assert "f.\tTravel\t..........$\t3,566.00" in text.splitlines()
    assert "e.\tSupplies\t..........$\t1,000.00" in text.splitlines()


def test_a_rule_between_a_label_box_and_its_value_box_is_not_a_column(noa_pdf):
    text, _ = _pymupdf_extract_with_pages(noa_pdf)
    assert "j.\tTOTAL DIRECT COSTS\t$\t82,275.30" in text.splitlines()
    assert "k.\tINDIRECT COSTS\t$\t14,398.18" in text.splitlines()


def test_the_right_column_follows_the_left_instead_of_interleaving(noa_pdf):
    lines = _pymupdf_extract_with_pages(noa_pdf)[0].splitlines()
    last_left = max(i for i, line in enumerate(lines) if line.startswith(("a.\tSal", "k.\t")))
    first_right = next(i for i, line in enumerate(lines) if line.startswith("12. AWARD"))
    assert first_right > last_left
    assert "a. Amount of Federal Financial Assistance\t$ 96,673.48" in lines


def test_no_text_is_lost_or_added(noa_pdf):
    with pymupdf.open(noa_pdf) as doc:
        before = Counter(doc[0].get_text("text").split())
        reading = _form_page_reading(doc[0])
    assert reading is not None
    assert Counter(reading[0].split()) == before


def test_other_pages_and_page_markers_are_unchanged(noa_pdf):
    text, markers = _pymupdf_extract_with_pages(noa_pdf)
    assert [m["value"] for m in markers] == [1, 2]
    assert text[markers[1]["char_offset"]:].strip() == "Special conditions follow on this page."


def test_a_quote_of_label_and_figure_verifies(noa_pdf):
    text, _ = _pymupdf_extract_with_pages(noa_pdf)
    assert find_quote_offset(text, "Travel ..........$ 3,566.00") is not None


def test_a_form_written_in_reading_order_is_left_as_read():
    doc = pymupdf.open()
    page = _noa_page(doc, in_order=True)
    assert _form_page_reading(page) is None


def test_a_table_header_row_stays_one_line(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    cols = [40, 120, 240, 330]
    header = ["LINE#", "FINANCIAL ACCT", "AMT OF FIN ASST", "START DATE"]
    data = ["1", "0051049525-00010", "$96,673.48", "08/21/2024"]
    for y in (100, 112, 124):
        page.draw_line((32, y), (420, y))
    for x in (32, 115, 235, 325, 420):
        page.draw_line((x, 100), (x, 124))
    # Labels of a scattered form above the table make the page a form page.
    for i, (name, _) in enumerate([("4. GRANT NO.", ""), ("4a. FAIN", ""), ("17. VENDOR CODE", "")]):
        page.insert_text((40, 40 + 12 * i), name, fontsize=8)
    for x, h in zip(cols, header):
        page.insert_text((x, 109), h, fontsize=7)
    for x, v in zip(cols, data):
        page.insert_text((x, 121), v, fontsize=7)
    for i, v in enumerate(["L24AC00293-00", "L24AC00293", "0070233692"]):
        page.insert_text((150, 40 + 12 * i), v, fontsize=8)
    reading = _form_page_reading(page)
    assert reading is not None
    lines = reading[0].splitlines()
    assert "\t".join(header) in lines
    assert "\t".join(data) in lines
    assert "4. GRANT NO.\tL24AC00293-00" in lines


def test_pairs_kept_reads_markdown_rows_and_emphasis():
    pairs = [("Supplies", "1,000.00"), ("Travel", "3,566.00")]
    assert _pairs_kept("| e. *Supplies* | $ | 1,000.00 |\n| f. Travel | $ | 3,566.00 |", pairs) == 1.0
    assert _pairs_kept("e. Supplies $\nf. Travel $\n1,000.00\n3,566.00", pairs) == 0.0
    assert _pairs_kept("anything", []) == 1.0


def test_fast_path_markdown_that_parts_labels_from_figures_is_replaced(noa_pdf):
    broken = "e. Supplies ...$\nf. Travel ...$\n3,566.00\n1,000.00\n"
    result = SimpleNamespace(pages=[
        SimpleNamespace(page=0, markdown=broken),
        SimpleNamespace(page=1, markdown="Special conditions follow on this page."),
    ])
    texts = _fast_path_page_texts(noa_pdf, result)
    assert "e.\tSupplies\t..........$\t1,000.00" in texts[0].splitlines()
    assert texts[1] == "Special conditions follow on this page."


def test_fast_path_markdown_stands_when_pymupdf_reads_other_words(noa_pdf):
    """A font PyMuPDF decodes to glyph IDs reads as gibberish there; the
    fast path's Markdown of that page must not be swapped for it."""
    broken = ("FDP Cost Reimbursement Subaward. Pass-Through Entity terms and conditions. Subrecipient shall "
              "submit invoices monthly.\ne. Supplies ...$\nf. Travel ...$\nh. Other ...$\n3,566.00\n1,000.00\n")
    result = SimpleNamespace(pages=[SimpleNamespace(page=0, markdown=broken)])
    assert _fast_path_page_texts(noa_pdf, result) == {0: broken}


def test_fast_path_markdown_that_keeps_the_pairs_stands(noa_pdf):
    rows = "\n".join(f"| {letter} {name} | {figure} |" for _, letter, name, figure in LEFT_ROWS + BOXED_ROWS)
    result = SimpleNamespace(pages=[SimpleNamespace(page=0, markdown=rows)])
    assert _fast_path_page_texts(noa_pdf, result) == {0: rows}


def test_fast_path_skips_pages_it_was_told_to(noa_pdf):
    result = SimpleNamespace(pages=[
        SimpleNamespace(page=0, markdown="x"), SimpleNamespace(page=1, markdown="y"),
    ])
    assert _fast_path_page_texts(noa_pdf, result, skip=[0]) == {1: "y"}
