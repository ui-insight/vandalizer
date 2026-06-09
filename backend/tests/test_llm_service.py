"""Tests for app.services.llm_service — protocol detection."""

import asyncio

from app.services import llm_service
from app.services.llm_service import (
    SUPPORTED_PROTOCOLS,
    detect_api_protocol,
)


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

    def test_vllm_substring_detected(self):
        assert detect_api_protocol("vllm/qwen3") == "vllm"


def test_supported_protocols_contains_all_branches():
    """Guard against the enum drifting away from the routing branches."""
    assert set(SUPPORTED_PROTOCOLS) == {"openai", "anthropic", "openrouter", "ollama", "vllm"}


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
