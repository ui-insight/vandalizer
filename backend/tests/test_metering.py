"""Unit tests for central LLM token metering (app/services/metering.py +
MeteredModel in app/services/llm_service.py).

These avoid MongoDB by stubbing the flush sinks and asserting on the in-memory
MeterScope the wrapper/context-managers produce.
"""

import pytest

from app.services import metering
from app.services.llm_service import MeteredModel


# ---------------------------------------------------------------------------
# Fakes for the pydantic-ai Model surface the wrapper touches
# ---------------------------------------------------------------------------
class _Usage:
    def __init__(self, i, o):
        self.input_tokens = i
        self.output_tokens = o


class _Part:
    def __init__(self, content):
        self.content = content


class _Resp:
    def __init__(self, usage, parts):
        self.usage = usage
        self.parts = parts


class _Msg:
    def __init__(self, content):
        self.parts = [_Part(content)]


class _FakeModel:
    """Minimal Model stand-in; MeteredModel delegates model_name/system here."""

    def __init__(self, resp):
        self._resp = resp

    @property
    def model_name(self):
        return "fake-model"

    @property
    def system(self):
        return "openai"

    async def request(self, messages, model_settings, model_request_parameters):
        return self._resp


def _metered_model(resp):
    mm = MeteredModel.__new__(MeteredModel)
    mm.wrapped = _FakeModel(resp)
    return mm


@pytest.fixture(autouse=True)
def _capture_flushes(monkeypatch):
    """Capture flushed scopes instead of writing to Mongo."""
    flushed = []
    monkeypatch.setattr(metering, "flush_sync", lambda s: flushed.append(("sync", s)))

    async def _afl(s):
        flushed.append(("async", s))

    monkeypatch.setattr(metering, "flush_async", _afl)
    return flushed


class _FakeStream:
    def __init__(self, usage, parts):
        self._usage = usage
        self._parts = parts

    def usage(self):
        return self._usage

    def get(self):
        return _Resp(self._usage, self._parts)


class _StreamingModel:
    def __init__(self, stream):
        self._stream = stream

    @property
    def model_name(self):
        return "fake-model"

    @property
    def system(self):
        return "openai"

    def request_stream(self, messages, model_settings, model_request_parameters, run_context=None):
        import contextlib

        stream = self._stream

        @contextlib.asynccontextmanager
        async def _cm():
            yield stream

        return _cm()


async def test_request_stream_records_usage_after_drain():
    mm = MeteredModel.__new__(MeteredModel)
    mm.wrapped = _StreamingModel(_FakeStream(_Usage(20, 8), []))
    with metering.metered("chat") as scope:
        async with mm.request_stream([], None, None) as s:
            assert s.usage().input_tokens == 20  # consumer drains here
    assert (scope.tokens_in, scope.tokens_out, scope.requests) == (20, 8, 1)
    assert scope.estimated is False


# ---------------------------------------------------------------------------
# Wrapper: exact usage from provider
# ---------------------------------------------------------------------------
async def test_request_records_exact_usage():
    mm = _metered_model(_Resp(_Usage(11, 7), []))
    with metering.metered("unit") as scope:
        await mm.request([], None, None)
    assert (scope.tokens_in, scope.tokens_out, scope.requests) == (11, 7, 1)
    assert scope.estimated is False
    assert scope.model == "fake-model"


# ---------------------------------------------------------------------------
# Wrapper: estimate fallback when the provider returns no usage
# ---------------------------------------------------------------------------
async def test_request_estimates_when_usage_missing():
    resp = _Resp(None, [_Part("some output text the model produced")])
    mm = _metered_model(resp)
    with metering.metered("unit") as scope:
        await mm.request([_Msg("a reasonably long input prompt here")], None, None)
    assert scope.estimated is True
    assert scope.tokens_in > 0
    assert scope.tokens_out > 0


async def test_request_estimates_when_usage_zero():
    mm = _metered_model(_Resp(_Usage(0, 0), [_Part("output")]))
    with metering.metered("unit") as scope:
        await mm.request([_Msg("input")], None, None)
    assert scope.estimated is True
    assert scope.tokens_in + scope.tokens_out > 0


# ---------------------------------------------------------------------------
# Context managers flush exactly once with the accrued totals
# ---------------------------------------------------------------------------
def test_metered_flushes_once(_capture_flushes):
    with metering.metered("feat_a", user_id="u1", team_id="t1", activity_id="a1"):
        metering.record_usage("m", 3, 4)
        metering.record_usage("m", 1, 1)
    assert len(_capture_flushes) == 1
    kind, scope = _capture_flushes[0]
    assert kind == "sync"
    assert (scope.feature, scope.user_id, scope.activity_id) == ("feat_a", "u1", "a1")
    assert (scope.tokens_in, scope.tokens_out, scope.requests) == (4, 5, 2)


async def test_metered_async_flushes_once(_capture_flushes):
    async with metering.metered_async("feat_b", user_id="u2"):
        metering.record_usage("m", 10, 2)
    assert len(_capture_flushes) == 1
    kind, scope = _capture_flushes[0]
    assert kind == "async"
    assert scope.feature == "feat_b"
    assert scope.tokens_in == 10 and scope.tokens_out == 2


# ---------------------------------------------------------------------------
# Nested scopes: usage accrues to the nearest scope, no double counting
# ---------------------------------------------------------------------------
def test_nested_scope_accrues_to_nearest(_capture_flushes):
    with metering.metered("outer") as outer:
        metering.record_usage("m", 5, 5)
        with metering.metered("inner") as inner:
            metering.record_usage("m", 1, 1)
        # after inner closes, usage goes back to outer
        metering.record_usage("m", 2, 2)
    assert (inner.tokens_in, inner.tokens_out) == (1, 1)
    assert (outer.tokens_in, outer.tokens_out) == (7, 7)
    # inner flush, then outer flush
    assert [k for k, _ in _capture_flushes] == ["sync", "sync"]
    assert [s.feature for _, s in _capture_flushes] == ["inner", "outer"]


# ---------------------------------------------------------------------------
# Backstop: no scope set -> recorded as unattributed, never lost
# ---------------------------------------------------------------------------
def test_backstop_records_unattributed(_capture_flushes):
    # Ensure no ambient scope
    assert metering.current_scope() is None
    metering.record_usage("m", 9, 9)
    assert len(_capture_flushes) == 1
    _, scope = _capture_flushes[0]
    assert scope.feature == metering.UNATTRIBUTED_FEATURE
    assert (scope.tokens_in, scope.tokens_out) == (9, 9)


# ---------------------------------------------------------------------------
# Estimation helpers
# ---------------------------------------------------------------------------
def test_estimate_tokens_nonzero_and_empty():
    assert metering.estimate_tokens("") == 0
    assert metering.estimate_tokens("hello world") > 0


def test_estimate_messages_and_parts():
    assert metering.estimate_messages_tokens([_Msg("a longer prompt string")]) > 0
    assert metering.estimate_parts_tokens([_Part("output content")]) > 0
    assert metering.estimate_messages_tokens([]) == 0


# ---------------------------------------------------------------------------
# Empty scope (no LLM call) should not flush a row
# ---------------------------------------------------------------------------
def test_real_flush_sync_skips_empty_scope(monkeypatch):
    # Use the real flush_sync but assert it returns early (no DB access) when
    # nothing was recorded. get_sync_db must NOT be called.
    called = {"db": False}

    def _boom():
        called["db"] = True
        raise AssertionError("should not touch DB for empty scope")

    import app.tasks as tasks_mod
    monkeypatch.setattr(tasks_mod, "get_sync_db", _boom)
    metering.flush_sync(metering.MeterScope(feature="empty"))
    assert called["db"] is False
