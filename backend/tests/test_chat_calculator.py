"""Budget arithmetic in chat: the calculate tool, the "calculated" label, and the
send-back for figures worked out in the model's head (NIH R01 budget ticket)."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import RetryPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.services.calculation_claims import require_calculated_figures
from app.services.chat_calculator import Calculation, run
from app.services.kb_answer_grounding import calculated_only, calculation_formulas, unsupported_figures

# The ticket's sheet: five cost rows, an indirect row, and stated totals.
SHEET = """## Budget
| Category | Y1 | Y2 | Y3 | Y4 | Y5 | Total |
| --- | --- | --- | --- | --- | --- | --- |
| Personnel | $200,000 | $150,000 | $150,000 | $152,000 | $140,000 | $792,000 |
| Equipment | $15,000 | $15,000 | $0 | $0 | $0 | $30,000 |
| Travel | $8,000 | $6,000 | $6,000 | $7,000 | $5,000 | $32,000 |
| Supplies | $20,000 | $6,000 | $20,000 | $20,000 | $15,000 | $81,000 |
| Other | $10,000 | $10,000 | $10,000 | $10,000 | $10,000 | $50,000 |
| Total | $304,000 | $240,000 | $241,000 | $246,000 | $219,000 | $1,250,000 |
Indirect costs are expected to be $51k–$57k per year, $265,000 in total."""
ROWS = {"Personnel": [200000, 150000, 150000, 152000, 140000], "Equipment": [15000, 15000, 0, 0, 0],
        "Travel": [8000, 6000, 6000, 7000, 5000], "Supplies": [20000, 6000, 20000, 20000, 15000],
        "Other": [10000] * 5}
TOTALS = [304000, 240000, 241000, 246000, 219000]


def _steps(results):
    return {s["label"]: s for s in results["steps"]}


def test_ticket_budget_reconciles_exactly_with_every_row():
    calcs = []
    for year in range(5):
        terms = " + ".join(str(values[year]) for values in ROWS.values())
        calcs.append(Calculation(label=f"Y{year + 1} direct", expression=terms))
        calcs.append(Calculation(label=f"Y{year + 1} indirect", expression=f"{TOTALS[year]} - {{Y{year + 1} direct}}"))
        calcs.append(Calculation(label=f"Y{year + 1} in range", expression=f"51000 <= {{Y{year + 1} indirect}} <= 57000"))
    calcs.append(Calculation(label="Indirect total", expression=", ".join(f"{{Y{y} indirect}}" for y in range(1, 6)).join(["sum(", ")"])))
    steps = _steps(run(calcs))
    assert [steps[f"Y{y} direct"]["result"] for y in range(1, 6)] == ["253,000", "187,000", "186,000", "189,000", "170,000"]
    assert [steps[f"Y{y} indirect"]["result"] for y in range(1, 6)] == ["51,000", "53,000", "55,000", "57,000", "49,000"]
    assert [steps[f"Y{y} in range"]["check"] for y in range(1, 6)] == [True, True, True, True, False]
    assert steps["Indirect total"]["result"] == "265,000"
    assert steps["Y2 indirect"]["expression"] == "240000 - (187000)"


@pytest.mark.parametrize("expression, expected", [
    ("0.1 + 0.2", "0.3"),
    ("round(51234 / 1000) * 1000", "51,000"),
    ("max(1, 5, 3) - min(4, 2)", "3"),
    ("(1250000 - 985000) / 1250000 * 100", "21.2"),
    ("2 ** 10", "1,024"),
])
def test_exact_arithmetic(expression, expected):
    assert run([Calculation(label="x", expression=expression)])["steps"][0]["result"] == expected


@pytest.mark.parametrize("expression, error", [
    ("__import__('os').system('ls')", "Only numbers"),
    ("open('/etc/passwd')", "Only numbers"),
    ("sum(1,250,000)", "thousands separators"),
    ("1 / 0", "Division by zero"),
    ("10 ** 100", "Powers"),
    ("{missing} + 1", "No earlier step"),
    ("1 +", "Not a valid expression"),
])
def test_unsafe_or_ambiguous_input_is_refused_not_guessed(expression, error):
    step = run([Calculation(label="x", expression=expression)])["steps"][0]
    assert error in step["error"] and "result" not in step


def test_currency_symbols_are_accepted_and_failed_steps_stay_out_of_references():
    steps = _steps(run([
        Calculation(label="a", expression="$15,000"),
        Calculation(label="b", expression="$15000 + $5000"),
        Calculation(label="c", expression="{a} + 1"),
    ]))
    assert "error" in steps["a"] and steps["b"]["result"] == "20,000"
    assert "No earlier step" in steps["c"]["error"]


def test_calculated_figures_are_labelled_not_flagged_as_general_knowledge():
    output = json.dumps(run([Calculation(label="Y1", expression="253000"), Calculation(label="rate", expression="51000 / 253000 * 100")]))
    answer = "Y1 direct costs are $253k (20.2% indirect). Unrelated: $99,000."
    flagged = unsupported_figures(answer, "")
    assert calculated_only(flagged, answer, [output]) == ["$253k", "20.2%"]


def test_calculated_figures_carry_the_step_as_their_formula():
    # Merged onto 6ef022e1's calculated_figures shape ({figure, formula}).
    output = json.dumps(run([Calculation(label="Y1 direct", expression="200000 + 15000 + 8000 + 20000 + 10000")]))
    assert calculation_formulas(["$253k", "$99,000"], [output]) == {
        "$253k": "Y1 direct: 200000 + 15000 + 8000 + 20000 + 10000 = 253,000",
    }


@pytest.mark.parametrize("expression", [
    "1e400",  # a float literal that is infinite
    "9e999999 * 9e999999",  # Decimal overflow
    "-" * 1500 + "1",  # recursion past the stack limit
    "0 ** -1",
])
def test_pathological_input_is_a_step_error_not_a_crash(expression):
    step = run([Calculation(label="x", expression=expression)])["steps"][0]
    assert "error" in step and "result" not in step


def test_later_steps_use_full_precision_not_the_displayed_rounding():
    steps = _steps(run([
        Calculation(label="rate", expression="1 / 3"),
        Calculation(label="amount", expression="{rate} * 300000"),
    ]))
    assert steps["rate"]["result"] == "0.333333"
    # 0.333333 × 300000 would be 99,999.9.
    assert steps["amount"]["result"] == "100,000"


def _agent(replies: list[str], calculate_first: bool = False):
    async def model(messages, info: AgentInfo):
        if calculate_first and not any(type(p).__name__ == "ToolReturnPart" for m in messages for p in m.parts):
            yield {0: DeltaToolCall(name="calculate", json_args=json.dumps({"calculations": [
                {"label": "Y1 direct", "expression": "200000 + 15000 + 8000 + 20000 + 10000"},
                {"label": "Y1 indirect", "expression": "304000 - {Y1 direct}"},
            ]}))}
            return
        retried = any(isinstance(p, RetryPromptPart) for p in messages[-1].parts)
        yield replies[1] if retried and len(replies) > 1 else replies[0]

    agent = Agent(FunctionModel(stream_function=model), deps_type=SimpleNamespace)

    @agent.tool
    def calculate(ctx: RunContext[SimpleNamespace], calculations: list[Calculation]) -> dict:
        return run(calculations)

    agent.output_validator(require_calculated_figures)
    return agent


async def _run(agent, deps):
    async with agent.iter("Do the numbers in this budget add up?", deps=deps) as run_:
        async for node in run_:
            if Agent.is_model_request_node(node) or Agent.is_call_tools_node(node):
                async with node.stream(run_.ctx) as stream:
                    async for _ in stream:
                        pass
    return run_.result.output


def _deps(**kw):
    return SimpleNamespace(context_document_uuids=["budget"], documents_read=[], user_message="Do the numbers add up?",
                           calculation_retry_used=False, **kw)


TICKET_REPLY = "Direct costs by year: Y1 $243k, Y2 $205k. Indirect needed: Y1 $61k."
CALCULATED = "Calculated from the table: Y1 direct $253,000 (all five rows), so Y1 indirect is $51,000."
FROM_SHEET = "Y1 totals $304,000 and the budget totals $1,250,000, as stated in the sheet."


@pytest.mark.asyncio
async def test_head_arithmetic_about_a_document_is_sent_back_once():
    with patch("app.services.calculation_claims._document_texts", AsyncMock(return_value=[SHEET])):
        assert await _run(_agent([TICKET_REPLY, CALCULATED]), _deps()) == CALCULATED
        # A second miss is accepted rather than failing the turn.
        assert await _run(_agent([TICKET_REPLY]), _deps()) == TICKET_REPLY


@pytest.mark.asyncio
async def test_figures_from_the_sheet_or_a_calculate_step_pass():
    with patch("app.services.calculation_claims._document_texts", AsyncMock(return_value=[SHEET])):
        assert await _run(_agent([FROM_SHEET, "retried"]), _deps()) == FROM_SHEET
        assert await _run(_agent([CALCULATED, "retried"], calculate_first=True), _deps()) == CALCULATED


@pytest.mark.asyncio
async def test_turns_without_documents_are_not_checked():
    texts = AsyncMock(return_value=[SHEET])
    with patch("app.services.calculation_claims._document_texts", texts):
        deps = _deps()
        deps.context_document_uuids = []
        assert await _run(_agent([TICKET_REPLY, "retried"]), deps) == TICKET_REPLY
    texts.assert_not_awaited()


def test_a_share_the_tool_returned_as_a_fraction_matches_its_percentage():
    """Support ticket: "625000 / 1250000 = 0.5", stated as "50.0%", was flagged."""
    output = json.dumps(run([Calculation(label="Personnel share", expression="625000 / 1250000"),
                             Calculation(label="Gap", expression="625000 - 265000")]))
    assert calculation_formulas(["50.0%", "50%", "$360,000", "0.5%", "$0.50"], [output]) == {
        "50.0%": "Personnel share: 625000 / 1250000 = 0.5",
        "50%": "Personnel share: 625000 / 1250000 = 0.5",
        "$360,000": "Gap: 625000 - 265000 = 360,000",
        "0.5%": "Personnel share: 625000 / 1250000 = 0.5",
        "$0.50": "Personnel share: 625000 / 1250000 = 0.5",
    }
    # A step that doesn't divide is not read as a share: 0.5 isn't 50%.
    plain = json.dumps(run([Calculation(label="Half", expression="0.25 + 0.25")]))
    assert calculation_formulas(["50%"], [plain]) == {}
