"""One approval card approves one action (support ticket).

With Move files, Add to inbox ×3 and Save to folder waiting, clicking Move
files carried out all of them: every card sent "Yes, go ahead", and the gate
let any action armed on an earlier turn run.
"""

from types import SimpleNamespace

import pytest

from app.services.approval_scope import blocked_instruction, decide
from app.services.chat_tools import _confirm_fingerprint, _confirm_gate

MOVE = {"fp": "fp-move", "turn": 4, "tool": "move_documents_to_project", "call_id": "call-move"}
INBOX = {"fp": "fp-inbox", "turn": 4, "tool": "propose_obligations", "call_id": "call-inbox"}
SAVE = {"fp": "fp-save", "turn": 4, "tool": "save_to_folder", "call_id": "call-save"}


class TestDecide:
    def test_a_card_approves_only_its_own_action(self):
        turn = decide([MOVE, INBOX, SAVE], approval_for="call-move")
        assert turn.approved == {"fp-move"} and turn.mode == "card"

    def test_a_card_that_is_no_longer_armed_approves_nothing(self):
        assert decide([INBOX], approval_for="call-move").approved == frozenset()

    def test_cancel_disarms_only_that_card(self):
        turn = decide([MOVE, INBOX, SAVE], decline_for="call-save")
        assert turn.approved == frozenset() and [p["fp"] for p in turn.remaining] == ["fp-move", "fp-inbox"]

    def test_typed_yes_runs_the_one_waiting_action(self):
        assert decide([MOVE], approval_for=None).approved == {"fp-move"}
        # An older leftover doesn't make a fresh single preview ambiguous.
        old = {**SAVE, "turn": 1}
        assert decide([old, MOVE]).approved == {"fp-move"}

    def test_typed_yes_with_several_waiting_runs_nothing(self):
        turn = decide([MOVE, INBOX, SAVE])
        assert turn.approved == frozenset() and turn.mode == "typed_ambiguous" and turn.waiting == 3

    def test_nothing_waiting(self):
        assert decide([]).approved == frozenset() and decide(None).mode == "none"

    def test_the_model_is_told_why(self):
        assert "different card" in blocked_instruction("card", 3)
        assert "3 actions are waiting" in blocked_instruction("typed_ambiguous", 3)
        assert "do not say it is done" in blocked_instruction("card", 1)


class _Conversation:
    def __init__(self, pending):
        self.pending_confirmations = list(pending)

    async def save(self):
        return None


def _ctx(conversation, *, approved, mode="card", call_id="call-now"):
    deps = SimpleNamespace(
        conversation=conversation, turn_marker=6,
        approved_confirmations=approved, approval_mode=mode, approval_waiting=3,
    )
    return SimpleNamespace(deps=deps, tool_call_id=call_id)


PREVIEW = {"action": "save_to_folder", "preview": "Save Award Snapshot.md", "needs_confirmation": True}


@pytest.mark.asyncio
async def test_gate_refuses_an_armed_action_this_turn_did_not_approve():
    fp = _confirm_fingerprint("save_to_folder", {"name": "Award Snapshot.md"})
    conv = _Conversation([{"fp": fp, "turn": 4, "tool": "save_to_folder", "call_id": "call-save"}])
    out = await _confirm_gate(
        _ctx(conv, approved=frozenset({"fp-move"})), tool_name="save_to_folder",
        key={"name": "Award Snapshot.md"}, confirmed=True, preview=PREVIEW,
    )
    assert out is not None and out["still_waiting"] is True
    assert "needs_confirmation" not in out, "not a new card: its own card is still waiting"
    assert "different card" in out["assistant_instruction"]
    # Still armed, under its own card's id, so that card can still approve it.
    assert conv.pending_confirmations == [{"fp": fp, "turn": 4, "tool": "save_to_folder", "call_id": "call-save"}]


@pytest.mark.asyncio
async def test_gate_runs_the_action_this_turn_approved():
    fp = _confirm_fingerprint("save_to_folder", {"name": "Award Snapshot.md"})
    conv = _Conversation([{"fp": fp, "turn": 4, "tool": "save_to_folder", "call_id": "call-save"}])
    out = await _confirm_gate(
        _ctx(conv, approved=frozenset({fp})), tool_name="save_to_folder",
        key={"name": "Award Snapshot.md"}, confirmed=True, preview=PREVIEW,
    )
    assert out is None
    assert conv.pending_confirmations == []


@pytest.mark.asyncio
async def test_a_preview_records_its_card_id():
    conv = _Conversation([])
    await _confirm_gate(
        _ctx(conv, approved=frozenset(), call_id="call-save"), tool_name="save_to_folder",
        key={"name": "a.md"}, confirmed=False, preview=PREVIEW,
    )
    assert conv.pending_confirmations[0]["call_id"] == "call-save"


# ---------------------------------------------------------------------------
# Through chat_stream: the ticket's turn, with a model that tries everything.
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock  # noqa: E402

from pydantic_ai import Agent, RunContext, Tool  # noqa: E402
from pydantic_ai.models.function import DeltaToolCall, FunctionModel  # noqa: E402

from tests.test_chat_output import chat_harness  # noqa: E402,F401 — fixture

TOOLS = ("move_documents_to_project", "propose_obligations", "save_to_folder")


def _armed():
    return [
        {"fp": _confirm_fingerprint(name, {"card": name}), "turn": 0, "tool": name, "call_id": f"call-{name}"}
        for name in TOOLS
    ]


def _agent(executed: list[str]) -> Agent:
    def make(name):
        async def tool(ctx: RunContext, confirmed: bool = False) -> dict:
            gate = await _confirm_gate(ctx, tool_name=name, key={"card": name}, confirmed=confirmed,
                                       preview={"action": name, "preview": name, "needs_confirmation": True})
            if gate is not None:
                return gate
            executed.append(name)
            return {"status": "completed"}
        return Tool(tool, name=name, takes_ctx=True)

    called: list[bool] = []

    async def respond(messages, info):
        if not called:
            called.append(True)
            # The model reads "Yes, go ahead" as approval for everything waiting.
            yield {i: DeltaToolCall(name=name, json_args='{"confirmed": true}', tool_call_id=f"run-{name}")
                   for i, name in enumerate(TOOLS)}
        else:
            for char in "Done.":
                yield char

    return Agent(FunctionModel(stream_function=respond), tools=[make(n) for n in TOOLS])


@pytest.mark.parametrize("approval_for,expected", [
    ("call-move_documents_to_project", ["move_documents_to_project"]),
    (None, []),  # typed "yes" with three waiting: nothing runs
])
async def test_one_card_click_runs_only_that_action(chat_harness, approval_for, expected):  # noqa: F811
    conv = chat_harness.conversation
    conv.pending_confirmations = _armed()
    conv.save = AsyncMock()
    executed: list[str] = []
    chunks = await chat_harness.run(_agent(executed), message="Yes, go ahead", approval_for=approval_for)
    assert executed == expected
    blocked = [c for c in chunks if c["kind"] == "tool_result" and isinstance(c.get("content"), dict) and c["content"].get("still_waiting")]
    assert len(blocked) == 3 - len(expected)
    # The other two cards stay armed under their own ids.
    assert {p["call_id"] for p in conv.pending_confirmations} == {f"call-{n}" for n in TOOLS if n not in expected}
    # ...and the client is told exactly which cards are still waiting.
    pending = [c for c in chunks if c["kind"] == "pending_approvals"]
    assert set(pending[-1]["call_ids"]) == {f"call-{n}" for n in TOOLS if n not in expected}
