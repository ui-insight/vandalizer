"""Integration tests for the KB Autovalidate optimizer routes.

Covers POST /optimize (incl. validation, 409 active-run conflict),
GET /optimize/active, GET /optimize/{run_uuid} (incl. cross-KB lookup
rejection), POST cancel, POST apply (incl. status guard).
"""

import datetime
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token


_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="user1"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.demo_status = None
    user.api_token_hash = None
    user.api_token_created_at = None
    user.api_token_expires_at = None
    return user


def _auth(user_id="user1"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


def _stub_kb(uuid="kb-1"):
    kb = MagicMock()
    kb.uuid = uuid
    kb.user_id = "user1"
    return kb


def _stub_run(*, uuid="opt-1", kb_uuid="kb-1", status="completed", best_config=None,
              started_at=None, completed_at=None):
    run = MagicMock()
    run.uuid = uuid
    run.kb_uuid = kb_uuid
    run.status = status
    run.phase = status
    run.progress_message = "ok"
    run.current_trial_index = 0
    run.total_trials_planned = 0
    run.best_score_so_far = None
    run.best_config_so_far = None
    run.token_budget = 1_000_000
    run.tokens_used = 0
    run.estimated_cost_usd = None
    run.actual_cost_usd = None
    run.baseline_no_kb_score = 0.3
    run.baseline_default_score = 0.6
    run.optimized_score = 0.85
    run.judge_variance = 0.04
    run.judge_model = "test-model"
    run.best_config = best_config
    run.trials = []
    run.data_source_suggestions = []
    run.options = {}
    run.error_message = None
    run.started_at = started_at or datetime.datetime.now(datetime.timezone.utc)
    run.completed_at = completed_at
    run.cancel_requested = False
    run.save = AsyncMock()
    return run


# ---------------------------------------------------------------------------
# POST /optimize
# ---------------------------------------------------------------------------


class TestStartOptimization:
    @pytest.mark.asyncio
    async def test_happy_path_returns_run_uuid_and_queues_task(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()

        fake_task = MagicMock(); fake_task.delay = MagicMock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
            patch("app.services.optimization_governance.enforce_and_record_start", new=AsyncMock()),
            patch("app.tasks.kb_validation_tasks.optimize_kb_task", fake_task),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=None)  # no active run
            instance = _stub_run(uuid="opt-new")
            instance.insert = AsyncMock()
            MockRun.return_value = instance
            resp = await client.post(
                "/api/knowledge/kb-1/optimize",
                json={"token_budget": 500_000, "apply_on_finish": False},
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert "run_uuid" in body and body["run_uuid"]
        # Celery task was kicked off with the right inputs.
        fake_task.delay.assert_called_once()
        args = fake_task.delay.call_args.args
        # (kb_uuid, user_id, run_uuid, token_budget, include_indexing_track, apply_on_finish)
        assert args[0] == "kb-1"
        assert args[3] == 500_000

    @pytest.mark.asyncio
    async def test_rejects_missing_token_budget(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/knowledge/kb-1/optimize", json={},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 400
        assert "token_budget" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_rejects_zero_or_negative_budget(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            for budget in (0, -100):
                resp = await client.post(
                    "/api/knowledge/kb-1/optimize",
                    json={"token_budget": budget},
                    cookies=cookies, headers=headers,
                )
                assert resp.status_code == 400, f"budget={budget} should 400"

    @pytest.mark.asyncio
    async def test_returns_409_when_active_run_exists(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        active = _stub_run(uuid="opt-active", status="running")

        fake_task = MagicMock(); fake_task.delay = MagicMock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
            patch("app.tasks.kb_validation_tasks.optimize_kb_task", fake_task),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=active)
            resp = await client.post(
                "/api/knowledge/kb-1/optimize",
                json={"token_budget": 500_000},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 409
        assert "opt-active" in resp.json()["detail"]
        fake_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_404_when_kb_missing(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=None),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/knowledge/missing/optimize",
                json={"token_budget": 500_000},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /optimize/active and /optimize/{run_uuid}
# ---------------------------------------------------------------------------


class TestGetOptimization:
    @pytest.mark.asyncio
    async def test_active_returns_run_when_running(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        active = _stub_run(status="running")
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=active)
            resp = await client.get("/api/knowledge/kb-1/optimize/active", cookies=cookies, headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["run"] is not None
        assert body["run"]["status"] == "running"
        assert body["run"]["uuid"] == "opt-1"

    @pytest.mark.asyncio
    async def test_active_returns_null_when_no_active_run(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=None)
            resp = await client.get("/api/knowledge/kb-1/optimize/active", cookies=cookies, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"run": None}

    @pytest.mark.asyncio
    async def test_get_run_404s_on_cross_kb_lookup(self, client):
        """A run UUID that doesn't belong to this KB must 404 (no info leak)."""
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb(uuid="kb-1")
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=None)
            resp = await client.get(
                "/api/knowledge/kb-1/optimize/foreign-run-uuid",
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Optimization run not found"


# ---------------------------------------------------------------------------
# POST /optimize/{run_uuid}/cancel
# ---------------------------------------------------------------------------


class TestCancelOptimization:
    @pytest.mark.asyncio
    async def test_cancel_flips_flag(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        run = _stub_run(status="running")
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=run)
            resp = await client.post(
                "/api/knowledge/kb-1/optimize/opt-1/cancel",
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancel_requested"
        assert run.cancel_requested is True
        run.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_is_noop_when_run_already_terminal(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        run = _stub_run(status="completed")
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=run)
            resp = await client.post(
                "/api/knowledge/kb-1/optimize/opt-1/cancel",
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert "not running" in body.get("note", "")
        run.save.assert_not_awaited()


# ---------------------------------------------------------------------------
# POST /optimize/{run_uuid}/apply
# ---------------------------------------------------------------------------


class TestApplyOptimization:
    @pytest.mark.asyncio
    async def test_apply_writes_override_to_kb(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        kb.save = AsyncMock()
        kb.rag_config_override = None
        winning = {"k": 12, "model": "claude-haiku-4-5", "prompt_variant": "strict",
                   "query_rewriting": True, "source_label_visibility": True}
        run = _stub_run(status="completed", best_config=winning)
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=run)
            resp = await client.post(
                "/api/knowledge/kb-1/optimize/opt-1/apply",
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["applied_config"]["k"] == 12
        # KB was mutated and saved.
        assert kb.rag_config_override == winning
        assert kb.rag_config_override_run_uuid == "opt-1"
        kb.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_apply_400s_when_run_not_completed(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        run = _stub_run(status="running", best_config={"k": 10})
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=run)
            resp = await client.post(
                "/api/knowledge/kb-1/optimize/opt-1/apply",
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 400
        assert "running" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_history_returns_summaries_newest_first(self, client):
        """List route paginates and returns compact summaries (no full trials)."""
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        runs = [
            _stub_run(uuid=f"opt-{i}", status="completed",
                      best_config={"k": 8 + i})
            for i in range(3)
        ]
        # Make sort/skip/limit chain work on the query mock.
        chained = MagicMock()
        chained.sort = MagicMock(return_value=chained)
        chained.skip = MagicMock(return_value=chained)
        chained.limit = MagicMock(return_value=chained)
        chained.to_list = AsyncMock(return_value=runs)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find = MagicMock(return_value=chained)
            resp = await client.get(
                "/api/knowledge/kb-1/optimize",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 3
        # Confirm the chain was called with newest-first sort.
        chained.sort.assert_called_once_with("-started_at")
        # Summaries don't include the full trial bodies.
        for item in body["items"]:
            assert "trials" not in item
            assert "num_trials" in item
            assert "best_config" in item

    @pytest.mark.asyncio
    async def test_history_pagination_params_flow_through(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        chained = MagicMock()
        chained.sort = MagicMock(return_value=chained)
        chained.skip = MagicMock(return_value=chained)
        chained.limit = MagicMock(return_value=chained)
        chained.to_list = AsyncMock(return_value=[])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find = MagicMock(return_value=chained)
            resp = await client.get(
                "/api/knowledge/kb-1/optimize?limit=5&skip=10",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        chained.skip.assert_called_once_with(10)
        chained.limit.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_history_404_when_kb_missing(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=None),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get(
                "/api/knowledge/missing/optimize",
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 404


class TestListOptimizationHistory:
    """Group marker for the three history tests inserted above. The actual
    tests live inside TestApplyOptimization for historical reasons (the
    initial sed-driven refactor inserted them there); pytest collects them
    regardless of the parent class name."""
    pass


class TestApplyOptimizationEdgeCases:
    @pytest.mark.asyncio
    async def test_apply_400s_when_no_best_config(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        kb = _stub_kb()
        run = _stub_run(status="completed", best_config=None)
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.organization_service.get_user_org_ancestry", new_callable=AsyncMock),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.models.kb_optimization_run.KBOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=run)
            resp = await client.post(
                "/api/knowledge/kb-1/optimize/opt-1/apply",
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 400
        assert "best_config" in resp.json()["detail"]
