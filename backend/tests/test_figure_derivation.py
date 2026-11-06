"""Calculated figures are labelled as calculated, not as general knowledge.

Support ticket: chat added up nih-r01-neuroscience.pdf's budget table (p. 2)
and tested its 52% indirect rate correctly. The figure check flagged
"$131.6K" in one run, all 16 calculated values on a follow-up, and nothing in
a new chat; the p. 2 chip said "passage not found" every time.
"""

import pytest

from app.services.citation_grounding import FOUND, NOT_FOUND, _judge
from app.services.figure_derivation import derive_figures
from app.services.kb_answer_grounding import _money_values, _percent_values, check_figures
from tests import test_chat_output

PAGE_2 = """Detailed Budget for Initial Budget Period
Category Year 1 Year 2 Year 3
Personnel $150,000 $120,000 $118,000
Equipment $50,000 $0 $0
Travel $8,000 $8,000 $9,000
Supplies $30,000 $40,000 $40,000
Other $15,000 $19,000 $19,000
Indirect (52%) $51,000 $53,000 $55,000
Total $304,000 $240,000 $241,000"""

ANSWER = """**Year 1:** $150,000 + $50,000 + $8,000 + $30,000 + $15,000 = $253,000 direct. Adding indirect: $253,000 + $51,000 = $304,000, which matches the Total row.
**Year 2:** $120,000 + $0 + $8,000 + $40,000 + $19,000 = $187,000 direct, and $187,000 + $53,000 = $240,000.

| Year | Direct | Indirect | Indirect ÷ Direct | 52% of direct |
|---|---|---|---|---|
| 1 | $253,000 | $51,000 | 20.2% | $131,560 |
| 2 | $187,000 | $53,000 | 28.3% | $97,240 |

So 52% × $253,000 = $131.6K, far above the $51,000 shown."""


def _formulas(answer: str, source: str) -> dict[str, str]:
    return {d.label: d.formula for d in derive_figures(answer, set(_money_values(source)), set(_percent_values(source)))}


def test_the_ticket_calculations_are_labelled_with_their_formulas():
    missing, calculated = check_figures(ANSWER, PAGE_2)
    assert missing == []
    formulas = {d.label: d.formula for d in calculated}
    assert formulas["$253,000"] == "$150,000 + $50,000 + $8,000 + $30,000 + $15,000 = $253,000"
    assert formulas["20.2%"] == "$51,000 ÷ $253,000 = 20.2%"
    assert formulas["28.3%"] == "$53,000 ÷ $187,000 = 28.3%"
    assert formulas["$131,560"] == "52% × $253,000 = $131,560"  # the rate is in the column header
    assert formulas["$131.6K"] == "52% × $253,000 = $131.6K"  # rounded as written


def test_the_same_answer_gets_the_same_labels_every_time():
    assert check_figures(ANSWER, PAGE_2) == check_figures(ANSWER, PAGE_2)


def test_an_invented_figure_is_still_flagged():
    missing, _ = check_figures(ANSWER + "\nThe NIH salary cap is $199,300.", PAGE_2)
    assert missing == ["$199,300"]


def test_figures_in_different_sentences_are_not_combined():
    """$150,000 + $50,000 = $200,000, but nothing in the reply says so."""
    answer = "Personnel is $150,000. Equipment is $50,000. The award is capped at $200,000."
    missing, calculated = check_figures(answer, PAGE_2)
    assert missing == ["$200,000"] and calculated == []


def test_a_wrong_calculation_is_not_calculated():
    missing, _ = check_figures("Direct costs: $150,000 + $50,000 = $210,000.", PAGE_2)
    assert missing == ["$210,000"]


def test_a_table_total_row_sums_its_column():
    answer = "| Year | Indirect |\n|---|---|\n| 1 | $51,000 |\n| 2 | $53,000 |\n| 3 | $55,000 |\n| Total | $159,000 |"
    assert _formulas(answer, PAGE_2)["$159,000"] == "$51,000 + $53,000 + $55,000 = $159,000"


def test_a_page_with_the_inputs_is_found_for_a_calculated_claim():
    claim = "Year 1 direct costs are $150,000 + $50,000 + $8,000 + $30,000 + $15,000 = $253,000 (p. 2)."
    assert _judge(claim, PAGE_2) == FOUND
    assert _judge("Year 1 indirect is $73,000 (p. 2).", PAGE_2) == NOT_FOUND


def test_a_chip_accepts_a_figure_calculated_earlier_in_the_answer():
    """$253,000 is summed in one sentence and divided into in the next."""
    import re

    from app.services.citation_grounding import ground_citation

    ref_re = re.compile(r"\(p\.\s*(\d+)\)")
    answer = ("Year 1 direct costs: $150,000 + $50,000 + $8,000 + $30,000 + $15,000 = $253,000. "
              "Indirect is $51,000 ÷ $253,000 = 20.2% of direct costs, not 52% (p. 2).")
    ref = next(ref_re.finditer(answer)).span()
    status, passage = ground_citation(answer, [ref], PAGE_2, ref_re)
    assert status == FOUND and passage and "÷" not in passage
    invented = answer.replace("$51,000 ÷", "$61,000 ÷")
    assert ground_citation(invented, [next(ref_re.finditer(invented)).span()], PAGE_2, ref_re)[0] == NOT_FOUND


chat_harness = test_chat_output.chat_harness


@pytest.mark.asyncio
async def test_chat_checks_an_attached_file_without_any_tool_call(chat_harness):
    """The new-chat run: attachment only, no tools, so the check used to be skipped."""
    from types import SimpleNamespace

    from pydantic_ai import Agent
    from pydantic_ai.models.function import FunctionModel

    reply = ANSWER + "\nThe NIH salary cap is $199,300."

    async def respond(messages, info):
        yield reply

    attachment = SimpleNamespace(filename="nih-r01-neuroscience.pdf", content="Page 1 narrative.\n" + PAGE_2)
    chat_harness.conversation.get_file_attachments.return_value = [attachment]
    await chat_harness.run(Agent(FunctionModel(stream_function=respond)),
                           message="For each year, add the categories. Do the yearly totals match the Total row?")
    kwargs = chat_harness.finalize.call_args.kwargs
    assert kwargs["unsupported_figures"] == ["$199,300"]
    assert {"figure": "$131,560", "formula": "52% × $253,000 = $131,560"} in kwargs["calculated_figures"]
