"""Tests for v5.0 launch funnel: email templates, engagement service,
demo-request endpoint, admin blast trigger, cert-complete hook, and chat
milestone tracking.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Email templates — pure functions, no DB
# ---------------------------------------------------------------------------


class TestEmailTemplates:
    def test_v5_launch_announcement_shape(self):
        from app.services.email_service import v5_launch_announcement_email

        subject, html = v5_launch_announcement_email("Ada", "https://app.example.com")
        assert "5.0" in subject
        assert "Ada" in html
        assert "https://app.example.com" in html
        # Confirms the trust-layer narrative is in the copy
        assert "validated" in html.lower() or "quality" in html.lower()

    def test_agentic_chat_drip_step_bounds(self):
        from app.services.email_service import agentic_chat_drip_email

        s1, _ = agentic_chat_drip_email("Ada", step=1, frontend_url="https://app")
        s5, _ = agentic_chat_drip_email("Ada", step=5, frontend_url="https://app")
        # Steps 0 and 99 should clamp into range, not error
        s0, _ = agentic_chat_drip_email("Ada", step=0, frontend_url="https://app")
        s99, _ = agentic_chat_drip_email("Ada", step=99, frontend_url="https://app")
        assert s0 == s1
        assert s99 == s5
        assert s1 != s5

    def test_agentic_chat_drip_role_overrides_apply(self):
        from app.services.email_service import agentic_chat_drip_email

        _, default_html = agentic_chat_drip_email("Ada", step=1, frontend_url="https://app")
        _, pi_html = agentic_chat_drip_email("Ada", step=1, frontend_url="https://app", role="pi")
        assert default_html != pi_html
        # PI variant should name the PI's context
        assert "R01" in pi_html or "my current" in pi_html

    def test_agentic_chat_drip_unknown_role_falls_back(self):
        from app.services.email_service import agentic_chat_drip_email

        _, default_html = agentic_chat_drip_email("Ada", step=1, frontend_url="https://app")
        _, weird_html = agentic_chat_drip_email("Ada", step=1, frontend_url="https://app", role="zzz")
        assert default_html == weird_html

    def test_certification_complete_links_to_cert_panel(self):
        from app.services.email_service import certification_complete_email

        subject, html = certification_complete_email("Ada", "https://app.example.com")
        assert "Certified" in subject
        # V-11: link deep-opens the Certification panel
        assert "/certification" in html

    def test_powerup_milestone_mentions_count(self):
        from app.services.email_service import powerup_milestone_email

        subject, html = powerup_milestone_email("Ada", workflow_count=42, frontend_url="https://app")
        assert "42" in subject
        assert "42" in html

    def test_demo_request_admin_email_includes_all_fields(self):
        from app.services.email_service import demo_request_admin_notification_email

        subject, html = demo_request_admin_notification_email(
            name="Ada", email="ada@example.edu", institution="UExample",
            role="research_admin", message="Tell me more",
        )
        assert "Ada" in subject
        assert "ada@example.edu" in html
        assert "UExample" in html
        assert "research_admin" in html
        assert "Tell me more" in html

    def test_demo_request_confirmation_personalizes(self):
        from app.services.email_service import demo_request_confirmation_email

        subject, html = demo_request_confirmation_email("Ada")
        assert "Ada" in html
        assert "demo" in subject.lower() or "vandalizer" in subject.lower()


# ---------------------------------------------------------------------------
# Engagement service — v5 functions
# ---------------------------------------------------------------------------


class TestStartAgenticChatDrip:
    def test_enrolls_new_user(self):
        from app.services.engagement_service import start_agentic_chat_drip

        user = MagicMock()
        user.agentic_drip_next_at = None
        user.agentic_drip_step = 0
        start_agentic_chat_drip(user)
        assert user.agentic_drip_next_at is not None

    def test_skips_already_enrolled(self):
        from app.services.engagement_service import start_agentic_chat_drip

        user = MagicMock()
        user.agentic_drip_next_at = datetime.datetime.now(datetime.timezone.utc)
        user.agentic_drip_step = 2
        original = user.agentic_drip_next_at
        start_agentic_chat_drip(user)
        assert user.agentic_drip_next_at == original


@pytest.mark.asyncio
class TestRecordChatWorkflowRun:
    async def test_sets_first_chat_workflow_at(self):
        from app.services import engagement_service

        user = MagicMock()
        user.first_chat_workflow_at = None
        user.chat_workflow_count = 0
        user.save = AsyncMock()

        with patch("app.services.engagement_service.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)
            await engagement_service.record_chat_workflow_run("user1")

        assert user.first_chat_workflow_at is not None
        assert user.chat_workflow_count == 1
        user.save.assert_awaited_once()

    async def test_preserves_first_timestamp_on_reruns(self):
        from app.services import engagement_service

        earlier = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
        user = MagicMock()
        user.first_chat_workflow_at = earlier
        user.chat_workflow_count = 5
        user.save = AsyncMock()

        with patch("app.services.engagement_service.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)
            await engagement_service.record_chat_workflow_run("user1")

        assert user.first_chat_workflow_at == earlier
        assert user.chat_workflow_count == 6

    async def test_missing_user_is_silent(self):
        """Tool layer calls this opportunistically — must never raise."""
        from app.services import engagement_service

        with patch("app.services.engagement_service.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=None)
            await engagement_service.record_chat_workflow_run("nobody")  # no raise


@pytest.mark.asyncio
class TestAnnouncementIdempotency:
    async def test_skips_opted_out_users(self):
        from app.services import engagement_service

        opted_out = MagicMock()
        opted_out.email = "a@b.com"
        opted_out.name = "Ada"
        opted_out.user_id = "u1"
        opted_out.email_preferences = {"announcements": False}
        opted_out.v5_announcement_sent_at = None
        opted_out.save = AsyncMock()

        qc = MagicMock()
        qc.limit.return_value.to_list = AsyncMock(return_value=[opted_out])

        with patch("app.services.engagement_service.User") as MockUser, \
             patch("app.services.engagement_service.send_email", AsyncMock(return_value=True)) as mock_send:
            MockUser.find.return_value = qc
            count = await engagement_service.process_v5_launch_announcement()

        assert count == 0
        mock_send.assert_not_called()
        assert opted_out.v5_announcement_sent_at is None

    async def test_sets_sent_timestamp_on_success(self):
        from app.services import engagement_service

        user = MagicMock()
        user.email = "a@b.com"
        user.name = "Ada"
        user.user_id = "u1"
        user.email_preferences = {}
        user.v5_announcement_sent_at = None
        user.save = AsyncMock()

        qc = MagicMock()
        qc.limit.return_value.to_list = AsyncMock(return_value=[user])

        with patch("app.services.engagement_service.User") as MockUser, \
             patch("app.services.engagement_service.send_email", AsyncMock(return_value=True)):
            MockUser.find.return_value = qc
            count = await engagement_service.process_v5_launch_announcement()

        assert count == 1
        assert user.v5_announcement_sent_at is not None


@pytest.mark.asyncio
class TestBackfillAgenticChatDrip:
    async def test_enrolls_eligible_users(self):
        from app.services import engagement_service

        user = MagicMock()
        user.email = "a@b.com"
        user.email_preferences = {}
        user.agentic_drip_next_at = None
        user.save = AsyncMock()

        qc = MagicMock()
        qc.limit.return_value.to_list = AsyncMock(return_value=[user])

        with patch("app.services.engagement_service.User") as MockUser:
            MockUser.find.return_value = qc
            enrolled = await engagement_service.backfill_agentic_chat_drip()

        assert enrolled == 1
        assert user.agentic_drip_next_at is not None

    async def test_respects_onboarding_opt_out(self):
        from app.services import engagement_service

        user = MagicMock()
        user.email = "a@b.com"
        user.email_preferences = {"onboarding": False}
        user.agentic_drip_next_at = None
        user.save = AsyncMock()

        qc = MagicMock()
        qc.limit.return_value.to_list = AsyncMock(return_value=[user])

        with patch("app.services.engagement_service.User") as MockUser:
            MockUser.find.return_value = qc
            enrolled = await engagement_service.backfill_agentic_chat_drip()

        assert enrolled == 0
        user.save.assert_not_awaited()


# ---------------------------------------------------------------------------
# Demo-request endpoint — auth-free public endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDemoRequestEndpoint:
    async def test_rejects_invalid_email(self, client):
        resp = await client.post(
            "/api/demo/request-contact",
            json={
                "name": "Ada",
                "email": "not-an-email",
                "institution": "UExample",
                "role": "research_admin",
            },
        )
        assert resp.status_code in (400, 422)

    async def test_returns_503_when_no_admin_configured(self, client):
        from app.main import app
        from app.dependencies import get_settings

        def _empty_settings():
            s = MagicMock()
            s.demo_request_to_email = ""
            s.resend_from_email = ""
            s.smtp_from_email = ""
            return s

        app.dependency_overrides[get_settings] = _empty_settings
        try:
            resp = await client.post(
                "/api/demo/request-contact",
                json={
                    "name": "Ada",
                    "email": "ada@example.edu",
                    "institution": "UExample",
                    "role": "research_admin",
                },
            )
        finally:
            app.dependency_overrides.pop(get_settings, None)
        assert resp.status_code == 503

    async def test_successful_submission_sends_both_emails(self, client):
        from app.main import app
        from app.dependencies import get_settings

        def _populated_settings():
            s = MagicMock()
            s.demo_request_to_email = "admin@v.com"
            s.resend_from_email = ""
            s.smtp_from_email = ""
            return s

        app.dependency_overrides[get_settings] = _populated_settings
        try:
            with patch("app.routers.contact.email_service.send_email", AsyncMock(return_value=True)) as mock_send:
                resp = await client.post(
                    "/api/demo/request-contact",
                    json={
                        "name": "Ada",
                        "email": "ada@example.edu",
                        "institution": "UExample",
                        "role": "research_admin",
                        "message": "Hi",
                    },
                )
        finally:
            app.dependency_overrides.pop(get_settings, None)
        assert resp.status_code == 202
        # Admin notification + user confirmation = 2 sends
        assert mock_send.await_count == 2


# ---------------------------------------------------------------------------
# Cert-complete hook — exercises the side-effect without full service run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCertificationCompleteHook:
    async def test_fires_notification_deep_linked_to_cert_panel(self):
        """The hook wraps both sub-calls in try/except, so we just verify the
        notification side-effect shape (V-11 deep link)."""
        from app.services.certification_service import _fire_certification_complete_hooks

        with patch("app.services.notification_service.create_notification", AsyncMock()) as mock_notify:
            await _fire_certification_complete_hooks("u1")

        assert mock_notify.await_count == 1
        kwargs = mock_notify.await_args.kwargs
        assert kwargs["link"] == "/certification"
        assert kwargs["kind"] == "certification_complete"
        assert "u1" == kwargs["user_id"]

    async def test_email_is_idempotent_via_timestamp(self):
        from app.services.engagement_service import send_certification_complete_email_for

        user = MagicMock()
        user.email = "a@b.com"
        user.name = "Ada"
        user.user_id = "u1"
        user.certification_complete_sent_at = datetime.datetime.now(datetime.timezone.utc)
        user.save = AsyncMock()

        with patch("app.services.engagement_service.send_email", AsyncMock(return_value=True)) as mock_send:
            ok = await send_certification_complete_email_for(user)

        assert ok is False
        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# Admin blast endpoint — auth gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAdminAnnouncementEndpoint:
    async def test_requires_admin(self, client):
        # Unauthenticated → 401/403 (depending on middleware)
        resp = await client.post(
            "/api/admin/announcements/v5-launch",
            json={"batch_size": 10, "dry_run": True},
        )
        assert resp.status_code in (401, 403)

    async def test_backfill_requires_admin(self, client):
        resp = await client.post(
            "/api/admin/announcements/backfill-agentic-drip",
            json={"batch_size": 10, "dry_run": True},
        )
        assert resp.status_code in (401, 403)
