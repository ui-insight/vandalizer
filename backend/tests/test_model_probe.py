"""Tests for the LLM endpoint context-window probe."""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.model_probe import (
    ProbeResult,
    _match_model_entry,
    probe_context_window,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubTransport(httpx.MockTransport):
    """httpx MockTransport that captures the last request for inspection."""

    def __init__(self, handler):
        super().__init__(handler)
        self.last_request: httpx.Request | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        self.last_request = request
        return super().handle_request(request)


@pytest.fixture
def patch_httpx(monkeypatch):
    """Patch httpx.AsyncClient so probes route to a MockTransport."""

    def _install(handler):
        transport = _StubTransport(handler)
        real_init = httpx.AsyncClient.__init__

        def _init(self, *args, **kwargs):
            kwargs["transport"] = transport
            return real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", _init)
        return transport

    return _install


def _json_response(status: int, payload):
    return httpx.Response(status, content=json.dumps(payload).encode())


# ---------------------------------------------------------------------------
# Model matching helper
# ---------------------------------------------------------------------------


def test_match_model_entry_prefers_exact_id():
    entries = [{"id": "foo"}, {"id": "bar"}, {"id": "baz"}]
    assert _match_model_entry(entries, "bar") == {"id": "bar"}


def test_match_model_entry_is_case_insensitive():
    entries = [{"id": "Meta-Llama-3-70B"}]
    assert _match_model_entry(entries, "meta-llama-3-70b") == {"id": "Meta-Llama-3-70B"}


def test_match_model_entry_falls_back_to_suffix():
    entries = [{"id": "openrouter/meta-llama/llama-3-70b"}]
    assert _match_model_entry(entries, "llama-3-70b") == entries[0]


def test_match_model_entry_returns_none_when_no_match():
    assert _match_model_entry([{"id": "foo"}], "bar") is None


def test_match_model_entry_takes_first_when_no_name():
    entries = [{"id": "a"}, {"id": "b"}]
    assert _match_model_entry(entries, "") == {"id": "a"}


# ---------------------------------------------------------------------------
# vLLM (OpenAI-compatible /v1/models with max_model_len)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_vllm_finds_max_model_len(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/models")
        return _json_response(200, {
            "object": "list",
            "data": [
                {"id": "Llama-3-70B", "object": "model", "max_model_len": 65536},
            ],
        })

    patch_httpx(handler)
    result = await probe_context_window(
        endpoint="https://vllm.example.com",
        api_protocol="vllm",
        api_key="secret",
        model_name="Llama-3-70B",
    )
    assert result == ProbeResult(
        context_window=65536,
        source="vllm_max_model_len",
        detail=None,
        raw={"id": "Llama-3-70B", "object": "model", "max_model_len": 65536},
    )


@pytest.mark.asyncio
async def test_probe_appends_v1_when_missing(patch_httpx):
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return _json_response(200, {
            "data": [{"id": "m", "max_model_len": 4096}]
        })

    patch_httpx(handler)
    await probe_context_window(
        endpoint="https://server.example.com",
        api_protocol="vllm",
        api_key="",
        model_name="m",
    )
    assert captured == ["https://server.example.com/v1/models"]


@pytest.mark.asyncio
async def test_probe_does_not_double_v1(patch_httpx):
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return _json_response(200, {"data": [{"id": "m", "max_model_len": 4096}]})

    patch_httpx(handler)
    await probe_context_window(
        endpoint="https://server.example.com/v1",
        api_protocol="vllm",
        api_key="",
        model_name="m",
    )
    assert captured == ["https://server.example.com/v1/models"]


@pytest.mark.asyncio
async def test_probe_sends_authorization_header(patch_httpx):
    captured_headers: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.append(dict(request.headers))
        return _json_response(200, {"data": [{"id": "m", "max_model_len": 1024}]})

    patch_httpx(handler)
    await probe_context_window(
        endpoint="https://x.example.com",
        api_protocol="vllm",
        api_key="sk-abc",
        model_name="m",
    )
    assert captured_headers[0].get("authorization") == "Bearer sk-abc"


@pytest.mark.asyncio
async def test_probe_skips_auth_when_no_api_key(patch_httpx):
    captured_headers: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.append(dict(request.headers))
        return _json_response(200, {"data": [{"id": "m", "max_model_len": 1024}]})

    patch_httpx(handler)
    await probe_context_window(
        endpoint="https://x.example.com",
        api_protocol="vllm",
        api_key="no-api-key",
        model_name="m",
    )
    assert "authorization" not in captured_headers[0]


# ---------------------------------------------------------------------------
# OpenRouter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_openrouter_uses_context_length(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {
            "data": [
                {"id": "meta-llama/llama-3-70b", "context_length": 131072},
            ],
        })

    patch_httpx(handler)
    result = await probe_context_window(
        endpoint="https://openrouter.ai/api",
        api_protocol="openrouter",
        api_key="key",
        model_name="meta-llama/llama-3-70b",
    )
    assert result.context_window == 131072
    assert result.source == "openrouter_context_length"


# ---------------------------------------------------------------------------
# OpenAI (no context field exposed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_openai_reports_no_field(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {
            "data": [
                {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
            ],
        })

    patch_httpx(handler)
    result = await probe_context_window(
        endpoint="https://api.openai.com",
        api_protocol="openai",
        api_key="sk",
        model_name="gpt-4o",
    )
    assert result.context_window is None
    assert result.source == "openai_no_field"
    assert "context length" in (result.detail or "").lower()


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_no_endpoint():
    result = await probe_context_window(
        endpoint="",
        api_protocol="vllm",
        api_key="",
        model_name="m",
    )
    assert result.context_window is None
    assert result.source == "no_endpoint"


@pytest.mark.asyncio
async def test_probe_handles_401(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b"{}")

    patch_httpx(handler)
    result = await probe_context_window(
        endpoint="https://x.example.com",
        api_protocol="vllm",
        api_key="bad",
        model_name="m",
    )
    assert result.context_window is None
    assert "401" in (result.detail or "") or "rejected" in (result.detail or "").lower()


@pytest.mark.asyncio
async def test_probe_handles_404(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"not found")

    patch_httpx(handler)
    result = await probe_context_window(
        endpoint="https://x.example.com",
        api_protocol="vllm",
        api_key="",
        model_name="m",
    )
    assert result.context_window is None
    assert result.source == "error"


@pytest.mark.asyncio
async def test_probe_handles_non_json(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>oops</html>")

    patch_httpx(handler)
    result = await probe_context_window(
        endpoint="https://x.example.com",
        api_protocol="vllm",
        api_key="",
        model_name="m",
    )
    assert result.context_window is None
    assert result.source == "error"


@pytest.mark.asyncio
async def test_probe_handles_no_matching_model(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {"data": [{"id": "other"}]})

    patch_httpx(handler)
    result = await probe_context_window(
        endpoint="https://x.example.com",
        api_protocol="vllm",
        api_key="",
        model_name="missing",
    )
    assert result.context_window is None
    assert "missing" in (result.detail or "")


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_ollama_reads_model_info(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/show"
        return _json_response(200, {
            "model_info": {
                "general.architecture": "llama",
                "llama.context_length": 8192,
            },
        })

    patch_httpx(handler)
    result = await probe_context_window(
        endpoint="http://ollama.local:11434",
        api_protocol="ollama",
        api_key="",
        model_name="llama3:latest",
    )
    assert result.context_window == 8192
    assert result.source == "ollama_show"


@pytest.mark.asyncio
async def test_probe_ollama_falls_back_to_parameters_blob(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {
            "parameters": "stop \"\\n\\n\"\nnum_ctx 16384\n",
        })

    patch_httpx(handler)
    result = await probe_context_window(
        endpoint="http://ollama.local:11434",
        api_protocol="ollama",
        api_key="",
        model_name="custom",
    )
    assert result.context_window == 16384


@pytest.mark.asyncio
async def test_probe_ollama_missing_model(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"{}")

    patch_httpx(handler)
    result = await probe_context_window(
        endpoint="http://ollama.local:11434",
        api_protocol="ollama",
        api_key="",
        model_name="nope",
    )
    assert result.context_window is None
    assert "nope" in (result.detail or "")


# ---------------------------------------------------------------------------
# Anthropic (skipped entirely)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_anthropic_returns_no_probe():
    result = await probe_context_window(
        endpoint="https://api.anthropic.com",
        api_protocol="anthropic",
        api_key="sk",
        model_name="claude-sonnet-4-6",
    )
    assert result.context_window is None
    assert result.source == "anthropic_no_probe"
