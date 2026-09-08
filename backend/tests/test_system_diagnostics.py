"""Unit tests for system diagnostics — error classification, readiness grading,
and the model diagnostic step breakdown."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.system_diagnostics import (
    _classify_error,
    build_readiness,
    diagnose_model,
)


def _cfg(**overrides):
    """A SystemConfig-like stub. build_readiness/diagnose_model only read
    attributes and call model_dump(), so a SimpleNamespace suffices."""
    base = dict(
        available_models=[],
        default_model="",
        ocr_endpoint="",
        ocr_api_key="",
        ocr_provider="raw",
        llm_endpoint="",
        auth_methods=[],
        oauth_providers=[],
    )
    base.update(overrides)
    ns = SimpleNamespace(**base)
    ns.model_dump = lambda: dict(base)
    return ns


# --- error classification -------------------------------------------------


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Error code: 401 - invalid api key", "auth"),
        ("Unauthorized", "auth"),
        ("model gpt-9 does not exist", "model_not_found"),
        ("404 not found", "model_not_found"),
        ("Request timed out", "timeout"),
        ("429 rate limit exceeded", "rate_limit"),
        ("Connection error: getaddrinfo failed", "connection"),
        ("Connection refused", "connection"),
        # pydantic-ai's UserError for an unsupported output mode. Before it was
        # classified it fell to "unknown" — "read the raw error" — for the one
        # failure with a precise remedy.
        ("Native structured output is not supported by this model.", "capability"),
        ("Tool output is not supported by this model.", "capability"),
        ("some unexpected boom", "unknown"),
    ],
)
def test_classify_error_categories(message, expected):
    result = _classify_error(Exception(message))
    assert result["category"] == expected
    # Every classification must give the admin something actionable.
    assert result["why"] and result["fix"] and result["title"]


# --- readiness grading ----------------------------------------------------


def test_readiness_empty_install_blocks_on_llm():
    report = build_readiness(_cfg())
    assert report["ready"] is False
    assert report["blockers_remaining"] == 1
    llm = next(i for i in report["items"] if i["key"] == "llm")
    assert llm["severity"] == "blocker"
    assert llm["status"] == "missing"


def test_readiness_models_without_default_is_incomplete():
    report = build_readiness(_cfg(available_models=[{"name": "gpt-4o"}], default_model=""))
    llm = next(i for i in report["items"] if i["key"] == "llm")
    assert llm["status"] == "incomplete"
    # An LLM that exists but has no default still leaves the blocker unmet.
    assert report["ready"] is False


def test_readiness_fully_configured_is_ready():
    report = build_readiness(_cfg(
        available_models=[{"name": "gpt-4o"}],
        default_model="gpt-4o",
        ocr_endpoint="https://ocr.example",
        auth_methods=["password"],
    ))
    assert report["ready"] is True
    assert report["blockers_remaining"] == 0
    assert all(i["status"] == "configured" for i in report["items"])


# --- model diagnostics ----------------------------------------------------


def test_diagnose_model_out_of_range():
    import asyncio

    result = asyncio.run(diagnose_model(_cfg(), 0))
    assert result["ok"] is False
    assert result["error"]["category"] == "config"


def test_diagnose_model_success_reports_steps():
    cfg = _cfg(
        available_models=[{"name": "gpt-4o", "tag": "openai", "api_protocol": "openai", "api_key": "k"}],
        default_model="gpt-4o",
    )
    text_run = MagicMock()
    text_run.output = "ok"
    text_run.usage = lambda: SimpleNamespace(request_tokens=3, response_tokens=1, total_tokens=4)
    struct_run = MagicMock()
    struct_run.output = SimpleNamespace(answer="ok")
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=[text_run, struct_run])

    import asyncio

    with patch("app.services.system_diagnostics.get_agent_model", return_value=MagicMock()), \
         patch("pydantic_ai.Agent", return_value=fake_agent), \
         patch("app.services.system_diagnostics.decrypt_value", return_value="secret"):
        result = asyncio.run(diagnose_model(cfg, 0))

    assert result["ok"] is True
    assert result["tokens"]["total"] == 4
    labels = [c["label"] for c in result["checks"]]
    assert labels == [
        "Model configuration", "API protocol", "Endpoint", "API key",
        "Live completion", "Structured output",
    ]
    assert all(c["ok"] for c in result["checks"])


def test_diagnose_model_failure_is_classified():
    cfg = _cfg(
        available_models=[{"name": "gpt-4o", "api_protocol": "openai", "api_key": "k"}],
    )
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=Exception("Error code: 401 - invalid api key"))

    import asyncio

    with patch("app.services.system_diagnostics.get_agent_model", return_value=MagicMock()), \
         patch("pydantic_ai.Agent", return_value=fake_agent), \
         patch("app.services.system_diagnostics.decrypt_value", return_value="secret"):
        result = asyncio.run(diagnose_model(cfg, 0))

    assert result["ok"] is False
    assert result["error"]["category"] == "auth"
    # The live-completion step should be the one that failed.
    assert result["checks"][-1]["label"] == "Live completion"
    assert result["checks"][-1]["ok"] is False


# --- structured output: the capability the features actually need ---------


def test_diagnose_model_structured_output_failure_is_not_ok():
    """A model that chats but cannot return a schema-constrained object is
    broken for extraction and every workflow, so the test must go red.

    This is the exact production shape: the endpoint was reachable, the
    credentials were good, the model answered "ok" — and every extraction
    failed. Reporting that model as healthy is what kept the real cause
    invisible until a user filed a ticket.
    """
    cfg = _cfg(
        available_models=[{"name": "Qwen/Qwen3-32B", "api_protocol": "vllm",
                           "endpoint": "http://inference.local:8000"}],
    )
    text_run = MagicMock()
    text_run.output = "ok"
    text_run.usage = lambda: SimpleNamespace(request_tokens=3, response_tokens=1, total_tokens=4)
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=[
        text_run,
        Exception("Native structured output is not supported by this model."),
    ])

    import asyncio

    with patch("app.services.system_diagnostics.get_agent_model", return_value=MagicMock()), \
         patch("pydantic_ai.Agent", return_value=fake_agent), \
         patch("app.services.system_diagnostics.decrypt_value", return_value=""):
        result = asyncio.run(diagnose_model(cfg, 0))

    assert result["ok"] is False
    assert result["error"]["category"] == "capability"
    # Connectivity passed; the capability did not. Both must be visible, or the
    # admin cannot tell "unreachable" from "reachable but unusable".
    by_label = {c["label"]: c for c in result["checks"]}
    assert by_label["Live completion"]["ok"] is True
    assert by_label["Structured output"]["ok"] is False
    assert "extraction and workflows will fail" in by_label["Structured output"]["detail"]
    assert "structured output failed" in result["summary"]


def test_diagnose_model_probes_the_mode_the_engine_will_use():
    """The probe must ask for the same output mode a real run asks for.

    A diagnostic that always used the default mode would pass on exactly the
    configuration extraction fails on.
    """
    from pydantic_ai import NativeOutput

    cfg = _cfg(
        available_models=[{"name": "Qwen/Qwen3-32B", "api_protocol": "vllm",
                           "endpoint": "http://inference.local:8000"}],
    )
    text_run = MagicMock()
    text_run.output = "ok"
    text_run.usage = lambda: SimpleNamespace(request_tokens=1, response_tokens=1, total_tokens=2)
    struct_run = MagicMock()
    struct_run.output = SimpleNamespace(answer="ok")
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=[text_run, struct_run])
    agent_cls = MagicMock(return_value=fake_agent)

    import asyncio

    with patch("app.services.system_diagnostics.get_agent_model", return_value=MagicMock()), \
         patch("pydantic_ai.Agent", agent_cls), \
         patch("app.services.system_diagnostics.decrypt_value", return_value=""):
        result = asyncio.run(diagnose_model(cfg, 0))

    assert result["ok"] is True
    # Second Agent(...) construction is the structured probe.
    probe_kwargs = agent_cls.call_args_list[1].kwargs
    assert isinstance(probe_kwargs["output_type"], NativeOutput)


def test_diagnose_model_reports_the_dialed_url_not_the_stored_one():
    """vLLM/Ollama append "/v1" to the saved endpoint and the OpenAI provider
    does not, so the stored string alone cannot tell an admin which URL was
    called — and switching protocol silently changes it."""
    cfg = _cfg(
        available_models=[{"name": "qwen3-32b", "api_protocol": "vllm",
                           "endpoint": "http://inference.local:8000"}],
    )
    text_run = MagicMock()
    text_run.output = "ok"
    text_run.usage = lambda: SimpleNamespace(request_tokens=1, response_tokens=1, total_tokens=2)
    struct_run = MagicMock()
    struct_run.output = SimpleNamespace(answer="ok")
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=[text_run, struct_run])

    import asyncio

    with patch("app.services.system_diagnostics.get_agent_model", return_value=MagicMock()), \
         patch("app.services.system_diagnostics.unwrap_model_base_url",
               return_value="http://inference.local:8000/v1"), \
         patch("pydantic_ai.Agent", return_value=fake_agent), \
         patch("app.services.system_diagnostics.decrypt_value", return_value=""):
        result = asyncio.run(diagnose_model(cfg, 0))

    endpoint_check = next(c for c in result["checks"] if c["label"] == "Endpoint")
    assert "→ dialing http://inference.local:8000/v1" in endpoint_check["detail"]
    assert result["endpoint"] == "http://inference.local:8000/v1"
