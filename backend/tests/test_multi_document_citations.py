"""Page chips for answers that cite several attached documents (#1011).

In the first measured RA run (#1005, gpt-oss-120b on the deployed v5 build),
8 of 12 attached-document answers had no citation chips: each had two or
three files attached, and a page chip was only made when exactly one attached
document had pages. The model named the file every time, in its own 【…】
syntax or in prose. These are those answers, verbatim, against the same
fictional sources paged the same way.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.chat_service import derive_document_citations
from app.services.citation_grounding import normalize_citation_markup

SRC = Path(__file__).parent / "fixtures" / "ra_usability_sources"


def _doc(uuid, title, pages):
    raw, markers = "", []
    for i, page in enumerate(pages, 1):
        markers.append({"kind": "page", "value": i, "char_offset": len(raw)})
        raw += page.strip() + "\n"
    return SimpleNamespace(uuid=uuid, title=title, raw_text=raw, text_markers=markers)


def _sources():
    notice = (SRC / "sponsor-notice.txt").read_text()
    parts = re.split(r"\n(?=\d\. )", notice.strip())
    proposal = (SRC / "proposal-draft.txt").read_text()
    head, rest = proposal.split("\nDraft budget", 1)
    budget, notes = rest.split("\nReadiness notes", 1)
    return {
        "notice": _doc("notice", "sponsor-notice.pdf", [parts[0] + "\n" + parts[1]] + parts[2:]),
        "amend": _doc("amend", "sponsor-amendment.pdf", [(SRC / "sponsor-amendment.txt").read_text()]),
        "prop": _doc("prop", "proposal-draft.pdf", [head, "Draft budget" + budget, "Readiness notes" + notes]),
    }


def _chips(answer, *names):
    docs = _sources()
    chips = derive_document_citations(normalize_citation_markup(answer), [docs[n] for n in names])
    return [(c["document_uuid"], c["page"], c["grounding"]) for c in chips]


class TestAnswersFromTheMeasuredRun:
    def test_deadline_amended_cites_three_files(self):
        answer = (
            "- **November 19, 2026 at 5:00 p.m. PT** – the amendment supersedes the original deadline "
            "(see sponsor‑amendment.pdf, p. 1)【p. 1】.\n"
            "- The proposal draft (proposal‑draft.pdf, p. 1) lists an internal tracking deadline of "
            "**November 12, 2026 at 5:00 p.m. PT**, matching the original notice deadline "
            "(see sponsor‑notice.pdf, p. 2)【p. 2】."
        )
        assert _chips(answer, "notice", "amend", "prop") == [
            ("amend", 1, "found"), ("prop", 1, "found"), ("notice", 2, "found"),
        ]

    def test_internal_deadline_in_fullwidth_markup(self):
        answer = (
            "- No, the institutional review deadline stayed the same: **November 9 2026 at noon "
            "Pacific Time**【sponsor-notice.pdf†p. 2】【sponsor-amendment.pdf†p. 1】."
        )
        assert _chips(answer, "notice", "amend") == [("notice", 2, "found"), ("amend", 1, "found")]

    def test_page_then_file_in_brackets(self):
        answer = (
            "- **Budget justification** – not attached in the draft proposal [p. 3 of proposal‑draft.pdf].\n"
            "The sponsor notice lists the required items (project narrative, itemized budget, budget "
            "justification, signed letter) [p. 4 of sponsor‑notice.pdf]."
        )
        assert _chips(answer, "notice", "prop") == [("prop", 3, "found"), ("notice", 4, "found")]

    def test_a_figure_drawn_from_two_pages_cited_side_by_side(self):
        """$50,000 and $200,000 are on the proposal's budget page, 25% on the
        notice's: neither page holds the claim alone, together they do."""
        answer = (
            "- **Indirect‑cost rate used:** 25% (the proposal lists $50,000 indirect on $200,000 "
            "direct = 25%)【proposal-draft.pdf p. 2】【sponsor-notice.pdf p. 3】."
        )
        assert _chips(answer, "notice", "prop") == [("prop", 2, "found"), ("notice", 3, "found")]

    def test_bare_pages_with_two_files_attached_still_make_no_chip(self):
        answer = (
            "- The sponsor notice caps the maximum direct‑cost request at **$180,000** [p. 3].\n"
            "- The proposal draft lists a **direct‑cost total of $200,000** [p. 2]."
        )
        assert _chips(answer, "notice", "prop") == []


class TestWrongCitationsAreStillCaught:
    def test_a_wrong_figure_is_not_found_on_its_named_page(self):
        answer = "The cap is $150,000 (sponsor-notice.pdf, p. 3). The draft asks for $200,000 (proposal-draft.pdf, p. 2)."
        assert _chips(answer, "notice", "prop") == [("notice", 3, "not_found"), ("prop", 2, "found")]

    def test_the_right_fact_cited_to_the_wrong_file(self):
        assert _chips("The direct-cost cap is $180,000 (proposal-draft.pdf, p. 2).", "notice", "prop") == [
            ("prop", 2, "not_found"),
        ]

    def test_each_reference_in_one_sentence_is_judged_on_its_own_clause(self):
        answer = "The draft's $200,000 (proposal-draft.pdf, p. 2) exceeds the $180,000 cap (sponsor-notice.pdf, p. 3)."
        assert _chips(answer, "notice", "prop") == [("prop", 2, "found"), ("notice", 3, "found")]

    def test_side_by_side_pages_do_not_rescue_a_page_that_adds_nothing(self):
        """The amendment states none of these figures; citing it next to the
        budget page must not borrow the budget page's support."""
        answer = "Direct costs total $200,000 (proposal-draft.pdf, p. 2) (sponsor-amendment.pdf, p. 1)."
        assert ("amend", 1, "not_found") in _chips(answer, "prop", "amend")


@pytest.mark.parametrize("raw,expected", [
    ("Nov 12【p. 2】.", "Nov 12 (p. 2)."),
    ("Nov 9【sponsor-notice.pdf†p. 2】【sponsor-amendment.pdf†p. 1】.", "Nov 9 (sponsor-notice.pdf, p. 2) (sponsor-amendment.pdf, p. 1)."),
    ("Capped【Source: notice.pdf】", "Capped [Source: notice.pdf]"),
    ("See this【3†L4-L10】 passage.", "See this passage."),
    ("No markup (p. 2).", "No markup (p. 2)."),
])
def test_fullwidth_citation_markup_is_rewritten(raw, expected):
    assert normalize_citation_markup(raw) == expected
