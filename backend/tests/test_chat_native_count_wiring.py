"""How `chat_stream` hands a provider-native token count to the budget planner.

`chat_stream` is a 400-line async generator over Mongo, ChromaDB and a live
model; it is covered by the integration tiers, not here. So the decisions that
matter are pulled out into small pure helpers and asserted directly:

* `_build_chat_prompt`  -- what the counter is asked to count. It has to be the
  prompt chat actually sends, documents and all, because those dominate the
  payload and they are the digit-dense content the 1.5 default margin was sized
  for. A ratio measured on prompt-and-history alone is the wrong sample.
* `_native_for_model`   -- routing can switch models between the count and the
  plan. A count for one model is not a count for another.
* `_margin_for`         -- routing and planning have to agree on the number, so
  it comes from `token_safety_margin`, never from a ratio computed here.
* `_measure_native_count` -- must never raise into the chat path, and must
  produce nothing at all when the provider cannot count.
"""

from __future__ import annotations

import pytest

from app.services import chat_service
from app.services.chat_service import (
    _build_chat_prompt,
    _margin_for,
    _measure_native_count,
    _native_for_model,
    _suggest_model_for_overflow,
)
from app.services.context_budget import (
    DEFAULT_TOKEN_SAFETY_MARGIN,
    DocumentSegment,
    NativeCount,
    plan_and_compact_context,
    token_safety_margin,
)
from app.services.native_token_count import NativeCountResult

MODEL = "anthropic/claude-sonnet-4-5"
OTHER_MODEL = "anthropic/claude-opus-4-1"


# ---------------------------------------------------------------------------
# _build_chat_prompt -- the payload the ratio is measured over
# ---------------------------------------------------------------------------


class TestBuildChatPrompt:
    DOCS = [DocumentSegment(label="proposal", text="BUDGET TABLE 12,345.67")]
    ATTACHMENTS = [DocumentSegment(label="file:notes.txt", text="ATTACHED NOTES")]

    def test_documents_and_attachments_are_in_the_counted_payload(self):
        """The whole point of constraint 2: the counter must see the content
        that dominates the request, not just the question."""
        prompt = _build_chat_prompt(
            "What is the total?",
            self.DOCS,
            self.ATTACHMENTS,
            have_context=True,
            include_onboarding_context=False,
        )
        assert "BUDGET TABLE 12,345.67" in prompt
        assert "ATTACHED NOTES" in prompt
        assert "What is the total?" in prompt

    def test_the_reference_document_scaffolding_is_reproduced(self):
        prompt = _build_chat_prompt(
            "Q", self.DOCS, [], have_context=True, include_onboarding_context=False
        )
        assert prompt == (
            "Q\n\n"
            "--- BEGIN REFERENCE DOCUMENTS (provided for context only) ---\n"
            "BUDGET TABLE 12,345.67\n"
            "--- END REFERENCE DOCUMENTS ---"
        )

    def test_onboarding_only_keeps_its_own_wording(self):
        """`chat_stream` deliberately words the onboarding-only prompt
        differently; a helper that flattened the two would change the prompt
        the model sees, not merely the one we count."""
        prompt = _build_chat_prompt(
            "How do I start?",
            [DocumentSegment(label="onboarding", text="ONBOARDING")],
            [],
            have_context=False,
            include_onboarding_context=True,
        )
        assert prompt == "ONBOARDING\n\nUser question: How do I start?"

    def test_no_context_is_the_bare_message(self):
        prompt = _build_chat_prompt(
            "Hello", [], [], have_context=False, include_onboarding_context=False
        )
        assert prompt == "Hello"

    def test_attachments_follow_documents(self):
        prompt = _build_chat_prompt(
            "Q", self.DOCS, self.ATTACHMENTS,
            have_context=True, include_onboarding_context=False,
        )
        assert prompt.index("BUDGET TABLE") < prompt.index("ATTACHED NOTES")


# ---------------------------------------------------------------------------
# _native_for_model -- routing switched the model out from under the count
# ---------------------------------------------------------------------------


class TestNativeForModel:
    COUNT = NativeCount(model_name=MODEL, tokens=1000, baseline_tokens=800)

    def test_a_count_for_this_model_is_kept(self):
        assert _native_for_model(self.COUNT, MODEL) is self.COUNT

    def test_a_count_for_another_model_is_dropped(self):
        """Routing may reassign `model_name` between the count and the plan.
        Vocabularies differ per model, so carrying the measurement across is the
        wrong-ruler mistake the safety margin exists to correct."""
        assert _native_for_model(self.COUNT, OTHER_MODEL) is None

    def test_no_count_stays_no_count(self):
        assert _native_for_model(None, MODEL) is None

    def test_the_planner_would_fail_closed_anyway(self):
        """Documenting the backstop, not relying on it: even if a stale count
        did reach the planner, `_native_margin` rejects on the name mismatch
        and the 1.5 ladder is restored."""
        assert token_safety_margin(OTHER_MODEL, None, native=self.COUNT) == (
            DEFAULT_TOKEN_SAFETY_MARGIN
        )


# ---------------------------------------------------------------------------
# _margin_for -- one number for routing and planning
# ---------------------------------------------------------------------------


class TestMarginFor:
    def test_the_margin_is_token_safety_margin_not_a_hand_rolled_ratio(self):
        """`token_safety_margin` weighs exactness, a configured value and
        tiktoken-is-the-real-tokenizer ahead of the measurement. A local
        `tokens / baseline` here would ignore all three and hand routing a
        number the planner never applied."""
        native = NativeCount(model_name=MODEL, tokens=1200, baseline_tokens=1000)
        assert _margin_for(native, MODEL, None) == token_safety_margin(
            MODEL, None, native=native
        )

    def test_a_configured_margin_still_wins(self):
        """The property above, stated where the two answers actually differ:
        the raw ratio is 1.2, the deployment configured 2.0."""
        native = NativeCount(model_name=MODEL, tokens=1200, baseline_tokens=1000)
        config = {"token_safety_margin": 2.0}
        assert _margin_for(native, MODEL, config) == 2.0
        assert native.tokens / native.baseline_tokens == pytest.approx(1.2)

    def test_no_count_means_no_margin(self):
        """None is what makes the routing call identical to today's:
        `model_routing._sized_for` then derives the margin from name and config
        exactly as it always has."""
        assert _margin_for(None, MODEL, None) is None


# ---------------------------------------------------------------------------
# _measure_native_count -- the pre-flight itself
# ---------------------------------------------------------------------------


class _Recorder:
    """Stands in for `count_natively`, recording what it was asked to count."""

    def __init__(self, result):
        self.result = result
        self.kwargs: dict | None = None

    async def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self.result


class TestMeasureNativeCount:
    SYSTEM = "You are a careful research administrator."
    PROMPT = (
        "What is the total?\n\n"
        "--- BEGIN REFERENCE DOCUMENTS (provided for context only) ---\n"
        "BUDGET TABLE 12,345.67\n"
        "--- END REFERENCE DOCUMENTS ---"
    )

    async def _measure(self, monkeypatch, recorder):
        monkeypatch.setattr(chat_service, "count_natively", recorder)
        return await _measure_native_count(
            model_name=MODEL,
            model_config=None,
            sys_config_doc={},
            system_prompt=self.SYSTEM,
            prompt=self.PROMPT,
            history=[],
        )

    @pytest.mark.asyncio
    async def test_the_counter_is_given_the_whole_prompt(self, monkeypatch):
        """Constraint 2 at the seam: the documents ride in as the user message,
        because that is how `chat_stream` sends them."""
        recorder = _Recorder(
            NativeCountResult(tokens=900, covers_system_prompt=True, source="anthropic")
        )
        await self._measure(monkeypatch, recorder)
        assert recorder.kwargs is not None
        assert recorder.kwargs["user_message"] == self.PROMPT
        assert "BUDGET TABLE" in recorder.kwargs["user_message"]

    @pytest.mark.asyncio
    async def test_the_baseline_covers_the_same_prompt(self, monkeypatch):
        """Constraint 1 at the seam: the provider counted the documents, so the
        baseline has to as well, or the ratio compares two different texts."""
        from app.services.context_budget import count_raw_tokens

        recorder = _Recorder(
            NativeCountResult(tokens=900, covers_system_prompt=True, source="anthropic")
        )
        native = await self._measure(monkeypatch, recorder)
        assert native is not None
        assert native.baseline_tokens == (
            count_raw_tokens(self.SYSTEM, MODEL, None)
            + count_raw_tokens(self.PROMPT, MODEL, None)
        )

    @pytest.mark.asyncio
    async def test_an_unusable_result_produces_nothing(self, monkeypatch):
        recorder = _Recorder(
            NativeCountResult(
                tokens=None, covers_system_prompt=False, source="unavailable:protocol-openai"
            )
        )
        assert await self._measure(monkeypatch, recorder) is None

    @pytest.mark.asyncio
    async def test_nothing_raises_into_the_chat_path(self, monkeypatch):
        """`count_natively` promises never to raise, but this sits in front of
        the first token of a chat response and must not depend on that promise
        holding for every future provider."""

        async def boom(**kwargs):
            raise RuntimeError("provider client exploded")

        monkeypatch.setattr(chat_service, "count_natively", boom)
        assert await _measure_native_count(
            model_name=MODEL,
            model_config=None,
            sys_config_doc={},
            system_prompt=self.SYSTEM,
            prompt=self.PROMPT,
            history=[],
        ) is None


# ---------------------------------------------------------------------------
# An unusable count leaves the stream exactly as it was
# ---------------------------------------------------------------------------


class TestUnusableCountChangesNothing:
    PIECES = dict(
        system_prompt="You are a helpful assistant.",
        user_message="What is the total budget?",
        history=[],
        documents=[DocumentSegment(label="proposal", text="word " * 60_000)],
        attachments=[],
    )
    SMALL = {"name": "small", "tag": "small", "context_window": 32768, "privacy": "internal"}

    def test_the_planner_is_called_exactly_as_today(self):
        """`native=None` is the parameter default throughout `context_budget`,
        so the no-count path plans the identical request."""
        today = plan_and_compact_context(
            model_name="small", model_config=self.SMALL, **self.PIECES
        )
        with_none = plan_and_compact_context(
            model_name="small", model_config=self.SMALL, native=None, **self.PIECES
        )
        assert with_none.plan.to_dict() == today.plan.to_dict()
        assert [a.to_dict() for a in with_none.actions] == [
            a.to_dict() for a in today.actions
        ]

    def test_the_suggestion_is_unchanged_without_a_margin(self):
        compacted = plan_and_compact_context(
            model_name="small", model_config=self.SMALL, **self.PIECES
        )
        sys_config = {
            "available_models": [
                self.SMALL,
                {"name": "large", "tag": "large", "context_window": 262144,
                 "privacy": "internal"},
            ]
        }
        assert _suggest_model_for_overflow(
            compacted, "small", self.SMALL, sys_config, 60_000,
        ) == _suggest_model_for_overflow(
            compacted, "small", self.SMALL, sys_config, 60_000, current_margin=None,
        )


class TestSuggestionCarriesTheMeasuredMargin:
    def test_current_margin_reaches_suggest_document_model(self, monkeypatch):
        """The offer has to be sized on the same ruler as the estimate, or it
        names a model the request would then fail on."""
        seen: dict = {}

        def fake_suggest(**kwargs):
            seen.update(kwargs)
            return {"name": "large", "tag": "large", "context_window": 262144}

        monkeypatch.setattr(chat_service, "suggest_document_model", fake_suggest)

        class _Compacted:
            actions = [object()]

        _suggest_model_for_overflow(
            _Compacted(), "small", None, {}, 60_000, current_margin=1.07,
        )
        assert seen["current_margin"] == 1.07
