"""Phase 3 of the agentic-chat harness uplift: replay-time micro-compaction.

Old read-tool results replay as CLEARED_TOOL_RESULT_MARKER once the persisted
boundary advances; stored segments (UI/audit) keep full payloads; write-tool
previews are never touched (confirm-gate invariant)."""

from pydantic_ai.messages import ToolReturnPart

from app.models.chat import (
    ChatMessage,
    ChatConversation,
    ChatRole,
    CLEARED_TOOL_RESULT_MARKER,
)
from app.services.chat_tools import COMPACTABLE_TOOLS


def _assistant_with_result(tool_name: str, call_id: str, content="BULKY " * 50):
    # model_construct: build without a live Beanie collection (repo test idiom).
    return ChatMessage.model_construct(
        role=ChatRole.ASSISTANT,
        message="done",
        segments=[
            {"kind": "tool_call", "call": {
                "tool_name": tool_name, "tool_call_id": call_id, "args": {},
            }},
            {"kind": "tool_result", "result": {
                "tool_name": tool_name, "tool_call_id": call_id, "content": content,
            }},
            {"kind": "text", "content": "done"},
        ],
    )


def _plain_message(role: ChatRole, text: str):
    return ChatMessage.model_construct(role=role, message=text, segments=None)


def _conv(**overrides) -> ChatConversation:
    fields = {
        "uuid": "c1",
        "title": "t",
        "user_id": "u1",
        "messages": [],
        "context_mode": "full",
        "context_cutoff_index": 0,
        "last_context_tokens": 0,
        "last_context_message_count": -1,
        "tool_results_cleared_before": 0,
        **overrides,
    }
    return ChatConversation.model_construct(**fields)


def _tool_returns(model_messages) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in model_messages:
        for part in getattr(m, "parts", ()):
            if isinstance(part, ToolReturnPart):
                out[part.tool_call_id] = part.content
    return out


class TestCompactableToolClassification:
    def test_gated_write_tools_are_never_compactable(self):
        # Clearing a write preview would break the confirm-gate handshake:
        # the model could mis-describe what the user approved.
        for name in (
            "create_knowledge_base", "add_documents_to_kb", "add_url_to_kb",
            "run_workflow", "approve_workflow_step", "reject_workflow_step",
            "run_validation", "create_extraction_from_document",
            "start_optimization", "apply_optimization", "save_to_folder",
            "create_project", "run_pin_on_project", "pin_to_project",
            "create_automation", "create_workflow", "propose_test_case",
            "set_project_status", "unpin_from_project",
            "regenerate_validation_plan",
        ):
            assert name not in COMPACTABLE_TOOLS

    def test_status_tools_stay_out(self):
        assert "get_workflow_status" not in COMPACTABLE_TOOLS
        assert "get_optimization_run" not in COMPACTABLE_TOOLS

    def test_bulky_read_tools_are_in(self):
        for name in ("get_document_text", "search_knowledge_base",
                     "run_extraction", "web_search", "fetch_url"):
            assert name in COMPACTABLE_TOOLS


class TestClearingPass:
    def _conversation(self, msgs: list[ChatMessage], boundary: int) -> ChatConversation:
        return _conv(tool_results_cleared_before=boundary)

    def test_message_level_clearing_swaps_content(self):
        msg = _assistant_with_result("get_document_text", "tc_1")
        replay = msg.to_model_messages(cleared_tool_call_ids={"tc_1"})
        returns = _tool_returns(replay)
        assert returns["tc_1"] == CLEARED_TOOL_RESULT_MARKER
        # Stored segment untouched — clearing is replay-only.
        assert msg.segments[1]["result"]["content"].startswith("BULKY")

    def test_boundary_and_floor(self):
        # Four assistant messages with compactable results; boundary at 3 —
        # the first three are candidates, but the LAST compactable result in
        # the whole conversation (tc_4) plus everything past the boundary
        # stays. tc_1/tc_2/tc_3 clear... except the floor only matters when
        # the newest compactable result is itself old.
        msgs = [
            _assistant_with_result("get_document_text", "tc_1"),
            _assistant_with_result("web_search", "tc_2"),
            _assistant_with_result("search_documents", "tc_3"),
            _assistant_with_result("run_extraction", "tc_4"),
        ]
        conv = self._conversation(msgs, boundary=3)
        cleared = conv._cleared_tool_call_ids(msgs, COMPACTABLE_TOOLS)
        assert cleared == {"tc_1", "tc_2", "tc_3"}

    def test_floor_keeps_most_recent_compactable_even_when_old(self):
        # All compactable results sit before the boundary → the newest one
        # (tc_2) survives so the model keeps one concrete result.
        msgs = [
            _assistant_with_result("get_document_text", "tc_1"),
            _assistant_with_result("web_search", "tc_2"),
            _plain_message(ChatRole.USER, "hi"),
            _plain_message(ChatRole.ASSISTANT, "plain text reply"),
        ]
        conv = self._conversation(msgs, boundary=4)
        cleared = conv._cleared_tool_call_ids(msgs, COMPACTABLE_TOOLS)
        assert cleared == {"tc_1"}

    def test_non_compactable_results_never_clear(self):
        msgs = [
            _assistant_with_result("add_documents_to_kb", "tc_w"),
            _assistant_with_result("get_workflow_status", "tc_s"),
            _assistant_with_result("get_document_text", "tc_r1"),
            _assistant_with_result("get_document_text", "tc_r2"),
        ]
        conv = self._conversation(msgs, boundary=4)
        cleared = conv._cleared_tool_call_ids(msgs, COMPACTABLE_TOOLS)
        assert cleared == {"tc_r1"}  # tc_r2 is the floor; write/status kept

    def test_zero_boundary_clears_nothing(self):
        msgs = [_assistant_with_result("get_document_text", "tc_1")]
        conv = self._conversation(msgs, boundary=0)
        assert conv._cleared_tool_call_ids(msgs, COMPACTABLE_TOOLS) == set()

    def test_no_compactable_set_clears_nothing(self):
        msgs = [_assistant_with_result("get_document_text", "tc_1")]
        conv = self._conversation(msgs, boundary=1)
        assert conv._cleared_tool_call_ids(msgs, frozenset()) == set()


class TestAdvanceBoundaryTrigger:
    """_maybe_advance_microcompact_boundary: anchored estimate vs 60% trigger."""

    def _conversation(self, n_messages: int, anchor: int) -> ChatConversation:
        from beanie import PydanticObjectId

        return _conv(
            messages=[PydanticObjectId() for _ in range(n_messages)],
            last_context_tokens=anchor,
            # Anchor stamped before the current user message arrived.
            last_context_message_count=n_messages - 1,
        )

    def _patch_save(self, monkeypatch, saved: list):
        async def fake_save(self):
            saved.append(True)
        monkeypatch.setattr(ChatConversation, "save", fake_save)

    async def test_advances_past_trigger(self, monkeypatch):
        from app.services.chat_service import _maybe_advance_microcompact_boundary

        saved: list = []
        self._patch_save(monkeypatch, saved)
        # 200k window → effective 191,808 → trigger ~115k. Anchor 150k is past.
        conv = self._conversation(n_messages=20, anchor=150_000)
        advanced = await _maybe_advance_microcompact_boundary(
            conv, "test-model", "hello", {"context_window": 200_000},
        )
        assert advanced is True
        assert conv.tool_results_cleared_before == 20 - 1 - 6
        # Anchor dropped: this turn's meter must count the cleared replay.
        assert conv.last_context_tokens == 0
        assert saved

    async def test_below_trigger_does_nothing(self, monkeypatch):
        from app.services.chat_service import _maybe_advance_microcompact_boundary

        self._patch_save(monkeypatch, [])
        conv = self._conversation(n_messages=20, anchor=50_000)
        advanced = await _maybe_advance_microcompact_boundary(
            conv, "test-model", "hello", {"context_window": 200_000},
        )
        assert advanced is False
        assert conv.tool_results_cleared_before == 0
        assert conv.last_context_tokens == 50_000

    async def test_stale_anchor_waits_for_reanchor(self, monkeypatch):
        from app.services.chat_service import _maybe_advance_microcompact_boundary

        self._patch_save(monkeypatch, [])
        conv = self._conversation(n_messages=20, anchor=150_000)
        conv.last_context_message_count = 5  # e.g. a failed turn intervened
        advanced = await _maybe_advance_microcompact_boundary(
            conv, "test-model", "hello", {"context_window": 200_000},
        )
        assert advanced is False

    async def test_boundary_is_monotonic(self, monkeypatch):
        from app.services.chat_service import _maybe_advance_microcompact_boundary

        self._patch_save(monkeypatch, [])
        conv = self._conversation(n_messages=10, anchor=150_000)
        conv.tool_results_cleared_before = 8  # already past 10-1-6=3
        advanced = await _maybe_advance_microcompact_boundary(
            conv, "test-model", "hello", {"context_window": 200_000},
        )
        assert advanced is False
        assert conv.tool_results_cleared_before == 8

    async def test_short_conversation_never_advances(self, monkeypatch):
        from app.services.chat_service import _maybe_advance_microcompact_boundary

        self._patch_save(monkeypatch, [])
        # Even past the trigger, ≤7 messages means nothing is old enough.
        conv = self._conversation(n_messages=5, anchor=150_000)
        advanced = await _maybe_advance_microcompact_boundary(
            conv, "test-model", "hello", {"context_window": 200_000},
        )
        assert advanced is False
