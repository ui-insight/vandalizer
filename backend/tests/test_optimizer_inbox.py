"""Tests for the optimizer inbox — the triage surface for auto-generated
tuning suggestions and failed tuning runs.

Covers GET /inbox (access scoping, categorization, item names, failure
surfacing, dismissed filtering), GET /inbox/count, and the dismiss/restore
endpoints including the manage-rights gate.
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


def _make_user(user_id="user1"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_staff = False
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.token_version = 0
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


def _run(**overrides):
    """A run document stand-in.

    ``SimpleNamespace`` rather than ``MagicMock`` on purpose: the router makes
    boolean decisions on these fields, and every MagicMock attribute is truthy.
    """
    base = dict(
        uuid="run-1",
        status="completed",
        started_at=_NOW,
        completed_at=_NOW,
        optimized_score=0.82,
        baseline_default_score=0.70,
        options={"shadow_trigger": "quality_alert", "shadow_trigger_detail": {"severity": "high"}},
        tied_with_baseline=False,
        best_config={"step_overrides": {"s1": {"model": "m"}}},
        apply_preview={"total": 4, "will_change": 2, "regressions": 0, "items": []},
        suggestions=[],
        dismissed_at=None,
        dismissed_by=None,
        applied_at=None,
        reverted_at=None,
        previous_override=None,
        error_message=None,
        error_code=None,
        error_context=None,
        stopped_reason=None,
        phase="done",
        progress_message="",
        judge_model="judge-1",
        overfitting_warning=False,
        tokens_used=1000,
        token_budget=200000,
    )
    base.update(overrides)
    ns = SimpleNamespace(**base)
    ns.save = AsyncMock()
    return ns


def _find_chain(items):
    chain = MagicMock()
    chain.sort.return_value = chain
    chain.limit.return_value = chain
    chain.to_list = AsyncMock(return_value=items)
    return chain


class _InboxHarness:
    """Context manager stacking every patch the inbox endpoints need."""

    def __init__(self, *, kb=(), extraction=(), workflow=(), authorized=True, can_manage=True,
                 kb_doc=None, ss_doc=None, wf_doc=None):
        self.kb, self.extraction, self.workflow = list(kb), list(extraction), list(workflow)
        self.authorized = authorized
        self.can_manage = can_manage
        self.kb_doc = kb_doc or SimpleNamespace(title="Compliance KB", uuid="kb-1")
        self.ss_doc = ss_doc or SimpleNamespace(
            title="Budget fields", uuid="ss-1",
            extraction_config_override=None, extraction_config_override_set_at=None,
        )
        self.wf_doc = wf_doc or SimpleNamespace(
            name="Proposal intake", config_override=None, config_override_set_at=None,
        )
        self._stack = []

    def _authorized(self, doc):
        async def _impl(*_args, manage=False, **_kwargs):
            if not self.authorized:
                return None
            if manage and not self.can_manage:
                return None
            return doc
        return _impl

    def __enter__(self):
        user = _make_user("user1")
        patches = [
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User"),
            patch("app.routers.optimizer_inbox.KBOptimizationRun"),
            patch("app.routers.optimizer_inbox.ExtractionOptimizationRun"),
            patch("app.routers.optimizer_inbox.WorkflowOptimizationRun"),
            patch("app.routers.optimizer_inbox.access_control.get_team_access_context",
                  new_callable=AsyncMock, return_value=MagicMock()),
            patch("app.routers.optimizer_inbox.organization_service.get_user_org_ancestry",
                  new_callable=AsyncMock, return_value=[]),
            patch("app.routers.optimizer_inbox.access_control.get_authorized_knowledge_base",
                  new=self._authorized(self.kb_doc)),
            patch("app.routers.optimizer_inbox.access_control.get_authorized_search_set",
                  new=self._authorized(self.ss_doc)),
            patch("app.routers.optimizer_inbox.access_control.get_authorized_workflow",
                  new=self._authorized(self.wf_doc)),
        ]
        entered = [p.__enter__() for p in patches]
        self._stack = patches
        entered[1].find_one = AsyncMock(return_value=user)
        self.MockKB, self.MockEx, self.MockWf = entered[2], entered[3], entered[4]
        self.MockKB.find = MagicMock(return_value=_find_chain(self.kb))
        self.MockEx.find = MagicMock(return_value=_find_chain(self.extraction))
        self.MockWf.find = MagicMock(return_value=_find_chain(self.workflow))
        self.MockKB.find_one = AsyncMock(return_value=self.kb[0] if self.kb else None)
        self.MockEx.find_one = AsyncMock(return_value=self.extraction[0] if self.extraction else None)
        self.MockWf.find_one = AsyncMock(return_value=self.workflow[0] if self.workflow else None)
        return self

    def __exit__(self, *exc):
        for p in reversed(self._stack):
            p.__exit__(*exc)
        return False


# ---------------------------------------------------------------------------
# GET /inbox
# ---------------------------------------------------------------------------


class TestListInbox:
    @pytest.mark.asyncio
    async def test_completed_shadow_run_is_a_reviewable_candidate(self, client):
        cookies, headers = _auth()
        run = _run(uuid="wf-run", workflow_id="507f1f77bcf86cd799439011")
        with _InboxHarness(workflow=[run]):
            resp = await client.get("/api/optimizer/inbox", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["surface"] == "workflow"
        assert item["category"] == "needs_review"
        # The name is the point — an item_id alone is unreadable in a UI.
        assert item["item_name"] == "Proposal intake"
        assert item["trigger"] == "quality_alert"
        assert item["can_manage"] is True
        assert item["link"] == "/?workflow=507f1f77bcf86cd799439011"
        assert body["counts"]["needs_review"] == 1
        # Legacy alias preserved for the original client contract.
        assert body["counts"]["pending_review"] == 1

    @pytest.mark.asyncio
    async def test_runs_for_inaccessible_items_are_hidden(self, client):
        cookies, headers = _auth()
        run = _run(uuid="wf-run", workflow_id="507f1f77bcf86cd799439011")
        with _InboxHarness(workflow=[run], authorized=False):
            resp = await client.get("/api/optimizer/inbox", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_view_only_access_shows_row_without_manage_rights(self, client):
        cookies, headers = _auth()
        run = _run(uuid="wf-run", workflow_id="507f1f77bcf86cd799439011")
        with _InboxHarness(workflow=[run], can_manage=False):
            resp = await client.get("/api/optimizer/inbox", cookies=cookies, headers=headers)

        item = resp.json()["items"][0]
        assert item["can_manage"] is False

    @pytest.mark.asyncio
    async def test_failed_run_surfaces_its_error(self, client):
        cookies, headers = _auth()
        run = _run(
            uuid="kb-run", kb_uuid="kb-1", status="failed",
            error_message="Judge model unavailable", error_code="judge_unavailable",
            optimized_score=None, best_config=None, options={},
        )
        with _InboxHarness(kb=[run]):
            resp = await client.get("/api/optimizer/inbox", cookies=cookies, headers=headers)

        item = resp.json()["items"][0]
        assert item["category"] == "failed"
        assert item["error_message"] == "Judge model unavailable"
        assert item["error_code"] == "judge_unavailable"
        assert resp.json()["counts"]["failed"] == 1

    @pytest.mark.asyncio
    async def test_tied_run_is_no_change_not_a_candidate(self, client):
        cookies, headers = _auth()
        run = _run(uuid="kb-run", kb_uuid="kb-1", tied_with_baseline=True)
        with _InboxHarness(kb=[run]):
            resp = await client.get("/api/optimizer/inbox", cookies=cookies, headers=headers)

        body = resp.json()
        assert body["items"][0]["category"] == "no_change"
        assert body["counts"]["needs_review"] == 0

    @pytest.mark.asyncio
    async def test_applied_kb_run_is_categorized_live(self, client):
        cookies, headers = _auth()
        run = _run(uuid="kb-run", kb_uuid="kb-1", applied_at=_NOW)
        with _InboxHarness(kb=[run]):
            resp = await client.get("/api/optimizer/inbox", cookies=cookies, headers=headers)

        item = resp.json()["items"][0]
        assert item["category"] == "applied"
        assert item["is_live"] is True

    @pytest.mark.asyncio
    async def test_reverted_kb_run_is_reviewable_again(self, client):
        cookies, headers = _auth()
        run = _run(uuid="kb-run", kb_uuid="kb-1", applied_at=_NOW, reverted_at=_NOW)
        with _InboxHarness(kb=[run]):
            resp = await client.get("/api/optimizer/inbox", cookies=cookies, headers=headers)

        assert resp.json()["items"][0]["category"] == "needs_review"

    @pytest.mark.asyncio
    async def test_extraction_run_is_live_only_when_override_matches(self, client):
        cookies, headers = _auth()
        run = _run(uuid="ex-run", search_set_uuid="ss-1", best_config={"model": "m2"})
        live_set = SimpleNamespace(
            title="Budget fields", uuid="ss-1",
            extraction_config_override={"model": "m2"},
            extraction_config_override_set_at=_NOW,
        )
        with _InboxHarness(extraction=[run], ss_doc=live_set):
            resp = await client.get("/api/optimizer/inbox", cookies=cookies, headers=headers)
        assert resp.json()["items"][0]["category"] == "applied"

        stale_set = SimpleNamespace(
            title="Budget fields", uuid="ss-1",
            extraction_config_override={"model": "something-else"},
            extraction_config_override_set_at=_NOW,
        )
        with _InboxHarness(extraction=[run], ss_doc=stale_set):
            resp = await client.get("/api/optimizer/inbox", cookies=cookies, headers=headers)
        assert resp.json()["items"][0]["category"] == "needs_review"

    @pytest.mark.asyncio
    async def test_dismissed_runs_are_hidden_unless_requested(self, client):
        cookies, headers = _auth()
        run = _run(uuid="kb-run", kb_uuid="kb-1", dismissed_at=_NOW, dismissed_by="user1")

        with _InboxHarness(kb=[run]):
            resp = await client.get("/api/optimizer/inbox", cookies=cookies, headers=headers)
        assert resp.json()["items"] == []

        with _InboxHarness(kb=[run]):
            resp = await client.get(
                "/api/optimizer/inbox?include_dismissed=true", cookies=cookies, headers=headers,
            )
        items = resp.json()["items"]
        assert len(items) == 1 and items[0]["category"] == "dismissed"

    @pytest.mark.asyncio
    async def test_query_window_covers_shadow_runs_and_failures(self, client):
        cookies, headers = _auth()
        with _InboxHarness() as h:
            await client.get("/api/optimizer/inbox?days=7", cookies=cookies, headers=headers)
            query = h.MockKB.find.call_args.args[0]

        assert "$or" in query
        assert {"options.shadow_trigger": {"$exists": True}} in query["$or"]
        assert {"status": "failed"} in query["$or"]
        assert "started_at" in query

    @pytest.mark.asyncio
    async def test_rejects_out_of_range_window(self, client):
        cookies, headers = _auth()
        with _InboxHarness():
            resp = await client.get("/api/optimizer/inbox?days=500", cookies=cookies, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_requires_auth(self, client):
        resp = await client.get("/api/optimizer/inbox")
        assert resp.status_code in (401, 403)


class TestInboxCount:
    @pytest.mark.asyncio
    async def test_count_matches_categories(self, client):
        cookies, headers = _auth()
        candidate = _run(uuid="kb-a", kb_uuid="kb-1")
        failure = _run(
            uuid="kb-b", kb_uuid="kb-1", status="failed",
            error_message="boom", best_config=None, options={},
        )
        with _InboxHarness(kb=[candidate, failure]):
            resp = await client.get("/api/optimizer/inbox/count", cookies=cookies, headers=headers)

        body = resp.json()
        assert body["needs_review"] == 1
        assert body["failed"] == 1
        assert body["total"] == 2


# ---------------------------------------------------------------------------
# Dismiss / restore
# ---------------------------------------------------------------------------


class TestDismiss:
    @pytest.mark.asyncio
    async def test_dismiss_stamps_who_and_when(self, client):
        cookies, headers = _auth()
        run = _run(uuid="kb-run", kb_uuid="kb-1")
        with _InboxHarness(kb=[run]):
            resp = await client.post(
                "/api/optimizer/inbox/kb/kb-run/dismiss", cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert run.dismissed_at is not None
        assert run.dismissed_by == "user1"
        run.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_restore_clears_dismissal(self, client):
        cookies, headers = _auth()
        run = _run(uuid="wf-run", workflow_id="507f1f77bcf86cd799439011",
                   dismissed_at=_NOW, dismissed_by="user1")
        with _InboxHarness(workflow=[run]):
            resp = await client.post(
                "/api/optimizer/inbox/workflow/wf-run/restore", cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert run.dismissed_at is None
        assert run.dismissed_by is None

    @pytest.mark.asyncio
    async def test_view_only_user_cannot_dismiss(self, client):
        cookies, headers = _auth()
        run = _run(uuid="kb-run", kb_uuid="kb-1")
        with _InboxHarness(kb=[run], can_manage=False):
            resp = await client.post(
                "/api/optimizer/inbox/kb/kb-run/dismiss", cookies=cookies, headers=headers,
            )

        assert resp.status_code == 404
        assert run.dismissed_at is None

    @pytest.mark.asyncio
    async def test_unknown_surface_is_rejected(self, client):
        cookies, headers = _auth()
        with _InboxHarness():
            resp = await client.post(
                "/api/optimizer/inbox/bogus/run-1/dismiss", cookies=cookies, headers=headers,
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_run_is_404(self, client):
        cookies, headers = _auth()
        with _InboxHarness():
            resp = await client.post(
                "/api/optimizer/inbox/kb/nope/dismiss", cookies=cookies, headers=headers,
            )
        assert resp.status_code == 404
