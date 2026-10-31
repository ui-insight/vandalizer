"""A fast-path page whose Markdown reads across what the page stacks is read
by PyMuPDF instead.

On NSF award notices pdf-inspector's Markdown printed the contact table's
phone numbers below it in reverse column order, so the first phone after the
grants official was the program officer's; listed every budget label and
then every figure, so a model called a budgeted line blank; and ran budget
lines and their figures into one row. The content stream wrote each contact
and each budget line whole, and PyMuPDF reads it that way.
"""

from types import SimpleNamespace

import pymupdf
import pytest

from app.services.document_readers import (
    _MIN_LAYOUT_BONDS,
    _bonds_kept,
    _fast_path_page_texts,
    _layout_bonds,
    _letters_and_digits,
    _page_lines,
    _reads_the_same_words,
)

AWARD_ROWS = [  # label, value, on one row
    ("Award Number (FAIN):", "DEB-2412345"),
    ("Award Date:", "08/01/2024"),
    ("Amount Obligated by this Amendment:", "$525,000"),
    ("Total Intended Award Amount:", "$2,100,000"),
    ("Total Approved Cost Share:", "$0"),
    ("Total Amount Obligated to Date:", "$525,000"),
]
WRAPPED_ROWS = [  # a label on two lines, and its value
    (("Research and", "Development Award:"), "Yes"),
    (("Managing Division", "Abbreviation:"), "DEB"),
    (("Assistance Listing", "Number(s) and Name(s):"), "Biological Sciences"),
]
CONTACTS = [  # x, the column's lines top to bottom
    (40, ["Managing Grants Official", "(Primary Contact)", "Name: Marcus T. Hollowell",
          "Email: mhollowell@nsf.gov", "Phone: (703) 292-8101"]),
    (230, ["Awarding Official", "Name: Jannele L. Gosey", "Email: jgosey@nsf.gov"]),
    (420, ["Managing Program Officer", "Name: Sylvia A. Underbrush",
           "Email: sunderbrush@nsf.gov", "Phone: (703) 292-7101"]),
]
BUDGET_ROWS = [
    ("Senior Personnel Count", "3.00"), ("Senior Personnel Amount", "$38,237"),
    ("Post Doctoral Count", "0.00"), ("Post Doctoral Amount", "$0"),
    ("Graduate Students Count", "3.00"), ("Graduate Students Amount", "$40,200"),
    ("Undergraduate Students Count", "11.00"), ("Undergraduate Students Amount", "$157,300"),
    ("Total Salaries and Wages", "$314,212"), ("C. Fringe Benefits", "$24,225"),
    ("D. Equipment", "$6,000"), ("Domestic Travel", "$39,852"),
    ("International Travel", "$4,608"), ("Materials Supplies", "$6,348"),
    ("Publication Costs", "$14,000"), ("Total Other Direct Costs", "$70,865"),
]


def _notice_page(doc):
    """An NSF notice's page: label/value rows, then three contact columns, each
    written whole before the next, as the notice's stream writes them."""
    page = doc.new_page(width=612, height=792)
    y = 60
    for label, value in AWARD_ROWS:
        page.insert_text((40, y), label, fontsize=9)
        page.insert_text((250, y), value, fontsize=9)
        y += 18
    for (first, second), value in WRAPPED_ROWS:
        page.insert_text((40, y), first, fontsize=9)
        page.insert_text((40, y + 11), second, fontsize=9)
        page.insert_text((250, y), value, fontsize=9)
        y += 30
    page.insert_text((40, y + 10), "NSF CONTACT INFORMATION", fontsize=10)
    for x, column in CONTACTS:
        for i, line in enumerate(column):
            page.insert_text((x, y + 34 + 11 * i), line, fontsize=9)
    return page


def _budget_page(doc):
    page = doc.new_page(width=612, height=792)
    for i, (label, value) in enumerate(BUDGET_ROWS):
        page.insert_text((60, 80 + 20 * i), label, fontsize=9)
        page.insert_text((300, 80 + 20 * i), value, fontsize=9)
    return page


PROSE = [
    "The National Science Foundation hereby awards a grant for support of the project",
    "described in the proposal referenced above. This award is subject to the general",
    "terms and conditions in effect on the date of the award, and to any special terms",
    "that follow. The awardee is responsible for full compliance with all programmatic",
    "and administrative terms, and for notifying the program officer of any change in",
    "the project's scope or personnel. Funds may not be used for purposes other than",
    "those described in the approved budget without the prior written approval of the",
    "cognizant grants official, as provided in the general conditions of the award.",
]


def _prose_page(doc):
    page = doc.new_page(width=612, height=792)
    for i, line in enumerate(PROSE * 2):
        page.insert_text((72, 72 + 13 * i), line, fontsize=10)
    return page


@pytest.fixture
def notice_pdf(tmp_path):
    doc = pymupdf.open()
    _notice_page(doc)
    _budget_page(doc)
    _prose_page(doc)
    path = tmp_path / "notice.pdf"
    doc.save(path)
    return str(path)


def _award_markdown() -> str:
    rows = [f"|{label}|{value}|" for label, value in AWARD_ROWS]
    rows += [f"|{first} {second}|{value}|" for (first, second), value in WRAPPED_ROWS]
    return "\n".join([rows[0], "|---|---|", *rows[1:]])


# The contact table as pdf-inspector made it: read across in rows, and the two
# phones moved below it, the program officer's first.
CONTACTS_ACROSS = """
# NSF CONTACT INFORMATION

|Managing Grants Official|Awarding Official|Managing Program Officer|
|---|---|---|
|(Primary Contact)|Name: Jannele L. Gosey|Name: Sylvia A. Underbrush|
|Name: Marcus T. Hollowell|Email: jgosey@nsf.gov|Email: sunderbrush@nsf.gov|
|Email: mhollowell@nsf.gov|||

**Phone:** (703) 292-7101 **Phone:** (703) 292-8101
"""


def _contacts_whole() -> str:
    return "\n# NSF CONTACT INFORMATION\n\n" + "\n\n".join(
        " ".join(f"**{line}**" if i == 0 else line for i, line in enumerate(column)) for _, column in CONTACTS
    )


def _budget_labels_then_figures() -> str:
    return "\n".join(label for label, _ in BUDGET_ROWS) + "\n" + "\n".join(value for _, value in BUDGET_ROWS)


def _result(*markdowns):
    return SimpleNamespace(pages=[SimpleNamespace(page=n, markdown=md) for n, md in enumerate(markdowns)])


def _line_after(text: str, line: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[lines.index(line) + 1]


def test_a_contact_table_read_across_is_replaced_so_each_phone_follows_its_official(notice_pdf):
    texts = _fast_path_page_texts(notice_pdf, _result(_award_markdown() + CONTACTS_ACROSS))
    assert _line_after(texts[0], "Email: mhollowell@nsf.gov") == "Phone: (703) 292-8101"
    assert _line_after(texts[0], "Email: sunderbrush@nsf.gov") == "Phone: (703) 292-7101"
    assert "|" not in texts[0]


def test_budget_labels_printed_before_their_figures_are_replaced(notice_pdf):
    texts = _fast_path_page_texts(notice_pdf, _result("x", _budget_labels_then_figures()))
    for label, value in BUDGET_ROWS:
        assert _line_after(texts[1], label) == value


def test_markdown_that_keeps_each_column_whole_stands(notice_pdf):
    markdown = _award_markdown() + _contacts_whole()
    rows = "|Senior Personnel Count|3.00|\n|---|---|\n" + "\n".join(f"|{lab}|{val}|" for lab, val in BUDGET_ROWS[1:])
    assert _fast_path_page_texts(notice_pdf, _result(markdown, rows)) == {0: markdown, 1: rows}


def test_a_prose_page_is_left_as_the_markdown_reads_it(notice_pdf):
    prose = " ".join(PROSE * 2)
    as_table = "|Terms|\n|---|\n|" + prose + "|"
    assert _fast_path_page_texts(notice_pdf, _result("x", "y", prose))[2] == prose
    assert _fast_path_page_texts(notice_pdf, _result("x", "y", as_table))[2] == as_table


def test_markdown_stands_when_pymupdf_reads_other_words(notice_pdf):
    """A font PyMuPDF decodes to glyph IDs reads as gibberish there; the
    Markdown of that page must not be swapped for it, however it is laid out."""
    other = CONTACTS_ACROSS + (
        "\nFDP Cost Reimbursement Subaward. Pass-Through Entity terms and conditions apply. Subrecipient "
        "shall submit invoices monthly to the pass-through entity, citing purchase order numbers, with "
        "certification signatures attached.\n"
    )
    texts = _fast_path_page_texts(notice_pdf, _result(_award_markdown() + other))
    assert texts[0] == _award_markdown() + other


def test_layout_bonds_are_stacked_lines_and_labels_beside_figures():
    doc = pymupdf.open()
    lines = _page_lines(_notice_page(doc))
    bonds = {(a.strip(), b.strip()) for a, b, _ in _layout_bonds(lines)}
    assert ("Email: mhollowell@nsf.gov", "Phone: (703) 292-8101") in bonds
    assert ("Research and", "Development Award:") in bonds
    assert ("Award Date:", "08/01/2024") in bonds
    # Side by side is not stacked: one column's header with the next column's.
    assert ("Managing Grants Official", "Awarding Official") not in bonds
    assert len(bonds) >= _MIN_LAYOUT_BONDS


def test_figures_stacked_on_figures_are_not_bonds():
    doc = pymupdf.open()
    page = doc.new_page()
    for i, figure in enumerate(["1,000.00", "2,000.00", "3,000.00"]):
        page.insert_text((300, 100 + 11 * i), figure, fontsize=9)
    assert _layout_bonds(_page_lines(page)) == []


def test_too_few_bonds_say_nothing():
    bonds = [("Name: A", "Email: a@x.gov", 0)] * (_MIN_LAYOUT_BONDS - 1)
    assert _bonds_kept("nothing alike", bonds) is None
    assert _bonds_kept("Name: A Email: a@x.gov", bonds + [bonds[0]]) == 1.0


def test_readings_compare_by_letters_and_digits():
    assert _letters_and_digits("Initiative,¹⁰ a **Multi-**\nYear |plan|") == "initiative10amultiyearplan"
    md = "<u>[Award](https://x.gov/a)</u> From: A <a@b.test>"
    assert _letters_and_digits(md, markdown=True) == "awardfromaabtest"


def test_markdown_that_repeats_a_block_still_reads_the_same_words():
    reading = "Principal Investigator: Michael S Strickland mstrickland@uidaho.edu Regents of the University of Idaho"
    markdown = reading + "\n|Strickland|mstrickland@uidaho.edu|of Idaho|"
    assert _reads_the_same_words(markdown, reading)
    assert not _reads_the_same_words(markdown, ")'3&RVW5HLPEXUVHPHQW")
