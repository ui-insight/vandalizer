"""Tests for the optimization orphan-run janitor (KB + workflow + extraction).

A hard-limit SIGKILL or worker death leaves a run at status="running" with no
handler ever finalizing it. The UI spins forever, and — worse — the start
paths 409 on any non-terminal run, so the subject is permanently blocked from
re-optimizing until someone edits the database. The janitor (and, for
workflows, the new reap-on-start sweep) is what breaks that deadlock.
"""

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
    # Explicit falsy values: on a bare MagicMock these attributes are truthy
    # mocks, which would silently route reap_one into the cancelled branch
    # and the revoke path.
    rd.cancel_requested = False
    rd.celery_task_id = None
    rd.save = AsyncMock()
    return rd


def _query(rows=()):
    q = MagicMock()
    q.to_list = AsyncMock(return_value=list(rows))
    return q


def _janitor_patches(kb=(), wf=(), ext=(), reap_one=None, wf_reap_one=None):
    return (
        patch("app.database.init_db", new=AsyncMock()),
        patch("app.models.kb_optimization_run.KBOptimizationRun.find", return_value=_query(kb)),
        patch(
            "app.models.workflow_optimization_run.WorkflowOptimizationRun.find",
            return_value=_query(wf),
        ),
        patch(
            "app.models.extraction_optimization_run.ExtractionOptimizationRun.find",
            return_value=_query(ext),
        ),
        patch(
            "app.services.extraction_optimizer.reap_one",
            new=reap_one or AsyncMock(side_effect=lambda r: r),
        ),
        patch(
            "app.services.workflow_optimizer.reap_one",
            new=wf_reap_one or AsyncMock(side_effect=lambda r: r),
        ),
    )


async def _run_janitor(**kwargs):
    patches = _janitor_patches(**kwargs)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        return await kb_validation_tasks._optimization_janitor_async()


@pytest.mark.asyncio
async def test_janitor_marks_abandoned_kb_runs_failed():
    """Runs in {queued, running} older than the 3-hour cutoff get reaped."""
    stuck1 = _make_stuck_run("opt-1", status="running", age_seconds=4 * 3600)
    stuck2 = _make_stuck_run("opt-2", status="queued", age_seconds=10 * 3600)

    result = await _run_janitor(kb=[stuck1, stuck2])

    assert result == {"reaped": 2, "scanned": 2}
    for r in (stuck1, stuck2):
        assert r.status == "failed"
        assert r.phase == "failed"
        assert "abandoned" in (r.error_message or "")
        assert r.completed_at is not None
        r.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_janitor_delegates_workflow_runs_to_workflow_reap_one():
    """WorkflowOptimizationRun had NO reaper at all: a hard-limit kill left it
    "running" forever, and start_workflow_optimization 409s on it with no
    sweep — permanently blocking re-optimization of that workflow. The
    janitor delegates to workflow_optimizer.reap_one (which also revokes the
    Celery task and honors a user cancel) so the finalization write exists in
    exactly one place."""
    stuck = _make_stuck_run("wf-1", status="running")

    async def _finalize(run):
        run.status = "failed"
        return run

    reap = AsyncMock(side_effect=_finalize)
    result = await _run_janitor(wf=[stuck], wf_reap_one=reap)

    reap.assert_awaited_once_with(stuck)
    assert result == {"reaped": 1, "scanned": 1}


@pytest.mark.asyncio
async def test_janitor_delegates_extraction_runs_to_reap_one():
    """Extraction runs carry a Celery task id and a cancel grace window;
    reap_one owns that logic (revoke + finalize), so the janitor must hand
    candidates to it rather than duplicate a simpler, wrong sweep."""
    candidate = _make_stuck_run("ext-1", status="running")
    reap_one = AsyncMock(side_effect=lambda r: r)

    result = await _run_janitor(ext=[candidate], reap_one=reap_one)

    reap_one.assert_awaited_once_with(candidate)
    # reap_one left it running (not actually stuck) -> scanned, not reaped.
    assert result == {"reaped": 0, "scanned": 1}


@pytest.mark.asyncio
async def test_janitor_counts_extraction_runs_reap_one_finalized():
    candidate = _make_stuck_run("ext-2", status="running")

    async def _finalize(run):
        run.status = "failed"
        return run

    result = await _run_janitor(ext=[candidate], reap_one=AsyncMock(side_effect=_finalize))
    assert result == {"reaped": 1, "scanned": 1}


@pytest.mark.asyncio
async def test_janitor_filter_uses_correct_cutoff_and_status_set():
    """Verify the Mongo query uses both the cutoff *and* status in {queued, running}."""
    captured: dict = {}

    def fake_find(filt):
        captured["filt"] = filt
        return _query()

    patches = _janitor_patches()
    with patches[0], patch(
        "app.models.kb_optimization_run.KBOptimizationRun.find", side_effect=fake_find,
    ), patches[2], patches[3], patches[4], patches[5]:
        await kb_validation_tasks._optimization_janitor_async()

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
    result = await _run_janitor()
    assert result == {"reaped": 0, "scanned": 0}


def test_janitor_task_is_in_beat_schedule_and_registered():
    """Sanity check: the task is wired up so beat will fire it hourly."""
    from app.celery_app import celery
    assert "tasks.passive.optimization_janitor" in celery.tasks
    assert "optimization-janitor" in celery.conf.beat_schedule


def test_orphan_age_is_2x_optimize_soft_time_limit():
    """Janitor cutoff must exceed the optimizers' own soft time limits so we
    never reap a legitimate Thorough-tier run mid-execution."""
    from app.tasks.kb_validation_tasks import optimize_kb_task
    from app.tasks.workflow_optimization_tasks import optimize_workflow_task

    assert kb_validation_tasks.ORPHAN_RUN_AGE_SECONDS >= 2 * optimize_kb_task.soft_time_limit
    assert kb_validation_tasks.ORPHAN_RUN_AGE_SECONDS >= optimize_workflow_task.time_limit


def test_workflow_stale_timeout_exceeds_the_task_hard_limit():
    """STALE_RUN_TIMEOUT_SECONDS hard-codes the task's time_limit + slack; if
    someone raises the task limit (e.g. a Thorough tier) without this
    constant, every near-limit run gets reaped while still executing. This
    assertion is what goes red."""
    from app.services import workflow_optimizer as wo
    from app.tasks.workflow_optimization_tasks import optimize_workflow_task

    assert wo.STALE_RUN_TIMEOUT_SECONDS >= optimize_workflow_task.time_limit


class TestWorkflowOptimizerReapOne:
    @pytest.mark.asyncio
    async def test_stale_run_is_finalized_as_failed_and_task_revoked(self):
        from app.services import workflow_optimizer as wo

        run = _make_stuck_run("wf-stale", age_seconds=wo.STALE_RUN_TIMEOUT_SECONDS + 60)
        with patch.object(wo, "_revoke_task") as revoke:
            out = await wo.reap_one(run)
        assert out.status == "failed"
        assert out.stopped_reason == "failed"
        assert "abandoned" in out.error_message
        # Without the revoke, a still-queued copy of the task later picks the
        # doc up, flips failed -> running, and runs concurrently with the
        # replacement run the reap unblocked.
        revoke.assert_called_once_with(run)
        run.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancelled_then_died_finalizes_as_cancelled_not_failed(self):
        """The user asked for the stop; the worker dying before its next
        cancel check must not turn that into a scary failure."""
        from app.services import workflow_optimizer as wo

        run = _make_stuck_run("wf-cancel", age_seconds=wo.STALE_RUN_TIMEOUT_SECONDS + 60)
        run.cancel_requested = True
        with patch.object(wo, "_revoke_task"):
            out = await wo.reap_one(run)
        assert out.status == "cancelled"
        assert out.stopped_reason == "cancelled"

    @pytest.mark.asyncio
    async def test_young_run_is_left_alone(self):
        from app.services import workflow_optimizer as wo

        run = _make_stuck_run("wf-young", age_seconds=60)
        out = await wo.reap_one(run)
        assert out.status == "running"
        run.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_terminal_run_is_untouched(self):
        from app.services import workflow_optimizer as wo

        run = _make_stuck_run("wf-done", status="completed", age_seconds=10 * 3600)
        out = await wo.reap_one(run)
        assert out.status == "completed"
        run.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_optimization_refuses_to_resurrect_a_terminal_run():
    """A task that sat queued long enough to be reaped must not pick its doc
    back up and flip failed -> running over the reaper's verdict."""
    from app.services import workflow_optimizer as wo

    run = _make_stuck_run("wf-reaped", status="failed")
    with patch(
        "app.models.workflow_optimization_run.WorkflowOptimizationRun.find_one",
        new=AsyncMock(return_value=run),
    ), patch.object(wo, "_update", new=AsyncMock()) as update:
        out = await wo.run_optimization("wf-1", "user-1", "wf-reaped")

    assert out is run
    assert out.status == "failed"
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_workflow_optimization_reaps_before_the_active_check():
    """The active-run 409 with no preceding sweep is what turned a dead run
    into a permanent block; the start endpoint must sweep first, the way
    the extraction start path does. Even when the 409 still fires (a
    genuinely active run), the sweep must already have run."""
    import secrets

    from httpx import ASGITransport, AsyncClient

    from app.config import Settings
    from app.utils.security import create_access_token

    settings = Settings(jwt_secret_key="test-secret-key", environment="development")
    token = create_access_token("testuser", settings)
    csrf = secrets.token_urlsafe(32)
    cookies = {"access_token": token, "csrf_token": csrf}
    headers = {"X-CSRF-Token": csrf}

    user = MagicMock()
    user.user_id = "testuser"
    user.is_admin = False
    user.token_version = 0
    user.is_demo_user = False
    user.demo_status = None

    wf = MagicMock()
    wf.id = "wf-1"
    wf.validation_plan = [{"id": "c1", "category": "content"}]

    active = MagicMock()
    active.uuid = "stuck-run"
    # The whole class is replaced (not just find_one): without init_beanie,
    # touching WorkflowOptimizationRun.workflow_id as a query field raises.
    model_cls = MagicMock()
    model_cls.workflow_id = "workflow_id"
    model_cls.find_one = AsyncMock(return_value=active)

    reap = AsyncMock()
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.get_authorized_workflow", AsyncMock(return_value=wf)), \
             patch("app.services.workflow_optimizer._resolve_test_inputs", AsyncMock(return_value=[{"i": 1}])), \
             patch("app.services.workflow_optimizer.reap_stale_runs", new=reap), \
             patch(
                 "app.models.workflow_optimization_run.WorkflowOptimizationRun",
                 new=model_cls,
             ):
            MockUser.find_one = AsyncMock(return_value=user)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/workflows/wf-1/optimize", json={},
                    cookies=cookies, headers=headers,
                )

    assert resp.status_code == 409
    reap.assert_awaited_once_with("wf-1")
