"""A KB citation names the page holding the claim, not the page the question
matched (#1058).

In #1005 run 2 a proposal-draft chunk crossing a page break was labelled by
the page that best matched the question, and the answer's project dates
(page 1) were cited as "proposal-draft.pdf, p. 3".
"""

from app.services.kb_answer_grounding import expand_snippet_refs

DATES = "Community Resilience Pilot. Project period: July 1, 2027 through June 30, 2028."
NOTES = "Readiness notes. The budget justification is not yet attached. A partner has promised a letter."


def _source(page=3):
    return {"ref": 1, "document_title": "proposal-draft.pdf", "cite_label": f"proposal-draft.pdf, p. {page}",
            "page": page, "page_end": None, "page_approximate": False}


def test_the_label_and_chip_move_to_the_page_holding_the_claim():
    src = _source()
    out = expand_snippet_refs("The project starts July 1, 2027 [S1].", [src], {1: [(1, DATES), (3, NOTES)]})
    assert out == "The project starts July 1, 2027 [Source: proposal-draft.pdf, p. 1]."
    assert (src["page"], src["cite_label"]) == (1, "proposal-draft.pdf, p. 1")


def test_two_claims_on_two_pages_each_get_their_page_and_the_chip_stays():
    src = _source()
    out = expand_snippet_refs(
        "The project starts July 1, 2027 [S1]. The budget justification is not yet attached [S1].",
        [src], {1: [(1, DATES), (3, NOTES)]},
    )
    assert "July 1, 2027 [Source: proposal-draft.pdf, p. 1]" in out
    assert "not yet attached [Source: proposal-draft.pdf, p. 3]" in out
    assert src["page"] == 3


def test_a_claim_neither_page_supports_keeps_the_label():
    src = _source()
    out = expand_snippet_refs("Equipment is $5,000 [S1].", [src], {1: [(1, DATES), (3, NOTES)]})
    assert out == "Equipment is $5,000 [Source: proposal-draft.pdf, p. 3]."
    assert src["page"] == 3


def test_a_single_page_snippet_is_unchanged():
    src = _source(page=2)
    assert expand_snippet_refs("Direct costs are $200,000 [S1].", [src]) == (
        "Direct costs are $200,000 [Source: proposal-draft.pdf, p. 2]."
    )
