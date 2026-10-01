"""An unreachable model provider is logged as an outage, not a bug.

Every concurrent extraction call during a DNS failure logged its own
traceback at error (Sentry 7723267818, nightly quality monitor). The
ExtractionError still propagates; the task that ran the extraction decides
whether the failure deserves an error.
"""

import logging

import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from app.services.extraction_engine import ExtractionEngine, ExtractionError, _log_llm_failure


class _Agent:
    def __init__(self, exc):
        self._exc = exc

    def run_sync(self, _prompt):
        raise self._exc


def _run_fallback(monkeypatch, exc):
    monkeypatch.setattr(
        "app.services.extraction_engine.create_chat_agent", lambda *a, **k: _Agent(exc),
    )
    engine = ExtractionEngine(system_config_doc={})
    with pytest.raises(ExtractionError):
        engine._extract_fallback_json("some document text", ["PI Name"], "test-model")


def _engine_records(caplog, level):
    return [r for r in caplog.records if r.name == "app.services.extraction_engine" and r.levelno == level]


def test_a_dns_failure_is_a_warning_and_still_fails_the_call(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    _run_fallback(monkeypatch, ModelAPIError(model_name="m", message="Connection error."))
    assert _engine_records(caplog, logging.ERROR) == []
    assert any("provider unreachable" in r.getMessage() for r in _engine_records(caplog, logging.WARNING))


def test_an_unexpected_failure_is_still_an_error(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    _run_fallback(monkeypatch, RuntimeError("bad payload shape"))
    errors = _engine_records(caplog, logging.ERROR)
    assert len(errors) == 1 and errors[0].exc_info


@pytest.mark.parametrize("exc,level", [
    (ModelHTTPError(status_code=503, model_name="m"), logging.WARNING),
    (ModelHTTPError(status_code=429, model_name="m"), logging.WARNING),
    # A renamed model or revoked key is configuration, not an outage.
    (ModelHTTPError(status_code=404, model_name="m"), logging.ERROR),
    (ModelHTTPError(status_code=401, model_name="m"), logging.ERROR),
])
def test_status_errors_split_on_whether_a_retry_could_help(caplog, exc, level):
    caplog.set_level(logging.WARNING)
    try:
        raise exc
    except ModelHTTPError as e:
        _log_llm_failure("Extraction LLM call failed", e)
    assert [r.levelno for r in caplog.records if r.name == "app.services.extraction_engine"] == [level]
