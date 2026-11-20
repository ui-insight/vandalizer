"""The NSF PAPPG and NIH GPS catalog KBs carry the guides themselves (#1006).

Both held only landing pages: three NSF navigation pages, and an NIH
JavaScript redirect stored as "Redirector". They now ship the guides' full
text as bundled files, like the eCFR regulations.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.fetch_sponsor_guides import CONTENT_CAP, _gps_page_text, html_main_text

SEEDS = Path(__file__).resolve().parents[1] / "seeds" / "knowledge_bases"


def _seed(name):
    return json.loads((SEEDS / name).read_text())


@pytest.mark.parametrize("name,min_sources", [("nsf_pappg.json", 15), ("nih_grants_policy.json", 21)])
def test_every_guide_source_is_bundled_text_of_real_length(name, min_sources):
    seed = _seed(name)
    bundled = [s for s in seed["items"][0]["sources"] if s.get("content_file")]
    assert len(bundled) >= min_sources
    urls = [s["url"] for s in seed["items"][0]["sources"]]
    assert len(urls) == len(set(urls)), "each source needs its own URL so upgrades can add it"
    for src in bundled:
        text = (SEEDS / src["content_file"]).read_text(encoding="utf-8")
        assert 2000 < len(text) < CONTENT_CAP, src["content_file"]


@pytest.mark.parametrize("name", ["nsf_pappg.json", "nih_grants_policy.json"])
def test_landing_pages_are_gone_and_retired_on_upgrade(name):
    seed = _seed(name)
    sources = seed["items"][0]["sources"]
    assert not any(s.get("url_title") == "Redirector" for s in sources)
    retired = set(seed["_seed_meta"]["retired_source_urls"])
    assert retired and not retired & {s["url"] for s in sources}


@pytest.mark.parametrize("file,phrase", [
    ("nsf-pappg-24-1-ch-2-proposal-preparation.txt", "no more than two months of their regular salary"),
    ("nsf-pappg-24-1-ch-2-proposal-preparation.txt", "Biographical Sketch"),
    ("nsf-pappg-24-1-ch-2-proposal-preparation.txt", "participant support costs"),
    ("nsf-pappg-24-1-ch-10-allowability-of-costs.txt", "Allowability"),
    ("nih-gps-fy2026-07.txt", "7.9.1 Selected Items of Cost"),
    ("nih-gps-fy2026-08.txt", "prior approval"),
])
def test_the_guides_answer_common_ra_questions(file, phrase):
    assert phrase.lower() in (SEEDS / "content" / file).read_text(encoding="utf-8").lower()


def test_gps_pages_keep_their_printed_labels_and_drop_running_headers():
    text = (SEEDS / "content" / "nih-gps-fy2026-07.txt").read_text(encoding="utf-8")
    assert "(GPS page IIA-" in text
    assert "Part II: Terms and Conditions" not in text


def test_html_main_text_keeps_headings_and_skips_navigation_and_the_toc_accordion():
    page = (
        "<html><nav>Site menu</nav><main>"
        "<div class='usa-accordion'><h2>Chapter II Table of Contents</h2><ol><li>A. Skip me</li></ol></div>"
        "<h2>C. Format of the Proposal</h2><p>Use 10-point font.</p>"
        "<ul><li>Arial</li><li>Helvetica</li></ul><button>Back to top</button>"
        "<table><tr><td>Item</td><td>Limit</td></tr></table>"
        "</main><footer>Footer</footer></html>"
    )
    text = html_main_text(page)
    assert "### C. Format of the Proposal" in text
    assert "Use 10-point font." in text and "- Arial" in text and "| Item | Limit" in text
    for gone in ("Site menu", "Table of Contents", "Skip me", "Back to top", "Footer"):
        assert gone not in text


def test_gps_page_text_strips_headers_joins_split_words_and_keeps_the_label():
    page = SimpleNamespace(get_text=lambda: (
        "Part II: Terms and Conditions of NIH Grant Awards - Subpart A\n"
        "7 Cost Consideration\n"
        "Costs must be reasonable and applic-\nable to the award.\n"
        "IIA-76\n"
    ))
    assert _gps_page_text(page, "7 Cost Consideration") == (
        "Costs must be reasonable and applicable to the award.\n(GPS page IIA-76)"
    )
