"""Tests for the KB optimization orphan-run janitor."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import kb_validation_tasks


def _make_stuck_run(uuid="opt-stuck", status="running", age_seconds=4 * 3600):
    rd = MagicMock()
    rd.uuid = uuid
    rd.status = status
    rd.phase = status
    rd.started_at = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(seconds=age_seconds)
    rd.completed_at = None
    rd.error_message = None
    rd.save = AsyncMock()
    return rd


@pytest.mark.asyncio
async def test_janitor_marks_abandoned_runs_failed():
    """Runs in {queued, running} older than the 3-hour cutoff get reaped."""
    stuck1 = _make_stuck_run("opt-1", status="running", age_seconds=4 * 3600)
    stuck2 = _make_stuck_run("opt-2", status="queued", age_seconds=10 * 3600)
    fake_query = MagicMock()
    fake_query.to_list = AsyncMock(return_value=[stuck1, stuck2])

    with patch.object(kb_validation_tasks, "_run_async", side_effect=lambda c: c), \
         patch("app.database.init_db", new=AsyncMock()), \
         patch("app.models.kb_optimization_run.KBOptimizationRun.find", return_value=fake_query):
        result = await kb_validation_tasks._kb_optimization_janitor_async()

    assert result == {"reaped": 2, "scanned": 2}
    for r in (stuck1, stuck2):
        assert r.status == "failed"
        assert r.phase == "failed"
        assert "abandoned" in (r.error_message or "")
        assert r.completed_at is not None
        r.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_janitor_filter_uses_correct_cutoff_and_status_set():
    """Verify the Mongo query uses both the cutoff *and* status in {queued, running}."""
    fake_query = MagicMock()
    fake_query.to_list = AsyncMock(return_value=[])
    captured: dict = {}

    def fake_find(filt):
        captured["filt"] = filt
        return fake_query

    with patch("app.database.init_db", new=AsyncMock()), \
         patch("app.models.kb_optimization_run.KBOptimizationRun.find", side_effect=fake_find):
        await kb_validation_tasks._kb_optimization_janitor_async()

    assert captured["filt"]["status"] == {"$in": ["queued", "running"]}
    # Cutoff must use $lt (less than) so younger runs are NOT reaped.
    assert "$lt" in captured["filt"]["started_at"]
    cutoff = captured["filt"]["started_at"]["$lt"]
    expected_age = datetime.timedelta(seconds=kb_validation_tasks.ORPHAN_RUN_AGE_SECONDS)
    delta = datetime.datetime.now(tz=datetime.timezone.utc) - cutoff
    # Should be approximately ORPHAN_RUN_AGE_SECONDS old (within 5s slop).
    assert abs((delta - expected_age).total_seconds()) < 5


@pytest.mark.asyncio
async def test_janitor_reports_zero_when_nothing_stuck():
    fake_query = MagicMock()
    fake_query.to_list = AsyncMock(return_value=[])

    with patch("app.database.init_db", new=AsyncMock()), \
         patch("app.models.kb_optimization_run.KBOptimizationRun.find", return_value=fake_query):
        result = await kb_validation_tasks._kb_optimization_janitor_async()

    assert result == {"reaped": 0, "scanned": 0}


def test_janitor_task_is_in_beat_schedule_and_registered():
    """Sanity check: the task is wired up so beat will fire it hourly."""
    from app.celery_app import celery
    assert "tasks.passive.kb_optimization_janitor" in celery.tasks
    assert "kb-optimization-janitor" in celery.conf.beat_schedule


def test_orphan_age_is_2x_optimize_soft_time_limit():
    """Janitor cutoff must exceed the optimizer's own soft time limit so we
    never reap a legitimate Thorough-tier run mid-execution."""
    from app.tasks.kb_validation_tasks import optimize_kb_task
    soft_limit = optimize_kb_task.soft_time_limit
    assert kb_validation_tasks.ORPHAN_RUN_AGE_SECONDS >= 2 * soft_limit
