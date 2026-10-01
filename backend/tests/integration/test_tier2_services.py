"""Tier 2 integration tests for services that previously could not be unit-tested
because Beanie's field descriptors and query operators don't work on MagicMock.

Each block here corresponds to a `@pytest.mark.skip(reason="Beanie ...")` test
in the unit suite. Real DB → real behavior.
"""

import datetime
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("INTEGRATION_MONGODB"),
        reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests",
    ),
    pytest.mark.integration_tier2,
    pytest.mark.asyncio(loop_scope="session"),
]


# ---------------------------------------------------------------------------
# team_service.invite_member / accept_invite — was: 4 skipped tests in
# test_team_service.py (Beanie field descriptors not available on MagicMock).
# ---------------------------------------------------------------------------

class TestInviteMemberWithRealDB:
    async def test_creates_new_invite(self, mongo_client):
        from app.models.team import Team, TeamInvite, TeamMembership
        from app.models.user import User
        from app.services.team_service import invite_member

        team = Team(uuid="t1", name="Team1", owner_user_id="alice")
        await team.insert()
        await TeamMembership(team=team.id, user_id="alice", role="admin").insert()
        await User(user_id="alice", email="alice@example.com", name="Alice").insert()

        with patch("app.services.team_service._send_invite_email", new_callable=AsyncMock):
            invite = await invite_member("t1", "bob@example.com", "member", "alice")

        assert invite.email == "bob@example.com"
        assert invite.role == "member"
        assert invite.team == team.id
        assert invite.resend_count == 0

        stored = await TeamInvite.find_one(TeamInvite.token == invite.token)
        assert stored is not None
        assert stored.email == "bob@example.com"

    async def test_resends_existing_pending_invite(self, mongo_client):
        from app.models.team import Team, TeamInvite, TeamMembership
        from app.models.user import User
        from app.services.team_service import invite_member

        team = Team(uuid="t2", name="Team2", owner_user_id="alice")
        await team.insert()
        await TeamMembership(team=team.id, user_id="alice", role="admin").insert()
        await User(user_id="alice", email="alice@example.com", name="Alice").insert()
        original = TeamInvite(
            team=team.id,
            email="bob@example.com",
            invited_by_user_id="alice",
            role="member",
            token="oldtoken",
        )
        await original.insert()

        with patch("app.services.team_service._send_invite_email", new_callable=AsyncMock):
            invite = await invite_member("t2", "bob@example.com", "admin", "alice")

        assert invite.id == original.id
        assert invite.role == "admin"
        assert invite.resend_count == 1
        assert invite.token != "oldtoken"

    async def test_requires_admin_role(self, mongo_client):
        from app.models.team import Team, TeamMembership
        from app.services.team_service import invite_member

        team = Team(uuid="t3", name="Team3", owner_user_id="alice")
        await team.insert()
        await TeamMembership(team=team.id, user_id="bob", role="member").insert()

        with pytest.raises(ValueError, match="Requires at least admin role"):
            await invite_member("t3", "carol@example.com", "member", "bob")


class TestAcceptInviteWithRealDB:
    async def test_creates_membership_and_sets_current_team(self, mongo_client):
        from app.models.team import Team, TeamInvite, TeamMembership
        from app.models.user import User
        from app.services.team_service import accept_invite

        team = Team(uuid="t4", name="Team4", owner_user_id="alice")
        await team.insert()
        invite = TeamInvite(
            team=team.id,
            email="bob@example.com",
            invited_by_user_id="alice",
            role="member",
            token="acceptme",
        )
        await invite.insert()
        bob = User(user_id="bob", email="bob@example.com", name="Bob")
        await bob.insert()

        with patch("app.services.team_service._notify_invite_accepted", new_callable=AsyncMock):
            result = await accept_invite("acceptme", bob)

        assert result.id == team.id

        membership = await TeamMembership.find_one(
            TeamMembership.team == team.id,
            TeamMembership.user_id == "bob",
        )
        assert membership is not None
        assert membership.role == "member"

        bob_reloaded = await User.find_one(User.user_id == "bob")
        assert bob_reloaded.current_team == team.id

        invite_reloaded = await TeamInvite.find_one(TeamInvite.token == "acceptme")
        assert invite_reloaded.accepted is True


# ---------------------------------------------------------------------------
# library_service.update_item / touch_item — was: 2 skipped tests in
# test_library_service.py (Beanie model class attrs not available on MagicMock).
# ---------------------------------------------------------------------------

class TestLibraryItemUpdateWithRealDB:
    async def _seed_user_and_library(self, scope: str = "personal"):
        from app.models.library import Library, LibraryItem, LibraryItemKind, LibraryScope
        from app.models.user import User
        from app.models.workflow import Workflow

        user = User(user_id="lib-user", email="u@example.com", name="U")
        await user.insert()

        wf = Workflow(name="WF", description="d", user_id="lib-user", steps=[], space="default")
        await wf.insert()

        item = LibraryItem(
            item_id=wf.id,
            kind=LibraryItemKind.WORKFLOW,
            added_by_user_id="lib-user",
            tags=[],
        )
        await item.insert()

        lib = Library(
            scope=LibraryScope(scope),
            title="My Lib",
            owner_user_id="lib-user",
            items=[item.id],
        )
        await lib.insert()
        return user, item, wf, lib

    async def test_update_item_persists_note_and_tags(self, mongo_client):
        from app.models.library import LibraryItem
        from app.services.library_service import update_item

        user, item, _wf, _lib = await self._seed_user_and_library()

        result = await update_item(str(item.id), user, note="updated", tags=["a", "b"])

        assert result is not None
        reloaded = await LibraryItem.get(item.id)
        assert reloaded.note == "updated"
        assert reloaded.tags == ["a", "b"]

    async def test_touch_item_sets_last_used_at(self, mongo_client):
        from app.models.library import LibraryItem
        from app.services.library_service import touch_item

        user, item, _wf, _lib = await self._seed_user_and_library()
        assert item.last_used_at is None

        ok = await touch_item(str(item.id), user)
        assert ok is True

        reloaded = await LibraryItem.get(item.id)
        assert reloaded.last_used_at is not None


# ---------------------------------------------------------------------------
# library_service.get_library_items — "last used" for workflows/extractions
# comes from the viewer's own run history, never from opening the item.
# ---------------------------------------------------------------------------

class TestLibraryLastUsedFromRunsWithRealDB:
    async def test_last_used_reflects_runs_not_clicks(self, mongo_client):
        from app.models.activity import ActivityEvent, ActivityType
        from app.models.library import Library, LibraryItem, LibraryItemKind, LibraryScope
        from app.models.search_set import SearchSet
        from app.models.user import User
        from app.models.workflow import Workflow
        from app.services.library_service import get_library_items

        user = User(user_id="runner", email="r@example.com", name="R")
        await user.insert()
        clicked_at = datetime.datetime(2026, 9, 20, tzinfo=datetime.timezone.utc)

        never_run = Workflow(name="Opened Only", user_id="runner", steps=[], space="default")
        ran = Workflow(name="Ran", user_id="runner", steps=[], space="default")
        teammate_ran = Workflow(name="Teammate Ran", user_id="runner", steps=[], space="default")
        for wf in (never_run, ran, teammate_ran):
            await wf.insert()
        extraction = SearchSet(title="Terms", uuid="ss-terms", status="active", set_type="extraction", user_id="runner")
        prompt = SearchSet(title="Summarize", uuid="ss-prompt", status="active", set_type="prompt", user_id="runner")
        await extraction.insert()
        await prompt.insert()

        # Every item carries a click-era stamp; only the prompt's should survive.
        items = [
            LibraryItem(item_id=never_run.id, kind=LibraryItemKind.WORKFLOW, added_by_user_id="runner", last_used_at=clicked_at),
            LibraryItem(item_id=ran.id, kind=LibraryItemKind.WORKFLOW, added_by_user_id="runner", last_used_at=clicked_at),
            LibraryItem(item_id=teammate_ran.id, kind=LibraryItemKind.WORKFLOW, added_by_user_id="runner", last_used_at=clicked_at),
            LibraryItem(item_id=extraction.id, kind=LibraryItemKind.SEARCH_SET, added_by_user_id="runner", last_used_at=clicked_at),
            LibraryItem(item_id=prompt.id, kind=LibraryItemKind.SEARCH_SET, added_by_user_id="runner", last_used_at=clicked_at),
        ]
        for it in items:
            await it.insert()
        lib = Library(scope=LibraryScope.PERSONAL, title="Mine", owner_user_id="runner", items=[i.id for i in items])
        await lib.insert()

        older = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)
        newer = datetime.datetime(2026, 8, 15, tzinfo=datetime.timezone.utc)
        for started in (older, newer):
            await ActivityEvent(type=ActivityType.WORKFLOW_RUN.value, user_id="runner", workflow=ran.id, started_at=started).insert()
        await ActivityEvent(type=ActivityType.WORKFLOW_RUN.value, user_id="someone-else", workflow=teammate_ran.id, started_at=newer).insert()
        await ActivityEvent(type=ActivityType.SEARCH_SET_RUN.value, user_id="runner", search_set_uuid="ss-terms", started_at=older).insert()

        result = {r["name"]: r["last_used_at"] for r in await get_library_items(str(lib.id), user)}

        assert result["Opened Only"] is None
        assert result["Ran"] == newer.isoformat()
        assert result["Teammate Ran"] is None
        assert result["Terms"] == older.isoformat()
        assert result["Summarize"] == clicked_at.isoformat()


# ---------------------------------------------------------------------------
# quality_service.detect_stale_items — was: 1 skipped test in
# test_quality_service.py (Beanie query operators not supported on MagicMock).
# ---------------------------------------------------------------------------

class TestDetectStaleItemsWithRealDB:
    async def test_returns_only_items_past_cutoff(self, mongo_client):
        from app.models.verification import VerifiedItemMetadata
        from app.services.quality_service import detect_stale_items

        old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=60)
        recent = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)

        await VerifiedItemMetadata(
            item_kind="workflow",
            item_id=str(ObjectId()),
            display_name="Old WF",
            quality_score=60.0,
            last_validated_at=old,
        ).insert()
        await VerifiedItemMetadata(
            item_kind="workflow",
            item_id=str(ObjectId()),
            display_name="Recent WF",
            quality_score=90.0,
            last_validated_at=recent,
        ).insert()

        stale = await detect_stale_items(max_age_days=14)

        assert len(stale) == 1
        assert stale[0]["display_name"] == "Old WF"


# ---------------------------------------------------------------------------
# verification_service.check_and_flag_stale_verification — was: 2 skipped tests
# in test_verification_service.py.
# ---------------------------------------------------------------------------

class TestStaleVerificationFlaggingWithRealDB:
    async def test_flags_stale_verified_workflow(self, mongo_client):
        from app.models.verification import VerifiedItemMetadata
        from app.models.workflow import Workflow
        from app.services.verification_service import check_and_flag_stale_verification

        wf = Workflow(name="W1", user_id="alice", steps=[], space="default", verified=True)
        await wf.insert()

        meta = VerifiedItemMetadata(
            item_kind="workflow",
            item_id=str(wf.id),
            display_name="W1",
            last_validated_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        )
        await meta.insert()

        # Avoid creating a real QualityAlert — patch its insert
        with patch("app.services.verification_service.QualityAlert") as mock_qa:
            instance = mock_qa.return_value
            instance.insert = AsyncMock()
            result = await check_and_flag_stale_verification("workflow", str(wf.id))

        assert result is True
        reloaded = await VerifiedItemMetadata.find_one(
            VerifiedItemMetadata.item_kind == "workflow",
            VerifiedItemMetadata.item_id == str(wf.id),
        )
        assert reloaded.last_validated_at is None

    async def test_no_op_when_not_verified(self, mongo_client):
        from app.models.workflow import Workflow
        from app.services.verification_service import check_and_flag_stale_verification

        wf = Workflow(name="W2", user_id="alice", steps=[], space="default", verified=False)
        await wf.insert()

        result = await check_and_flag_stale_verification("workflow", str(wf.id))
        assert result is False


# ---------------------------------------------------------------------------
# approvals router — was: 3 skipped tests in test_approval_routes.py
# (Pydantic v2 validation error — approval model field type mismatch).
# Real DB resolves the type mismatch.
# ---------------------------------------------------------------------------

import secrets as _secrets


def _route_auth(user_id: str):
    from app.config import Settings
    from app.utils.security import create_access_token

    settings = Settings(jwt_secret_key="test-secret-key", environment="development")
    token = create_access_token(user_id, settings)
    csrf = _secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def t2_client(mongo_client):
    """ASGITransport client with Beanie already initialized via mongo_client.

    The patches on init_db / get_settings configure the app to use the same
    DB and a stable JWT secret across the test process.
    """
    from unittest.mock import AsyncMock as _AsyncMock
    from app.config import Settings as _Settings
    from httpx import ASGITransport, AsyncClient

    settings = _Settings(jwt_secret_key="test-secret-key", environment="development")
    with patch("app.main.init_db", new_callable=_AsyncMock), \
         patch("app.dependencies.get_settings", return_value=settings):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


class TestApprovalRoutesWithRealDB:
    async def _seed(self, *, status: str = "pending", reviewer_id: str = "reviewer1"):
        from app.models.approval import ApprovalRequest
        from app.models.user import User
        from app.models.workflow import Workflow, WorkflowResult

        user = User(user_id=reviewer_id, email=f"{reviewer_id}@example.com", name=reviewer_id)
        await user.insert()

        wf = Workflow(name="WF", user_id=reviewer_id, steps=[], space="default")
        await wf.insert()
        wfr = WorkflowResult(workflow=wf.id, session_id="s1", status="awaiting_approval")
        await wfr.insert()

        approval = ApprovalRequest(
            uuid=f"appr-{uuid.uuid4().hex[:8]}",
            workflow_result_id=wfr.id,
            workflow_id=wf.id,
            step_index=0,
            step_name="Review",
            status=status,
            assigned_to_user_ids=[reviewer_id],
        )
        await approval.insert()
        return user, wf, wfr, approval

    async def test_approve_pending(self, t2_client):
        from app.celery_app import celery
        from app.models.approval import ApprovalRequest

        _user, _wf, _wfr, approval = await self._seed()
        cookies, headers = _route_auth("reviewer1")

        with patch.object(celery, "send_task") as mock_send, \
             patch("app.routers.reviews._notify_owner", new_callable=AsyncMock):
            resp = await t2_client.post(
                f"/api/reviews/{approval.uuid}/approve",
                json={"comments": "Looks good"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        reloaded = await ApprovalRequest.find_one(ApprovalRequest.uuid == approval.uuid)
        assert reloaded.status == "approved"
        assert reloaded.reviewer_user_id == "reviewer1"
        assert reloaded.reviewer_comments == "Looks good"
        mock_send.assert_called_once()

    async def test_reject_pending_marks_workflow_failed(self, t2_client):
        from app.models.approval import ApprovalRequest
        from app.models.workflow import WorkflowResult

        _user, _wf, wfr, approval = await self._seed()
        cookies, headers = _route_auth("reviewer1")

        with patch("app.routers.reviews._notify_owner", new_callable=AsyncMock):
            resp = await t2_client.post(
                f"/api/reviews/{approval.uuid}/reject",
                json={"comments": "Not acceptable"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        reloaded_a = await ApprovalRequest.find_one(ApprovalRequest.uuid == approval.uuid)
        assert reloaded_a.status == "rejected"
        reloaded_wfr = await WorkflowResult.get(wfr.id)
        assert reloaded_wfr.status == "failed"

    async def test_cannot_decide_already_resolved(self, t2_client):
        _user, _wf, _wfr, approval = await self._seed(status="approved")
        cookies, headers = _route_auth("reviewer1")

        resp = await t2_client.post(
            f"/api/reviews/{approval.uuid}/approve",
            json={"comments": "x"},
            cookies=cookies,
            headers=headers,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# auth router — was: 1 skipped test class in test_auth_routes.py
# (Auth config route accesses Beanie models directly; needs Tier 2).
# ---------------------------------------------------------------------------

class TestAuthConfigRouteWithRealDB:
    async def test_auth_config_returns_methods(self, t2_client, mongo_client):
        from app.models.system_config import SystemConfig

        # Ensure a singleton SystemConfig document exists with known auth_methods
        cfg = await SystemConfig.get_config()
        cfg.auth_methods = ["local"]
        cfg.oauth_providers = []
        await cfg.save()

        resp = await t2_client.get("/api/auth/config")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "auth_methods" in data
        assert "local" in data["auth_methods"]


# ---------------------------------------------------------------------------
# demo_service trial extension — engagement classification + self-serve renewal
# (counts/queries across Beanie models; needs Tier 2).
# ---------------------------------------------------------------------------

class TestTrialExtensionWithRealDB:
    async def _make_locked_trial(self, suffix: str, *, extensions_used: int = 0):
        """Create an exhausted trial application + user, return (app, user)."""
        from app.models.demo import DemoApplication
        from app.models.user import User

        uid = f"trial_{suffix}@example.com"
        now = datetime.datetime.now(datetime.timezone.utc)
        user = User(
            user_id=uid,
            email=uid,
            name=f"Trial {suffix}",
            is_demo_user=True,
            demo_status="exhausted",
            trial_token_budget=1000,
        )
        await user.insert()
        app = DemoApplication(
            uuid=f"app_{suffix}",
            name=f"Trial {suffix}",
            email=uid,
            organization="Test Org",
            status="exhausted",
            user_id=uid,
            expired_at=now,
            post_questionnaire_token=f"tok_{suffix}",
            trial_extensions_used=extensions_used,
        )
        await app.insert()
        return app, user

    async def test_engagement_low_when_never_logged_in(self, mongo_client):
        from app.services.demo_service import compute_trial_engagement

        _app, _user = await self._make_locked_trial("nologin")
        # last_login_at defaults to None
        assert await compute_trial_engagement("trial_nologin@example.com") == "low"

    async def test_engagement_low_with_few_artifacts(self, mongo_client):
        from app.models.document import SmartDocument
        from app.models.user import User
        from app.services.demo_service import compute_trial_engagement

        _app, user = await self._make_locked_trial("fewdocs")
        user.last_login_at = datetime.datetime.now(datetime.timezone.utc)
        await user.save()
        # 2 docs is below the LOW_ENGAGEMENT_MAX_ARTIFACTS=3 threshold
        for i in range(2):
            await SmartDocument(
                path="p", downloadpath="d", title=f"doc{i}",
                uuid=f"fewdocs_doc_{i}", user_id=user.user_id,
            ).insert()
        assert await compute_trial_engagement(user.user_id) == "low"

    async def test_engagement_engaged_at_threshold(self, mongo_client):
        from app.models.document import SmartDocument
        from app.models.user import User
        from app.services.demo_service import compute_trial_engagement

        _app, user = await self._make_locked_trial("engaged")
        user.last_login_at = datetime.datetime.now(datetime.timezone.utc)
        await user.save()
        for i in range(3):
            await SmartDocument(
                path="p", downloadpath="d", title=f"doc{i}",
                uuid=f"engaged_doc_{i}", user_id=user.user_id,
            ).insert()
        assert await compute_trial_engagement(user.user_id) == "engaged"

    async def test_self_extend_unlocks_and_extends(self, mongo_client):
        from app.config import Settings
        from app.models.demo import DemoApplication
        from app.models.user import User
        from app.services import demo_service

        app, _user = await self._make_locked_trial("extend")
        with patch.object(demo_service, "send_email", new_callable=AsyncMock):
            result = await demo_service.self_topup_trial(
                "tok_extend", None, Settings()
            )

        assert result["ok"] is True
        refreshed_app = await DemoApplication.find_one(DemoApplication.uuid == app.uuid)
        refreshed_user = await User.find_one(User.user_id == "trial_extend@example.com")
        assert refreshed_app.status == "active"
        assert refreshed_app.trial_extensions_used == 1
        assert refreshed_user.demo_status == "active"
        # The top-up raised the budget rather than resetting lifetime usage,
        # and the clock era is left behind entirely.
        assert refreshed_user.trial_token_budget == 1000 + Settings().trial_topup_tokens
        assert refreshed_user.demo_expires_at is None
        assert refreshed_app.expires_at is None

    async def test_self_extend_is_unlimited(self, mongo_client):
        # Top-ups are unlimited — going past the old 2-extension cap still
        # reactivates the account and bumps the counter for analytics.
        from app.config import Settings
        from app.models.demo import DemoApplication
        from app.models.user import User
        from app.services import demo_service

        app, _user = await self._make_locked_trial("uncapped", extensions_used=5)
        with patch.object(demo_service, "send_email", new_callable=AsyncMock):
            result = await demo_service.self_topup_trial(
                "tok_uncapped", None, Settings()
            )

        assert result["ok"] is True
        refreshed_app = await DemoApplication.find_one(DemoApplication.uuid == app.uuid)
        refreshed_user = await User.find_one(User.user_id == "trial_uncapped@example.com")
        assert refreshed_app.status == "active"
        assert refreshed_app.trial_extensions_used == 6
        assert refreshed_user.demo_status == "active"

    async def test_self_extend_persists_notes(self, mongo_client):
        from app.config import Settings
        from app.models.demo import DemoApplication, PostExperienceResponse
        from app.services import demo_service

        app, _user = await self._make_locked_trial("notes")
        with patch.object(demo_service, "send_email", new_callable=AsyncMock):
            await demo_service.self_topup_trial(
                "tok_notes", {"using_for": "grants"}, Settings()
            )

        stored = await DemoApplication.find_one(DemoApplication.uuid == app.uuid)
        responses = await PostExperienceResponse.find(
            PostExperienceResponse.demo_application_id == stored.id
        ).to_list()
        assert len(responses) == 1
        assert responses[0].responses["kind"] == "renewal_notes"
        assert responses[0].responses["using_for"] == "grants"

    async def test_get_trial_end_info(self, mongo_client):
        from app.services.demo_service import get_trial_end_info

        await self._make_locked_trial("info", extensions_used=1)
        info = await get_trial_end_info("tok_info")
        assert info is not None
        assert info["name"] == "Trial info"
        assert info["extensions_used"] == 1
        assert info["max_extensions"] == 2
        assert info["can_self_extend"] is True
        assert info["already_extended"] is True
        assert info["engagement"] == "low"

    async def test_get_trial_end_info_invalid_token(self, mongo_client):
        from app.services.demo_service import get_trial_end_info

        assert await get_trial_end_info("does_not_exist") is None


# ---------------------------------------------------------------------------
# demo_service.resend_credentials — status-aware recovery (no password rotation)
# ---------------------------------------------------------------------------

class TestResendCredentialsWithRealDB:
    async def _make_active_trial(self, suffix: str):
        from app.models.demo import DemoApplication
        from app.models.user import User

        uid = f"resend_{suffix}@example.com"
        future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=10)
        user = User(
            user_id=uid, email=uid, name=f"Resend {suffix}",
            is_demo_user=True, demo_status="active", demo_expires_at=future,
            password_hash="original-hash",
        )
        await user.insert()
        app = DemoApplication(
            uuid=f"resend_app_{suffix}", name=f"Resend {suffix}", email=uid,
            organization="Test Org", status="active", user_id=uid, expires_at=future,
        )
        await app.insert()
        return app, user

    async def test_active_sends_link_without_rotating_password(self, mongo_client):
        from app.config import Settings
        from app.models.user import User
        from app.services import demo_service

        app, _user = await self._make_active_trial("active")
        with patch.object(demo_service, "send_email", new_callable=AsyncMock, return_value=True), \
                patch.object(demo_service, "_create_magic_login_token", new_callable=AsyncMock, return_value="https://x/link"):
            result = await demo_service.resend_credentials(app.uuid, Settings())

        assert result["status"] == "sent"
        # The whole point: the password is NOT rotated on resend.
        refreshed = await User.find_one(User.user_id == app.user_id)
        assert refreshed.password_hash == "original-hash"

    async def test_active_send_failure_reported(self, mongo_client):
        from app.config import Settings
        from app.services import demo_service

        app, _user = await self._make_active_trial("failsend")
        with patch.object(demo_service, "send_email", new_callable=AsyncMock, return_value=False), \
                patch.object(demo_service, "_create_magic_login_token", new_callable=AsyncMock, return_value="https://x/link"):
            result = await demo_service.resend_credentials(app.uuid, Settings())

        assert result["status"] == "send_failed"

    async def test_pending_application_is_not_found_404_but_waitlist(self, mongo_client):
        from app.config import Settings
        from app.models.demo import DemoApplication
        from app.services import demo_service

        app = DemoApplication(
            uuid="resend_pending", name="Pending", email="pending@example.com",
            organization="Test Org", status="pending",
        )
        await app.insert()
        result = await demo_service.resend_credentials(app.uuid, Settings())
        assert result["status"] == "pending"

    async def test_expired_returns_renewal_token(self, mongo_client):
        from app.config import Settings
        from app.models.demo import DemoApplication
        from app.services import demo_service

        app = DemoApplication(
            uuid="resend_expired", name="Expired", email="expired@example.com",
            organization="Test Org", status="expired", user_id="expired@example.com",
            post_questionnaire_token="renew_tok_123",
        )
        await app.insert()
        result = await demo_service.resend_credentials(app.uuid, Settings())
        assert result["status"] == "expired"
        assert result["feedback_token"] == "renew_tok_123"

    async def test_unknown_uuid_not_found(self, mongo_client):
        from app.config import Settings
        from app.services import demo_service

        result = await demo_service.resend_credentials("nope", Settings())
        assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# library_service.get_library_items — quality data is batched (Sentry
# 7724573628: three queries per library row). Same answers as the per-item
# lookups: metadata wins; otherwise the newest non-smoke-test run.
# ---------------------------------------------------------------------------

class TestLibraryQualityBatchedWithRealDB:
    async def test_batched_quality_matches_per_item_rules(self, mongo_client):
        from app.models.library import Library, LibraryItem, LibraryItemKind, LibraryScope
        from app.models.search_set import SearchSet
        from app.models.user import User
        from app.models.validation_run import ValidationRun
        from app.models.verification import VerifiedItemMetadata
        from app.models.workflow import Workflow
        from app.services.library_service import get_library_items
        from app.services.quality_service import SMOKE_TEST_SOURCE

        user = User(user_id="q-owner", email="q@example.com", name="Q")
        await user.insert()
        with_meta = Workflow(name="Has Meta", user_id="q-owner", steps=[], space="default")
        runs_only = Workflow(name="Runs Only", user_id="q-owner", steps=[], space="default")
        unvalidated = Workflow(name="Never Validated", user_id="q-owner", steps=[], space="default")
        gone = Workflow(name="Deleted", user_id="q-owner", steps=[], space="default")
        for wf in (with_meta, runs_only, unvalidated, gone):
            await wf.insert()
        ss = SearchSet(title="Award Terms", uuid="ss-award", status="active", set_type="extraction", user_id="q-owner")
        await ss.insert()

        await VerifiedItemMetadata(item_kind="workflow", item_id=str(with_meta.id), quality_score=91.0, quality_tier="gold").insert()
        t0 = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
        for days, score, source in ((0, 50.0, None), (5, 72.0, None), (9, 10.0, SMOKE_TEST_SOURCE)):
            run = ValidationRun(item_kind="workflow", item_id=str(runs_only.id), score=score,
                                run_type="workflow", user_id="q-owner",
                                created_at=t0 + datetime.timedelta(days=days))
            if source:
                run.source = source
            await run.insert()
        # Search sets are validated under their uuid, not the ObjectId.
        await ValidationRun(item_kind="search_set", item_id="ss-award", score=88.0,
                            run_type="extraction", user_id="q-owner", created_at=t0).insert()

        items = [
            LibraryItem(item_id=wf.id, kind=LibraryItemKind.WORKFLOW, added_by_user_id="q-owner")
            for wf in (with_meta, runs_only, unvalidated, gone)
        ] + [LibraryItem(item_id=ss.id, kind=LibraryItemKind.SEARCH_SET, added_by_user_id="q-owner")]
        for it in items:
            await it.insert()
        lib = Library(scope=LibraryScope.PERSONAL, title="Q", owner_user_id="q-owner", items=[i.id for i in items])
        await lib.insert()
        await gone.delete()

        rows = {r["name"]: r for r in await get_library_items(str(lib.id), user)}

        assert set(rows) == {"Has Meta", "Runs Only", "Never Validated", "Award Terms"}
        assert rows["Has Meta"]["quality_score"] == 91.0
        assert rows["Has Meta"]["quality_tier"] == "gold"
        # Newest non-smoke run (72), not the newer smoke run (10) or the older one.
        assert rows["Runs Only"]["quality_score"] == 72.0
        assert rows["Runs Only"]["quality_asserted"] is False
        assert rows["Never Validated"].get("quality_score") is None
        assert rows["Award Terms"]["quality_score"] == 88.0

    async def test_query_count_does_not_grow_with_library_size(self, mongo_client, mongo_db_name):
        """The N+1 itself: count the commands against a real server. Main
        issued a target get, a metadata find and a latest-run find per row."""
        from collections import Counter

        from beanie import init_beanie
        from motor.motor_asyncio import AsyncIOMotorClient
        from pymongo import monitoring

        from app.database import ALL_MODELS
        from app.models.library import Library, LibraryItem, LibraryItemKind, LibraryScope
        from app.models.user import User
        from app.models.workflow import Workflow
        from app.services.library_service import get_library_items

        class _Count(monitoring.CommandListener):
            def __init__(self):
                self.by_collection = Counter()

            def started(self, event):
                if event.command_name in ("find", "aggregate"):
                    self.by_collection[(event.command_name, event.command.get(event.command_name))] += 1

            def succeeded(self, event):
                pass

            def failed(self, event):
                pass

        listener = _Count()
        client = AsyncIOMotorClient("mongodb://localhost:27017/", event_listeners=[listener])
        await init_beanie(database=client[mongo_db_name], document_models=ALL_MODELS)
        try:
            user = User(user_id="n1-owner", email="n1@example.com", name="N")
            await user.insert()
            workflows = [Workflow(name=f"WF {i}", user_id="n1-owner", steps=[], space="default") for i in range(6)]
            for wf in workflows:
                await wf.insert()
            items = [LibraryItem(item_id=wf.id, kind=LibraryItemKind.WORKFLOW, added_by_user_id="n1-owner") for wf in workflows]
            for it in items:
                await it.insert()
            lib = Library(scope=LibraryScope.PERSONAL, title="N", owner_user_id="n1-owner", items=[i.id for i in items])
            await lib.insert()

            listener.by_collection.clear()
            rows = await get_library_items(str(lib.id), user)
            assert len(rows) == 6

            counts = listener.by_collection
            assert counts[("find", "workflow")] <= 1, counts
            assert counts[("find", "verified_item_metadata")] <= 1, counts
            assert counts[("find", "validation_runs")] + counts[("aggregate", "validation_runs")] <= 1, counts
        finally:
            # Hand the models back to the session client for later tests.
            await init_beanie(database=mongo_client[mongo_db_name], document_models=ALL_MODELS)
            client.close()
