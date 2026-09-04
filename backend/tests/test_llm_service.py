"""Tests for app.services.llm_service — protocol detection."""

import asyncio
import httpx
import pytest
from unittest.mock import AsyncMock, patch

from app.services import llm_service
from app.services.llm_service import (
    SUPPORTED_PROTOCOLS,
    build_thinking_model_settings,
    detect_api_protocol,
)


def _cfg(**model_fields):
    """Wrap a single model config in a SystemConfig-shaped doc."""
    model_fields.setdefault("name", "the-model")
    return {"available_models": [model_fields]}


class TestExplicitProtocol:
    """When api_protocol is set on the model config, it wins over name-based detection."""

    def test_explicit_anthropic_passes_through(self):
        assert detect_api_protocol("any-model", {"api_protocol": "anthropic"}) == "anthropic"

    def test_explicit_openrouter_passes_through(self):
        assert detect_api_protocol("any-model", {"api_protocol": "openrouter"}) == "openrouter"

    def test_explicit_openai_passes_through(self):
        assert detect_api_protocol("any-model", {"api_protocol": "openai"}) == "openai"

    def test_explicit_ollama_passes_through(self):
        assert detect_api_protocol("any-model", {"api_protocol": "ollama"}) == "ollama"

    def test_explicit_vllm_passes_through(self):
        assert detect_api_protocol("any-model", {"api_protocol": "vllm"}) == "vllm"

    def test_explicit_overrides_name_based_default(self):
        # claude-* defaults to openai (back-compat with OpenAI-compat usage),
        # but an explicit anthropic protocol must override that.
        assert detect_api_protocol("claude-haiku-4-5", {"api_protocol": "anthropic"}) == "anthropic"

    def test_explicit_protocol_is_case_insensitive(self):
        assert detect_api_protocol("any", {"api_protocol": "Anthropic"}) == "anthropic"

    def test_unknown_protocol_falls_through_to_name_detection(self):
        # An unrecognized protocol value should not be returned; name-based
        # detection takes over.
        assert detect_api_protocol("gpt-4o", {"api_protocol": "bogus"}) == "openai"


class TestNameBasedDetection:
    """When api_protocol is not set, the model name drives the choice."""

    def test_openrouter_prefix_detected(self):
        assert detect_api_protocol("openrouter/anthropic/claude-haiku-4-5") == "openrouter"

    def test_gpt_prefix_is_openai(self):
        assert detect_api_protocol("gpt-4o") == "openai"

    def test_openai_namespace_is_openai(self):
        assert detect_api_protocol("openai/gpt-4o") == "openai"

    def test_claude_defaults_to_openai_for_back_compat(self):
        # Existing installs may have claude-* models pointed at the OpenAI-
        # compatible endpoint. Auto-detect must keep that behavior; users opt
        # into native anthropic by setting api_protocol explicitly.
        assert detect_api_protocol("claude-haiku-4-5") == "openai"

    def test_bare_name_defaults_to_ollama(self):
        assert detect_api_protocol("llama3.1") == "ollama"

    def test_gemini_name_is_google_not_ollama(self):
        # A bare "gemini-*" name routes to the native Google integration, and
        # must never fall through to the Ollama branch (which would silently
        # point the call at localhost:11434).
        assert detect_api_protocol("gemini-2.5-flash") == "google"
        assert detect_api_protocol("gemini-2.5-pro") == "google"

    def test_explicit_google_protocol_wins(self):
        assert detect_api_protocol("some-model", {"api_protocol": "google"}) == "google"

    def test_vllm_substring_detected(self):
        assert detect_api_protocol("vllm/qwen3") == "vllm"


class TestThinkingModelSettings:
    """chat_template_kwargs must never reach a strict external API (e.g. Gemini)."""

    def test_external_gemini_auto_detect_omits_chat_template_kwargs(self):
        # The reported bug: external=true, protocol left on Auto-detect (blank).
        # Google rejects the vLLM-style chat_template_kwargs with a 400.
        cfg = _cfg(name="gemini-3.5-flash-lite", external=True, api_protocol="", thinking=True)
        settings = build_thinking_model_settings("gemini-3.5-flash-lite", system_config_doc=cfg)
        assert "chat_template_kwargs" not in settings.get("extra_body", {})

    def test_external_openai_protocol_omits_chat_template_kwargs(self):
        cfg = _cfg(name="gemini-2.5-pro", external=True, api_protocol="openai", thinking=True)
        settings = build_thinking_model_settings("gemini-2.5-pro", system_config_doc=cfg)
        assert "chat_template_kwargs" not in settings.get("extra_body", {})

    def test_native_google_protocol_omits_chat_template_kwargs(self):
        cfg = _cfg(name="gemini-2.5-flash", api_protocol="google", thinking=True)
        settings = build_thinking_model_settings("gemini-2.5-flash", system_config_doc=cfg)
        assert "chat_template_kwargs" not in settings.get("extra_body", {})
        assert settings["thinking"] is True

    def test_native_google_auto_detect_omits_chat_template_kwargs(self):
        # Protocol left blank but the gemini name detects as google.
        cfg = _cfg(name="gemini-2.5-flash", api_protocol="", thinking=True)
        settings = build_thinking_model_settings("gemini-2.5-flash", system_config_doc=cfg)
        assert "chat_template_kwargs" not in settings.get("extra_body", {})

    def test_internal_vllm_still_sends_chat_template_kwargs(self):
        # Self-hosted (external=false) OpenAI-compatible servers still get the
        # Qwen3-style thinking control — this must not regress.
        cfg = _cfg(name="qwen3", external=False, api_protocol="vllm", thinking=True)
        settings = build_thinking_model_settings("qwen3", system_config_doc=cfg)
        assert settings["extra_body"]["chat_template_kwargs"] == {"enable_thinking": True}

    def test_internal_bare_name_still_sends_chat_template_kwargs(self):
        cfg = _cfg(name="qwen3", external=False, api_protocol="", thinking=True)
        settings = build_thinking_model_settings("qwen3", system_config_doc=cfg)
        assert settings["extra_body"]["chat_template_kwargs"] == {"enable_thinking": True}

    def test_ollama_uses_think_not_chat_template_kwargs(self):
        cfg = _cfg(name="llama3.1", external=False, api_protocol="ollama", thinking=True)
        settings = build_thinking_model_settings("llama3.1", system_config_doc=cfg)
        assert settings["extra_body"] == {"think": True}


class TestOutputCapAndTimeout:
    """Every request carries an output cap and a resolvable timeout."""

    def test_max_tokens_defaults_to_response_reserve(self):
        cfg = _cfg(name="m", context_window=128000)
        s = build_thinking_model_settings("m", system_config_doc=cfg)
        assert s["max_tokens"] == 8192  # min(8192, 128000 // 4)

    def test_response_reserve_override_respected(self):
        cfg = _cfg(name="m", context_window=128000, response_reserve_tokens=20000)
        s = build_thinking_model_settings("m", system_config_doc=cfg)
        assert s["max_tokens"] == 20000

    def test_timeout_defaults_to_system_setting(self):
        cfg = _cfg(name="m")
        s = build_thinking_model_settings("m", system_config_doc=cfg)
        assert s["timeout"] == 120.0  # config default workflow_llm_timeout_seconds

    def test_request_timeout_override_respected(self):
        cfg = _cfg(name="m", request_timeout_seconds=600)
        s = build_thinking_model_settings("m", system_config_doc=cfg)
        assert s["timeout"] == 600.0

    def test_temperature_is_absent_when_the_model_does_not_set_one(self):
        """Unconfigured models keep provider defaults — no silent behaviour change."""
        s = build_thinking_model_settings("m", system_config_doc=_cfg(name="m"))
        assert "temperature" not in s

    def test_temperature_override_is_sent(self):
        cfg = _cfg(name="m", temperature=0.2)
        s = build_thinking_model_settings("m", system_config_doc=cfg)
        assert s["temperature"] == 0.2

    def test_temperature_zero_is_sent_not_treated_as_unset(self):
        """0.0 is the whole point of the setting — the deterministic case.

        A truthiness check (``value or default``) silently drops it, which is
        indistinguishable from never having configured it.
        """
        cfg = _cfg(name="m", temperature=0)
        s = build_thinking_model_settings("m", system_config_doc=cfg)
        assert s["temperature"] == 0.0

    def test_integer_temperature_is_accepted_as_a_float(self):
        cfg = _cfg(name="m", temperature=1)
        s = build_thinking_model_settings("m", system_config_doc=cfg)
        assert s["temperature"] == 1.0

    def test_out_of_range_temperature_is_ignored(self):
        """Providers reject these outright; dropping the value keeps the request
        working rather than failing every call until an admin notices."""
        for bad in (-0.5, 2.5, 100):
            s = build_thinking_model_settings("m", system_config_doc=_cfg(name="m", temperature=bad))
            assert "temperature" not in s, bad

    def test_non_numeric_temperature_is_ignored(self):
        for bad in ("warm", "", None, True, [0.5]):
            s = build_thinking_model_settings("m", system_config_doc=_cfg(name="m", temperature=bad))
            assert "temperature" not in s, bad

    def test_thinking_model_gets_output_headroom(self):
        # Tiny window → reserve would be 1024; a thinking model needs room for
        # both reasoning and an answer, so the cap floors at 2048.
        cfg = _cfg(name="m", context_window=4096, thinking=True)
        s = build_thinking_model_settings("m", system_config_doc=cfg)
        assert s["max_tokens"] >= 2048

    def test_anthropic_thinking_budget_below_cap(self):
        cfg = _cfg(name="claude-x", api_protocol="anthropic", thinking=True, context_window=200000)
        s = build_thinking_model_settings("claude-x", system_config_doc=cfg)
        assert s["anthropic_thinking"]["type"] == "enabled"
        assert s["anthropic_thinking"]["budget_tokens"] < s["max_tokens"]

    def test_non_thinking_has_no_anthropic_budget(self):
        cfg = _cfg(name="claude-x", api_protocol="anthropic", thinking=False, context_window=200000)
        s = build_thinking_model_settings("claude-x", system_config_doc=cfg)
        assert "anthropic_thinking" not in s


class TestGoogleModelBuild:
    """The google protocol builds a native pydantic-ai GoogleModel."""

    def test_google_protocol_builds_google_model(self):
        from pydantic_ai.models.google import GoogleModel

        from app.services.llm_service import _build_agent_model

        cfg = _cfg(name="gemini-2.5-flash", api_protocol="google", api_key="plaintext-key")
        model = _build_agent_model("gemini-2.5-flash", system_config_doc=cfg)
        assert isinstance(model, GoogleModel)
        assert model.model_name == "gemini-2.5-flash"

    def test_google_prefix_is_stripped(self):
        from app.services.llm_service import _build_agent_model

        cfg = _cfg(name="google/gemini-2.5-pro", api_protocol="google", api_key="plaintext-key")
        model = _build_agent_model("google/gemini-2.5-pro", system_config_doc=cfg)
        assert model.model_name == "gemini-2.5-pro"


class TestVllmModelProfile:
    """A vLLM-served model must be reported as supporting JSON-schema output
    whatever it is named.

    vLLM enforces ``response_format: {"type": "json_schema"}`` server-side via
    guided decoding for every model it serves, so the capability belongs to the
    server. The profile inherited from OpenRouter answers for the model
    family's *own* hosted API instead: a HuggingFace-style name like
    "Qwen/Qwen3-32B" routes to ``qwen_model_profile``, which leaves
    ``supports_json_schema_output`` at its False default, and pydantic-ai then
    refuses NativeOutput with "Native structured output is not supported by
    this model." — every extraction against that model failed while the same
    weights registered under the bare name "qwen3-32b" worked.
    """

    @pytest.mark.parametrize("model_name", [
        "Qwen/Qwen3-32B",           # HuggingFace repo id, capitalised org
        "qwen/qwen3-32b",           # lowercase — matches OpenRouter's family map
        "RedHatAI/Qwen3-32B-FP8",   # quantised republish
        "meta-llama/Llama-3.3-70B-Instruct",
        "mistralai/Mistral-Small",
        "qwen3-32b",                # bare name — worked before, must keep working
        "gpt-oss-120b",
    ])
    def test_slash_named_models_support_json_schema_output(self, model_name):
        provider = llm_service.VLLMProvider(
            api_key="k", endpoint="http://inference.local:8000",
        )
        profile = provider.model_profile(model_name)
        assert profile is not None
        assert profile.supports_json_schema_output is True

    def test_family_specific_profile_bits_survive(self):
        """Overriding the capability flags must not discard the family's own
        schema transformer — Qwen needs InlineDefs, not the OpenAI one."""
        from pydantic_ai._json_schema import InlineDefsJsonSchemaTransformer

        provider = llm_service.VLLMProvider(
            api_key="k", endpoint="http://inference.local:8000",
        )
        profile = provider.model_profile("qwen/qwen3-32b")
        assert profile.json_schema_transformer is InlineDefsJsonSchemaTransformer


class TestModelSupportsStructuredOutput:
    """The admin's per-model "supports structured output" toggle."""

    def test_defaults_to_true_when_flag_absent(self):
        cfg = _cfg(name="m")
        assert llm_service.model_supports_structured_output("m", cfg) is True

    def test_defaults_to_true_for_an_unknown_model(self):
        cfg = _cfg(name="m")
        assert llm_service.model_supports_structured_output("other", cfg) is True

    def test_false_when_admin_turned_it_off(self):
        cfg = _cfg(name="m", supports_structured=False)
        assert llm_service.model_supports_structured_output("m", cfg) is False


class TestUseNativeStructuredOutput:
    """One decision, shared by the extraction engine and the admin Test button.

    They must not drift: a diagnostic that reimplements the rule can pass on
    exactly the configuration a real run fails on, which is how a broken
    production model sat behind a green badge.
    """

    def _cfg_for(self, **fields):
        fields.setdefault("name", "qwen3-32b")
        fields.setdefault("endpoint", "http://inference.local:8000")
        return {"available_models": [fields]}

    def test_vllm_asks_for_native_output(self):
        cfg = self._cfg_for(api_protocol="vllm")
        assert llm_service.use_native_structured_output("qwen3-32b", cfg) is True

    def test_other_protocols_do_not(self):
        cfg = self._cfg_for(api_protocol="ollama")
        assert llm_service.use_native_structured_output("qwen3-32b", cfg) is False

    def test_admin_toggle_turns_it_off(self):
        cfg = self._cfg_for(api_protocol="vllm", supports_structured=False)
        assert llm_service.use_native_structured_output("qwen3-32b", cfg) is False


class TestUnwrapModelBaseUrl:
    """The URL an agent will actually dial, which is not the stored endpoint."""

    def _cfg(self, **fields):
        return {"available_models": [fields]}

    def test_reading_base_url_off_the_wrapper_returns_nothing(self):
        """Why the helper exists: ``base_url`` resolves as a property on the
        wrapper classes themselves (defaulting to None on ``Model``) instead of
        falling through ``WrapperModel.__getattr__`` to the provider."""
        cfg = self._cfg(name="qwen3-32b", api_protocol="vllm",
                        endpoint="http://inference.local:8000")
        model = llm_service.get_agent_model("qwen3-32b", system_config_doc=cfg)
        assert getattr(model, "base_url", None) is None

    def test_vllm_appends_v1_to_the_stored_endpoint(self):
        cfg = self._cfg(name="qwen3-32b", api_protocol="vllm",
                        endpoint="http://inference.local:8000")
        model = llm_service.get_agent_model("qwen3-32b", system_config_doc=cfg)
        assert llm_service.unwrap_model_base_url(model).startswith(
            "http://inference.local:8000/v1"
        )

    def test_external_openai_model_builds_and_reports_its_url(self):
        """The "OpenAI" and "Custom" wizard presets both save external + the
        openai protocol. That branch passed ``openai_client=`` to
        ``OpenAIChatModel``, which takes only ``provider``/``profile``/
        ``settings`` — so it raised TypeError before any request was made and
        no test built a model to notice."""
        cfg = self._cfg(name="gpt-4o", api_protocol="openai", external=True,
                        endpoint="https://api.openai.com/v1")
        model = llm_service.get_agent_model("gpt-4o", system_config_doc=cfg)
        assert llm_service.unwrap_model_base_url(model).startswith(
            "https://api.openai.com/v1"
        )


def test_supported_protocols_contains_all_branches():
    """Guard against the enum drifting away from the routing branches."""
    assert set(SUPPORTED_PROTOCOLS) == {"openai", "anthropic", "openrouter", "ollama", "vllm", "google"}


class TestPerLoopHttpClient:
    """The httpx client must be reused per event loop, never rebuilt per call.

    Regression guard for the file-descriptor leak (prod incident 2026-06-03,
    Sentry 7517108223): a fresh client per LLM call piled connection pools onto
    each long-lived worker-thread loop until the process hit [Errno 24].
    """

    def test_same_loop_returns_same_client(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            first = llm_service._get_loop_http_client()
            second = llm_service._get_loop_http_client()
            assert first is second, "client must be reused within a loop, not rebuilt per call"
            assert not first.is_closed
        finally:
            loop.run_until_complete(first.aclose())
            loop.close()
            asyncio.set_event_loop(None)

    def test_distinct_loops_get_distinct_clients(self):
        # Each event loop gets its own client — sharing one across loops is what
        # caused pydantic-ai's "bound to a different event loop" error (#455).
        loop_a = asyncio.new_event_loop()
        asyncio.set_event_loop(loop_a)
        client_a = llm_service._get_loop_http_client()

        loop_b = asyncio.new_event_loop()
        asyncio.set_event_loop(loop_b)
        client_b = llm_service._get_loop_http_client()
        try:
            assert client_a is not client_b
        finally:
            loop_a.run_until_complete(client_a.aclose())
            loop_b.run_until_complete(client_b.aclose())
            loop_a.close()
            loop_b.close()
            asyncio.set_event_loop(None)

    def test_dropped_loop_is_evicted_from_registry(self):
        # When a loop is garbage-collected (e.g. a workflow worker thread exits),
        # its entry must drop out of the WeakKeyDictionary so the client — and
        # the file descriptors it holds — can be reclaimed.
        import gc

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = llm_service._get_loop_http_client()
        loop.run_until_complete(client.aclose())
        loop.close()
        asyncio.set_event_loop(None)
        assert loop in llm_service._loop_http_clients
        del loop, client
        gc.collect()
        assert len(llm_service._loop_http_clients) == 0


class TestRateLimitRetryTransport:
    """A 429 from the gateway is a per-minute window, not a blip: wait for the
    window to move (Retry-After if given, else exponential + jitter), and on
    exhaustion return the real 429 so the SDK raises its own RateLimitError
    (Sentry VANDALIZER-BACKEND-2T: three SDK retries inside 400ms, all 429)."""

    @staticmethod
    def _client(statuses, headers=None):
        """Client whose transport answers with the given statuses in order."""
        calls = []

        def handler(request):
            calls.append(request)
            status = statuses[min(len(calls) - 1, len(statuses) - 1)]
            return httpx.Response(
                status, json={"detail": "x"},
                headers=headers if status == 429 else None,
            )

        transport = llm_service.RateLimitRetryTransport(
            httpx.MockTransport(handler), max_attempts=4, base_wait=2.0, max_wait=30.0,
        )
        return httpx.AsyncClient(transport=transport), calls

    @pytest.mark.asyncio
    async def test_retries_429_then_returns_success(self):
        client, calls = self._client([429, 429, 200])
        with patch.object(llm_service.asyncio, "sleep", new=AsyncMock()) as sleep, \
             patch.object(llm_service.random, "uniform", return_value=0.0):
            async with client:
                r = await client.post("https://gw.example/v1/chat/completions", json={"a": 1})
        assert r.status_code == 200
        assert len(calls) == 3
        # exponential fallback: 2s, then 4s
        assert [c.args[0] for c in sleep.call_args_list] == [2.0, 4.0]

    @pytest.mark.asyncio
    async def test_honours_retry_after_header(self):
        client, _ = self._client([429, 200], headers={"Retry-After": "7"})
        with patch.object(llm_service.asyncio, "sleep", new=AsyncMock()) as sleep, \
             patch.object(llm_service.random, "uniform", return_value=0.0):
            async with client:
                r = await client.post("https://gw.example/v1/chat/completions", json={})
        assert r.status_code == 200
        assert sleep.call_args_list[0].args[0] == 7.0

    @pytest.mark.asyncio
    async def test_exhaustion_returns_the_real_429(self):
        """Not raised: an escaping exception would reach the OpenAI SDK as a
        'Connection error' and hide that this was a rate limit."""
        client, calls = self._client([429])
        with patch.object(llm_service.asyncio, "sleep", new=AsyncMock()) as sleep:
            async with client:
                r = await client.post("https://gw.example/v1/chat/completions", json={})
        assert r.status_code == 429
        assert len(calls) == 4  # max_attempts
        assert sleep.await_count == 3

    @pytest.mark.asyncio
    async def test_other_statuses_pass_through_untouched(self):
        client, calls = self._client([500])
        with patch.object(llm_service.asyncio, "sleep", new=AsyncMock()) as sleep:
            async with client:
                r = await client.post("https://gw.example/v1/chat/completions", json={})
        assert r.status_code == 500
        assert len(calls) == 1
        sleep.assert_not_awaited()

    def test_loop_client_is_built_on_the_retry_transport(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            client = llm_service._get_loop_http_client()
            assert isinstance(client._transport, llm_service.RateLimitRetryTransport)
        finally:
            loop.run_until_complete(client.aclose())
            loop.close()
            asyncio.set_event_loop(None)


class TestTruncationCapture:
    """A response that stops at max_tokens is detectable by the caller."""

    def test_events_land_in_the_open_sink(self):
        from app.services.llm_service import capture_truncation, record_truncation

        with capture_truncation() as events:
            record_truncation("qwen3", 8192)
        assert events == [{"model": "qwen3", "max_tokens": 8192}]

    def test_no_sink_open_is_a_no_op(self):
        from app.services.llm_service import record_truncation

        record_truncation("qwen3", 8192)  # logs only; must not raise

    def test_sinks_do_not_leak_to_the_next_block(self):
        from app.services.llm_service import capture_truncation, record_truncation

        with capture_truncation() as first:
            record_truncation("qwen3", 8192)
        with capture_truncation() as second:
            pass
        assert len(first) == 1
        assert second == []

    def test_note_finish_only_fires_on_length(self):
        from unittest.mock import MagicMock

        from app.services.llm_service import MeteredModel, capture_truncation

        # Bypass WrapperModel.__init__ (it resolves a real provider) and hand
        # the wrapper a stub; model_name delegates to it.
        model = MeteredModel.__new__(MeteredModel)
        model.wrapped = MagicMock(model_name="qwen3")
        stopped = MagicMock(finish_reason="stop")
        truncated = MagicMock(finish_reason="length")

        with capture_truncation() as events:
            model._note_finish(stopped, {"max_tokens": 8192})
            model._note_finish(None, {"max_tokens": 8192})
            model._note_finish(truncated, {"max_tokens": 8192})
        assert [e["max_tokens"] for e in events] == [8192]

    def test_describe_truncation_names_the_cap(self):
        from app.services.llm_service import describe_truncation

        text = describe_truncation([{"model": "qwen3", "max_tokens": 8192}])
        assert "8,192-token output limit" in text
        assert "Response reserve" in text

    def test_describe_truncation_without_a_known_cap(self):
        from app.services.llm_service import describe_truncation

        text = describe_truncation([{"model": "qwen3", "max_tokens": None}])
        assert "output limit" in text
