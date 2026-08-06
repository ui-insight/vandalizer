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
        assert "no response" in body
        assert "context over budget" in body


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


# ---------------------------------------------------------------------------
# Citation persistence
# ---------------------------------------------------------------------------


class TestCitationPersistence:
    def _citation(self, **overrides):
        base = {
            "document_id": "src-1",
            "document_title": "budget.xlsx",
            "page": None,
            "sheet": "Year 1",
            "chunk_id": "src-1_chunk_3",
            "score": 0.42,
            "similarity": 0.79,
            "content_preview": "| Category | Amount |",
        }
        base.update(overrides)
        return base

    def test_chat_message_to_dict_includes_citations(self):
        from app.models.chat import ChatMessage, ChatRole

        msg = ChatMessage.model_construct(
            role=ChatRole.ASSISTANT,
            message="answer",
            citations=[self._citation()],
        )
        d = msg.to_dict()
        assert d["citations"] == [self._citation()]

    def test_chat_message_to_dict_omits_absent_citations(self):
        from app.models.chat import ChatMessage, ChatRole

        msg = ChatMessage.model_construct(
            role=ChatRole.ASSISTANT, message="answer", citations=None,
        )
        assert "citations" not in msg.to_dict()

    @pytest.mark.asyncio
    async def test_finalize_passes_citations_to_add_message(self):
        from unittest.mock import AsyncMock

        from app.models.chat import ChatRole
        from app.services.chat_service import _finalize

        conversation = MagicMock()
        conversation.add_message = AsyncMock()
        citations = [self._citation()]

        await _finalize(
            conversation, "answer", [], None, None, "user-1",
            citations=citations,
        )

        conversation.add_message.assert_awaited_once()
        args, kwargs = conversation.add_message.await_args
        assert args[0] == ChatRole.ASSISTANT
        assert kwargs["citations"] == citations


# ---------------------------------------------------------------------------
# System prompt selection
# ---------------------------------------------------------------------------


class TestChatSystemPromptSelection:
    """Every context state must resolve to a grounded prompt.

    The no-context branch used to fall through to ``system_prompt=None``, which
    ``create_chat_agent`` turns into ``DEFAULT_CHAT_SYSTEM_PROMPT`` — a prompt
    carrying no grounding rule at all. That let "what is the total requested in
    this proposal?" be answered from invention when no proposal was attached.
    """

    def _select(self, **overrides):
        from app.services.chat_service import select_chat_system_prompt
        kwargs = dict(
            kb_sources=[],
            have_context=False,
            kb_uuid=None,
            is_first_session=False,
            include_onboarding_context=False,
            manifest_block="",
        )
        kwargs.update(overrides)
        return select_chat_system_prompt(**kwargs)

    def test_no_context_selects_the_no_document_prompt(self):
        from app.services.llm_service import NO_DOCUMENT_SYSTEM_PROMPT
        assert self._select() == NO_DOCUMENT_SYSTEM_PROMPT

    def test_no_context_never_resolves_to_the_ungrounded_default(self):
        from app.services.llm_service import DEFAULT_CHAT_SYSTEM_PROMPT
        selected = self._select()
        assert selected
        assert selected != DEFAULT_CHAT_SYSTEM_PROMPT

    def test_retrieved_kb_sources_select_the_kb_prompt(self):
        from app.services.llm_service import KB_CHAT_SYSTEM_PROMPT
        assert self._select(kb_sources=[{"document_title": "budget.xlsx"}]) == (
            KB_CHAT_SYSTEM_PROMPT
        )

    def test_kb_prompt_carries_the_manifest_block(self):
        from app.services.llm_service import KB_CHAT_SYSTEM_PROMPT
        # Deliberately not a realistic filename: KB_CHAT_SYSTEM_PROMPT cites
        # "budget.xlsx" as an example, so asserting on that would pass even if
        # the manifest were dropped entirely.
        sentinel = "manifest-sentinel-9f3a2c.pdf"
        selected = self._select(
            kb_sources=[{"document_title": sentinel}],
            manifest_block=f"\n--- FILES ---\n{sentinel}\n",
        )
        assert selected.startswith(KB_CHAT_SYSTEM_PROMPT)
        assert sentinel in selected

    def test_document_context_selects_the_document_prompt(self):
        from app.services.llm_service import DOCUMENT_CHAT_SYSTEM_PROMPT
        assert self._select(have_context=True) == DOCUMENT_CHAT_SYSTEM_PROMPT

    def test_document_prompt_has_absence_guardrails(self):
        # Grant budgets are dense with figures yet often lack the asked-for
        # field; the model must not substitute a neighbouring value (#610).
        from app.services.llm_service import DOCUMENT_CHAT_SYSTEM_PROMPT
        assert "Check before answering" in DOCUMENT_CHAT_SYSTEM_PROMPT
        assert "related-but-different value" in DOCUMENT_CHAT_SYSTEM_PROMPT
        assert "blank form field is not zero" in DOCUMENT_CHAT_SYSTEM_PROMPT
        assert 'states "None", report "None"' in DOCUMENT_CHAT_SYSTEM_PROMPT

    def test_requested_kb_with_no_retrieval_selects_the_empty_kb_prompt(self):
        from app.services.llm_service import build_project_kb_empty_prompt
        assert self._select(kb_uuid="kb-1") == build_project_kb_empty_prompt("")

    def test_first_session_selects_the_onboarding_prompt(self):
        from app.services.llm_service import FIRST_SESSION_SYSTEM_PROMPT
        assert self._select(is_first_session=True) == FIRST_SESSION_SYSTEM_PROMPT

    def test_explicit_onboarding_selects_the_help_prompt(self):
        from app.services.llm_service import HELP_CHAT_SYSTEM_PROMPT
        assert self._select(include_onboarding_context=True) == HELP_CHAT_SYSTEM_PROMPT

    def test_retrieved_sources_take_precedence_over_document_context(self):
        from app.services.llm_service import KB_CHAT_SYSTEM_PROMPT
        assert self._select(
            kb_sources=[{"document_title": "a.pdf"}], have_context=True,
        ) == KB_CHAT_SYSTEM_PROMPT

    def test_document_context_takes_precedence_over_an_empty_kb(self):
        from app.services.llm_service import DOCUMENT_CHAT_SYSTEM_PROMPT
        assert self._select(have_context=True, kb_uuid="kb-1") == (
            DOCUMENT_CHAT_SYSTEM_PROMPT
        )

    def test_an_empty_kb_still_outranks_onboarding_branches(self):
        from app.services.llm_service import build_project_kb_empty_prompt
        assert self._select(
            kb_uuid="kb-1", is_first_session=True, include_onboarding_context=True,
        ) == build_project_kb_empty_prompt("")


class TestNoDocumentPromptContent:
    """The no-document prompt must say the four things the branch depends on.

    Asserted as behavioural clauses rather than exact strings so the wording can
    be revised without breaking the suite.
    """

    def _prompt(self) -> str:
        from app.services.llm_service import NO_DOCUMENT_SYSTEM_PROMPT
        return NO_DOCUMENT_SYSTEM_PROMPT.lower()

    def test_states_that_no_document_is_available(self):
        assert "no document" in self._prompt()

    def test_forbids_inventing_document_specific_content(self):
        prompt = self._prompt()
        assert "invent" in prompt or "fabricat" in prompt

    def test_tells_the_model_to_ask_for_the_source(self):
        assert "attach" in self._prompt()

    def test_still_permits_general_knowledge_answers(self):
        assert "general" in self._prompt()

    def test_carries_the_shared_identity_preamble(self):
        from app.services.llm_service import (
            NO_DOCUMENT_SYSTEM_PROMPT,
            VANDALIZER_IDENTITY_PREAMBLE,
        )
        assert NO_DOCUMENT_SYSTEM_PROMPT.startswith(VANDALIZER_IDENTITY_PREAMBLE)


class TestNoDocumentGroundingEveryTurn:
    """The no-document grounding must survive follow-up turns.

    Same failure mode as TestChatAgentGroundingEveryTurn: a static
    ``system_prompt`` is injected by pydantic-ai only when message_history is
    empty, so a grounding rule delivered that way silently disappears on the
    second question — exactly when a user follows up on a fabricated answer.
    """

    @pytest.mark.asyncio
    async def test_no_document_prompt_delivered_on_followup_turn(self, monkeypatch):
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, TextPart
        from app.services import llm_service

        seen: list = []

        def fn(messages, info):
            seen.append(getattr(messages[-1], "instructions", "NO_ATTR"))
            return ModelResponse(parts=[TextPart("ok")])

        monkeypatch.setattr(llm_service, "get_agent_model", lambda *a, **k: FunctionModel(fn))
        monkeypatch.setattr(llm_service, "build_thinking_model_settings", lambda *a, **k: {})
        agent = llm_service.create_chat_agent(
            "test-model", system_prompt=llm_service.NO_DOCUMENT_SYSTEM_PROMPT,
        )

        first = await agent.run("what is the total requested in this proposal?")
        await agent.run("what page did you get that from?", message_history=first.new_messages())

        # pydantic-ai strips surrounding whitespace from instructions, so compare
        # stripped rather than asserting the constant verbatim.
        expected = llm_service.NO_DOCUMENT_SYSTEM_PROMPT.strip()
        assert len(seen) == 2, f"expected two model requests; saw {len(seen)}"
        assert seen[0] == expected, "grounding missing on the first turn"
        assert seen[1] == expected, (
            "grounding must persist onto the follow-up turn — this is the turn "
            f"where a user challenges a fabricated answer; saw {seen[1]!r}"
        )
