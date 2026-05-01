"""Tests for app.services.llm_service — protocol detection."""

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
