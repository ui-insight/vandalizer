"""Regression tests for optimization-run timestamp serialization.

Datetimes read back from Mongo are naive (the Motor client isn't tz_aware), so
a bare ``.isoformat()`` emits no timezone offset. Browsers then parse the
string as *local* time, which for users west of UTC pushes ``started_at`` into
the future and pins the live elapsed-time readout at 0s. The serializers must
emit an explicit UTC offset so the wire format is unambiguous.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

from app.routers.knowledge import (
    _elapsed_seconds,
    _iso_utc,
    _serialize_optimization_run,
    _summarise_optimization_run,
)
from app.routers.workflows import (
    _serialize_workflow_optimization_run,
    _summarise_workflow_optimization_run,
)
from app.routers.extractions import (
    _serialize_extraction_optimization_run,
    _summarise_extraction_optimization_run,
)


# A naive datetime — exactly what Beanie/Motor hands back on read.
NAIVE = datetime.datetime(2026, 6, 15, 18, 0, 0)
AWARE = datetime.datetime(2026, 6, 15, 18, 0, 0, tzinfo=datetime.timezone.utc)


def test_iso_utc_adds_offset_to_naive_datetime():
    out = _iso_utc(NAIVE)
    assert out is not None
    assert out.endswith("+00:00"), f"naive datetime serialized without offset: {out}"


def test_iso_utc_preserves_already_utc_instant():
    # Same wall-clock instant, naive vs aware, must serialize identically.
    assert _iso_utc(NAIVE) == _iso_utc(AWARE)


def test_iso_utc_passes_through_none():
    assert _iso_utc(None) is None


def _kb_run_with(started_at):
    run = MagicMock()
    run.started_at = started_at
    run.completed_at = None
    run.applied_at = None
    run.reverted_at = None
    return run


def test_kb_serializer_started_at_carries_offset():
    out = _serialize_optimization_run(_kb_run_with(NAIVE))
    assert out["started_at"].endswith("+00:00")


def test_kb_summary_started_at_carries_offset():
    out = _summarise_optimization_run(_kb_run_with(NAIVE))
    assert out["started_at"].endswith("+00:00")


def _wf_run_with(started_at):
    run = MagicMock()
    run.started_at = started_at
    run.completed_at = None
    return run


def test_workflow_serializer_started_at_carries_offset():
    out = _serialize_workflow_optimization_run(_wf_run_with(NAIVE))
    assert out["started_at"].endswith("+00:00")


def test_workflow_summary_started_at_carries_offset():
    out = _summarise_workflow_optimization_run(_wf_run_with(NAIVE))
    assert out["started_at"].endswith("+00:00")


def _extraction_run_with(started_at):
    run = MagicMock()
    run.started_at = started_at
    run.completed_at = None
    run.cancel_requested_at = None
    return run


def test_extraction_serializer_started_at_carries_offset():
    out = _serialize_extraction_optimization_run(_extraction_run_with(NAIVE))
    assert out["started_at"].endswith("+00:00")


def test_extraction_summary_started_at_carries_offset():
    out = _summarise_extraction_optimization_run(_extraction_run_with(NAIVE))
    assert out["started_at"].endswith("+00:00")


# --- Server-authoritative elapsed seconds ---------------------------------
# The live timer used to do ``Date.now() - started_at`` in the browser, mixing
# the client wall clock with the server's start timestamp. On a drifted backend
# (e.g. a Docker VM behind the host) that surfaced the full skew as a sudden
# jump (~3m30s) the instant polling replaced the optimistic client seed. The
# fix moves the elapsed computation server-side; the client only ticks deltas.

def test_elapsed_seconds_completed_run_is_exact_duration():
    start = datetime.datetime(2026, 6, 15, 18, 0, 0, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2026, 6, 15, 18, 3, 30, tzinfo=datetime.timezone.utc)
    assert _elapsed_seconds(start, end) == 210


def test_elapsed_seconds_treats_naive_start_as_utc():
    # A naive start (Mongo read-back) must measure against UTC now, not local.
    start = datetime.datetime(2026, 6, 15, 18, 0, 0)
    end = datetime.datetime(2026, 6, 15, 18, 0, 30)
    assert _elapsed_seconds(start, end) == 30


def test_elapsed_seconds_clamps_negative_to_zero():
    start = datetime.datetime(2026, 6, 15, 18, 0, 30, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2026, 6, 15, 18, 0, 0, tzinfo=datetime.timezone.utc)
    assert _elapsed_seconds(start, end) == 0


def test_elapsed_seconds_none_start_is_none():
    assert _elapsed_seconds(None, None) is None


def test_elapsed_seconds_running_run_uses_now():
    # No completed_at → measured against current UTC time, so non-negative.
    start = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(seconds=5)
    assert _elapsed_seconds(start, None) >= 0


def test_serializers_emit_elapsed_seconds():
    completed = datetime.datetime(2026, 6, 15, 18, 0, 0, tzinfo=datetime.timezone.utc)

    kb = _kb_run_with(NAIVE)
    kb.completed_at = completed
    wf = _wf_run_with(NAIVE)
    wf.completed_at = completed
    ex = _extraction_run_with(NAIVE)
    ex.completed_at = completed

    for out in (
        _serialize_optimization_run(kb),
        _serialize_workflow_optimization_run(wf),
        _serialize_extraction_optimization_run(ex),
    ):
        assert "elapsed_seconds" in out
        assert isinstance(out["elapsed_seconds"], int)
        assert out["elapsed_seconds"] >= 0
