"""Figures quoted from an attached spreadsheet are not flagged as recalled.

Support ticket (vandalizer-dev build 621, NIH_R01_Budget_Clean.xlsx): every
Indirect cell the answer quoted ("$53,000, $55,000, $49,000") was listed as
"Not in the retrieved sources … may come from the model's general
knowledge". The cells are currency-formatted, and the workbook's text holds
them as "53000".
"""

from types import SimpleNamespace

import openpyxl
import pytest
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel

from app.services.document_readers import extract_text_from_xlsx
from tests.test_chat_output import chat_harness as chat_harness

QUESTION = (
    "Do the numbers in this budget add up? Check every row and year, and check "
    "the indirect costs against a $51k–$57k per-year range."
)


@pytest.fixture
def budget_text(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Category", "Year 1", "Year 2", "Year 3"])
    ws.append(["Personnel", 250000, 257500, 265225])
    ws.append(["Indirect", 53000, 55000, 49000])
    for row in ws.iter_rows(min_row=2, min_col=2):
        for cell in row:
            cell.number_format = '"$"#,##0'
    path = tmp_path / "NIH_R01_Budget_Clean.xlsx"
    wb.save(path)
    text = extract_text_from_xlsx(str(path))
    assert "53000" in text and "$53,000" not in text  # what the checker actually sees
    return text


async def _flags(chat_harness, attachment_text, answer):
    chat_harness.conversation.get_file_attachments.return_value = [
        SimpleNamespace(filename="NIH_R01_Budget_Clean.xlsx", file_type=".xlsx", content=attachment_text),
    ]

    async def respond(messages, info):
        yield answer

    await chat_harness.run(Agent(FunctionModel(stream_function=respond)), message=QUESTION)
    return chat_harness.finalize.call_args.kwargs.get("unsupported_figures")


async def test_cells_quoted_from_an_attached_spreadsheet_are_not_flagged(chat_harness, budget_text):
    answer = (
        "Indirect costs are $53,000 (Year 1), $55,000 (Year 2) and $49,000 (Year 3). "
        "Years 1 and 2 fall inside $51,000–$57,000; Year 3 is below it."
    )
    assert not await _flags(chat_harness, budget_text, answer)


async def test_a_figure_the_spreadsheet_never_states_is_still_flagged(chat_harness, budget_text):
    answer = "Indirect costs are $53,000 in Year 1 and $61,000 in Year 4."
    assert await _flags(chat_harness, budget_text, answer) == ["$61,000"]
