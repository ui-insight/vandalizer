"""Multi-step requests guide the user one step at a time (support ticket).

Setting up a NIFA subaward left Move files, Add to inbox and Save page waiting
at once; "Yes, go ahead" didn't say which card it approved, so chat sometimes
ran one and sometimes explained again; and the next action was buried in long
replies with no clear finish.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import chat_tools
from app.services.approval_scope import approval_reminder, decide
from app.services.chat_tools import _confirm_gate

MOVE = {"fp": "fp-move", "turn": 4, "tool": "move_documents_to_project", "call_id": "call-move",
        "label": "Move files", "summary": "Move NIFA-UI-OSU.pdf into NIFA Subaward"}
INBOX = {"fp": "fp-inbox", "turn": 4, "tool": "propose_obligations", "call_id": "call-inbox",
         "label": "Add to inbox", "summary": "Add 3 deadlines to the RA inbox"}
PAGE = {"fp": "fp-page", "turn": 4, "tool": "create_html_artifact", "call_id": "call-page", "label": "Save page"}


class TestApprovalReminder:
    def test_a_click_names_the_card_and_only_that_action(self):
        pending = [MOVE, INBOX, PAGE]
        note = approval_reminder(decide(pending, approval_for="call-inbox"), pending, approval_for="call-inbox")
        assert '"Add to inbox" (Add 3 deadlines to the RA inbox)' in note
        assert "call propose_obligations" in note and "confirmed=true" in note
        assert "Do not run any other waiting action" in note
        # The rest of the queue, in order, so the reply can name the next step.
        assert note.index('"Move files"') < note.index('"Save page"')
        assert ":::details" in note

    def test_a_skip_names_the_skipped_card(self):
        pending = [MOVE, INBOX]
        note = approval_reminder(decide(pending, decline_for="call-move"), pending, decline_for="call-move")
        assert 'skipped "Move files"' in note and "will not run" in note
        assert '"Add to inbox"' in note

    def test_a_typed_yes_with_several_waiting_asks_which_one(self):
        pending = [MOVE, INBOX, PAGE]
        note = approval_reminder(decide(pending), pending)
        assert "3 steps are waiting" in note and "run none" in note
        assert "Which one:" in note
        for label in ("Move files", "Add to inbox", "Save page"):
            assert f'"{label}"' in note

    def test_a_typed_reply_with_one_waiting_names_it(self):
        note = approval_reminder(decide([INBOX]), [INBOX])
        assert '"Add to inbox"' in note and "If the user's message approves it" in note

    def test_entries_saved_before_labels_still_read(self):
        old = {"fp": "fp-x", "turn": 2, "tool": "save_to_folder", "call_id": "call-x"}
        note = approval_reminder(decide([old], approval_for="call-x"), [old], approval_for="call-x")
        assert '"save to folder"' in note

    def test_nothing_waiting_adds_nothing(self):
        assert approval_reminder(decide([]), []) == ""
        assert approval_reminder(decide([MOVE], approval_for="gone"), [MOVE], approval_for="gone") == ""


class _Conversation:
    def __init__(self):
        self.pending_confirmations: list[dict] = []

    async def save(self):
        return None


@pytest.mark.asyncio
async def test_a_preview_records_what_its_card_says():
    conv = _Conversation()
    ctx = SimpleNamespace(deps=SimpleNamespace(conversation=conv, turn_marker=6), tool_call_id="call-inbox")
    await _confirm_gate(
        ctx, tool_name="propose_obligations", key={"items": 3}, confirmed=False,
        preview={"preview": "Add 3 deadlines\n to the RA inbox", "approval_label": "Add to inbox", "needs_confirmation": True},
    )
    (entry,) = conv.pending_confirmations
    assert entry["label"] == "Add to inbox"
    assert entry["summary"] == "Add 3 deadlines to the RA inbox"
    assert entry["call_id"] == "call-inbox"


def _task(content, status, result=None):
    task = {"content": content, "active_form": content + "ing", "status": status}
    if result is not None:
        task["result"] = result
    return task


@pytest.mark.asyncio
async def test_plan_results_are_kept_for_completed_steps_only():
    conversation = SimpleNamespace(pending_confirmations=[], save=AsyncMock())
    deps = SimpleNamespace(plan_state=None, conversation=conversation, turn_marker=1, completion_claim_retry_used=False)
    ok = await chat_tools.update_plan(SimpleNamespace(deps=deps), [
        _task("Create project", "completed", "project created"),
        _task("Add deadlines", "in_progress", "3 deadlines added"),
        _task("Save page", "pending"),
    ])
    assert "error" not in ok
    assert deps.plan_state[0]["result"] == "project created"
    assert "result" not in deps.plan_state[1], "an unfinished step cannot report a result"
    assert "result" not in deps.plan_state[2]
