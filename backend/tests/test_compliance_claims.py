"""Compliance replies say what was checked, and flag replaced 2 CFR 200 figures.

Support ticket: with no compliance rules defined, chat answered "Does this
subaward comply with 2 CFR 200 and NIH Grants Policy?" with a "Pass/Fail
Compliance Check" of 16 "✅ Pass" rows that meant only "mentioned in the
document", and gave the Single Audit threshold as $750K (now $1,000,000).
"""

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel

from app.services.compliance_claims import (
    NOTE_PREFIX,
    PRESENCE_NOTE,
    relabel_presence_checks,
    superseded_threshold_note,
)

from tests import test_chat_output

chat_harness = test_chat_output.chat_harness

TICKET_REPLY = """An automated compliance check isn't available: no compliance rules are defined.

## Pass/Fail Compliance Check
| Requirement | Result | Evidence |
|---|---|---|
| 2 CFR 200 compliance clause | ✅ Pass | Explicitly cited |
| FCOI compliance (42 CFR 50) | **✅ Pass** — cited in Attachment 2 | p. 4 |
| Data sharing plan | ❌ Fail | Not found |
| Indirect rate | ⚠️ Review | Rate stated, basis unclear |

Potential gap: Single Audit clause — should reference 2 CFR 200 Subpart F if subrecipient expends ≥$750K federal."""

NO_RULES = [{"tool_name": "check_compliance", "content": {"rules_checked": 0, "message": "no rules"}}]


def test_presence_marks_replace_pass_fail_when_no_rules_ran():
    out = relabel_presence_checks(TICKET_REPLY, NO_RULES)
    assert "## Document review (stated / not stated)" in out
    assert "| 2 CFR 200 compliance clause | ✓ Stated in document | Explicitly cited |" in out
    assert "| FCOI compliance (42 CFR 50) | ✓ Stated in document — cited in Attachment 2 | p. 4 |" in out
    assert "| Data sharing plan | ✗ Not confirmed | Not found |" in out
    assert "| Indirect rate | ⚠️ Review |" in out  # not a pass or a fail, left as written
    assert "Pass" not in out and "Fail" not in out
    assert out.endswith(PRESENCE_NOTE)


def test_a_real_rule_check_keeps_its_pass_fail():
    ran = [{"tool_name": "check_compliance", "content": {"rules_checked": 4}}]
    assert relabel_presence_checks(TICKET_REPLY, ran) == TICKET_REPLY


@pytest.mark.parametrize("reply", [
    "| Step | Result |\n|---|---|\n| Extract | ✅ Pass |",  # not about compliance
    "The subaward cites 2 CFR 200 and passes the threshold.",  # no table
])
def test_other_replies_are_untouched(reply):
    assert relabel_presence_checks(reply, []) == reply



def test_words_containing_pass_are_left_unchanged():
    """Support ticket: "Pass-through / PI" read "✓ Stated in document -through / PI",
    in chat and in the Excel download."""
    reply = (
        "Subaward compliance summary (2 CFR 200)\n"
        "| Party | Role | Status |\n|---|---|---|\n"
        "| University of Idaho | Pass-through / PI | ✅ Pass |\n"
        "| Oregon State | Subrecipient | Fail-safe clause noted |\n"
        "| Sponsor | Met-Life rider | Passing review |"
    )
    out = relabel_presence_checks(reply, NO_RULES)
    assert "| Pass-through / PI |" in out
    assert "| Fail-safe clause noted |" in out
    assert "| Met-Life rider |" in out and "| Passing review |" in out
    assert "| University of Idaho | Pass-through / PI | ✓ Stated in document |" in out


@pytest.mark.parametrize("cell,expected", [
    ("✅ Pass - cited in §4", "✓ Stated in document - cited in §4"),
    ("Pass -cited", "✓ Stated in document -cited"),
    ("Pass- cited", "✓ Stated in document - cited"),
    ("Pass—cited", "✓ Stated in document —cited"),
    ("Pass: p. 4", "✓ Stated in document : p. 4"),
    ("❌ Fail - missing", "✗ Not confirmed - missing"),
])
def test_a_status_with_its_reason_is_still_relabelled(cell, expected):
    out = relabel_presence_checks(f"Compliance review\n| Item | Result |\n|---|---|\n| Clause | {cell} |", NO_RULES)
    assert f"| Clause | {expected} |" in out


def test_header_relabel_applies_to_the_header_row_only():
    reply = "Compliance review\n| Item | Pass/Fail |\n|---|---|\n| Overall | Pass/Fail |"
    out = relabel_presence_checks(reply, [])
    assert "| Item | Stated in document? |" in out
    assert out.endswith(PRESENCE_NOTE)


def test_the_ticket_single_audit_figure_gets_the_current_threshold():
    note = superseded_threshold_note(TICKET_REPLY)
    assert note.startswith(NOTE_PREFIX)
    assert "$1,000,000" in note and "October 1, 2024" in note and "eCFR" in note


@pytest.mark.parametrize("reply,current", [
    ("Equipment is defined as items costing $5,000 or more per unit.", "$10,000"),
    ("The de minimis rate of 10% of MTDC applies.", "15%"),
    ("MTDC includes the first $25,000 of each subaward.", "$50,000"),
    ("Fixed amount subawards are limited to $250,000.", "$500,000"),
    ("| Single Audit | Required above $750,000 | 200.501 |", "$1,000,000"),
])
def test_each_replaced_threshold_is_noted(reply, current):
    assert current in superseded_threshold_note(reply)


@pytest.mark.parametrize("reply", [
    "The Single Audit threshold rose from $750,000 to $1,000,000 in 2024.",  # states the current figure
    "The total subaward amount is $750,000.00 for two years.",  # not in an audit context
    "The F&A rate is 10% of salaries.",  # 10% outside a de minimis context
    "",
])
def test_figures_outside_their_rule_or_already_current_are_left_alone(reply):
    assert superseded_threshold_note(reply) == ""


def test_chat_prompt_and_no_rules_result_forbid_pass_fail_for_presence():
    from app.services.llm_service import AGENTIC_CHAT_SYSTEM_PROMPT

    assert "not a compliance determination" in AGENTIC_CHAT_SYSTEM_PROMPT
    assert "$1,000,000" in AGENTIC_CHAT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_chat_saves_the_relabelled_reply_with_the_threshold_note(chat_harness):
    async def respond(messages, info):
        yield TICKET_REPLY

    await chat_harness.run(Agent(FunctionModel(stream_function=respond)),
                           message="Does this subaward comply with 2 CFR 200 and NIH Grants Policy? Give me a pass/fail list.")
    saved = chat_harness.finalize.call_args.args[1]
    assert "✅ Pass" not in saved and PRESENCE_NOTE in saved
    assert "$1,000,000" in saved and saved.rstrip().endswith("Verify figures against the current eCFR text.")
