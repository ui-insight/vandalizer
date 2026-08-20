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

# A syntactically valid ObjectId, so the real access layer gets past its parse.
_WF_OID = "507f1f77bcf86cd799439011"


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
        # ``user_id="user1"`` on each stand-in: these tests stub the authorized
        # lookups to cover categorization and naming, but the router still asks
        # whether a *view-only* row belongs to the caller before keeping it
        # (see ``_is_own_or_team_item``). Owning them keeps that orthogonal —
        # TestRealAccessScoping is where the ownership rule itself is tested.
        self.kb_doc = kb_doc or SimpleNamespace(
            title="Compliance KB", uuid="kb-1", user_id="user1", team_id=None,
            shared_with_team=False,
        )
        self.ss_doc = ss_doc or SimpleNamespace(
            title="Budget fields", uuid="ss-1", user_id="user1", team_id=None,
            extraction_config_override=None, extraction_config_override_set_at=None,
        )
        self.wf_doc = wf_doc or SimpleNamespace(
            name="Proposal intake", user_id="user1", team_id=None,
            config_override=None, config_override_set_at=None,
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


# ---------------------------------------------------------------------------
# Access scoping against the REAL access-control layer
#
# Every test above stubs ``access_control.get_authorized_*``, which makes them
# blind to what those functions actually grant. That blindness is how a
# support ticket ("any authenticated user sees every team's optimizer runs")
# got past a green suite: view access to a *verified catalog KB*, a *global
# search set*, or a *workflow published to the catalog library* is granted to
# every authenticated user by design, and the inbox was accepting it as
# grounds to show a row. These tests drive the real predicates.
# ---------------------------------------------------------------------------


class _RealAccessHarness:
    """Patch the DB reads under the real access-control functions, nothing more.

    Each surface gets one run pointing at one item owned by ``victim`` in team
    ``team-uuid``; the item's shape (verified / global / library-published) and
    the caller's relationship to it are what each test varies.
    """

    def __init__(self, *, caller="attacker", role=None, examiner=False,
                 kb_fields=None, ss_fields=None, wf_in_verified_library=False):
        self.caller, self.role, self.examiner = caller, role, examiner
        self.kb_fields = kb_fields or {}
        self.ss_fields = ss_fields or {}
        self.wf_in_verified_library = wf_in_verified_library
        self._stack = []

    def __enter__(self):
        from app.routers import optimizer_inbox as oi
        from app.services import access_control as ac
        import app.models.search_set as ss_mod
        import app.models.workflow as wf_mod

        self.user = _make_user(self.caller)
        self.user.is_examiner = self.examiner

        wf = SimpleNamespace(
            id=_WF_OID, user_id="victim", team_id="team-uuid", share_token=None,
            name="Victim proposal intake", config_override=None,
            config_override_set_at=None,
        )
        kb = SimpleNamespace(**{
            "id": "kb-oid", "uuid": "kb-1", "user_id": "victim", "team_id": "team-uuid",
            "shared_with_team": False, "verified": False, "organization_ids": [],
            "title": "Victim KB", **self.kb_fields,
        })
        ss = SimpleNamespace(**{
            "id": "ss-oid", "uuid": "ss-1", "user_id": "victim", "team_id": "team-uuid",
            "is_global": False, "title": "Victim budget fields",
            "extraction_config_override": None,
            "extraction_config_override_set_at": None, **self.ss_fields,
        })

        patches = [
            patch.object(oi, "KBOptimizationRun"),
            patch.object(oi, "ExtractionOptimizationRun"),
            patch.object(oi, "WorkflowOptimizationRun"),
            patch.object(ac, "TeamMembership"),
            patch.object(ac, "Team"),
            patch.object(ac, "LibraryItem"),
            patch.object(ac, "Library"),
            patch.object(ac, "VerificationRequest"),
            patch.object(ac, "VerifiedItemMetadata"),
            patch.object(ac, "KnowledgeBase"),
            patch.object(wf_mod, "Workflow"),
            patch.object(ss_mod, "SearchSet"),
            patch("app.services.organization_service.get_user_org_ancestry",
                  new_callable=AsyncMock, return_value=[]),
        ]
        (MK, ME, MW, MTM, MT, MLI, MLIB, MVR, MVM, MKB, MWF,
         MSS, _org) = [p.__enter__() for p in patches]
        self._stack = patches

        MK.find = MagicMock(return_value=_find_chain([_run(uuid="kb-run", kb_uuid="kb-1")]))
        ME.find = MagicMock(return_value=_find_chain([_run(uuid="ex-run", search_set_uuid="ss-1")]))
        MW.find = MagicMock(return_value=_find_chain([_run(uuid="wf-run", workflow_id=_WF_OID)]))

        if self.role:
            MTM.find = MagicMock(return_value=_find_chain(
                [SimpleNamespace(team="team-oid", role=self.role)]))
            MT.find = MagicMock(return_value=_find_chain(
                [SimpleNamespace(id="team-oid", uuid="team-uuid")]))
        else:
            MTM.find = MagicMock(return_value=_find_chain([]))
            MT.find = MagicMock(return_value=_find_chain([]))

        if self.wf_in_verified_library:
            from app.models.library import LibraryScope

            MLI.find = MagicMock(return_value=_find_chain(
                [SimpleNamespace(id="li", kind=MagicMock(value="workflow"), item_id=_WF_OID)]))
            MLIB.find = MagicMock(return_value=_find_chain(
                [SimpleNamespace(scope=LibraryScope.VERIFIED, owner_user_id="victim", team=None)]))
        else:
            MLI.find = MagicMock(return_value=_find_chain([]))
            MLIB.find = MagicMock(return_value=_find_chain([]))

        MVR.find_one = AsyncMock(return_value=None)
        MVM.find_one = AsyncMock(return_value=None)
        MKB.find_one = AsyncMock(return_value=kb)
        MWF.get = AsyncMock(return_value=wf)
        MSS.find_one = AsyncMock(return_value=ss)
        return self

    def __exit__(self, *exc):
        for p in reversed(self._stack):
            p.__exit__(*exc)
        return False

    async def surfaces(self):
        """``{surface: can_manage}`` for the rows this caller actually gets."""
        from app.routers.optimizer_inbox import _collect

        items = await _collect(self.user, days=14, include_dismissed=False)
        return {i["surface"]: i["can_manage"] for i in items}


class TestRealAccessScoping:
    @pytest.mark.asyncio
    async def test_outsider_sees_nothing(self):
        """The plain cross-team case: no membership, no rows."""
        with _RealAccessHarness() as h:
            assert await h.surfaces() == {}

    @pytest.mark.asyncio
    async def test_verified_catalog_kb_does_not_expose_its_runs(self):
        """A verified KB is readable fleet-wide; its tuning runs are not."""
        with _RealAccessHarness(kb_fields={"verified": True}) as h:
            assert "kb" not in await h.surfaces()

    @pytest.mark.asyncio
    async def test_global_search_set_does_not_expose_its_runs(self):
        with _RealAccessHarness(ss_fields={"is_global": True}) as h:
            assert "extraction" not in await h.surfaces()

    @pytest.mark.asyncio
    async def test_catalog_published_workflow_does_not_expose_its_runs(self):
        """Publishing a workflow to the verified library shares the workflow,
        not the quality scores and failure detail of runs against it."""
        with _RealAccessHarness(wf_in_verified_library=True) as h:
            assert "workflow" not in await h.surfaces()

    @pytest.mark.asyncio
    async def test_owner_sees_all_three_with_manage(self):
        with _RealAccessHarness(caller="victim") as h:
            assert await h.surfaces() == {"kb": True, "extraction": True, "workflow": True}

    @pytest.mark.asyncio
    async def test_teammate_still_sees_team_items(self):
        """The view-only row is the point of the inbox for non-managers —
        a shared team KB and workflow must survive the scoping fix."""
        with _RealAccessHarness(caller="colleague", role="member",
                                kb_fields={"shared_with_team": True}) as h:
            surfaces = await h.surfaces()
        assert surfaces["workflow"] is False   # visible, not actionable
        assert surfaces["kb"] is False
        assert "extraction" in surfaces

    @pytest.mark.asyncio
    async def test_unshared_team_kb_stays_private_to_its_owner(self):
        """``shared_with_team`` is opt-in; membership alone isn't visibility."""
        with _RealAccessHarness(caller="colleague", role="member") as h:
            assert "kb" not in await h.surfaces()

    @pytest.mark.asyncio
    async def test_examiner_keeps_verified_kb_rows_they_can_act_on(self):
        """Examiners curate verified KBs, so those rows are theirs to triage —
        the scoping fix must not take the catalog-governance role's work away."""
        with _RealAccessHarness(examiner=True, kb_fields={"verified": True}) as h:
            surfaces = await h.surfaces()
        assert surfaces["kb"] is True
        # ...but the examiner flag grants nothing on the other two surfaces.
        assert "workflow" not in surfaces and "extraction" not in surfaces
