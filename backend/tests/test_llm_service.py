"""Tests for app.services.llm_service — protocol detection."""

import asyncio

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
