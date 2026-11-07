"""Figures in a KB answer must come from the snippets the model was shown."""

import json
from pathlib import Path

from app.services.kb_answer_grounding import tool_output_as_source, unsupported_citations, unsupported_figures

# The § 200.501 text the 2 CFR 200 KB actually holds (2024 revision).
SNIPPETS = (
    "**Source: Subpart F—Audit Requirements**\n"
    "(a) Audit required. A non-Federal entity that expends $1,000,000 or more "
    "during the non-Federal entity's fiscal year in Federal awards must have a "
    "single or program-specific audit conducted for that year.\n"
    "Equal to or exceed $1,000,000 but less than or equal to $34 million\n"
    "a de minimis indirect cost rate of up to 15 percent of modified total "
    "direct costs (MTDC)."
)


def test_flags_the_superseded_threshold_from_the_ticket():
    answer = "The single audit threshold is **$750,000** in Federal expenditures."
    assert unsupported_figures(answer, SNIPPETS) == ["$750,000"]


def test_the_current_threshold_is_supported():
    answer = "Entities expending $1,000,000 or more need a single audit [Source: Subpart F]."
    assert unsupported_figures(answer, SNIPPETS) == []


def test_values_are_compared_not_strings():
    answer = "The threshold is $1 million; Type A tops out at $34,000,000; de minimis is 15%."
    assert unsupported_figures(answer, SNIPPETS) == []


def test_scaled_forms_are_checked_too():
    assert unsupported_figures("It used to be $750K.", SNIPPETS) == ["$750K"]
    assert unsupported_figures("It is $1.5 million.", SNIPPETS) == ["$1.5 million"]


def test_a_percent_is_not_supported_by_the_same_dollar_number():
    assert unsupported_figures("The rate is 34%.", SNIPPETS) == ["34%"]
    assert unsupported_figures("The fee is $15.", SNIPPETS) == ["$15"]


def test_a_percentage_in_words_is_checked():
    assert unsupported_figures("The de minimis rate is 10 percent.", SNIPPETS) == ["10 percent"]


def test_section_numbers_dates_and_counts_are_left_alone():
    answer = "See § 200.501 (effective October 1, 2024); there are 3 audit types."
    assert unsupported_figures(answer, SNIPPETS) == []


def test_reports_each_figure_once_in_answer_order():
    answer = "Either 12% or $750,000 — and again, $750,000, not 12%."
    assert unsupported_figures(answer, SNIPPETS) == ["12%", "$750,000"]


def test_a_figure_the_question_supplied_is_supported_when_passed_in():
    # chat_service passes the question alongside the snippets, so answering
    # "is it still $750,000?" with "no, not $750,000" is not flagged.
    question = "Is the single audit threshold still $750,000?"
    answer = "No — not $750,000; it is now $1,000,000."
    assert unsupported_figures(answer, f"{SNIPPETS}\n{question}") == []


def test_no_snippets_means_every_figure_is_unsupported():
    assert unsupported_figures("It is $750,000.", "") == ["$750,000"]


def test_empty_answer():
    assert unsupported_figures("", SNIPPETS) == []


# Support ticket: chat repeated what its validation and optimization tools
# returned and flagged every number as possibly from general knowledge.
VALIDATION_RESULT = json.dumps({
    "extraction_set": "Award terms",
    "num_runs": 3,
    "accuracy": 0.8234,
    "consistency": 0.92,
    "score": 85.1,
    "challenging_fields": [{"field": "PI", "accuracy": 0.77, "consistency": 0.96}],
})


def test_validation_scores_on_a_0_to_1_scale_support_their_percents():
    answer = (
        "Accuracy came in at 82% with 92% consistency (score 85.1%). "
        "PI is the weakest field: 77% accurate, 96% consistent."
    )
    assert unsupported_figures(answer, tool_output_as_source(VALIDATION_RESULT)) == []


def test_optimizer_score_percent_and_cost_are_supported():
    result = json.dumps({"score_percent": 91, "estimated_cost_usd": 1.37, "tokens_used": 412000})
    answer = "The best config scored 91% and cost about $1 ($1.37)."
    assert unsupported_figures(answer, tool_output_as_source(result)) == []


def test_figures_the_tool_did_not_return_are_still_flagged():
    answer = "Accuracy was 88%, it ran 3 times, and it cost $412,000."
    # num_runs and tokens_used are not percents or dollars, and 0.8234 is
    # not 88%.
    result = json.dumps({"accuracy": 0.8234, "num_runs": 3, "tokens_used": 412})
    assert unsupported_figures(answer, tool_output_as_source(result)) == ["88%", "$412,000"]


def test_a_plain_text_tool_result_still_reads_bare_amounts_as_dollars():
    assert unsupported_figures("Budget: $1,250,000.", tool_output_as_source("budget 1250000")) == []


# --- Citations: the cited source must contain what the answer credits to it ---

# "Subaward Policies" ticket: the 200.332 source was a scraped eCFR page with
# the title and site chrome but none of the rule text.
STUB_332 = "2 CFR 200.332 — Requirements for pass-through entities."
STUB_TEXT = (
    "eCFR :: 2 CFR 200.332 -- Requirements for pass-through entities. "
    "An official website of the United States government. Enhanced Content. "
    "Displaying title 2, up to date as of 10/10/2026. Timeline. Published Edition."
)
QUESTION = (
    "According to 2 CFR 200.332 in this knowledge base, what must a "
    "pass-through entity do to monitor a subrecipient?"
)
RECALLED = (
    "A pass-through entity must:\n"
    "- Review financial and performance reports the subrecipient submits.\n"
    "- Follow up on deficiencies found through audits and on-site reviews, and "
    "ensure timely corrective action.\n"
    "- Issue a management decision on audit findings within six months.\n"
    "- Consider site visits, training and technical assistance as needed.\n\n"
    f"[Source: {STUB_332}]"
)
RULE_TEXT = (
    "(e) Monitor the activity of the subrecipient as necessary to ensure that the "
    "subaward is used for authorized purposes, in compliance with the terms and "
    "conditions of the subaward. Pass-through entity monitoring of the "
    "subrecipient must include: (1) Reviewing financial and performance reports "
    "required by the pass-through entity. (2) Following-up and ensuring that the "
    "subrecipient takes timely and appropriate action on all deficiencies "
    "detected through audits, on-site reviews, and written confirmation from the "
    "subrecipient. (3) Issuing a management decision for applicable audit "
    "findings pertaining only to the Federal award provided to the subrecipient."
)
GROUNDED = (
    "Monitoring must include:\n"
    "- Reviewing the financial and performance reports the pass-through requires.\n"
    "- Following up on deficiencies detected through audits and on-site reviews, "
    "making sure the subrecipient takes timely, appropriate action.\n"
    "- Issuing a management decision on audit findings tied to its award.\n\n"
    f"[Source: {STUB_332}]"
)


def test_flags_the_answer_from_the_ticket():
    assert unsupported_citations(RECALLED, {STUB_332: STUB_TEXT}, QUESTION) == [
        STUB_332
    ]


def test_the_same_answer_is_supported_by_the_rule_text():
    assert unsupported_citations(GROUNDED, {STUB_332: RULE_TEXT}, QUESTION) == []


def test_a_citation_naming_a_source_that_was_not_retrieved_is_flagged():
    assert unsupported_citations(RECALLED, {"Subpart F": RULE_TEXT}, QUESTION) == [
        STUB_332
    ]


def test_citations_name_the_source_loosely():
    # A page locator, a dropped period, or the title cut short still finds
    # the snippet the model was shown.
    for cited in ("2 CFR 200.332 — Requirements for pass-through entities (p. 3)",
                  "2 CFR 200.332"):
        answer = GROUNDED.replace(STUB_332, cited)
        assert unsupported_citations(answer, {STUB_332: RULE_TEXT}) == []


def test_adjacent_citations_share_the_span_before_them():
    answer = GROUNDED.replace(f"[Source: {STUB_332}]", f"[Source: {STUB_332}] [Source: Stub]")
    assert unsupported_citations(answer, {STUB_332: RULE_TEXT, "Stub": STUB_TEXT}) == []


def test_text_marked_as_general_knowledge_is_not_attributed_to_the_citation():
    answer = (
        "_Beyond the retrieved sources:_ Many universities also run annual "
        "subrecipient risk questionnaires and desk reviews.\n\n" + GROUNDED
    )
    assert unsupported_citations(answer, {STUB_332: RULE_TEXT}) == []


def test_short_fragments_and_uncited_answers_are_left_alone():
    assert unsupported_citations("See the policy. [Source: Stub]", {"Stub": STUB_TEXT}) == []
    assert unsupported_citations("No citation here at all.", {}) == []
    assert unsupported_citations("", {}) == []


# 52 answers written by a separate model, which had not seen this check, from
# real 2 CFR 200 snippets: faithful (heavy paraphrase included), written from
# memory against a title-only page, and citing a real but off-topic snippet.
CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "kb_citation_support_cases.json").read_text()
)


def _flags(case):
    texts: dict[str, str] = {}
    for s in case["snippets"]:
        texts[s["source"]] = texts.get(s["source"], "") + "\n" + s["text"]
    return unsupported_citations(case["answer"], texts, case["question"])


def test_corpus_faithful_answers_raise_no_flag():
    flagged = [c["id"] for c in CASES if c["kind"] == "grounded" and _flags(c)]
    assert flagged == []


def test_corpus_title_only_sources_are_always_flagged():
    missed = [c["id"] for c in CASES if c["kind"] == "stub" and not _flags(c)]
    assert missed == []


def test_corpus_off_topic_citations_are_mostly_flagged():
    # Two of twelve share enough vocabulary with the snippet to clear the bar:
    # the cost of keeping faithful paraphrase unflagged (see _MIN_SUPPORT).
    missed = sorted(c["id"] for c in CASES if c["kind"] == "wrong_source" and not _flags(c))
    assert missed == ["w_308_travel", "w_332_mon"]


# --- Passages the agent's own search_knowledge_base calls returned ---------
#
# The check read only the pre-fetched KB snippets. A correct citation of a
# passage the agent searched for was flagged as not retrieved, and an answer
# with no KB attached was never checked however the agent searched.


def _kb_search(*entries: tuple[str, str]) -> dict:
    return {
        "tool_name": "search_knowledge_base",
        "tool_call_id": "t1",
        "content": [{"source_name": name, "content": text} for name, text in entries],
    }


def _miscited(answer: str, tool_results: list[dict], history=(), *, kbs_attached: bool):
    from app.services.chat_service import _miscited_sources

    return _miscited_sources(
        answer, QUESTION, [], tool_results, list(history), kbs_attached=kbs_attached,
    )


def test_a_citation_of_a_passage_the_agent_searched_is_supported():
    results = [_kb_search((STUB_332, RULE_TEXT))]
    assert _miscited(GROUNDED, results, kbs_attached=True) == []


def test_a_title_only_passage_the_agent_searched_is_flagged():
    results = [_kb_search((STUB_332, STUB_TEXT))]
    assert _miscited(RECALLED, results, kbs_attached=True) == [STUB_332]


def test_checked_when_the_agent_searched_with_no_kb_attached():
    results = [_kb_search((STUB_332, STUB_TEXT))]
    assert _miscited(RECALLED, results, kbs_attached=False) == [STUB_332]
    # Nothing attached and nothing searched: nothing to check against.
    assert _miscited(RECALLED, [], kbs_attached=False) == []


def test_an_earlier_turns_search_counts():
    from pydantic_ai.messages import ModelRequest, ToolReturnPart

    history = [ModelRequest(parts=[ToolReturnPart(
        tool_name="search_knowledge_base", tool_call_id="old",
        content=[{"source_name": STUB_332, "content": STUB_TEXT}],
    )])]
    assert _miscited(RECALLED, [], history, kbs_attached=False) == [STUB_332]


def test_other_tools_results_are_not_sources():
    results = [{"tool_name": "fetch_url", "tool_call_id": "t2",
                "content": [{"source_name": STUB_332, "content": RULE_TEXT}]}]
    assert _miscited(GROUNDED, results, kbs_attached=True) == [STUB_332]
