"""The built-in figure check on Pages.

Support ticket: a Page's figures had no visible origin, calculated and
hand-changed figures looked like copied ones, and nothing checked them before
saving or publishing. A page shipped with a wrong figure and a false source
note (#1122). The test case: "Change Personnel Year 2 to $142k" when the
spreadsheet says $124k.
"""

import re
from datetime import datetime, timezone
from types import SimpleNamespace

from bs4 import BeautifulSoup

from app.services import artifacts, chat_page_previews as previews, page_figures as pf
from app.services.page_printing import render_page
from tests.test_artifacts import Collection

SHEET = """## Budget
| Category | Y1 | Y2 | Y3 | Total |
| --- | --- | --- | --- | --- |
| Personnel | 250000 | 124000 | 251000 | 625000 |
| Equipment | 15000 | 15000 | 0 | 30000 |
| Total | 265000 | 139000 | 251000 | 655000 |"""
TITLE = "NIH R01 Budget Table.xlsx"

EDITED_PAGE = """<html><head></head><body><h1>NIH R01 Budget</h1>
<table><tr><th>Category</th><th>Y1</th><th>Y2</th><th>Y3</th><th>Total</th></tr>
<tr><td>Personnel</td><td>$250k</td><td><span data-source-value="$124k">$142k</span></td><td>$251k</td><td>$643k</td></tr>
<tr><td>Equipment</td><td>$15k</td><td>$15k</td><td>$0</td><td>$30k</td></tr></table>
<p>Indirect costs are 52% of direct costs.</p></body></html>"""


def _sources():
    return [(TITLE, pf._index_source(TITLE, SHEET, None))]


def _by_figure(result):
    return {f["figure"]: f for f in result["figures"]}


def test_each_figure_is_stated_calculated_manual_or_not_found():
    result = pf.check(EDITED_PAGE, _sources())
    figures = _by_figure(result)
    assert figures["$250k"] == {
        "figure": "$250k", "status": "stated", "origin": f"{TITLE} · Budget · Personnel, Y1",
        "origins": [{"text": f"{TITLE} · Budget · Personnel, Y1", "row": "Personnel", "column": "Y1"}],
    }
    assert figures["$142k"]["status"] == "manual"
    assert figures["$142k"]["source_value"] == "$124k" and figures["$142k"]["source_value_found"] is True
    assert figures["$142k"]["where"] == "Personnel"
    # The knock-on total is calculated from the manual edit, not "not found".
    assert figures["$643k"] == {"figure": "$643k", "status": "calculated", "formula": "$250k + $142k + $251k = $643k"}
    assert figures["52%"]["status"] == "unmatched"
    assert (result["stated"], result["calculated"], result["manual"], result["unmatched"]) == (5, 1, 1, 1)
    assert result["sources"] == [TITLE]


def test_the_summary_names_manual_edits_and_figures_not_found():
    assert pf.summary(pf.check(EDITED_PAGE, _sources())) == (
        "6 of 8 figures match the source (1 calculated) · 1 manual edit (Personnel) · "
        "1 not found in the source (52%)"
    )
    assert pf.summary(None) == "Figures not checked: this Page has no recorded source file."


def test_a_manual_edit_whose_source_value_is_wrong_is_reported():
    page = EDITED_PAGE.replace('data-source-value="$124k"', 'data-source-value="$128k"')
    edit = _by_figure(pf.check(page, _sources()))["$142k"]
    assert edit["source_value_found"] is False
    soup = BeautifulSoup(page, "html.parser")
    pf.annotate(soup, pf.check(page, _sources()))
    assert soup.find("span", class_="vz-figure--manual")["title"] == "Manual edit: source says $128k (not found in the source)"


def test_an_unmarked_override_is_not_found_rather_than_hidden():
    page = EDITED_PAGE.replace('<span data-source-value="$124k">$142k</span>', "$142k")
    assert _by_figure(pf.check(page, _sources()))["$142k"]["status"] == "unmatched"


def test_rounded_figures_match_to_the_precision_shown():
    result = pf.check("<p>Total direct costs: $655k ($0.66M).</p>", _sources())
    assert {f["figure"]: f["status"] for f in result["figures"]} == {"$655k": "stated", "$0.66M": "stated"}


def test_a_pdf_figure_names_its_page():
    text = "Cover page\nSubaward amount: $412,500 over two years."
    markers = [{"kind": "page", "value": 1, "char_offset": 0},
               {"kind": "page", "value": 3, "char_offset": len("Cover page\n")}]
    sources = [("subaward.pdf", pf._index_source("subaward.pdf", text, markers))]
    assert _by_figure(pf.check("<p>Award: $412,500</p>", sources))["$412,500"]["origin"] == "subaward.pdf, p. 3"


def test_hover_text_names_the_cell_a_repeated_value_comes_from():
    result = pf.check(EDITED_PAGE, _sources())
    soup = BeautifulSoup(EDITED_PAGE, "html.parser")
    pf.annotate(soup, result)
    hovers = [(s["title"], s.get_text()) for s in soup.find_all("span", class_="vz-figure")]
    assert (f"From {TITLE} · Budget · Equipment, Y1", "$15k") in hovers
    assert (f"From {TITLE} · Budget · Equipment, Y2", "$15k") in hovers
    assert ("Calculated: $250k + $142k + $251k = $643k", "$643k") in hovers
    assert ("Not found in the source files", "52%") in hovers
    note = soup.find(id="vandalizer-figure-check").get_text()
    assert note.startswith(f"Figures checked against {TITLE} on ")
    assert "1 manual edit (Personnel)" in note


def test_the_sanitizer_keeps_the_manual_edit_marker():
    cleaned, _warnings = artifacts.clean_html(EDITED_PAGE, "Budget")
    assert 'data-source-value="$124k"' in cleaned


def test_a_preview_records_the_check_and_the_saved_page_shows_it():
    db = SimpleNamespace(html_artifacts=Collection(), chat_page_previews=Collection(), smart_document=Collection())
    db.smart_document.docs.append({"uuid": "sheet", "title": TITLE, "raw_text": SHEET, "text_markers": None})
    preview = previews.prepare(db, "owner", "chat", "Budget", EDITED_PAGE, None, None,
                               {"kind": "chat", "documents": [{"uuid": "sheet", "title": TITLE, "version_number": 1}]})
    check = preview["source"]["figure_check"]
    assert check["manual"] == 1 and check["unmatched"] == 1
    saved = previews.save(db, "owner", "chat", preview["_id"])
    assert saved["figure_check"].startswith("6 of 8 figures match the source")
    page = artifacts.get(db, saved["artifact_uuid"])
    assert artifacts.metadata(page, True)["figure_check"][saved["revision"]] == saved["figure_check"]
    rendered, _csp = render_page(artifacts.revision(page), 1)
    assert 'class="vz-figure vz-figure--manual"' in rendered
    assert "Figures checked against" in rendered
    # Rendering again doesn't stack a second note.
    again, _ = render_page({**artifacts.revision(page), "html": rendered}, 1)
    assert again.count('id="vandalizer-figure-check"') == 1


def test_a_page_without_source_files_is_not_checked():
    db = SimpleNamespace(html_artifacts=Collection(), chat_page_previews=Collection(), smart_document=Collection())
    preview = previews.prepare(db, "owner", "chat", "Notes", "<p>$5,000</p>", None, None, {"kind": "chat"})
    assert "figure_check" not in preview["source"]
    rendered, _ = render_page({"title": "Notes", "html": preview["prepared_html"],
                               "created_at": datetime.now(timezone.utc), "source": preview["source"]}, 1)
    assert "vandalizer-figure-check" not in rendered and not re.search(r"vz-figure", rendered)
