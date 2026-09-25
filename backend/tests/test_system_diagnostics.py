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


# --- OCR diagnostics ------------------------------------------------------
#
# The regression these pin: the probe this replaced was a GET that reported any
# HTTP response as success. Both of UIdaho's OCR services answer a GET with 405,
# so the admin panel read green for a month while one returned HTTP 500 to every
# real conversion and the other returned an empty body. Each test below fails if
# the probe stops doing the conversion.


def _ocr_cfg(**overrides):
    return _cfg(**{
        "ocr_endpoint": "https://ocr.example/convert",
        "ocr_api_key": "",
        "ocr_provider": "raw",
        "ocr_options": {},
        "ocr_async": False,
        "ocr_timeout_seconds": 120,
        **overrides,
    })


def test_diagnose_ocr_converts_a_real_page_and_reports_the_text():
    import asyncio

    from app.services.system_diagnostics import diagnose_ocr

    with patch("app.services.ocr_client.convert", return_value="Vandalizer OCR probe. The quick brown fox.") as convert:
        result = asyncio.run(diagnose_ocr(_ocr_cfg()))

    assert result["ok"] is True
    # A conversion was actually attempted, against the configured endpoint,
    # with a real file on disk.
    assert convert.call_count == 1
    assert convert.call_args.kwargs["endpoint"] == "https://ocr.example/convert"
    assert convert.call_args.kwargs["pdf_path"].endswith(".pdf")
    labels = [c["label"] for c in result["checks"]]
    assert "Live conversion" in labels and "Text returned" in labels
    assert all(c["ok"] for c in result["checks"])


def test_diagnose_ocr_fails_when_the_service_500s():
    """The MindRouter outage: an instant 500 on every conversion."""
    import asyncio

    from app.services import ocr_client
    from app.services.system_diagnostics import diagnose_ocr

    err = ocr_client.OcrRequestError(
        "OCR endpoint returned HTTP 500", status_code=500, body='{"error":"Internal server error"}',
    )
    with patch("app.services.ocr_client.convert", side_effect=err):
        result = asyncio.run(diagnose_ocr(_ocr_cfg()))

    assert result["ok"] is False
    assert result["error"]["category"] == "service"
    assert "500" in result["error"]["title"]
    # Names the OCR service as the fault, so an admin doesn't re-type a URL
    # that was never wrong.
    assert "not in this configuration" in result["error"]["why"]
    assert next(c for c in result["checks"] if c["label"] == "Live conversion")["ok"] is False


def test_diagnose_ocr_fails_on_an_empty_bodied_success():
    """The dotsocr outage: HTTP 200 carrying a bare newline.

    The old ping called this healthy. Ingestion treats it as "too little text"
    and silently falls back to PyMuPDF, so a scanned page becomes an empty
    document behind a green badge — the failure worth catching loudest.
    """
    import asyncio

    from app.services.system_diagnostics import diagnose_ocr

    with patch("app.services.ocr_client.convert", return_value="\n"):
        result = asyncio.run(diagnose_ocr(_ocr_cfg()))

    assert result["ok"] is False
    assert result["error"]["category"] == "empty"
    assert next(c for c in result["checks"] if c["label"] == "Text returned")["ok"] is False


def test_diagnose_ocr_classifies_a_refused_key():
    import asyncio

    from app.services import ocr_client
    from app.services.system_diagnostics import diagnose_ocr

    err = ocr_client.OcrRequestError("nope", status_code=401, body="missing api key")
    with patch("app.services.ocr_client.convert", side_effect=err):
        result = asyncio.run(diagnose_ocr(_ocr_cfg()))

    assert result["ok"] is False
    assert result["error"]["category"] == "auth"


def test_diagnose_ocr_reports_the_convert_url_for_docling():
    """The most-misconfigured docling field: the stored root is rewritten."""
    import asyncio

    from app.services.system_diagnostics import diagnose_ocr

    cfg = _ocr_cfg(ocr_endpoint="https://docling.example.edu", ocr_provider="docling")
    with patch("app.services.ocr_client.convert", return_value="Vandalizer OCR probe page text"):
        result = asyncio.run(diagnose_ocr(cfg))

    assert result["convert_url"] == "https://docling.example.edu/v1/convert/file"
    assert "https://docling.example.edu/v1/convert/file" in next(
        c for c in result["checks"] if c["label"] == "Provider"
    )["detail"]


def test_diagnose_ocr_without_an_endpoint_is_a_config_error():
    import asyncio

    from app.services.system_diagnostics import diagnose_ocr

    result = asyncio.run(diagnose_ocr(_ocr_cfg(ocr_endpoint="")))
    assert result["ok"] is False
    assert result["error"]["category"] == "config"


def test_diagnose_ocr_caps_the_probe_timeout():
    """A one-page probe must not hold a request open for the document timeout."""
    import asyncio

    import httpx

    from app.services.system_diagnostics import _OCR_PROBE_MAX_TIMEOUT, diagnose_ocr

    seen = {}
    real_client = httpx.Client

    def spy(*a, **kw):
        seen["timeout"] = kw.get("timeout")
        return real_client(*a, **kw)

    with (
        patch("httpx.Client", side_effect=spy),
        patch("app.services.ocr_client.convert", return_value="Vandalizer OCR probe page text"),
    ):
        asyncio.run(diagnose_ocr(_ocr_cfg(ocr_timeout_seconds=900)))

    assert seen["timeout"] == _OCR_PROBE_MAX_TIMEOUT


def test_diagnose_ocr_probe_cleans_up_its_temp_file():
    import asyncio
    import os

    from app.services.system_diagnostics import diagnose_ocr

    captured = {}

    def grab(*a, **kw):
        captured["path"] = kw["pdf_path"]
        return "Vandalizer OCR probe page text"

    with patch("app.services.ocr_client.convert", side_effect=grab):
        asyncio.run(diagnose_ocr(_ocr_cfg()))

    assert not os.path.exists(captured["path"])


# --- readiness reflects the probe ----------------------------------------


def test_readiness_marks_a_configured_but_broken_ocr_as_broken():
    """Presence is not health. An endpoint string sat at 'configured' for a
    month while every conversion behind it failed."""
    cfg = _cfg(ocr_endpoint="https://ocr.example", ocr_provider="raw")
    probe = {"ok": False, "error": {"title": "OCR service returned HTTP 500"}}

    item = next(i for i in build_readiness(cfg, ocr_probe=probe)["items"] if i["key"] == "ocr")

    assert item["status"] == "broken"
    assert item["summary"] == "OCR service returned HTTP 500"


def test_readiness_without_a_probe_stays_presence_based():
    """The checklist must still render instantly on page load."""
    cfg = _cfg(ocr_endpoint="https://ocr.example", ocr_provider="raw")
    item = next(i for i in build_readiness(cfg)["items"] if i["key"] == "ocr")
    assert item["status"] == "configured"


def test_readiness_broken_ocr_does_not_block_readiness():
    """OCR is 'recommended': uploads degrade without it, so a broken service
    is a red row, not an install-blocking verdict."""
    cfg = _cfg(
        available_models=[{"name": "gpt-4o"}], default_model="gpt-4o",
        ocr_endpoint="https://ocr.example", auth_methods=["password"],
    )
    report = build_readiness(cfg, ocr_probe={"ok": False, "error": {"title": "down"}})
    assert report["ready"] is True



def test_ocr_probe_bounds_the_async_poll():
    """The docling async path polls for up to 15 minutes by default; the probe
    passes its own cap so a stuck task can't hold a worker that long."""
    import asyncio

    from app.services import system_diagnostics as sd

    with patch("app.services.ocr_client.convert", return_value="Vandalizer OCR probe. The quick brown fox.") as convert:
        asyncio.run(sd.diagnose_ocr(_ocr_cfg(ocr_async=True, ocr_provider="docling")))
    assert convert.call_args.kwargs["max_poll_seconds"] == sd._OCR_PROBE_MAX_TIMEOUT


def test_ocr_probe_gives_up_on_a_service_that_never_finishes():
    import asyncio
    import time

    from app.services import system_diagnostics as sd

    def hang(*a, **kw):
        time.sleep(1)
        return "never"

    with patch.object(sd, "_OCR_PROBE_TOTAL_TIMEOUT", 0.05), \
         patch("app.services.ocr_client.convert", side_effect=hang):
        result = asyncio.run(sd.diagnose_ocr(_ocr_cfg()))
    assert result["ok"] is False
    assert result["error"]["category"] == "timeout"
