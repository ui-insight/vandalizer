"""Tests for app.services.chat_service — _ThinkTagParser and _extract_event_content.

The streaming chat functions are tested via integration tiers; here we focus
on the deterministic parsing helpers that can be unit-tested without LLM calls.
"""

from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# _ThinkTagParser
# ---------------------------------------------------------------------------


class TestThinkTagParser:
    def _make(self):
        from app.services.chat_service import _ThinkTagParser
        return _ThinkTagParser()

    def test_plain_text_passes_through(self):
        p = self._make()
        result = p.feed("Hello world")
        # May hold back a few chars for safety
        texts = [c for k, c in result if k == "text"]
        assert "".join(texts).startswith("Hello")

    def test_detects_think_block(self):
        p = self._make()
        result = p.feed("<think>reasoning here</think>visible")
        kinds = [k for k, _ in result]
        assert "thinking" in kinds
        assert "text" in kinds

    def test_thinking_content_captured(self):
        p = self._make()
        result = p.feed("<thinking>deep thought</thinking>answer")
        thinking_parts = [c for k, c in result if k == "thinking"]
        assert any("deep thought" in t for t in thinking_parts)

    def test_flush_emits_remaining(self):
        p = self._make()
        # Feed text that ends with '<' so parser holds it back
        p.feed("partial<")
        result = p.flush()
        assert len(result) > 0
        assert result[0][0] == "text"

    def test_flush_empty_when_nothing_pending(self):
        p = self._make()
        # Feed enough to emit everything, then flush
        p.feed("hello world this is a long enough string")
        p.flush()
        p.pending = ""
        result = p.flush()
        assert result == []

    def test_streaming_across_chunks(self):
        p = self._make()
        # Split a think tag across two chunks
        r1 = p.feed("before<thi")
        r2 = p.feed("nk>inside</think>after")
        r3 = p.flush()

        all_parts = r1 + r2 + r3
        text_parts = "".join(c for k, c in all_parts if k == "text")
        think_parts = "".join(c for k, c in all_parts if k == "thinking")

        assert "before" in text_parts
        assert "after" in text_parts
        assert "inside" in think_parts

    def test_nested_angle_brackets_dont_break(self):
        p = self._make()
        result = p.feed("x < 5 and y > 3")
        all_text = "".join(c for k, c in result if k == "text")
        # Should preserve the comparison operators
        flush = p.flush()
        all_text += "".join(c for k, c in flush if k == "text")
        assert "x" in all_text

    def test_multiple_think_blocks(self):
        p = self._make()
        result = p.feed("<think>first</think>middle<think>second</think>end")
        flush = p.flush()
        all_parts = result + flush

        thinking = [c for k, c in all_parts if k == "thinking"]
        text = [c for k, c in all_parts if k == "text"]

        assert any("first" in t for t in thinking)
        assert any("second" in t for t in thinking)
        assert any("middle" in t for t in text)


# ---------------------------------------------------------------------------
# _extract_event_content
# ---------------------------------------------------------------------------


class TestExtractEventContent:
    def test_text_part_start_event(self):
        from app.services.chat_service import _extract_event_content
        from pydantic_ai.messages import PartStartEvent, TextPart

        event = PartStartEvent(index=0, part=TextPart(content="hello"))
        content, is_thinking = _extract_event_content(event)
        assert content == "hello"
        assert is_thinking is False

    def test_thinking_part_start_event(self):
        from app.services.chat_service import _extract_event_content
        from pydantic_ai.messages import PartStartEvent, ThinkingPart

        event = PartStartEvent(index=0, part=ThinkingPart(content="reasoning"))
        content, is_thinking = _extract_event_content(event)
        assert content == "reasoning"
        assert is_thinking is True

    def test_text_part_delta_event(self):
        from app.services.chat_service import _extract_event_content
        from pydantic_ai.messages import PartDeltaEvent, TextPartDelta

        event = PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="more text"))
        content, is_thinking = _extract_event_content(event)
        assert content == "more text"
        assert is_thinking is False

    def test_thinking_part_delta_event(self):
        from app.services.chat_service import _extract_event_content
        from pydantic_ai.messages import PartDeltaEvent, ThinkingPartDelta

        event = PartDeltaEvent(index=0, delta=ThinkingPartDelta(content_delta="more thought"))
        content, is_thinking = _extract_event_content(event)
        assert content == "more thought"
        assert is_thinking is True

    def test_unrecognized_event_returns_none(self):
        from app.services.chat_service import _extract_event_content

        # A plain object that isn't PartStartEvent or PartDeltaEvent
        event = object()
        content, is_thinking = _extract_event_content(event)
        assert content is None


class TestBuildInterruptedBody:
    """Guards the user/assistant pairing invariant on stream failures.

    chat.py persists the user message before streaming. If the LLM call
    times out or is cancelled, _save_failed_assistant_turn uses this helper
    to compose a placeholder so the conversation never has consecutive user
    turns (which pydantic-ai rejects on the next request).
    """

    def test_partial_text_is_preserved_with_interrupted_suffix(self):
        from app.services.chat_service import _build_interrupted_body

        body = _build_interrupted_body(["Hello ", "world"], "client disconnected")
        assert body.startswith("Hello world")
        assert "interrupted" in body
        assert "client disconnected" in body

    def test_no_partial_yields_no_response_placeholder(self):
        from app.services.chat_service import _build_interrupted_body

        body = _build_interrupted_body([], "request timed out")
        assert "no response" in body
        assert "request timed out" in body

    def test_strips_residual_think_tags_from_partial(self):
        from app.services.chat_service import _build_interrupted_body

        body = _build_interrupted_body(
            ["<think>internal monologue</think>visible answer"],
            "connection closed",
        )
        assert "internal monologue" not in body
        assert "visible answer" in body

    def test_whitespace_only_partial_treated_as_empty(self):
        from app.services.chat_service import _build_interrupted_body

        body = _build_interrupted_body(["   \n  "], "context over budget")
        assert body.startswith("_(no response")
