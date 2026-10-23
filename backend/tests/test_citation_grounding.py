"""Page citations on attached documents are checked against the page (#998).

``derive_document_citations`` used to turn every "p. N" the model wrote into a
chip that looked exactly like a retrieved source, checking only that page N
existed. These cases use the fictional sponsor notice from the RA usability
fixtures, split into one page per section.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.chat_service import derive_document_citations

NOTICE = (Path(__file__).parent / "fixtures" / "ra_usability_sources" / "sponsor-notice.txt").read_text()


def _notice(*, approximate: bool = False):
    """The notice with a page marker before each numbered section."""
    raw = NOTICE
    offsets = [0] + [raw.index(f"\n{n}. ") + 1 for n in (2, 3, 4)]
    markers = [
        {"kind": "page", "value": i + 1, "char_offset": off, "approximate": approximate}
        for i, off in enumerate(offsets)
    ]
    return SimpleNamespace(uuid="notice-v1", title="notice-v1.pdf", raw_text=raw, text_markers=markers)


def _chip(answer: str, doc=None) -> dict:
    chips = derive_document_citations(answer, [doc or _notice()])
    assert len(chips) == 1, chips
    return chips[0]


class TestSupportedCitations:
    @pytest.mark.parametrize("answer", [
        "The maximum direct-cost request is $180,000 (p. 3).",
        "Indirect costs may not exceed 25% of direct costs (p. 3).",
        "The sponsor deadline is November 12, 2026 at 5:00 p.m. Pacific Time (p. 2).",
        "Proposals are due Nov 12 (p. 2).",
        "Equipment purchases are not permitted (p. 3).",
        "The maximum direct-cost request is $180,000. (p. 3)",
        # Paraphrases: the wording differs, the page still says it.
        "Each university can send only one application (p. 1).",
        "The notice doesn’t say whether PIs must be citizens (p. 1).",
        "The notice does not specify a page limit for the budget justification (p. 4).",
        "The sponsor deadline is 5 p.m. Pacific on November 12 (p. 2).",
    ])
    def test_a_claim_the_page_supports_is_found(self, answer):
        assert _chip(answer)["grounding"] == "found"

    def test_the_preview_is_the_supporting_passage_not_the_top_of_the_page(self):
        chip = _chip("The direct-cost cap is $180,000 (p. 3).")
        assert "$180,000" in chip["content_preview"]
        assert not chip["content_preview"].startswith("3. Budget")


class TestUnsupportedCitations:
    @pytest.mark.parametrize("answer,why", [
        ("The maximum direct-cost request is $200,000 (p. 3).", "wrong figure"),
        ("The direct-cost cap is $180,000 (p. 2).", "right figure, wrong page"),
        ("Proposals are due November 19, 2026 (p. 2).", "the amendment's date, cited to the notice"),
        ("Indirect costs are capped at 15% (p. 3).", "wrong rate"),
        ("Each campus may submit up to three proposals for a seed grant program (p. 4).", "nothing on the page"),
        # The RA test set's missing-page-limit case: the notice sets none.
        ("The budget justification is limited to 3 pages (p. 4).", "an invented limit"),
        ("The letter of support must be signed by the dean (p. 4).", "an invented signatory"),
    ])
    def test_a_claim_the_page_does_not_support_is_not_found(self, answer, why):
        chip = _chip(answer)
        assert chip["grounding"] == "not_found", why
        # The chip still opens the page, but its preview is only where to look.
        assert chip["page"] in (2, 3, 4)

    def test_a_bare_reference_has_nothing_to_check(self):
        assert _chip("See p. 4.")["grounding"] == "unchecked"

    def test_one_supported_sentence_is_enough_for_the_page(self):
        chip = _chip("The cap is $180,000 (p. 3). Equipment is not permitted (p. 3).")
        assert chip["grounding"] == "found"


class TestApproximatePages:
    def test_an_interpolated_page_also_checks_its_neighbours(self):
        """OCR page boundaries are estimates, so a claim one page off is not
        called unsupported for the estimate's error."""
        chip = _chip("The maximum direct-cost request is $180,000 (p. ~2).", _notice(approximate=True))
        assert chip["page_approximate"] is True
        assert chip["grounding"] == "found"

    def test_a_measured_page_does_not(self):
        assert _chip("The maximum direct-cost request is $180,000 (p. 2).")["grounding"] == "not_found"
