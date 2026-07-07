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
        assert "context over budget" in body


# ---------------------------------------------------------------------------
# _build_project_context — the block that makes the agent project-aware
# ---------------------------------------------------------------------------


class TestBuildProjectContext:
    @pytest.mark.asyncio
    async def test_empty_when_project_unauthorized(self):
        from unittest.mock import AsyncMock, patch

        from app.services import chat_service, project_service

        # The helper imports project_service lazily; patch on the module singleton.
        with patch.object(project_service, "get_authorized_project",
                          AsyncMock(return_value=None)):
            out = await chat_service._build_project_context("missing", MagicMock())
        assert out == ""

    @pytest.mark.asyncio
    async def test_includes_title_state_role_and_pin_target_ids(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from app.services import chat_service, project_service

        project = SimpleNamespace(
            uuid="p1", title="NIH R01", state="active", description="Grant",
        )
        overview = {
            "role": "owner",
            "capabilities": {
                "files": {"count": 4, "folders": 1},
                "knowledge": {"ready": True, "documents": 3},
            },
        }
        pins = [
            {"pin_type": "workflow", "target_id": "wf-1", "name": "Compliance check"},
            {"pin_type": "extraction", "target_id": "ss-1", "name": "Budget fields"},
        ]
        with (
            patch.object(project_service, "get_authorized_project",
                        AsyncMock(return_value=project)),
            patch.object(project_service, "get_project_overview",
                        AsyncMock(return_value=overview)),
            patch.object(project_service, "list_pins",
                        AsyncMock(return_value=pins)),
        ):
            out = await chat_service._build_project_context("p1", MagicMock())

        assert "NIH R01" in out
        assert "state: active" in out
        assert "their role: owner" in out
        assert "wf-1" in out and "ss-1" in out  # target_ids the agent runs with
        assert "WHOLE workspace" in out  # the do-not-narrow instruction


# ---------------------------------------------------------------------------
# _brand_org_text — white-label identity branding
# ---------------------------------------------------------------------------


class TestBrandOrgText:
    def _brand(self, text, org):
        from app.services.chat_service import _brand_org_text
        return _brand_org_text(text, org)

    def test_default_deploy_is_unchanged(self):
        text = "You are Vandalizer, built for research administration at the University of Idaho."
        # Empty org and the literal default both mean "use built-in defaults".
        assert self._brand(text, "") == text
        assert self._brand(text, "Vandalizer") == text

    def test_custom_org_swaps_product_name(self):
        out = self._brand("You are the Vandalizer assistant.", "Acme Research")
        assert "Vandalizer" not in out
        assert "Acme Research" in out

    def test_custom_org_drops_home_institution(self):
        # White-label deploys are not the University of Idaho — the geography
        # must not leak once a custom org name is configured.
        text = (
            "You are Vandalizer, a document intelligence assistant built for "
            "research administration at the University of Idaho."
        )
        out = self._brand(text, "Boise State University")
        assert "University of Idaho" not in out
        assert "built for research administration." in out

    def test_custom_org_drops_institution_first_session_phrasing(self):
        text = "You are the assistant, built at the University of Idaho for research administration."
        out = self._brand(text, "Acme")
        assert "University of Idaho" not in out
        assert "built for research administration" in out


# ---------------------------------------------------------------------------
# _classify_stream_error — never leak raw exceptions to the user
# ---------------------------------------------------------------------------


class TestClassifyStreamError:
    def _classify(self, exc):
        from app.services.chat_service import _classify_stream_error
        return _classify_stream_error(exc)

    def test_context_length_is_a_warning(self):
        severity, msg = self._classify(Exception("This exceeds model's maximum context length"))
        assert severity == "warning"
        assert "too large" in msg

    def test_transient_gateway_is_a_warning(self):
        severity, msg = self._classify(Exception("502 bad gateway"))
        assert severity == "warning"
        assert "try again" in msg.lower()

    def test_unexpected_error_does_not_leak_raw_exception(self):
        secret = "Traceback: psycopg2.OperationalError at 10.0.0.5:5432"
        severity, msg = self._classify(Exception(secret))
        assert severity == "error"
        # The raw exception text must not reach the user-facing message.
        assert secret not in msg
        assert "10.0.0.5" not in msg
        assert "went wrong" in msg.lower()


# ---------------------------------------------------------------------------
# _hold_message_for_unreadable_docs — don't hallucinate about unread files
# ---------------------------------------------------------------------------


class TestHoldMessageForUnreadableDocs:
    """The user attaches a doc that's still OCR-processing (or that failed
    extraction) and asks a question. chat_stream must NOT run the agent — it
    would confabulate about a file it never read — and instead return an honest
    holding reply. This covers the decision + wording; chat_stream wires it to
    a stream-and-return."""

    def _hold(self, **over):
        from app.services.chat_service import _hold_message_for_unreadable_docs

        kwargs = dict(
            document_uuids=["doc-1"],
            doc_segments=[],
            kb_sources=[],
            attachment_segments=[],
            skipped_no_text=[],
            errored_docs=[],
        )
        kwargs.update(over)
        return _hold_message_for_unreadable_docs(**kwargs)

    def test_holds_when_doc_still_processing(self):
        msg = self._hold(skipped_no_text=["19E777.pdf"])
        assert msg is not None
        assert "19E777.pdf" in msg
        assert "still being processed" in msg

    def test_holds_when_doc_extraction_failed(self):
        msg = self._hold(errored_docs=["19E777.pdf"])
        assert msg is not None
        assert "extraction failed" in msg
        assert "Retry extraction" in msg

    def test_processing_takes_priority_and_pluralizes(self):
        msg = self._hold(skipped_no_text=["a.pdf", "b.pdf"], errored_docs=["c.pdf"])
        assert "they are" in msg and "them" in msg  # plural phrasing
        assert "still being processed" in msg  # not-ready wins over failed

    def test_no_hold_when_a_doc_is_readable(self):
        # One doc produced text → run the agent normally.
        assert self._hold(doc_segments=["## Document: x"], skipped_no_text=["y.pdf"]) is None

    def test_no_hold_with_kb_or_attachment_grounding(self):
        assert self._hold(kb_sources=[{"x": 1}], skipped_no_text=["y.pdf"]) is None
        assert self._hold(attachment_segments=["web"], skipped_no_text=["y.pdf"]) is None

    def test_no_hold_when_no_docs_attached(self):
        # Plain chat with no document context — never holds.
        assert self._hold(document_uuids=[], skipped_no_text=[]) is None


# ---------------------------------------------------------------------------
# create_chat_agent grounding-prompt delivery (regression)
# ---------------------------------------------------------------------------


class TestChatAgentGroundingEveryTurn:
    """The grounding prompt must reach the model on EVERY turn, not just the
    first message of a conversation.

    pydantic-ai injects a static ``system_prompt`` only when ``message_history``
    is empty (``_agent_graph``: ``if not messages: parts.extend(_sys_parts())``).
    Multi-turn chat rebuilds history from stored ChatMessage text, which carries
    no system prompt, so ``create_chat_agent(..., system_prompt=)`` silently
    dropped the KB cite-by-filename / refuse-when-unsupported guardrails on every
    follow-up question — an out-of-scope question that was refused in a fresh
    chat would get answered as a follow-up. The fix passes the prompt as
    ``instructions``, which pydantic-ai re-sends on every model request.
    """

    def _agent_capturing_instructions(self, monkeypatch, prompt):
        """Build a real create_chat_agent whose model records the
        ``instructions`` seen on each request, with no network/config deps."""
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, TextPart
        from app.services import llm_service

        seen: list = []

        def fn(messages, info):
            seen.append(getattr(messages[-1], "instructions", "NO_ATTR"))
            return ModelResponse(parts=[TextPart("ok")])

        monkeypatch.setattr(llm_service, "get_agent_model", lambda *a, **k: FunctionModel(fn))
        monkeypatch.setattr(llm_service, "build_thinking_model_settings", lambda *a, **k: {})
        agent = llm_service.create_chat_agent("test-model", system_prompt=prompt)
        return agent, seen

    @pytest.mark.asyncio
    async def test_prompt_delivered_on_followup_turn(self, monkeypatch):
        prompt = "GROUNDING: refuse when the snippets don't support an answer."
        agent, seen = self._agent_capturing_instructions(monkeypatch, prompt)

        first = await agent.run("an out-of-scope question")
        # Replay history exactly as multi-turn chat does, then ask again.
        await agent.run("another out-of-scope question", message_history=first.new_messages())

        assert seen == [prompt, prompt], (
            "grounding prompt must be present on the follow-up turn, not just "
            f"the first; saw {seen}"
        )
