"""A draft an output validator sent back is never mentioned or flagged.

Support ticket (NIH_R01_Budget_Clean.xlsx, "Summarize the budget", new chat):
the reply said "My earlier figures were wrong — I had restated numbers that
weren't in the file. The correct Y1 is $304,000 (not $253,000)…", and the
warning listed the hidden draft's figures as "Not in the retrieved sources".
"""

import inspect
from types import SimpleNamespace

import openpyxl
import pytest
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.messages import ModelRequest, RetryPromptPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from app.services.document_readers import extract_text_from_xlsx
from app.services.hidden_drafts import (
    UNSEEN_DRAFT_INSTRUCTION,
    had_hidden_retry,
    unseen_draft_retry,
    without_draft_corrections,
    without_refuted_figures,
)
from tests.test_chat_output import chat_harness as chat_harness



@pytest.fixture
def sheet(tmp_path):
    wb = openpyxl.Workbook()
    for row in [["Category", "Year 1", "Year 2", "Year 3"], ["Personnel", 250000, 190000, 200000],
                ["Total", 304000, 240000, 251000]]:
        wb.active.append(row)
    path = tmp_path / "NIH_R01_Budget_Clean.xlsx"
    wb.save(path)
    return extract_text_from_xlsx(str(path))

DRAFT = "The budget totals $253,000 in Year 1, $268,000 in Year 2 and $257,000 in Year 3."
CORRECTED = (
    "My earlier figures were wrong — I had restated numbers that weren't in the file. "
    "The correct Y1 is $304,000 (not $253,000), Y2 $240,000 (not $268,000) and "
    "Y3 $251,000 (not $257,000).\n\n"
    "My previous reply contained incorrect figures and arithmetic errors.\n\n"
    "Personnel is the largest category in every year."
)
CLEAN = (
    "The correct Y1 is $304,000, Y2 $240,000 and Y3 $251,000.\n\n"
    "Personnel is the largest category in every year."
)


def test_draft_corrections_are_removed_and_the_answer_kept():
    assert without_draft_corrections(CORRECTED) == CLEAN


@pytest.mark.parametrize("text,expected", [
    ("Year 1 is $304,000, not $253,000.", "Year 1 is $304,000."),
    ("Year 1 is $304,000 instead of $253,000; Year 2 is $240,000.", "Year 1 is $304,000; Year 2 is $240,000."),
    ("Apologies for the confusion. Year 1 is $304,000.", "Year 1 is $304,000."),
    ("| Year | Total |\n| --- | --- |\n| 1 | $304,000 (previously $253,000) |",
     "| Year | Total |\n| --- | --- |\n| 1 | $304,000 |"),
])
def test_draft_correction_forms(text, expected):
    assert without_draft_corrections(text) == expected


@pytest.mark.parametrize("answer", [
    "Year 2 is $240,000, down from $304,000 in Year 1.",
    "The first year's total is $304,000.",
    "Indirect costs are not included in the first table.",
    "The sponsor's earlier version of the form is attached (Version 2).",
])
def test_ordinary_answers_are_unchanged(answer):
    assert without_draft_corrections(answer) == answer


def test_refuted_figures_are_not_claims():
    assert without_refuted_figures("Y1 is $304,000 (not $253,000).") == "Y1 is $304,000."


def test_only_a_rejected_answer_counts_as_a_hidden_draft():
    tool_retry = ModelRequest(parts=[RetryPromptPart(content="bad args", tool_name="calculate")])
    answer_retry = ModelRequest(parts=[RetryPromptPart(content="figures don't match")])
    assert not had_hidden_retry([ModelRequest(parts=[UserPromptPart(content="hi")]), tool_retry])
    assert had_hidden_retry([tool_retry, answer_retry])


@pytest.mark.parametrize("is_async", [True, False])
async def test_a_validator_retry_says_the_draft_was_never_shown(is_async):
    def check(ctx: RunContext[None], output: str) -> str:
        raise ModelRetry("Year 1 does not match the spreadsheet.")

    async def async_check(ctx: RunContext[None], output: str) -> str:
        return check(ctx, output)

    wrapped = unseen_draft_retry(async_check if is_async else check)
    assert inspect.iscoroutinefunction(wrapped) is is_async
    assert list(inspect.signature(wrapped).parameters) == ["ctx", "output"]
    with pytest.raises(ModelRetry) as raised:
        result = wrapped(None, DRAFT)
        if is_async:
            await result
    assert raised.value.message == f"Year 1 does not match the spreadsheet.\n\n{UNSEEN_DRAFT_INSTRUCTION}"


async def _run(chat_harness, sheet, replies, validator=None):
    chat_harness.conversation.get_file_attachments.return_value = [
        SimpleNamespace(filename="NIH_R01_Budget_Clean.xlsx", file_type=".xlsx", content=sheet),
    ]
    prompts = []

    async def respond(messages, info):
        prompts.append(messages[-1])
        yield replies[min(len(prompts), len(replies)) - 1]

    agent = Agent(FunctionModel(stream_function=respond))
    if validator:
        agent.output_validator(unseen_draft_retry(validator))
    await chat_harness.run(agent, message="Summarize the budget.")
    saved = chat_harness.finalize.call_args
    return saved.args[1], saved.kwargs.get("unsupported_figures"), prompts


async def test_a_reply_after_a_hidden_draft_has_only_the_corrected_answer(chat_harness, sheet):
    def figures_match(ctx: RunContext[None], output: str) -> str:
        if "$253,000" in output and "(not $253,000)" not in output:
            raise ModelRetry("Year 1 does not match the spreadsheet.")
        return output

    answer, flagged, prompts = await _run(chat_harness, sheet, [DRAFT, CORRECTED], figures_match)
    assert len(prompts) == 2
    assert UNSEEN_DRAFT_INSTRUCTION in prompts[1].parts[-1].model_response()
    assert answer == CLEAN
    assert not flagged


async def test_without_a_hidden_draft_the_reply_is_left_as_written(chat_harness, sheet):
    """In a longer chat, a correction of a reply the user did see is kept,
    and its refuted figures still aren't flagged."""
    answer, flagged, _ = await _run(chat_harness, sheet, [CORRECTED])
    assert answer == CORRECTED
    assert not flagged
