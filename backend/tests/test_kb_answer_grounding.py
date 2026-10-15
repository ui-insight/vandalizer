"""Figures in a KB answer must come from the snippets the model was shown."""

import json

from app.services.kb_answer_grounding import tool_output_as_source, unsupported_figures

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
