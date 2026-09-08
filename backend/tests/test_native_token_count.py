"""The provider's own token count, or an honest admission that there isn't one.

`context_budget` inflates a tiktoken estimate by 1.5 for every model it cannot
tokenize exactly. Anthropic and Google will tell us the real number. The value
of that is entirely conditional on this module never *guessing* — a count that
silently comes back wrong, short, or from the wrong provider is worse than the
margin it replaces, because the caller drops the margin on the strength of it.

So every test here guards one of two properties: the figure is right when it is
returned, and nothing is returned when it isn't.
"""

from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace

import pytest

from app.services import native_token_count as ntc
from app.services.native_token_count import NativeCountResult, count_natively

_LOGGER = "app.services.native_token_count"


# ---------------------------------------------------------------------------
# Fakes. Real objects where they are cheap (ModelRequest, ModelHTTPError);
# hand-written stand-ins for the model, because constructing a real
# AnthropicModel needs credentials and a live client.
# ---------------------------------------------------------------------------


class FakeUsage:
    """What `Model.count_tokens` returns: a RequestUsage-shaped object."""

    def __init__(self, input_tokens):
        self.input_tokens = input_tokens


class FakeModel:
    """Stands in for the `MeteredModel(AnthropicModel(...))` get_agent_model returns.

    Records every call so tests can assert on what was actually sent to the
    provider, not merely on what came back.
    """

    def __init__(self, *, usage=None, error=None, delay=0.0):
        self.usage = usage
        self.error = error
        self.delay = delay
        self.calls: list[tuple] = []

    async def count_tokens(self, messages, model_settings, model_request_parameters):
        self.calls.append((messages, model_settings, model_request_parameters))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.usage


class ModelFactory:
    """Replacement for `get_agent_model` that counts its own invocations.

    The no-I/O gate is asserted as "this was never called", so the recording has
    to live in the fake rather than in a mock's call list.
    """

    def __init__(self, model):
        self.model = model
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, model_name, thinking_override=None, system_config_doc=None):
        self.calls.append((model_name, system_config_doc))
        return self.model


@pytest.fixture(autouse=True)
def _reset_coalescing():
    """Per-process coalescing is process state, and pytest shares a process.

    Without this, whether a failure logs at WARNING or DEBUG depends on which
    test ran first, and the assertions below would pass or fail on collection
    order.
    """
    ntc._UNAVAILABLE_LOGGED.clear()
    ntc._CIRCUIT.clear()
    yield
    ntc._UNAVAILABLE_LOGGED.clear()
    ntc._CIRCUIT.clear()


def _install(monkeypatch, *, protocol, model=None):
    """Wire the module's two seams and hand back the model factory."""
    monkeypatch.setattr(
        ntc, "get_model_api_protocol", lambda name, doc=None: protocol
    )
    factory = ModelFactory(model)
    monkeypatch.setattr(ntc, "get_agent_model", factory)
    monkeypatch.setattr(
        ntc, "build_thinking_model_settings", lambda *a, **k: {"timeout": 120.0}
    )
    return factory


async def _count(**overrides):
    kwargs = dict(
        model_name="anthropic/claude-sonnet-4-5",
        model_config=None,
        system_config_doc=None,
        system_prompt="You are a helpful assistant.",
        user_message="How many tokens is this?",
        history=[],
    )
    kwargs.update(overrides)
    return await count_natively(**kwargs)


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


class TestASuccessfulCount:
    @pytest.mark.asyncio
    async def test_anthropic_returns_the_providers_figure(self, monkeypatch):
        """The whole point: the number comes back unmodified. Anything that
        rounded, inflated, or re-estimated it would put us back where we started.
        """
        _install(monkeypatch, protocol="anthropic", model=FakeModel(usage=FakeUsage(4_213)))

        result = await _count()

        assert result.tokens == 4_213
        assert result.usable is True
        assert result.source == "anthropic"

    @pytest.mark.asyncio
    async def test_anthropics_count_covers_the_system_prompt(self, monkeypatch):
        """`_messages_count_tokens` passes `system=` (models/anthropic.py), so
        the figure already includes the instructions. A caller that added its own
        system-prompt allowance on top would double-count and route requests to
        compaction they did not need.
        """
        _install(monkeypatch, protocol="anthropic", model=FakeModel(usage=FakeUsage(4_213)))

        result = await _count()

        assert result.covers_system_prompt is True

    @pytest.mark.asyncio
    async def test_google_returns_the_figure_but_not_for_the_system_prompt(
        self, monkeypatch
    ):
        """The defect this flag exists for. `GoogleProvider(api_key=...)` is the
        `google-gla` provider, and models/google.py:341 attaches
        `system_instruction` to the count config only when the provider is NOT
        google-gla. So Gemini's count silently omits the entire system prompt --
        for KB chat that is a multi-kilobyte grounding preamble. Reporting it as
        a complete count would under-count by exactly the thing the margin used
        to cover.
        """
        _install(monkeypatch, protocol="google", model=FakeModel(usage=FakeUsage(1_907)))

        result = await _count(model_name="gemini-2.5-flash")

        assert result.tokens == 1_907
        assert result.usable is True
        assert result.covers_system_prompt is False
        assert result.source == "google"


class TestWhatIsSentToTheProvider:
    @pytest.mark.asyncio
    async def test_the_counted_messages_are_history_plus_this_turn(self, monkeypatch):
        """A count of the wrong messages is the most dangerous failure here,
        because it succeeds. Counting only the new turn and dropping history is
        an under-count that grows with the conversation.
        """
        from pydantic_ai.messages import ModelRequest

        model = FakeModel(usage=FakeUsage(10))
        _install(monkeypatch, protocol="anthropic", model=model)
        prior = [ModelRequest.user_text_prompt("an earlier turn")]

        await _count(history=prior, user_message="the new turn")

        messages = model.calls[0][0]
        assert len(messages) == 2
        assert messages[0] is prior[0]

    @pytest.mark.asyncio
    async def test_the_caller_s_history_list_is_not_mutated(self, monkeypatch):
        """The caller is holding the live chat history. Appending this turn in
        place would leave a duplicate user message in the real request.
        """
        model = FakeModel(usage=FakeUsage(10))
        _install(monkeypatch, protocol="anthropic", model=model)
        history: list = []

        await _count(history=history)

        assert history == []

    @pytest.mark.asyncio
    async def test_the_system_prompt_rides_as_instructions(self, monkeypatch):
        """`create_chat_agent` passes the prompt as `instructions`, not
        `system_prompt`. Counting it the other way counts a request the app
        never sends.
        """
        model = FakeModel(usage=FakeUsage(10))
        _install(monkeypatch, protocol="anthropic", model=model)

        await _count(system_prompt="GROUNDING RULES")

        last = model.calls[0][0][-1]
        assert last.instructions == "GROUNDING RULES"

    @pytest.mark.asyncio
    async def test_the_pre_flight_gets_a_short_timeout_not_the_chat_one(
        self, monkeypatch
    ):
        """This runs before the first token of a chat response.
        `build_thinking_model_settings` sets timeout=120, and
        `RateLimitRetryTransport` retries a 429 six times honouring Retry-After
        up to 60s. Inheriting either turns a budgeting nicety into a two-minute
        stall in front of every message.
        """
        model = FakeModel(usage=FakeUsage(10))
        _install(monkeypatch, protocol="anthropic", model=model)

        await _count()

        settings = model.calls[0][1]
        assert settings["timeout"] == ntc.NATIVE_COUNT_TIMEOUT_SECONDS
        assert settings["timeout"] < 120.0

    @pytest.mark.asyncio
    async def test_no_tools_are_declared(self, monkeypatch):
        """`create_chat_agent` registers none, and tool schemas are billable
        input on Anthropic. Counting tools the request will not carry inflates
        the figure.
        """
        model = FakeModel(usage=FakeUsage(10))
        _install(monkeypatch, protocol="anthropic", model=model)

        await _count()

        params = model.calls[0][2]
        assert params.function_tools == []
        assert params.output_tools == []


class TestTheNoIOGate:
    """A protocol whose model cannot count must cost nothing -- not a request,
    not a client, not a decrypted API key. `OpenAIModel.count_tokens` raises
    NotImplementedError, so without the gate every OpenAI-shaped model would
    build a full provider client on every chat turn to learn that.
    """

    @pytest.mark.parametrize("protocol", ["vllm", "ollama", "openrouter", "openai"])
    @pytest.mark.asyncio
    async def test_an_ineligible_protocol_never_builds_a_model(
        self, monkeypatch, protocol
    ):
        factory = _install(monkeypatch, protocol=protocol, model=FakeModel(usage=FakeUsage(99)))

        result = await _count(model_name="Qwen/Qwen3.5-9B")

        assert factory.calls == [], "the gate must run before any model is built"
        assert result.usable is False
        assert result.tokens is None
        assert protocol in result.source

    @pytest.mark.asyncio
    async def test_an_ineligible_protocol_is_not_a_warning(self, monkeypatch, caplog):
        """Most deployments are OpenAI-compatible. "this model cannot count" is
        the normal, expected answer for them, and warning about it would put a
        line in the log on every chat turn forever.
        """
        _install(monkeypatch, protocol="vllm")

        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            await _count(model_name="Qwen/Qwen3.5-9B")

        assert _warnings(caplog) == []

    @pytest.mark.asyncio
    async def test_a_supplied_model_config_decides_the_protocol(self, monkeypatch):
        """The caller already holds the model's config -- `token_safety_margin`
        takes the same dict. When it is supplied, the admin's explicit
        `api_protocol` is authoritative and no second scan of
        `available_models` is needed. Patching the doc lookup to raise is what
        proves the config path, and not the lookup, was taken.
        """
        def _should_not_be_called(name, doc=None):
            raise AssertionError("a supplied model_config makes this lookup redundant")

        monkeypatch.setattr(ntc, "get_model_api_protocol", _should_not_be_called)
        factory = ModelFactory(FakeModel(usage=FakeUsage(512)))
        monkeypatch.setattr(ntc, "get_agent_model", factory)
        monkeypatch.setattr(ntc, "build_thinking_model_settings", lambda *a, **k: {})

        result = await _count(
            model_name="house-claude", model_config={"api_protocol": "anthropic"}
        )

        assert result.tokens == 512
        assert result.source == "anthropic"

    @pytest.mark.asyncio
    async def test_a_supplied_model_config_can_also_close_the_gate(self, monkeypatch):
        """`detect_api_protocol` falls back to name matching, and a bare
        "claude-..." name resolves to "openai" -- so the same path has to be
        able to say no, not only yes.
        """
        monkeypatch.setattr(
            ntc, "get_model_api_protocol", lambda name, doc=None: "anthropic"
        )
        factory = ModelFactory(FakeModel(usage=FakeUsage(512)))
        monkeypatch.setattr(ntc, "get_agent_model", factory)

        result = await _count(
            model_name="gpt-4o", model_config={"api_protocol": "openai"}
        )

        assert result.usable is False
        assert factory.calls == []

    @pytest.mark.asyncio
    async def test_a_broken_protocol_lookup_is_still_fail_closed(self, monkeypatch):
        """The gate itself is code, and code raises. A traceback out of the
        lookup must read as "no native count", not as a failed chat request.
        """
        def _boom(name, doc=None):
            raise RuntimeError("system config unreadable")

        monkeypatch.setattr(ntc, "get_model_api_protocol", _boom)
        factory = ModelFactory(FakeModel(usage=FakeUsage(99)))
        monkeypatch.setattr(ntc, "get_agent_model", factory)

        result = await _count()

        assert result.usable is False
        assert factory.calls == []


class TestFailuresAreFailClosed:
    """Every one of these must return an unusable result rather than raise. The
    caller is mid-request to a user; a budgeting pre-flight that can break the
    chat is strictly worse than the 1.5 margin it replaces.
    """

    @pytest.mark.asyncio
    async def test_not_implemented_is_not_an_error(self, monkeypatch):
        """`OpenAIModel.count_tokens` raises this. The protocol gate should
        already have caught it, but a misconfigured api_protocol -- an admin
        setting "anthropic" on an OpenAI-compatible gateway -- gets past the gate
        and lands here.
        """
        _install(
            monkeypatch,
            protocol="anthropic",
            model=FakeModel(error=NotImplementedError()),
        )

        result = await _count()

        assert result.usable is False
        assert result.tokens is None
        assert "unavailable" in result.source

    @pytest.mark.asyncio
    async def test_a_slow_provider_is_abandoned(self, monkeypatch):
        """The timeout is the only thing standing between a degraded provider
        and a chat UI that hangs before showing a single token.
        """
        monkeypatch.setattr(ntc, "NATIVE_COUNT_TIMEOUT_SECONDS", 0.01)
        _install(monkeypatch, protocol="anthropic", model=FakeModel(usage=FakeUsage(10), delay=5.0))

        result = await asyncio.wait_for(_count(), timeout=2.0)

        assert result.usable is False
        assert "timeout" in result.source

    @pytest.mark.asyncio
    async def test_a_rate_limited_count_is_unavailable(self, monkeypatch):
        """A 429 on the count endpoint is the likeliest real failure, and the
        one most likely to arrive in a burst. `ModelHTTPError` is what
        pydantic-ai converts Anthropic's APIStatusError into.
        """
        from pydantic_ai.exceptions import ModelHTTPError

        _install(
            monkeypatch,
            protocol="anthropic",
            model=FakeModel(
                error=ModelHTTPError(
                    status_code=429, model_name="claude-sonnet-4-5", body=None
                )
            ),
        )

        result = await _count()

        assert result.usable is False
        assert result.tokens is None

    @pytest.mark.asyncio
    async def test_a_raw_provider_sdk_error_is_unavailable(self, monkeypatch):
        """Google's `google.genai` errors are not wrapped by pydantic-ai; they
        propagate raw. Catching only pydantic-ai's exception types would let
        those straight through into the chat path, which is why the handler is
        a blanket `except Exception`.
        """
        class SomeGenaiError(Exception):
            pass

        _install(
            monkeypatch,
            protocol="google",
            model=FakeModel(error=SomeGenaiError("PERMISSION_DENIED")),
        )

        result = await _count(model_name="gemini-2.5-flash")

        assert result.usable is False

    @pytest.mark.parametrize(
        "usage",
        [
            pytest.param(FakeUsage(None), id="input_tokens-is-None"),
            pytest.param(FakeUsage(0), id="input_tokens-is-zero"),
            pytest.param(object(), id="no-input_tokens-attribute"),
            pytest.param(None, id="no-usage-object-at-all"),
            pytest.param(FakeUsage("4213"), id="input_tokens-is-a-string"),
        ],
    )
    @pytest.mark.asyncio
    async def test_a_malformed_usage_object_is_unavailable(self, monkeypatch, usage):
        """The failure mode with teeth. A count of 0 or None that reached the
        caller as a *number* would say "this prompt is free", and the caller
        drops its safety margin on the strength of it. Zero is not a count;
        it is a missing count wearing a count's clothes.
        """
        _install(monkeypatch, protocol="anthropic", model=FakeModel(usage=usage))

        result = await _count()

        assert result.usable is False
        assert result.tokens is None

    @pytest.mark.asyncio
    async def test_a_negative_count_is_unavailable(self, monkeypatch):
        """`usable` is defined as tokens > 0, not tokens is not None. A negative
        figure would otherwise pass a `is not None` check and shrink the
        measured prompt below zero.
        """
        _install(monkeypatch, protocol="anthropic", model=FakeModel(usage=FakeUsage(-1)))

        assert (await _count()).usable is False

    @pytest.mark.asyncio
    async def test_a_boolean_is_not_a_token_count(self, monkeypatch):
        """`isinstance(True, int)` is True in Python, so a bare int check lets
        `input_tokens=True` through as a count of 1.
        """
        _install(monkeypatch, protocol="anthropic", model=FakeModel(usage=FakeUsage(True)))

        assert (await _count()).usable is False


class TestFailureLoggingIsCoalesced:
    """Same rationale, and the same shape, as
    `token_estimate_check._log_failure_once` and
    `context_budget._warn_estimated_once`. The failures this reports are
    systemic -- a misconfigured protocol, a provider that is down, an expired
    key -- so they say the same thing on every chat turn, indefinitely. Loud
    once per model per process, DEBUG thereafter, and it resets on restart so a
    deploy or a config change is visible again.
    """

    @pytest.mark.asyncio
    async def test_the_first_failure_warns(self, monkeypatch, caplog):
        _install(
            monkeypatch,
            protocol="anthropic",
            model=FakeModel(error=RuntimeError("provider down")),
        )

        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            await _count()

        assert len(_warnings(caplog)) == 1
        assert "anthropic/claude-sonnet-4-5" in _warnings(caplog)[0].getMessage()

    @pytest.mark.asyncio
    async def test_the_same_failure_repeated_drops_to_debug(self, monkeypatch, caplog):
        """Chat calls this once per turn. Warning every time is the per-request
        noise the coalescing exists to remove.
        """
        _install(
            monkeypatch,
            protocol="anthropic",
            model=FakeModel(error=RuntimeError("provider down")),
        )

        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            for _ in range(50):
                await _count()

        # Two, and only two, however long the outage lasts: the failure itself,
        # then the notice that counting is paused. Fifty turns rather than four
        # so this pins the bound rather than an arithmetic coincidence.
        assert len(_warnings(caplog)) == 2
        assert "pausing it" in _warnings(caplog)[1].getMessage()
        # Occurrences two onward are the only evidence the failure is ongoing
        # rather than a one-off at startup -- but they stop once the breaker
        # opens, because after that there is no attempt to report.
        assert len([r for r in caplog.records if r.levelno == logging.DEBUG]) == (
            ntc.NATIVE_COUNT_FAILURE_THRESHOLD - 1
        )

    @pytest.mark.asyncio
    async def test_a_second_model_is_still_reported_loudly(self, monkeypatch, caplog):
        """Coalescing is per model, so one broken model cannot silence the next
        one -- the failure mode a single module-level flag would introduce.
        """
        _install(
            monkeypatch,
            protocol="anthropic",
            model=FakeModel(error=RuntimeError("provider down")),
        )

        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            await _count(model_name="anthropic/claude-sonnet-4-5")
            await _count(model_name="anthropic/claude-haiku-4-5")

        warnings = _warnings(caplog)
        assert len(warnings) == 2
        assert "claude-haiku-4-5" in warnings[1].getMessage()


class TestNativeCountResult:
    def test_a_missing_count_is_not_usable(self):
        assert NativeCountResult(
            tokens=None, covers_system_prompt=False, source="unavailable:x"
        ).usable is False

    def test_the_result_is_frozen(self):
        """The caller makes a budgeting decision from it. Nothing downstream
        should be able to edit the provider's figure in place.
        """
        result = NativeCountResult(
            tokens=10, covers_system_prompt=True, source="anthropic"
        )
        with pytest.raises(Exception):
            result.tokens = 20  # type: ignore[misc]


# ---------------------------------------------------------------------------
# native_count_for -- the baseline that makes the provider's figure a ratio
# ---------------------------------------------------------------------------


class FakePart:
    """One part of a pydantic-ai ModelMessage, as `count_message_tokens` reads it."""

    def __init__(self, content):
        self.content = content


class FakeMessage:
    def __init__(self, *contents):
        self.parts = [FakePart(c) for c in contents]


class TestNativeCountFor:
    """The baseline has to cover exactly the text the provider counted.

    The margin is `tokens / baseline_tokens`. If the two numbers describe
    different text the ratio is not a measurement of anything -- and because a
    low ratio clamps to 1.0, a baseline that includes text the provider never
    saw under-budgets a tiktoken figure that was already reading low. That is
    the direction that hard-fails a request, so the component set is asserted
    on both sides of the `covers_system_prompt` asymmetry.
    """

    MODEL = "anthropic/claude-sonnet-4-5"
    SYSTEM = "You are a careful research administrator. " * 40
    USER = "What is the total budget? " * 200

    def _result(self, *, covers: bool, tokens: int = 12345):
        return NativeCountResult(
            tokens=tokens,
            covers_system_prompt=covers,
            source="anthropic" if covers else "google",
        )

    def _call(self, *, covers: bool, history=None, tokens: int = 12345):
        return ntc.native_count_for(
            self._result(covers=covers, tokens=tokens),
            model_name=self.MODEL,
            model_config=None,
            system_prompt=self.SYSTEM,
            user_message=self.USER,
            history=history or [],
        )

    def test_anthropic_baseline_includes_the_system_prompt(self):
        """Anthropic's `_messages_count_tokens` sends `system=`, so the prompt
        is on the provider's side of the ratio and must be on ours."""
        from app.services.context_budget import count_raw_tokens

        native = self._call(covers=True)
        assert native is not None
        assert native.baseline_tokens == (
            count_raw_tokens(self.SYSTEM, self.MODEL, None)
            + count_raw_tokens(self.USER, self.MODEL, None)
        )

    def test_google_baseline_omits_the_system_prompt(self):
        """`google-gla` never attaches `system_instruction` to the count config,
        so counting it locally would inflate the baseline against a provider
        figure that never saw it -- shrinking the ratio toward the 1.0 clamp."""
        from app.services.context_budget import count_raw_tokens

        native = self._call(covers=False)
        assert native is not None
        assert native.baseline_tokens == count_raw_tokens(self.USER, self.MODEL, None)

    def test_the_system_prompt_is_the_only_difference_between_the_two(self):
        from app.services.context_budget import count_raw_tokens

        with_prompt = self._call(covers=True)
        without = self._call(covers=False)
        assert with_prompt is not None and without is not None
        assert with_prompt.baseline_tokens - without.baseline_tokens == (
            count_raw_tokens(self.SYSTEM, self.MODEL, None)
        )

    def test_history_is_counted_because_the_provider_counted_it(self):
        """`_ask_provider` sends `list(history)` ahead of this turn's message."""
        empty = self._call(covers=True)
        with_history = self._call(
            covers=True, history=[FakeMessage("an earlier answer " * 100)]
        )
        assert empty is not None and with_history is not None
        assert with_history.baseline_tokens > empty.baseline_tokens

    def test_the_baseline_carries_no_safety_margin(self):
        """A margin on the baseline would divide itself back out of the ratio
        and report the provider as cheaper than it is."""
        from app.services.context_budget import count_tokens

        native = self._call(covers=False)
        assert native is not None
        # This model has no local vocabulary, so `count_tokens` inflates by 1.5.
        inflated = count_tokens(self.USER, self.MODEL, None)
        assert native.baseline_tokens < inflated

    def test_the_count_is_labelled_with_the_model_it_was_measured_for(self):
        native = self._call(covers=True)
        assert native is not None
        assert native.model_name == self.MODEL
        assert native.tokens == 12345

    def test_an_unusable_result_produces_no_count(self):
        for result in (
            NativeCountResult(tokens=None, covers_system_prompt=False, source="unavailable:x"),
            NativeCountResult(tokens=0, covers_system_prompt=True, source="anthropic"),
        ):
            assert ntc.native_count_for(
                result,
                model_name=self.MODEL,
                model_config=None,
                system_prompt=self.SYSTEM,
                user_message=self.USER,
                history=[],
            ) is None

    def test_an_empty_payload_produces_no_count(self):
        """A zero baseline is not a measurement; `_native_margin` would reject
        it anyway, but handing it on would be handing on a divide by zero."""
        assert ntc.native_count_for(
            self._result(covers=False),
            model_name=self.MODEL,
            model_config=None,
            system_prompt="",
            user_message="",
            history=[],
        ) is None

    def test_the_resulting_margin_is_the_measured_ratio(self):
        """End of the chain: what the planner actually does with the pair."""
        from app.services.context_budget import token_safety_margin

        native = self._call(covers=False, tokens=999_999)
        assert native is not None
        margin = token_safety_margin(self.MODEL, None, native=native)
        assert margin == pytest.approx(native.tokens / native.baseline_tokens)


class TestRepeatedFailureStopsCostingTime:
    """The module already coalesced the failure *log*. It did not coalesce the
    failure *work*, so a deployment whose egress to the count endpoint is slow
    paid the full timeout on every chat turn, ahead of the first token, forever
    -- and said so at DEBUG after the first occurrence."""

    def setup_method(self):
        from app.services import native_token_count as ntc
        ntc._CIRCUIT.clear()
        ntc._UNAVAILABLE_LOGGED.clear()

    teardown_method = setup_method

    @pytest.mark.asyncio
    async def test_the_provider_stops_being_called_after_repeated_failures(self, monkeypatch):
        """The point of the breaker: not a quieter log, an absent request."""
        from app.services import native_token_count as ntc

        calls = 0

        async def boom(**_kw):
            nonlocal calls
            calls += 1
            raise RuntimeError("count endpoint unreachable")

        monkeypatch.setattr(ntc, "_ask_provider", boom)
        monkeypatch.setattr(ntc, "_protocol_for", lambda *a, **k: "anthropic")

        for _ in range(10):
            res = await ntc.count_natively(
                model_name="claude-x", model_config={}, system_config_doc={},
                system_prompt="s", user_message="u", history=[],
            )
            assert not res.usable

        assert calls == ntc.NATIVE_COUNT_FAILURE_THRESHOLD, (
            f"provider was called {calls} times across 10 turns; the breaker "
            "should stop the work, not just the logging"
        )
        assert res.source == "unavailable:circuit-open"

    @pytest.mark.asyncio
    async def test_a_working_provider_never_trips_it(self, monkeypatch):
        from app.services import native_token_count as ntc

        calls = 0

        async def ok(**_kw):
            nonlocal calls
            calls += 1
            return SimpleNamespace(input_tokens=100)

        monkeypatch.setattr(ntc, "_ask_provider", ok)
        monkeypatch.setattr(ntc, "_protocol_for", lambda *a, **k: "anthropic")
        monkeypatch.setattr(ntc, "_token_count", lambda usage: 100)

        for _ in range(10):
            res = await ntc.count_natively(
                model_name="claude-x", model_config={}, system_config_doc={},
                system_prompt="s", user_message="u", history=[],
            )
            assert res.usable
        assert calls == 10

    @pytest.mark.asyncio
    async def test_recovery_is_retried_once_the_cooldown_elapses(self, monkeypatch):
        """An outage must not disable counting until the next deploy."""
        from app.services import native_token_count as ntc

        failing = True
        calls = 0

        async def flaky(**_kw):
            nonlocal calls
            calls += 1
            if failing:
                raise RuntimeError("down")
            return SimpleNamespace(input_tokens=100)

        monkeypatch.setattr(ntc, "_ask_provider", flaky)
        monkeypatch.setattr(ntc, "_protocol_for", lambda *a, **k: "anthropic")
        monkeypatch.setattr(ntc, "_token_count", lambda usage: 100)

        for _ in range(5):
            await ntc.count_natively(
                model_name="claude-x", model_config={}, system_config_doc={},
                system_prompt="s", user_message="u", history=[],
            )
        tripped_at = calls

        # Provider recovers, cooldown elapses.
        failing = False
        now = time.monotonic()
        monkeypatch.setattr(ntc.time, "monotonic",
                            lambda: now + ntc.NATIVE_COUNT_COOLDOWN_SECONDS + 1)

        res = await ntc.count_natively(
            model_name="claude-x", model_config={}, system_config_doc={},
            system_prompt="s", user_message="u", history=[],
        )
        assert res.usable, "the breaker never re-tested the provider"
        assert calls == tripped_at + 1
        # And a success clears the record rather than leaving it primed.
        assert "claude-x" not in ntc._CIRCUIT

    @pytest.mark.asyncio
    async def test_one_model_failing_does_not_disable_another(self, monkeypatch):
        from app.services import native_token_count as ntc

        async def only_claude_fails(*, model_name, **_kw):
            if model_name == "claude-x":
                raise RuntimeError("down")
            return SimpleNamespace(input_tokens=100)

        monkeypatch.setattr(ntc, "_ask_provider", only_claude_fails)
        monkeypatch.setattr(ntc, "_protocol_for", lambda *a, **k: "anthropic")
        monkeypatch.setattr(ntc, "_token_count", lambda usage: 100)

        for _ in range(5):
            await ntc.count_natively(
                model_name="claude-x", model_config={}, system_config_doc={},
                system_prompt="s", user_message="u", history=[],
            )
        res = await ntc.count_natively(
            model_name="gemini-y", model_config={}, system_config_doc={},
            system_prompt="s", user_message="u", history=[],
        )
        assert res.usable
