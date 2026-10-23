"""Answers must not turn "the sources don't say" into "it's allowed" (#1012).

The first measured RA run (#1005, docs/reviews/2026-10-08-ra-expected-checks.md,
gpt-oss-120b on the deployed v5 build) passed every factual question. Its only
partial answers read the sources' silence as a rule. Those answers, verbatim,
are the flagged cases below; the passing answers from the same run, which
report the gap without concluding anything from it, must stay unflagged.
"""

import pytest

from app.services.llm_service import DOCUMENT_CHAT_RULES, KB_CHAT_RULES
from app.services.silence_inference import inferences_from_silence

FLAGGED = {
    # missing-page-limit, files attached: the conclusion is the next sentence.
    "page-limit attached": (
        "- The sponsor notice explicitly says it **does not specify a page limit for the "
        "budget justification**【p. 4】. → Therefore, the budget justification may be any "
        "length (no defined maximum)."
    ),
    # missing-page-limit, knowledge base.
    "page-limit kb": (
        "- The sponsor notice does **not** set a page‑limit for the budget justification, "
        "so it may be any length. [Source: sponsor-notice.pdf]"
    ),
    # missing-eligibility, files attached.
    "eligibility attached": (
        "- The notice does **not** require the PI to be a U.S. citizen; citizenship "
        "eligibility is not specified. [p. 1]"
    ),
    "silent so allowed": "The guide is silent on foreign travel, so it is allowed.",
    "no mention so no cap": "The amendment doesn't mention a cost-share cap. This means there is no cap on cost share.",
}

NOT_FLAGGED = {
    # missing-eligibility, knowledge base: reports the gap, concludes nothing.
    "eligibility kb": (
        "- The sponsor notice does **not** list citizenship as a eligibility requirement; it "
        "only states the application must be submitted by a university research office and "
        "does not specify any US‑citizen requirement. [Source: sponsor-notice.pdf (p. 1–3)]"
    ),
    # missing-exception: the notice itself rules out a waiver process.
    "exception": (
        "**No waiver can be assumed.** - The sponsor notice caps the maximum direct‑cost request "
        "at **$180,000** and states explicitly that it **“does not give an exception or waiver "
        "process”**【p. 3】. Because the notice provides no mechanism for a waiver, you must treat "
        "the excess direct costs as non‑compliant unless the sponsor later issues a formal exception."
    ),
    "source says there is no limit": "The notice states there is no page limit for the budget justification (p. 4).",
    "gap reported, sponsor named": (
        "The notice does not specify a page limit for the budget justification. Confirm with the "
        "sponsor's guide before assuming one."
    ),
    "unchanged dates": "The amendment confirms that all project dates from the original notice remain unchanged.",
    "missing material": (
        "Budget justification – not attached in the draft proposal (see proposal-draft.pdf, p. 3). "
        "Signed community-partner letter – promised but not yet received."
    ),
    "deadline with p.m.": "- **Sponsor deadline:** November 12 2026, 5:00 p.m. Pacific Time [p. 2]",
    "gap then advice": (
        "The notice does not specify citizenship eligibility. It does not say whether non-citizens "
        "may apply, so ask the sponsor."
    ),
}


@pytest.mark.parametrize("answer", FLAGGED.values(), ids=FLAGGED.keys())
def test_a_conclusion_drawn_from_silence_is_flagged(answer):
    flagged = inferences_from_silence(answer)
    assert len(flagged) == 1
    assert "【" not in flagged[0] and "**" not in flagged[0]


@pytest.mark.parametrize("answer", NOT_FLAGGED.values(), ids=NOT_FLAGGED.keys())
def test_reporting_a_gap_or_a_stated_rule_is_not_flagged(answer):
    assert inferences_from_silence(answer) == []


def test_the_flag_quotes_the_answer_and_keeps_abbreviations_whole():
    flagged = inferences_from_silence(FLAGGED["eligibility attached"])
    assert flagged == [
        "The notice does not require the PI to be a U.S. citizen; citizenship eligibility is not specified."
    ]


def test_the_follow_on_sentence_is_included():
    (flagged,) = inferences_from_silence(FLAGGED["page-limit attached"])
    assert "does not specify a page limit" in flagged and "may be any length" in flagged


def test_at_most_three_and_no_repeats():
    answer = " ".join([FLAGGED["silent so allowed"]] * 2 + [
        "The notice is silent on cost share, so it is not required.",
        "The amendment does not mention travel, so it is permitted.",
        "The guide does not state a cap, so there is no limit on equipment.",
    ])
    flagged = inferences_from_silence(answer)
    assert len(flagged) == 3
    assert len(set(flagged)) == 3


def test_empty_answer():
    assert inferences_from_silence("") == []


@pytest.mark.parametrize("rules", [DOCUMENT_CHAT_RULES, KB_CHAT_RULES], ids=["documents", "kb"])
def test_both_chat_rule_sets_tell_the_model_not_to_read_silence_as_a_rule(rules):
    assert "When the sources don't address something" in rules
    assert "Recommend confirming with the sponsor" in rules
