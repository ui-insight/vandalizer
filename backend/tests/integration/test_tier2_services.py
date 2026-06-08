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
        """Create a locked demo application + user, return (app, user)."""
        from app.models.demo import DemoApplication
        from app.models.user import User

        uid = f"trial_{suffix}@example.com"
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        user = User(
            user_id=uid,
            email=uid,
            name=f"Trial {suffix}",
            is_demo_user=True,
            demo_status="locked",
            demo_expires_at=past,
        )
        await user.insert()
        app = DemoApplication(
            uuid=f"app_{suffix}",
            name=f"Trial {suffix}",
            email=uid,
            organization="Test Org",
            status="expired",
            user_id=uid,
            expires_at=past,
            expired_at=past,
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
            result = await demo_service.self_extend_trial(
                "tok_extend", None, Settings()
            )

        assert result["ok"] is True
        refreshed_app = await DemoApplication.find_one(DemoApplication.uuid == app.uuid)
        refreshed_user = await User.find_one(User.user_id == "trial_extend@example.com")
        assert refreshed_app.status == "active"
        assert refreshed_app.trial_extensions_used == 1
        assert refreshed_user.demo_status == "active"
        now = datetime.datetime.now(datetime.timezone.utc)
        # New expiry is ~14 days out
        assert refreshed_app.expires_at.replace(tzinfo=datetime.timezone.utc) > now + datetime.timedelta(days=13)

    async def test_self_extend_blocked_at_cap(self, mongo_client):
        from app.config import Settings
        from app.models.user import User
        from app.services import demo_service

        await self._make_locked_trial("capped", extensions_used=2)
        with patch.object(demo_service, "send_email", new_callable=AsyncMock):
            result = await demo_service.self_extend_trial(
                "tok_capped", None, Settings()
            )

        assert result["ok"] is False
        assert result["reason"] == "cap_reached"
        # User stays locked
        refreshed_user = await User.find_one(User.user_id == "trial_capped@example.com")
        assert refreshed_user.demo_status == "locked"

    async def test_self_extend_persists_notes(self, mongo_client):
        from app.config import Settings
        from app.models.demo import DemoApplication, PostExperienceResponse
        from app.services import demo_service

        app, _user = await self._make_locked_trial("notes")
        with patch.object(demo_service, "send_email", new_callable=AsyncMock):
            await demo_service.self_extend_trial(
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
