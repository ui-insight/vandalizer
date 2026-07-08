"""Phase 5 of the agentic-chat harness uplift: transient-failure retries and
tool-error hints. RetryingModel wraps every model built by get_agent_model,
so these semantics apply to chat, extraction, workflows, and compaction."""

import types

import pytest

from app.services import llm_service
from app.services.chat_tools import _err
from app.services.llm_service import (
    is_transient_llm_error,
    MAX_TRANSIENT_LLM_RETRIES,
    RetryingModel,
)


class _Boom(Exception):
    def __init__(self, msg, status_code=None):
        super().__init__(msg)
        if status_code is not None:
            self.status_code = status_code


class TestTransientClassifier:
    def test_retryable_status_codes(self):
        for code in (408, 429, 500, 502, 503, 504, 529):
            assert is_transient_llm_error(_Boom("x", status_code=code))

    def test_non_retryable_status_codes(self):
        for code in (400, 401, 403, 404, 422):
            assert not is_transient_llm_error(_Boom("x", status_code=code))

    def test_connection_blips_retry(self):
        # The oauthdev class: "Connection error." from an unreachable gateway.
        assert is_transient_llm_error(_Boom("Connection error."))
        assert is_transient_llm_error(_Boom("peer closed connection"))
        assert is_transient_llm_error(_Boom("Request timed out"))

    def test_context_length_never_retries(self):
        # Phrased transiently by some gateways, but retrying cannot fix it.
        assert not is_transient_llm_error(_Boom("prompt is too long: maximum context reached"))
        assert not is_transient_llm_error(_Boom("connection error: context length exceeded"))

    def test_auth_never_retries(self):
        assert not is_transient_llm_error(_Boom("invalid api key"))
        assert not is_transient_llm_error(_Boom("authentication failed"))


class _FlakyModel:
    """Minimal Model stand-in: fails N times, then succeeds."""

    def __init__(self, failures: int, exc: Exception):
        self.failures = failures
        self.exc = exc
        self.calls = 0

    async def request(self, messages, model_settings, model_request_parameters):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return types.SimpleNamespace(parts=[], usage=None)


def _no_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(llm_service.asyncio, "sleep", instant)


class TestRetryingModel:
    def _wrap(self, inner) -> RetryingModel:
        model = RetryingModel.__new__(RetryingModel)
        # WrapperModel stores the inner model; bypass __init__ (it validates
        # real Model instances) and set the attribute it reads.
        model.wrapped = inner
        return model

    async def test_recovers_from_transient_failures(self, monkeypatch):
        _no_sleep(monkeypatch)
        inner = _FlakyModel(2, _Boom("Connection error."))
        wrapped = self._wrap(inner)
        await wrapped.request([], None, None)
        assert inner.calls == 3

    async def test_gives_up_after_max_retries(self, monkeypatch):
        _no_sleep(monkeypatch)
        inner = _FlakyModel(99, _Boom("Connection error."))
        wrapped = self._wrap(inner)
        with pytest.raises(_Boom):
            await wrapped.request([], None, None)
        assert inner.calls == MAX_TRANSIENT_LLM_RETRIES + 1

    async def test_non_transient_fails_immediately(self, monkeypatch):
        _no_sleep(monkeypatch)
        inner = _FlakyModel(99, _Boom("invalid api key", status_code=401))
        wrapped = self._wrap(inner)
        with pytest.raises(_Boom):
            await wrapped.request([], None, None)
        assert inner.calls == 1

    async def test_stream_open_failures_retry_but_entered_streams_do_not(self, monkeypatch):
        _no_sleep(monkeypatch)
        from contextlib import asynccontextmanager

        opens = {"count": 0}

        class _StreamInner:
            @asynccontextmanager
            async def request_stream(self, *a, **k):
                opens["count"] += 1
                if opens["count"] == 1:
                    raise _Boom("Connection error.")  # fails at open → retry
                yield types.SimpleNamespace()

        wrapped = self._wrap(_StreamInner())
        async with wrapped.request_stream([], None, None) as stream:
            assert stream is not None
        assert opens["count"] == 2

        # Mid-stream (post-entry) consumer errors must propagate, not retry.
        opens["count"] = 99  # any further open would be visible
        entered_then_failed = {"opens": 0}

        class _MidStreamInner:
            @asynccontextmanager
            async def request_stream(self, *a, **k):
                entered_then_failed["opens"] += 1
                yield types.SimpleNamespace()

        wrapped2 = self._wrap(_MidStreamInner())
        with pytest.raises(_Boom):
            async with wrapped2.request_stream([], None, None):
                raise _Boom("Connection error.")  # transient-looking, but mid-stream
        assert entered_then_failed["opens"] == 1


class TestToolErrorEnvelope:
    def test_hint_included_when_given(self):
        out = _err("Folder not found.", hint="Call list_folders and retry.")
        assert out == {"error": "Folder not found.", "hint": "Call list_folders and retry."}

    def test_plain_error_without_hint(self):
        assert _err("boom") == {"error": "boom"}
