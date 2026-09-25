"""Orphaned optimization runs heal on start and on read, in every collection (#835).

A worker SIGKILLed at its hard time limit leaves a run at status="running"
with nothing to finalize it. Extraction already swept orphans before its
active-run 409 and from its read endpoints; workflow swept on start only; KB
did neither and had no reaper outside the hourly janitor. These tests pin the
parity: the KB start path sweeps first, and the workflow and KB read
endpoints call ``reap_one`` so a dead run stops spinning on the next poll.
"""

from __future__ import annotations

import datetime
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token


def _make_run(uuid="opt-1", status="running", age_seconds=4 * 3600, cancel_requested=False):
    rd = MagicMock()
    rd.uuid = uuid
    rd.status = status
    rd.phase = status
    rd.started_at = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(
        seconds=age_seconds,
    )
    rd.completed_at = None
    rd.error_message = None
    rd.cancel_requested = cancel_requested
    rd.save = AsyncMock()
    return rd


# ---------------------------------------------------------------------------
# kb_optimizer.reap_one -- the KB collection's first on-demand reaper
# ---------------------------------------------------------------------------


class TestKbReapOne:
    @pytest.mark.asyncio
    async def test_stuck_run_is_finalized_failed(self):
        from app.services import kb_optimizer as ko

        run = _make_run(age_seconds=ko.STALE_RUN_TIMEOUT_SECONDS + 60)
        out = await ko.reap_one(run)

        assert out.status == "failed"
        assert out.phase == "failed"
        assert "abandoned" in out.error_message
        assert out.completed_at is not None
        run.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_requested_cancel_is_honoured_not_reported_as_failure(self):
        from app.services import kb_optimizer as ko

        run = _make_run(age_seconds=ko.STALE_RUN_TIMEOUT_SECONDS + 60, cancel_requested=True)
        out = await ko.reap_one(run)

        assert out.status == "cancelled"
        assert out.error_message is None
        run.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_run_still_inside_the_time_limit_is_untouched(self):
        from app.services import kb_optimizer as ko

        run = _make_run(age_seconds=ko.STALE_RUN_TIMEOUT_SECONDS - 60)
        out = await ko.reap_one(run)

        assert out.status == "running"
        run.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_terminal_and_missing_runs_are_untouched(self):
        from app.services import kb_optimizer as ko

        done = _make_run(status="completed", age_seconds=10 * 3600)
        assert (await ko.reap_one(done)).status == "completed"
        done.save.assert_not_awaited()
        assert await ko.reap_one(None) is None

    @pytest.mark.asyncio
    async def test_naive_started_at_is_treated_as_utc(self):
        from app.services import kb_optimizer as ko

        run = _make_run(age_seconds=ko.STALE_RUN_TIMEOUT_SECONDS + 60)
        run.started_at = run.started_at.replace(tzinfo=None)
        out = await ko.reap_one(run)
        assert out.status == "failed"

    @pytest.mark.asyncio
    async def test_reap_stale_runs_sweeps_every_active_run_for_the_kb(self):
        from app.services import kb_optimizer as ko

        a, b = _make_run("a"), _make_run("b")
        query = MagicMock()
        query.to_list = AsyncMock(return_value=[a, b])
        model_cls = MagicMock()
        model_cls.kb_uuid = "kb_uuid"
        model_cls.find.return_value = query
        with patch.object(ko, "KBOptimizationRun", model_cls), \
             patch.object(ko, "reap_one", new=AsyncMock(side_effect=lambda r: r)) as reap:
            await ko.reap_stale_runs("kb-1")
        assert [c.args[0] for c in reap.await_args_list] == [a, b]


# ---------------------------------------------------------------------------
# HTTP: start sweeps first; reads heal
# ---------------------------------------------------------------------------


def _auth():
    settings = Settings(jwt_secret_key="test-secret-key", environment="development")
    token = create_access_token("testuser", settings)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


def _user():
    user = MagicMock()
    user.user_id = "testuser"
    user.is_admin = False
    user.token_version = 0
    user.is_demo_user = False
    user.demo_status = None
    return user


def _model_cls(field: str, find_one_returns):
    # The whole class is replaced: without init_beanie, touching a query
    # field on the real Document class raises.
    cls = MagicMock()
    setattr(cls, field, field)
    cls.uuid = "uuid"
    cls.find_one = AsyncMock(return_value=find_one_returns)
    return cls


def _reaper(finalize: bool):
    async def _reap(run):
        if finalize and run is not None:
            run.status = "failed"
        return run
    return AsyncMock(side_effect=_reap)


async def _get(path: str, patches: list):
    cookies, headers = _auth()
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=_user())
            for p in patches:
                p.start()
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    return await client.get(path, cookies=cookies, headers=headers)
            finally:
                for p in reversed(patches):
                    p.stop()


class TestKbStartSweepsFirst:
    @pytest.mark.asyncio
    async def test_start_kb_optimization_reaps_before_the_active_check(self):
        """Even when the 409 still fires (a genuinely active run), the sweep
        must already have run -- same contract the workflow start has."""
        cookies, headers = _auth()
        kb = MagicMock()
        kb.uuid = "kb-1"
        active = MagicMock()
        active.uuid = "stuck-run"
        reap = AsyncMock()

        # The endpoint is rate-limited per address; other files in the same
        # process hit it first, so the limiter is off for this one call.
        from app.rate_limit import limiter

        limiter.enabled = False
        try:
            resp = await self._post(cookies, headers, kb, active, reap)
        finally:
            limiter.enabled = True

        assert resp.status_code == 409
        reap.assert_awaited_once_with("kb-1")

    async def _post(self, cookies, headers, kb, active, reap):
        with patch("app.main.init_db", new_callable=AsyncMock):
            from app.main import app

            with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
                 patch("app.dependencies.User") as MockUser, \
                 patch("app.routers.knowledge.organization_service.get_user_org_ancestry", AsyncMock(return_value=[])), \
                 patch("app.routers.knowledge._require_manageable_kb", AsyncMock(return_value=kb)), \
                 patch("app.services.kb_optimizer.reap_stale_runs", new=reap), \
                 patch("app.services.optimization_governance.enforce_and_record_start", new=AsyncMock()), \
                 patch("app.models.kb_optimization_run.KBOptimizationRun", new=_model_cls("kb_uuid", active)):
                MockUser.find_one = AsyncMock(return_value=_user())
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    return await client.post(
                        "/api/knowledge/kb-1/optimize", json={"token_budget": 1000},
                        cookies=cookies, headers=headers,
                    )


class TestWorkflowReadsHeal:
    def _patches(self, run, reap):
        wf = MagicMock()
        wf.id = "wf-1"
        return [
            patch("app.routers.workflows.get_authorized_workflow", AsyncMock(return_value=wf)),
            patch("app.models.workflow_optimization_run.WorkflowOptimizationRun", new=_model_cls("workflow_id", run)),
            patch("app.services.workflow_optimizer.reap_one", new=reap),
            patch("app.routers.workflows._serialize_workflow_optimization_run",
                  side_effect=lambda r: {"uuid": r.uuid, "status": r.status}),
        ]

    @pytest.mark.asyncio
    async def test_active_poll_reports_no_run_once_reaped(self):
        run = _make_run("stuck")
        reap = _reaper(finalize=True)
        resp = await _get("/api/workflows/wf-1/optimize/active", self._patches(run, reap))
        assert resp.status_code == 200
        assert resp.json() == {"run": None}
        reap.assert_awaited_once_with(run)

    @pytest.mark.asyncio
    async def test_active_poll_keeps_a_live_run(self):
        run = _make_run("live")
        resp = await _get("/api/workflows/wf-1/optimize/active", self._patches(run, _reaper(finalize=False)))
        assert resp.json()["run"]["status"] == "running"

    @pytest.mark.asyncio
    async def test_status_poll_returns_the_healed_run(self):
        run = _make_run("stuck")
        reap = _reaper(finalize=True)
        resp = await _get("/api/workflows/wf-1/optimize/stuck", self._patches(run, reap))
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"
        reap.assert_awaited_once_with(run)


class TestKbReadsHeal:
    def _patches(self, run, reap):
        kb = MagicMock()
        kb.uuid = "kb-1"
        return [
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", AsyncMock(return_value=[])),
            patch("app.routers.knowledge.svc.get_knowledge_base", AsyncMock(return_value=kb)),
            patch("app.models.kb_optimization_run.KBOptimizationRun", new=_model_cls("kb_uuid", run)),
            patch("app.services.kb_optimizer.reap_one", new=reap),
            patch("app.routers.knowledge._serialize_optimization_run",
                  side_effect=lambda r: {"uuid": r.uuid, "status": r.status}),
        ]

    @pytest.mark.asyncio
    async def test_active_poll_reports_no_run_once_reaped(self):
        run = _make_run("stuck")
        reap = _reaper(finalize=True)
        resp = await _get("/api/knowledge/kb-1/optimize/active", self._patches(run, reap))
        assert resp.status_code == 200
        assert resp.json() == {"run": None}
        reap.assert_awaited_once_with(run)

    @pytest.mark.asyncio
    async def test_status_poll_returns_the_healed_run(self):
        run = _make_run("stuck")
        reap = _reaper(finalize=True)
        resp = await _get("/api/knowledge/kb-1/optimize/stuck", self._patches(run, reap))
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"
        reap.assert_awaited_once_with(run)


# ---------------------------------------------------------------------------
# Janitor: KB runs go through the same reaper as the on-demand paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_janitor_delegates_kb_runs_to_kb_reap_one():
    from app.tasks import kb_validation_tasks

    stuck = _make_run("kb-stuck")
    reap = _reaper(finalize=True)
    empty = MagicMock()
    empty.to_list = AsyncMock(return_value=[])
    kb_query = MagicMock()
    kb_query.to_list = AsyncMock(return_value=[stuck])

    with patch("app.database.init_db", new=AsyncMock()), \
         patch("app.models.kb_optimization_run.KBOptimizationRun.find", return_value=kb_query), \
         patch("app.models.workflow_optimization_run.WorkflowOptimizationRun.find", return_value=empty), \
         patch("app.models.extraction_optimization_run.ExtractionOptimizationRun.find", return_value=empty), \
         patch("app.services.kb_optimizer.reap_one", new=reap):
        result = await kb_validation_tasks._optimization_janitor_async()

    reap.assert_awaited_once_with(stuck)
    assert result == {"reaped": 1, "scanned": 1}
