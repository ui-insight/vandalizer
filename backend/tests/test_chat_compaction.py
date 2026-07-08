"""Phase 4 of the agentic-chat harness uplift: auto-compaction.

Covers the tail cutoff (minimums, cap, user-boundary snap, pending-
confirmation floor), summary post-processing, the trigger, and the circuit
breaker. The summarizer itself is exercised through compact_conversation with
a stubbed LLM call."""

import pytest

from app.models.chat import ChatConversation, ChatMessage, ChatRole
from app.services import chat_compaction
from app.services.chat_compaction import (
    CompactionError,
    compute_tail_cutoff,
    CONTINUATION_PREAMBLE,
    format_compact_summary,
    TAIL_MIN_MESSAGES,
)
from app.services.chat_service import (
    _autocompact_needed,
    AUTOCOMPACT_MAX_CONSECUTIVE_FAILURES,
)


def _msg(role: ChatRole, text: str) -> ChatMessage:
    return ChatMessage.model_construct(role=role, message=text, segments=None)


def _exchanges(n: int, chars_per_message: int = 200) -> list[ChatMessage]:
    msgs: list[ChatMessage] = []
    for i in range(n):
        msgs.append(_msg(ChatRole.USER, f"question {i} " + "x" * chars_per_message))
        msgs.append(_msg(ChatRole.ASSISTANT, f"answer {i} " + "y" * chars_per_message))
    return msgs


def _conv(**overrides) -> ChatConversation:
    fields = {
        "uuid": "c1",
        "title": "t",
        "user_id": "u1",
        "messages": [],
        "context_mode": "full",
        "context_cutoff_index": 0,
        "compact_summary": None,
        "pending_confirmations": [],
        "last_context_tokens": 0,
        "last_context_message_count": -1,
        "consecutive_autocompact_failures": 0,
        "tool_results_cleared_before": 0,
        **overrides,
    }
    return ChatConversation.model_construct(**fields)


class TestComputeTailCutoff:
    def test_small_conversation_keeps_everything(self):
        msgs = _exchanges(3)  # 6 messages, tiny
        assert compute_tail_cutoff(msgs, _conv()) == 0

    def test_minimums_win_over_token_target(self):
        # 30 tiny messages: token minimum can't be met, but message minimum
        # keeps at least TAIL_MIN_MESSAGES... actually tiny messages never
        # reach 10k tokens, so the tail extends all the way back → cutoff 0.
        msgs = _exchanges(15, chars_per_message=40)
        assert compute_tail_cutoff(msgs, _conv()) == 0

    def test_large_conversation_cuts_and_snaps_to_user_boundary(self):
        # 40 exchanges × ~2×2.5k tokens ≫ minimums: a cutoff must exist,
        # sit on a user message, and keep at least the message minimum.
        msgs = _exchanges(40, chars_per_message=10_000)
        conv = _conv()
        cutoff = compute_tail_cutoff(msgs, conv)
        assert 0 < cutoff < len(msgs)
        assert msgs[cutoff].role == ChatRole.USER
        assert len(msgs) - cutoff >= TAIL_MIN_MESSAGES

    def test_pending_confirmation_floors_the_cutoff(self):
        msgs = _exchanges(40, chars_per_message=10_000)
        conv = _conv(pending_confirmations=[{"fp": "abc", "turn": 4, "tool": "run_workflow"}])
        cutoff = compute_tail_cutoff(msgs, conv)
        assert cutoff <= 4

    def test_keep_tail_false_summarizes_everything(self):
        msgs = _exchanges(40, chars_per_message=10_000)
        assert compute_tail_cutoff(msgs, _conv(), keep_tail=False) == len(msgs)

    def test_keep_tail_false_still_respects_pending_confirmations(self):
        msgs = _exchanges(10)
        conv = _conv(pending_confirmations=[{"fp": "abc", "turn": 6, "tool": "save_to_folder"}])
        assert compute_tail_cutoff(msgs, conv, keep_tail=False) <= 6

    def test_prior_cutoff_is_the_floor(self):
        msgs = _exchanges(40, chars_per_message=10_000)
        conv = _conv(context_mode="compacted", context_cutoff_index=30)
        cutoff = compute_tail_cutoff(msgs, conv)
        assert cutoff >= 30


class TestFormatCompactSummary:
    def test_strips_analysis_and_unwraps_summary(self):
        raw = (
            "<analysis>chronological scratchpad noise</analysis>\n"
            "<summary>1. Primary Request: extract F&A rates</summary>"
        )
        out = format_compact_summary(raw)
        assert out.startswith(CONTINUATION_PREAMBLE)
        assert "scratchpad noise" not in out
        assert "extract F&A rates" in out

    def test_survives_missing_tags(self):
        out = format_compact_summary("plain summary text")
        assert out == CONTINUATION_PREAMBLE + "plain summary text"

    def test_unclosed_analysis_block_is_dropped(self):
        # A truncated response must not leak the scratchpad into context.
        with pytest.raises(CompactionError):
            format_compact_summary("<analysis>never closed and no summary")

    def test_empty_raises(self):
        with pytest.raises(CompactionError):
            format_compact_summary("  <analysis>only analysis</analysis>  ")


class TestCompactConversation:
    def _patched(self, monkeypatch, msgs, summary_raw="<summary>the summary</summary>"):
        # ChatMessage.find is a classmethod chain; patch at module level.
        class _FindResult:
            def __init__(self, items):
                self._items = items

            async def to_list(self):
                return self._items

        monkeypatch.setattr(
            chat_compaction.ChatMessage, "find",
            classmethod(lambda cls, *a, **k: _FindResult(msgs)),
        )

        calls: list[str] = []

        async def fake_summarize(transcript, model_name, sys_config_doc, user_id, team_id):
            calls.append(transcript)
            return summary_raw

        monkeypatch.setattr(chat_compaction, "_summarize", fake_summarize)

        saved: list[bool] = []

        async def fake_save(self):
            saved.append(True)

        monkeypatch.setattr(ChatConversation, "save", fake_save)
        return calls, saved

    async def test_happy_path_sets_cutoff_summary_and_resets(self, monkeypatch):
        from beanie import PydanticObjectId

        msgs = _exchanges(10)
        calls, saved = self._patched(monkeypatch, msgs)
        conv = _conv(
            messages=[PydanticObjectId() for _ in msgs],
            last_context_tokens=120_000,
            last_context_message_count=len(msgs),
            consecutive_autocompact_failures=2,
        )
        result = await chat_compaction.compact_conversation(
            conv, model_name="m", sys_config_doc={}, user_id="u1", keep_tail=False,
        )
        assert result.cutoff == len(msgs)
        assert result.summarized_count == len(msgs)
        assert conv.context_mode == "compacted"
        assert conv.compact_summary.startswith(CONTINUATION_PREAMBLE)
        assert conv.last_context_tokens == 0  # anchor invalidated
        assert conv.consecutive_autocompact_failures == 0  # breaker reset
        assert saved and calls

    async def test_prompt_too_long_retries_with_fewer_messages(self, monkeypatch):
        from beanie import PydanticObjectId

        msgs = _exchanges(10)
        transcripts: list[str] = []

        async def flaky_summarize(transcript, *a, **k):
            transcripts.append(transcript)
            if len(transcripts) == 1:
                raise RuntimeError("prompt is too long: 210000 tokens > maximum context")
            return "<summary>fit on retry</summary>"

        self._patched(monkeypatch, msgs)
        monkeypatch.setattr(chat_compaction, "_summarize", flaky_summarize)
        conv = _conv(messages=[PydanticObjectId() for _ in msgs])
        result = await chat_compaction.compact_conversation(
            conv, model_name="m", sys_config_doc={}, user_id="u1", keep_tail=False,
        )
        assert "fit on retry" in conv.compact_summary
        assert len(transcripts) == 2
        assert len(transcripts[1]) < len(transcripts[0])
        assert result.summarized_count == len(msgs)

    async def test_non_context_error_raises_compaction_error(self, monkeypatch):
        from beanie import PydanticObjectId

        msgs = _exchanges(10)
        self._patched(monkeypatch, msgs)

        async def broken_summarize(*a, **k):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(chat_compaction, "_summarize", broken_summarize)
        conv = _conv(messages=[PydanticObjectId() for _ in msgs])
        with pytest.raises(CompactionError):
            await chat_compaction.compact_conversation(
                conv, model_name="m", sys_config_doc={}, user_id="u1", keep_tail=False,
            )
        # Failure must not half-apply: mode unchanged.
        assert conv.context_mode == "full"

    async def test_nothing_to_compact_raises(self, monkeypatch):
        from beanie import PydanticObjectId

        msgs = _exchanges(2)  # tail keeps everything
        self._patched(monkeypatch, msgs)
        conv = _conv(messages=[PydanticObjectId() for _ in msgs])
        with pytest.raises(CompactionError):
            await chat_compaction.compact_conversation(
                conv, model_name="m", sys_config_doc={}, user_id="u1",
            )


class TestAutocompactTrigger:
    def _conv_with_anchor(self, anchor: int, n_messages: int = 30) -> ChatConversation:
        from beanie import PydanticObjectId

        return _conv(
            messages=[PydanticObjectId() for _ in range(n_messages)],
            last_context_tokens=anchor,
            last_context_message_count=n_messages - 1,
        )

    def test_fires_past_compact_threshold(self):
        # 200k window → effective 191,808 → compact at eff-13k ≈ 178.8k.
        conv = self._conv_with_anchor(185_000)
        assert _autocompact_needed(conv, "m", "hi", {"context_window": 200_000})

    def test_quiet_below_threshold(self):
        conv = self._conv_with_anchor(100_000)
        assert not _autocompact_needed(conv, "m", "hi", {"context_window": 200_000})

    def test_quiet_without_valid_anchor(self):
        conv = self._conv_with_anchor(185_000)
        conv.last_context_message_count = 3  # stale (e.g. microcompact just ran)
        assert not _autocompact_needed(conv, "m", "hi", {"context_window": 200_000})

    def test_breaker_constant(self):
        assert AUTOCOMPACT_MAX_CONSECUTIVE_FAILURES == 3
