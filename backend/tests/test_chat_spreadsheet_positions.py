"""A reply's yearly figures are held to the spreadsheet row and year they name.

Support ticket (NIH_R01_Budget_Clean.xlsx, "Summarize this budget"): Years 1
to 4 were all shown as $246,000 (Year 4's total) beside a $1,250,000 grand
total the years did not reach, and no warning appeared. Every number is in the
file, so only a check by position catches it.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import RetryPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.services.chat_spreadsheet_figures import (
    NOTE_HEADING,
    require_spreadsheet_figures,
    spreadsheet_figure_issues,
    spreadsheet_figures_note,
)
from app.services.document_readers import extract_text_from_xlsx
from tests.test_chat_output import chat_harness as chat_harness

ROWS = {
    "Personnel": [200000, 150000, 150000, 152000, 140000],
    "Equipment": [15000, 15000, 0, 0, 0],
    "Travel": [8000, 6000, 6000, 12000, 5000],
    "Supplies": [20000, 6000, 20000, 15000, 15000],
    "Other": [61000, 63000, 65000, 67000, 59000],
}
TOTALS = [304000, 240000, 241000, 246000, 219000]


@pytest.fixture(scope="module")
def sheet(tmp_path_factory):
    """The workbook's text exactly as chat receives it: bare numbers in a pipe table."""
    assert [sum(col) for col in zip(*ROWS.values())] == TOTALS
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Budget"
    ws.append(["NIH R01 Budget"])
    ws.append(["Category", "Year 1", "Year 2", "Year 3", "Year 4", "Year 5", "Total"])
    for label, amounts in ROWS.items():
        ws.append([label, *amounts, sum(amounts)])
    ws.append(["Total Costs", *TOTALS, sum(TOTALS)])
    for row in ws.iter_rows(min_row=3, min_col=2):
        for cell in row:
            cell.number_format = '"$"#,##0'
    path = tmp_path_factory.mktemp("budget") / "NIH_R01_Budget_Clean.xlsx"
    wb.save(path)
    text = extract_text_from_xlsx(str(path))
    assert "304000" in text and "$304,000" not in text
    return text


# Run 1 of the ticket.
REPEATED_YEAR = """## Budget summary

| Year | Total |
| --- | ---: |
| Year 1 | $246,000 |
| Year 2 | $246,000 |
| Year 3 | $246,000 |
| Year 4 | $246,000 |
| Year 5 | $219,000 |
| **Total** | **$1,250,000** |

The document shows the same total ($246,000) for Years 1–4.
"""
CORRECT = """| Category | Year 1 | Year 2 | Year 3 | Year 4 | Year 5 | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Personnel | $200,000 | $150,000 | $150,000 | $152,000 | $140,000 | $792,000 |
| Travel | $8,000 | $6,000 | $6,000 | $12,000 | $5,000 | $37,000 |
| **Total Costs** | **$304,000** | **$240,000** | **$241,000** | **$246,000** | **$219,000** | **$1,250,000** |

Travel is $8,000 in Year 1 and $12,000 in Year 4.
"""


def _texts(issues):
    return [issue.text for issue in issues]


def test_one_years_total_shown_for_other_years_is_caught_cell_by_cell(sheet):
    issues = _texts(spreadsheet_figure_issues(REPEATED_YEAR, [sheet]))
    assert "Total, Year 1: the reply shows $246,000; the spreadsheet has $304,000." in issues
    assert "Total, Year 2: the reply shows $246,000; the spreadsheet has $240,000." in issues
    assert "Total, Year 3: the reply shows $246,000; the spreadsheet has $241,000." in issues
    assert not any("Year 4:" in text or "Year 5:" in text for text in issues)


def test_years_that_do_not_add_up_to_the_total_shown_are_caught_without_any_spreadsheet():
    issues = _texts(spreadsheet_figure_issues(REPEATED_YEAR, []))
    assert issues == ["Total: Year 1 to Year 5 as shown add up to $1,203,000, not the $1,250,000 total shown."]


def test_year_columns_layout_is_checked_the_same_way(sheet):
    wrong = CORRECT.replace("**$304,000**", "**$246,000**").replace("| $8,000 |", "| $12,000 |")
    issues = _texts(spreadsheet_figure_issues(wrong, [sheet]))
    assert "Total Costs, Year 1: the reply shows $246,000; the spreadsheet has $304,000." in issues
    assert "Travel, Year 1: the reply shows $12,000; the spreadsheet has $8,000." in issues


def test_categories_that_do_not_reach_the_total_row_are_caught_unless_the_table_is_partial(sheet):
    wrong = "| Item | Year 1 | Year 2 |\n| --- | --- | --- |\n| Lab | $10,000 | $12,000 |\n| Field | $5,000 | $5,000 |\n| Total | $20,000 | $17,000 |\n"
    assert _texts(spreadsheet_figure_issues(wrong, [])) == [
        "Year 1: the categories shown add up to $15,000, not the $20,000 in the Total row.",
    ]
    # CORRECT shows two of the spreadsheet's five categories beside the full total.
    assert spreadsheet_figure_issues(CORRECT, [sheet]) == []


def test_a_correct_summary_raises_nothing(sheet):
    assert spreadsheet_figure_issues(CORRECT, [sheet]) == []
    assert spreadsheet_figures_note(CORRECT, [sheet]) == ""


def test_rounded_figures_and_a_table_of_some_years_are_not_faulted(sheet):
    partial = """| Category | Year 1 | Year 2 | Total |
| --- | ---: | ---: | ---: |
| Travel | $8k | $6k | $37k |
| Total Costs | $304k | $240k | $1.25M |
"""
    assert spreadsheet_figure_issues(partial, [sheet]) == []


@pytest.mark.parametrize("sentence,expected", [
    # Run 3 of the ticket: the file has $8,000 in Year 1 and $12,000 in Year 4.
    ("Travel is modest, at $8k in Y4.", "Travel, Year 4: the reply says $8k; the spreadsheet has $12,000."),
    ("Equipment — Year 1: $50,000 for microscopy.", "Equipment, Year 1: the reply says $50,000; the spreadsheet has $15,000."),
])
def test_a_sentence_naming_one_row_and_a_year_is_checked(sheet, sentence, expected):
    assert _texts(spreadsheet_figure_issues(sentence, [sheet])) == [expected]


@pytest.mark.parametrize("sentence", [
    "Travel is $8,000 in Year 1 and $12,000 in Year 4.",
    "Travel: $8,000 (Year 1), $6,000 (Year 2).",
    "Travel rises by $6,000 in Year 4.",  # a change, not a cell
    "Personnel and Travel together come to $208,000 in Year 1.",  # two rows named
    "Subawards are $40,000 in Year 1.",  # not a row of the spreadsheet
])
def test_sentences_the_check_cannot_place_are_left_alone(sheet, sentence):
    assert spreadsheet_figure_issues(sentence, [sheet]) == []


def test_the_note_lists_cells_and_year_sums_but_not_sentences(sheet):
    note = spreadsheet_figures_note(REPEATED_YEAR + "\nTravel is $8k in Y4.", [sheet])
    assert note.startswith(f"\n\n{NOTE_HEADING}")
    assert "Total, Year 1: the reply shows $246,000; the spreadsheet has $304,000." in note
    assert "add up to $1,203,000, not the $1,250,000 total shown" in note
    assert "Travel" not in note


def test_two_rows_with_one_label_are_not_guessed_between(sheet):
    second = sheet.replace("304000", "999000")
    assert not any(text.startswith("Total, Year 1:") for text in _texts(spreadsheet_figure_issues(REPEATED_YEAR, [sheet, second])))


def _agent(replies):
    async def model(messages, info: AgentInfo):
        retried = any(isinstance(p, RetryPromptPart) for p in messages[-1].parts)
        yield replies[1] if retried and len(replies) > 1 else replies[0]

    agent = Agent(FunctionModel(stream_function=model), deps_type=SimpleNamespace)
    agent.output_validator(require_spreadsheet_figures)
    return agent


async def _run(agent, deps):
    async with agent.iter("Summarize this budget.", deps=deps) as run:
        async for node in run:
            if Agent.is_model_request_node(node) or Agent.is_call_tools_node(node):
                async with node.stream(run.ctx) as stream:
                    async for _ in stream:
                        pass
    return run.result


def _deps():
    return SimpleNamespace(context_document_uuids=["budget"], documents_read=[], spreadsheet_retry_used=False)


async def test_a_wrong_table_is_sent_back_once_with_the_cells_to_correct(sheet):
    deps = _deps()
    with patch("app.services.chat_spreadsheet_figures._document_texts", AsyncMock(return_value=[sheet])):
        result = await _run(_agent([REPEATED_YEAR, CORRECT]), deps)
    assert result.output == CORRECT
    assert deps.spreadsheet_retry_used
    retry = next(p for m in result.all_messages() for p in m.parts if isinstance(p, RetryPromptPart))
    assert "Total, Year 1: the reply shows $246,000; the spreadsheet has $304,000." in retry.content
    assert "never repeat one year's figure for another year" in retry.content


async def test_a_correct_table_is_not_sent_back_and_a_second_wrong_one_is_not_looped(sheet):
    with patch("app.services.chat_spreadsheet_figures._document_texts", AsyncMock(return_value=[sheet])):
        deps = _deps()
        assert (await _run(_agent([CORRECT]), deps)).output == CORRECT
        assert not deps.spreadsheet_retry_used
        assert (await _run(_agent([REPEATED_YEAR, REPEATED_YEAR]), _deps())).output == REPEATED_YEAR


async def _reply(chat_harness, sheet, answer):
    chat_harness.conversation.get_file_attachments.return_value = [
        SimpleNamespace(filename="NIH_R01_Budget_Clean.xlsx", file_type=".xlsx", content=sheet),
    ]

    async def respond(messages, info):
        yield answer

    chunks = await chat_harness.run(Agent(FunctionModel(stream_function=respond)), message="Summarize this budget.")
    return "".join(c["content"] for c in chunks if c.get("kind") == "text")


async def test_a_reply_that_still_disagrees_reaches_the_user_with_the_differences_listed(chat_harness, sheet):
    reply = await _reply(chat_harness, sheet, REPEATED_YEAR)
    assert NOTE_HEADING in reply
    assert "Total, Year 1: the reply shows $246,000; the spreadsheet has $304,000." in reply
    assert "add up to $1,203,000, not the $1,250,000 total shown" in reply


async def test_a_correct_reply_reaches_the_user_unmarked(chat_harness, sheet):
    assert NOTE_HEADING not in await _reply(chat_harness, sheet, CORRECT)
