"""Tests for GET /api/admin/optimizer/activity — the read-only operator view
of every optimizer run, which is what makes silent tuning failures visible.
"""

import datetime
import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token


_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")
_NOW = datetime.datetime(2026, 7, 20, 12, 0, tzinfo=datetime.timezone.utc)
_WF_ID = "507f1f77bcf86cd799439011"


def _make_user(user_id="admin1", *, is_admin=True, is_staff=False):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Admin User"
    user.is_admin = is_admin
    user.is_staff = is_staff
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.token_version = 0
    user.demo_status = None
    user.api_token_hash = None
    user.api_token_created_at = None
    user.api_token_expires_at = None
    return user


def _auth(user_id="admin1"):
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


def _run(**overrides):
    base = dict(
        uuid="run-1",
        status="completed",
        user_id="user1",
        started_at=_NOW,
        completed_at=_NOW,
        optimized_score=0.82,
        baseline_default_score=0.70,
        options={},
        tied_with_baseline=False,
        best_config={"model": "m"},
        dismissed_at=None,
        applied_at=None,
        reverted_at=None,
        previous_override=None,
        error_message=None,
        error_code=None,
        stopped_reason="all_trials_complete",
        phase="done",
        progress_message="",
        tokens_used=1500,
        token_budget=200000,
        actual_cost_usd=0.4,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _find_chain(items):
    chain = MagicMock()
    chain.sort.return_value = chain
    chain.limit.return_value = chain
    chain.to_list = AsyncMock(return_value=items)
    return chain


class _AdminHarness:
    def __init__(self, *, kb=(), extraction=(), workflow=(), kbs=None, sets=None,
                 workflows=None, is_admin=True, is_staff=False):
        self.kb, self.extraction, self.workflow = list(kb), list(extraction), list(workflow)
        self.kbs = [SimpleNamespace(uuid="kb-1", title="Compliance KB")] if kbs is None else kbs
        self.sets = [] if sets is None else sets
        self.workflows = (
            [SimpleNamespace(id=_WF_ID, name="Proposal intake", config_override=None,
                             config_override_set_at=None)]
            if workflows is None else workflows
        )
        self.is_admin, self.is_staff = is_admin, is_staff
        self._stack = []

    def __enter__(self):
        user = _make_user(is_admin=self.is_admin, is_staff=self.is_staff)
        MockKB, MockEx, MockWf = MagicMock(), MagicMock(), MagicMock()
        MockKB.find = MagicMock(return_value=_find_chain(self.kb))
        MockEx.find = MagicMock(return_value=_find_chain(self.extraction))
        MockWf.find = MagicMock(return_value=_find_chain(self.workflow))
        self.MockKB, self.MockEx, self.MockWf = MockKB, MockEx, MockWf

        MockKBModel, MockSetModel, MockWfModel = MagicMock(), MagicMock(), MagicMock()
        MockKBModel.find = MagicMock(return_value=_find_chain(self.kbs))
        MockSetModel.find = MagicMock(return_value=_find_chain(self.sets))
        MockWfModel.find = MagicMock(return_value=_find_chain(self.workflows))

        patches = [
            patch("app.dependencies.decode_token", return_value={"sub": "admin1", "type": "access"}),
            patch("app.dependencies.User"),
            patch("app.models.kb_optimization_run.KBOptimizationRun", MockKB),
            patch("app.models.extraction_optimization_run.ExtractionOptimizationRun", MockEx),
            patch("app.models.workflow_optimization_run.WorkflowOptimizationRun", MockWf),
            patch("app.models.knowledge.KnowledgeBase", MockKBModel),
            patch("app.models.search_set.SearchSet", MockSetModel),
            patch("app.models.workflow.Workflow", MockWfModel),
            patch("app.routers.admin.User"),
        ]
        entered = [p.__enter__() for p in patches]
        self._stack = patches
        entered[1].find_one = AsyncMock(return_value=user)
        # Owner-email lookup inside the endpoint.
        entered[-1].find = MagicMock(
            return_value=_find_chain([SimpleNamespace(user_id="user1", email="user1@example.com")]),
        )
        return self

    def __exit__(self, *exc):
        for p in reversed(self._stack):
            p.__exit__(*exc)
        return False


class TestOptimizerActivity:
    @pytest.mark.asyncio
    async def test_non_admin_is_forbidden(self, client):
        cookies, headers = _auth()
        with _AdminHarness(is_admin=False):
            resp = await client.get(
                "/api/admin/optimizer/activity", cookies=cookies, headers=headers,
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_staff_can_read(self, client):
        cookies, headers = _auth()
        with _AdminHarness(is_admin=False, is_staff=True):
            resp = await client.get(
                "/api/admin/optimizer/activity", cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_failures_are_rolled_up_by_reason(self, client):
        cookies, headers = _auth()
        runs = [
            _run(uuid="a", kb_uuid="kb-1", status="failed",
                 error_code="judge_unavailable", error_message="judge down"),
            _run(uuid="b", kb_uuid="kb-1", status="failed",
                 error_code="judge_unavailable", error_message="judge down again"),
            _run(uuid="c", kb_uuid="kb-1", status="failed",
                 error_code=None, error_message="Something else entirely"),
        ]
        with _AdminHarness(kb=runs):
            resp = await client.get(
                "/api/admin/optimizer/activity", cookies=cookies, headers=headers,
            )

        summary = resp.json()["summary"]
        assert summary["failed"] == 3
        assert summary["failure_reasons"][0] == {"reason": "judge_unavailable", "count": 2}
        assert {"reason": "Something else entirely", "count": 1} in summary["failure_reasons"]

    @pytest.mark.asyncio
    async def test_pending_review_counts_unactioned_candidates(self, client):
        cookies, headers = _auth()
        runs = [
            # Reviewable: completed, has a config, nobody applied or dismissed it.
            _run(uuid="a", kb_uuid="kb-1"),
            # Tied with baseline — nothing to promote.
            _run(uuid="b", kb_uuid="kb-1", tied_with_baseline=True),
            # Already applied and live.
            _run(uuid="c", kb_uuid="kb-1", applied_at=_NOW),
            # Dismissed by its owner.
            _run(uuid="d", kb_uuid="kb-1", dismissed_at=_NOW),
        ]
        with _AdminHarness(kb=runs):
            resp = await client.get(
                "/api/admin/optimizer/activity", cookies=cookies, headers=headers,
            )

        summary = resp.json()["summary"]
        assert summary["total"] == 4
        assert summary["pending_review"] == 1
        assert summary["applied"] == 1
        assert summary["dismissed"] == 1

    @pytest.mark.asyncio
    async def test_rows_carry_owner_and_item_name(self, client):
        cookies, headers = _auth()
        run = _run(uuid="wf-a", workflow_id=_WF_ID,
                   options={"shadow_trigger": "quality_alert"})
        with _AdminHarness(workflow=[run]):
            resp = await client.get(
                "/api/admin/optimizer/activity", cookies=cookies, headers=headers,
            )

        row = resp.json()["runs"][0]
        assert row["item_name"] == "Proposal intake"
        assert row["item_deleted"] is False
        assert row["user_email"] == "user1@example.com"
        assert row["trigger"] == "quality_alert"
        assert resp.json()["summary"]["auto_triggered"] == 1
        assert resp.json()["summary"]["user_launched"] == 0

    @pytest.mark.asyncio
    async def test_deleted_item_is_flagged_not_dropped(self, client):
        cookies, headers = _auth()
        run = _run(uuid="kb-a", kb_uuid="kb-gone")
        with _AdminHarness(kb=[run], kbs=[]):
            resp = await client.get(
                "/api/admin/optimizer/activity", cookies=cookies, headers=headers,
            )

        row = resp.json()["runs"][0]
        assert row["item_deleted"] is True
        assert row["item_name"] is None

    @pytest.mark.asyncio
    async def test_surface_filter_skips_other_collections(self, client):
        cookies, headers = _auth()
        with _AdminHarness() as h:
            resp = await client.get(
                "/api/admin/optimizer/activity?surface=kb", cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        h.MockKB.find.assert_called_once()
        h.MockEx.find.assert_not_called()
        h.MockWf.find.assert_not_called()

    @pytest.mark.asyncio
    async def test_bogus_surface_is_rejected(self, client):
        cookies, headers = _auth()
        with _AdminHarness():
            resp = await client.get(
                "/api/admin/optimizer/activity?surface=nope", cookies=cookies, headers=headers,
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_trigger_filter_shapes_the_query(self, client):
        cookies, headers = _auth()
        with _AdminHarness() as h:
            await client.get(
                "/api/admin/optimizer/activity?trigger=auto", cookies=cookies, headers=headers,
            )
            auto_query = h.MockKB.find.call_args.args[0]
        assert auto_query["options.shadow_trigger"] == {"$exists": True}

        with _AdminHarness() as h:
            await client.get(
                "/api/admin/optimizer/activity?trigger=user", cookies=cookies, headers=headers,
            )
            user_query = h.MockKB.find.call_args.args[0]
        assert user_query["options.shadow_trigger"] == {"$exists": False}

    @pytest.mark.asyncio
    async def test_status_filter_is_passed_through(self, client):
        cookies, headers = _auth()
        with _AdminHarness() as h:
            await client.get(
                "/api/admin/optimizer/activity?status=failed", cookies=cookies, headers=headers,
            )
            query = h.MockKB.find.call_args.args[0]
        assert query["status"] == "failed"
