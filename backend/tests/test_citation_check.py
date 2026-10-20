"""Each knowledge-base citation in an output is checked against its passage
(app.services.citation_check): kept only when the passage states what the
statement relies on and the supporting excerpt is really in it."""

import json

from app.services.citation_check import check_citations, find_citations, quote_fragments

REASONABLE = {
    "label": "OMB UG — Subpart E—Cost Principles · part 10",
    "document_title": "Subpart E—Cost Principles", "chunk_id": "e9",
    "content": (
        "§ 200.404 Reasonable costs.\n\nA cost is reasonable if it does not exceed an amount "
        "that a prudent person would incur under the circumstances.\n(c) Market prices for "
        "comparable costs for the geographic area;"
    ),
}
ADVERTISING = {
    "label": "OMB UG — Subpart E—Cost Principles · part 46",
    "document_title": "Subpart E—Cost Principles", "chunk_id": "e45",
    "content": "§ 200.421 Advertising and public relations.\n\n(a) The term advertising costs means …",
}
SOURCES = [REASONABLE, ADVERTISING]


def _ask(verdicts):
    """A checker returning ``verdicts`` (id -> (supported, quote)) and
    recording what it was asked."""
    asked = []

    def ask(instructions, prompt):
        asked.append(prompt)
        return json.dumps({"items": [
            {"id": i, "supported": s, "quote": q} for i, (s, q) in verdicts.items()
        ]})

    return ask, asked


def test_finds_each_citation_with_the_statement_it_closes():
    text = ('{"summary": "Within the period [OMB UG — Subpart E—Cost Principles · part 46].", '
            '"rationale": "No market prices were supplied [OMB UG — Subpart E—Cost Principles · part 10]'
            '[OMB UG — Subpart E—Cost Principles · part 46]."}')
    cites = find_citations(text, SOURCES)
    assert [(c.index, c.claim) for c in cites] == [
        (1, "Within the period"),
        (0, "No market prices were supplied"),
        (1, "No market prices were supplied"),
    ]


def test_a_citation_that_ends_a_json_value_answers_for_the_whole_value():
    """The rule tells a model emitting JSON to end each value that draws on a
    passage with the tag. Judged on the last sentence alone, a rationale
    whose rule sits in its first sentence would lose its citation."""
    cite = "[OMB UG — Subpart E—Cost Principles · part 10]"
    text = (
        '{"rationale": "No quote or market price shows a prudent person would pay this. '
        f'Without such evidence, reasonableness cannot be confirmed {cite}.", '
        f'"summary": "Needs a \\"comparable\\" quote. Prices unknown {cite}", '
        f'"note": "First sentence. A mid-value citation {cite} then more text."}}'
    )
    claims = [c.claim for c in find_citations(text, SOURCES)]
    assert claims == [
        "No quote or market price shows a prudent person would pay this. "
        "Without such evidence, reasonableness cannot be confirmed",
        'Needs a \\"comparable\\" quote. Prices unknown',
        # Inside a value it still answers for its own sentence.
        "A mid-value citation",
    ]


def test_a_supported_citation_is_kept_with_its_verified_excerpt():
    text = "Market prices are needed to judge reasonableness [OMB UG — Subpart E—Cost Principles · part 10]."
    ask, asked = _ask({1: (True, "(c) Market prices for comparable costs for the geographic area")})
    check = check_citations(text, SOURCES, ask=ask)
    assert check.text == text
    assert check.kept == 1 and check.removed == []
    assert check.sources[0]["quotes"] == [{
        "claim": "Market prices are needed to judge reasonableness",
        "quote": "(c) Market prices for comparable costs for the geographic area",
    }]
    assert "§ 200.404 Reasonable costs." in asked[0]
    assert "quotes" not in SOURCES[0]  # the inputs are not mutated


def test_an_unsupported_citation_is_removed_and_reported():
    text = '{"rationale": "The date is within the period [OMB UG — Subpart E—Cost Principles · part 46]."}'
    ask, _ = _ask({1: (False, "")})
    check = check_citations(text, SOURCES, ask=ask)
    assert json.loads(check.text) == {"rationale": "The date is within the period."}
    assert check.removed == ["The date is within the period"]
    assert "quotes" not in check.sources[1]


def test_a_supported_verdict_with_an_excerpt_not_in_the_passage_is_removed():
    text = "Costs must be reasonable [OMB UG — Subpart E—Cost Principles · part 10]."
    ask, _ = _ask({1: (True, "All costs must be approved by the awarding agency in advance")})
    check = check_citations(text, SOURCES, ask=ask)
    assert check.text == "Costs must be reasonable."
    assert check.kept == 0


def test_an_excerpt_abbreviated_with_an_ellipsis_counts_when_every_piece_is_verbatim():
    pieces = quote_fragments(
        "A cost is reasonable if it does not exceed an amount … (c) Market prices for comparable costs",
        REASONABLE["content"],
    )
    assert pieces == ["A cost is reasonable if it does not exceed an amount", "(c) Market prices for comparable costs"]
    # Out of order, or one piece invented: not verbatim.
    assert quote_fragments("(c) Market prices … A cost is reasonable", REASONABLE["content"]) is None
    assert quote_fragments("A cost is reasonable … approved in advance", REASONABLE["content"]) is None
    assert quote_fragments("costs …", REASONABLE["content"]) is None


def test_when_the_check_cannot_run_every_citation_is_removed():
    def broken(instructions, prompt):
        raise RuntimeError("model down")

    text = "Reasonable [OMB UG — Subpart E—Cost Principles · part 10] and dated [OMB UG — Subpart E—Cost Principles · part 46]."
    check = check_citations(text, SOURCES, ask=broken)
    assert check.failed
    assert check.text == "Reasonable and dated."


def test_no_citations_means_no_model_call():
    ask, asked = _ask({})
    check = check_citations("Nothing cited here [N/A].", SOURCES, ask=ask)
    assert check.text == "Nothing cited here [N/A]."
    assert asked == []
