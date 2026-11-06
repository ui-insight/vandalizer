"""A multi-step chat request reports its true state (support ticket).

"Set up this subaward: create a project, add its reporting deadlines to the RA
inbox, extract the key details, and make a one-page snapshot Page" ended with
"✓ All 4 steps completed" and "Award snapshot saved" while four approval
cards waited, no Page, a .md file instead, an inbox step that failed before
the project was approved, three identical inbox cards, and two clearly
anchored NIFA deadlines refused.
"""
import datetime
import types
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai import ModelRetry

from app.models.obligation import ObligationSource
from app.services import approval_claims, chat_tools
from app.services.relative_deadlines import calculate_deadlines


def _deps(pending=(), marker=7, **extra):
    conversation = types.SimpleNamespace(pending_confirmations=[{"fp": f"fp{i}", "turn": turn, "tool": tool} for i, (tool, turn) in enumerate(pending)],
                                         save=AsyncMock())
    return types.SimpleNamespace(plan_state=None, conversation=conversation, turn_marker=marker,
                                 completion_claim_retry_used=False, **extra)


def _task(content, status):
    return {"content": content, "active_form": content + "ing", "status": status}


# ── Plan status ─────────────────────────────────────────────────────────────

async def test_plan_cannot_be_all_done_while_this_turns_cards_wait():
    deps = _deps(pending=[("move_documents_to_project", 7), ("propose_obligations", 7), ("save_to_folder", 7)])
    ctx = types.SimpleNamespace(deps=deps)
    tasks = [_task(name, "completed") for name in ("Create project", "Add deadlines", "Extract details", "Make page")]
    refused = await chat_tools.update_plan(ctx, tasks)
    assert "error" in refused and "3 approval card(s)" in refused["error"] and "awaiting_approval" in refused["hint"]
    assert deps.plan_state is None

    honest = [tasks[0], *(_task(t["content"], "awaiting_approval") for t in tasks[1:])]
    ok = await chat_tools.update_plan(ctx, honest)
    assert ok["ok"] and ok["completed"] == 1 and ok["awaiting_approval"] == 3 and not ok["all_done"]


async def test_cards_from_earlier_turns_dont_block_a_finished_plan():
    deps = _deps(pending=[("create_project", 3)])
    ok = await chat_tools.update_plan(types.SimpleNamespace(deps=deps), [_task("A", "completed"), _task("B", "completed")])
    assert ok["all_done"]


async def test_one_in_progress_is_still_required_while_work_remains():
    deps = _deps()
    bad = await chat_tools.update_plan(types.SimpleNamespace(deps=deps), [_task("A", "completed"), _task("B", "pending")])
    assert "Exactly one task must be in_progress" in bad["error"]
    two = await chat_tools.update_plan(types.SimpleNamespace(deps=deps), [_task("A", "in_progress"), _task("B", "in_progress")])
    assert "Exactly one task must be in_progress" in two["error"]


async def test_a_step_waiting_on_another_steps_approval_stays_pending():
    # The ticket's end state: the inbox step waits for Create project
    # (propose_obligations says to keep it pending) while cards wait.
    deps = _deps(pending=[("create_project", 7), ("save_to_folder", 7)])
    tasks = [_task("Create project", "awaiting_approval"), _task("Add deadlines", "pending"),
             _task("Extract details", "completed"), _task("Make page", "awaiting_approval")]
    ok = await chat_tools.update_plan(types.SimpleNamespace(deps=deps), tasks)
    assert ok.get("ok") and ok["awaiting_approval"] == 2 and not ok["all_done"]


# ── "Saved" while cards wait ────────────────────────────────────────────────

@pytest.mark.parametrize("reply, claims", [
    ("All four steps are prepared.", True),
    ("Award snapshot saved", True),
    ("The deadlines have been added to the RA inbox.", True),
    ("I saved it to the project folder.", True),
    ("All four steps are prepared and waiting for your approval.", False),
    ("Once you approve Add to inbox, the deadlines will be added.", False),
    ("The snapshot is not saved yet — approve Save to folder to save it.", False),
    ("Here is what the subaward says about reporting.", False),
])
def test_claims_done(reply, claims):
    assert approval_claims.claims_done(reply) is claims


def test_a_done_claim_with_waiting_cards_is_sent_back_once():
    deps = _deps(pending=[("propose_obligations", 7), ("save_to_folder", 7)])
    ctx = types.SimpleNamespace(deps=deps, partial_output=False)
    with pytest.raises(ModelRetry) as retry:
        approval_claims.require_honest_completion(ctx, "All four steps are prepared. Award snapshot saved")
    assert "Add to inbox" in str(retry.value) or "propose" in str(retry.value).lower()
    # Second miss accepted; no waiting cards → nothing to check.
    assert approval_claims.require_honest_completion(ctx, "All done.") == "All done."
    quiet = types.SimpleNamespace(deps=_deps(pending=[("save_to_folder", 2)]), partial_output=False)
    assert approval_claims.require_honest_completion(quiet, "Saved.") == "Saved."


def test_the_validator_is_registered_on_the_chat_agent():
    from app.services import llm_service
    import inspect
    assert "require_honest_completion" in inspect.getsource(llm_service.create_agentic_chat_agent)


# ── Inbox before the project exists ─────────────────────────────────────────

async def test_inbox_items_wait_for_a_pending_create_project():
    from tests.test_chat_tools import _make_context

    ctx = _make_context()
    ctx.deps.conversation = types.SimpleNamespace(pending_confirmations=[{"fp": "x", "turn": 5, "tool": "create_project"}])
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=None)):
        out = await chat_tools.propose_obligations(ctx, [{"kind": "deadline", "title": "Final report", "sources": []}])
    assert out["waiting_for"] == "create_project" and "error" not in out
    ctx.deps.conversation = types.SimpleNamespace(pending_confirmations=[])
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=None)):
        assert "No project is open" in (await chat_tools.propose_obligations(ctx, [{"kind": "deadline"}]))["error"]


# ── One card per action ─────────────────────────────────────────────────────

async def test_repeating_an_action_in_one_reply_is_one_card():
    conversation = types.SimpleNamespace(pending_confirmations=[], save=AsyncMock())
    ctx = types.SimpleNamespace(deps=types.SimpleNamespace(conversation=conversation, turn_marker=9))
    kwargs = {"tool_name": "propose_obligations", "key": {"project": "p", "items": "abc"}, "confirmed": False}
    first = await chat_tools._confirm_gate(ctx, preview={"preview": "Add 3 items", "action": "propose_obligations"}, **kwargs)
    second = await chat_tools._confirm_gate(ctx, preview={"preview": "Add 3 items\nNot included: X", "action": "propose_obligations"}, **kwargs)
    assert first["approval_key"] == second["approval_key"]
    assert "already_waiting" not in first and second["already_waiting"] is True
    assert len(conversation.pending_confirmations) == 1


async def test_the_card_the_chat_shows_is_the_one_armed():
    # The chat keeps the first card per approval_key; its button sends that
    # card's call id (approval_for), so the first call id must stay armed.
    conversation = types.SimpleNamespace(pending_confirmations=[], save=AsyncMock())
    deps = types.SimpleNamespace(conversation=conversation, turn_marker=9)
    kwargs = {"tool_name": "propose_obligations", "key": {"project": "p", "items": "abc"}, "confirmed": False}
    await chat_tools._confirm_gate(types.SimpleNamespace(deps=deps, tool_call_id="call-1"),
                                   preview={"preview": "Add 3 items"}, **kwargs)
    await chat_tools._confirm_gate(types.SimpleNamespace(deps=deps, tool_call_id="call-2"),
                                   preview={"preview": "Add 3 items\nNot included: X"}, **kwargs)
    assert [p["call_id"] for p in conversation.pending_confirmations] == ["call-1"]


# ── Page without a template ─────────────────────────────────────────────────

async def test_a_page_from_a_source_file_needs_no_template():
    from app.services import chat_artifact_tools

    save = AsyncMock(return_value={"needs_confirmation": True})
    ctx = types.SimpleNamespace(deps=types.SimpleNamespace(context_document_uuids=["sub"]))
    with patch.object(chat_artifact_tools, "_save", save):
        await chat_artifact_tools.create_html_artifact(ctx, "Award snapshot", "<main><h1>Award</h1></main>", source_document_uuid="sub")
    save.assert_awaited_once()
    with patch.object(chat_artifact_tools, "_save", save):
        refused = await chat_artifact_tools.create_html_artifact(ctx, "Award snapshot", template_values=[{"field_id": "x", "value": "1", "quote": "1"}])
        empty = await chat_artifact_tools.create_html_artifact(ctx, "Award snapshot", "", source_document_uuid="sub")
    assert "none was given" in refused["error"] and "do not deliver a different kind of output" in refused["hint"]
    assert "Write the Page in html" in empty["error"]
    assert save.await_count == 1


def test_the_agent_is_told_not_to_swap_a_page_for_a_file():
    from app.services.llm_service import AGENTIC_CHAT_SYSTEM_PROMPT
    assert "never substitute a different output" in AGENTIC_CHAT_SYSTEM_PROMPT


# ── Relative deadlines with a clear anchor ──────────────────────────────────

def _src(quote, role):
    return ObligationSource(document_uuid="sub", document_title="Subaward.pdf", page=2, quote=quote, role=role)


PERIOD = _src("Start Date: September 1, 2026  End Date: August 31, 2027", "period_of_performance")


def test_a_rule_with_its_own_dated_anchor():
    [due] = calculate_deadlines([_src("The annual progress report is due 60 days after March 1, 2027.", "timing")])
    assert due["due_at"].date() == datetime.date(2027, 4, 30)
    assert due["deadline_calculation"].anchor_kind == "stated_date"
    assert due["deadline_calculation"].formula == "2027-03-01 + 60 calendar days = 2027-04-30"


def test_a_rule_anchored_on_the_end_date():
    [due] = calculate_deadlines([_src("The final technical report is due 120 days after the End Date.", "timing"), PERIOD])
    assert due["due_at"].date() == datetime.date(2027, 12, 29)
    assert due["deadline_calculation"].anchor_kind == "performance_period_end"


@pytest.mark.parametrize("rule, reason", [
    ("Report due 60 days after March 1.", "must include its year"),
    ("Report due within 60 days of March 1, 2027.", "before or after"),
])
def test_unclear_anchors_are_still_refused(rule, reason):
    with pytest.raises(ValueError) as exc:
        calculate_deadlines([_src(rule, "timing"), PERIOD])
    assert reason in str(exc.value)
