"""Tier 2 integration tests for previously-uncovered routers/services.

Targets: activity, certification, demo (service), feedback, notifications.
Each test exercises a real Beanie ODM round-trip — no router-level mocking.
"""

import os
import secrets
import uuid
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("INTEGRATION_MONGODB"),
        reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests",
    ),
    pytest.mark.integration_tier2,
    pytest.mark.asyncio(loop_scope="session"),
]


def _route_auth(user_id: str):
    from app.config import Settings
    from app.utils.security import create_access_token

    settings = Settings(jwt_secret_key="test-secret-key", environment="development")
    token = create_access_token(user_id, settings)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def t2_client(mongo_client):
    from unittest.mock import AsyncMock as _AsyncMock
    from app.config import Settings as _Settings
    from httpx import ASGITransport, AsyncClient

    settings = _Settings(jwt_secret_key="test-secret-key", environment="development")
    with patch("app.main.init_db", new_callable=_AsyncMock), \
         patch("app.dependencies.get_settings", return_value=settings):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# notifications router
# ---------------------------------------------------------------------------

class TestNotificationsRouter:
    async def _seed_user_and_notifications(self, n_unread=2, n_read=1):
        from app.models.notification import Notification
        from app.models.user import User

        user = User(user_id="notif-user", email="n@example.com", name="N")
        await user.insert()

        unread = []
        for i in range(n_unread):
            n = Notification(
                user_id="notif-user",
                kind="verification_approved",
                title=f"Unread {i}",
                read=False,
            )
            await n.insert()
            unread.append(n)

        for i in range(n_read):
            n = Notification(
                user_id="notif-user",
                kind="verification_approved",
                title=f"Read {i}",
                read=True,
            )
            await n.insert()

        return user, unread

    async def test_list_returns_unread_count(self, t2_client):
        await self._seed_user_and_notifications(n_unread=2, n_read=1)
        cookies, headers = _route_auth("notif-user")

        resp = await t2_client.get("/api/notifications", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["notifications"]) == 3
        assert data["unread_count"] == 2

    async def test_count_only(self, t2_client):
        await self._seed_user_and_notifications(n_unread=3, n_read=0)
        cookies, headers = _route_auth("notif-user")

        resp = await t2_client.get("/api/notifications/count", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        assert resp.json() == {"unread_count": 3}

    async def test_mark_one_read(self, t2_client):
        from app.models.notification import Notification

        _user, unread = await self._seed_user_and_notifications(n_unread=2, n_read=0)
        cookies, headers = _route_auth("notif-user")

        target = unread[0]
        resp = await t2_client.post(
            f"/api/notifications/{target.uuid}/read",
            cookies=cookies, headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        reloaded = await Notification.find_one(Notification.uuid == target.uuid)
        assert reloaded.read is True

    async def test_mark_all_read(self, t2_client):
        from app.models.notification import Notification

        await self._seed_user_and_notifications(n_unread=3, n_read=0)
        cookies, headers = _route_auth("notif-user")

        resp = await t2_client.post(
            "/api/notifications/read-all", cookies=cookies, headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["marked_count"] == 3

        remaining_unread = await Notification.find(
            Notification.user_id == "notif-user", Notification.read == False  # noqa: E712
        ).to_list()
        assert remaining_unread == []


# ---------------------------------------------------------------------------
# activity router
# ---------------------------------------------------------------------------

class TestActivityRouter:
    async def _seed(self):
        from app.models.activity import ActivityEvent, ActivityStatus, ActivityType
        from app.models.user import User

        user = User(user_id="act-user", email="a@example.com", name="A")
        await user.insert()

        events = []
        for i in range(3):
            ev = ActivityEvent(
                type=ActivityType.WORKFLOW_RUN.value,
                title=f"Run {i}",
                status=ActivityStatus.COMPLETED.value,
                user_id="act-user",
            )
            await ev.insert()
            events.append(ev)
        return user, events

    async def test_list_streams_returns_user_events(self, t2_client):
        await self._seed()
        cookies, headers = _route_auth("act-user")

        resp = await t2_client.get("/api/activity/streams/", cookies=cookies, headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["events"]) == 3

    async def test_get_single_activity(self, t2_client):
        _user, events = await self._seed()
        cookies, headers = _route_auth("act-user")

        target = events[0]
        resp = await t2_client.get(f"/api/activity/{target.id}", cookies=cookies, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["activity"]["title"] == "Run 0"

    async def test_get_other_users_activity_404s(self, t2_client):
        from app.models.activity import ActivityEvent, ActivityStatus, ActivityType
        from app.models.user import User

        await User(user_id="act-user", email="a@example.com").insert()
        await User(user_id="other", email="o@example.com").insert()
        ev = ActivityEvent(
            type=ActivityType.WORKFLOW_RUN.value,
            title="Other's run",
            status=ActivityStatus.COMPLETED.value,
            user_id="other",
        )
        await ev.insert()

        cookies, headers = _route_auth("act-user")
        resp = await t2_client.get(f"/api/activity/{ev.id}", cookies=cookies, headers=headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# feedback router
# ---------------------------------------------------------------------------

class TestFeedbackRouter:
    async def test_submit_rating_creates_record(self, t2_client):
        from app.models.feedback import ExtractionQualityRecord
        from app.models.user import User

        await User(user_id="fb-user", email="fb@example.com").insert()
        cookies, headers = _route_auth("fb-user")

        resp = await t2_client.post(
            "/api/feedback/submit_rating",
            json={
                "pdf_title": "doc.pdf",
                "rating": 4,
                "comment": "Good",
                "result_json": {"extracted": "data"},
            },
            cookies=cookies, headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json() == {"complete": True}

        recs = await ExtractionQualityRecord.find(
            ExtractionQualityRecord.user_id == "fb-user"
        ).to_list()
        assert len(recs) == 1
        assert recs[0].star_rating == 4
        assert recs[0].pdf_title == "doc.pdf"

    async def test_submit_rating_rejects_out_of_range(self, t2_client):
        from app.models.user import User

        await User(user_id="fb-user", email="fb@example.com").insert()
        cookies, headers = _route_auth("fb-user")

        resp = await t2_client.post(
            "/api/feedback/submit_rating",
            json={"pdf_title": "doc.pdf", "rating": 99},
            cookies=cookies, headers=headers,
        )
        assert resp.status_code == 422  # pydantic Field(ge=1, le=5)

    async def test_submit_chat_feedback(self, t2_client):
        from app.models.feedback import ChatFeedback
        from app.models.user import User

        await User(user_id="fb-user", email="fb@example.com").insert()
        cookies, headers = _route_auth("fb-user")

        resp = await t2_client.post(
            "/api/feedback/chat",
            json={
                "conversation_uuid": "conv-1",
                "message_index": 2,
                "rating": "up",
                "comment": "Helpful",
            },
            cookies=cookies, headers=headers,
        )
        assert resp.status_code == 200

        recs = await ChatFeedback.find(ChatFeedback.user_id == "fb-user").to_list()
        assert len(recs) == 1
        assert recs[0].rating == "up"
        assert recs[0].message_index == 2


# ---------------------------------------------------------------------------
# certification router
# ---------------------------------------------------------------------------

class TestCertificationRouter:
    async def test_progress_creates_baseline_for_new_user(self, t2_client):
        from app.models.user import User

        await User(user_id="cert-user", email="c@example.com").insert()
        cookies, headers = _route_auth("cert-user")

        resp = await t2_client.get("/api/certification/progress", cookies=cookies, headers=headers)

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["user_id"] == "cert-user"
        assert data["total_xp"] == 0
        assert data["certified"] is False

    async def test_progress_returns_existing(self, t2_client):
        from app.models.certification import CertificationProgress
        from app.models.user import User

        await User(user_id="cert-user", email="c@example.com").insert()
        await CertificationProgress(
            user_id="cert-user",
            total_xp=100,
            level="apprentice",
            modules={"intro": {"completed": True, "stars": 3}},
        ).insert()
        cookies, headers = _route_auth("cert-user")

        resp = await t2_client.get("/api/certification/progress", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_xp"] == 100
        assert data["level"] == "apprentice"
        assert "intro" in data["modules"]


# ---------------------------------------------------------------------------
# demo service (route is gated by enable_trial_system; test the service path)
# ---------------------------------------------------------------------------

class TestDemoService:
    async def test_submit_application_creates_record(self, mongo_client):
        from app.config import Settings
        from app.models.demo import DemoApplication
        from app.services import demo_service

        settings = Settings(jwt_secret_key="test", environment="development")

        with patch("app.services.demo_service.send_email", new_callable=AsyncMock):
            app = await demo_service.submit_application(
                name="Jane Doe",
                email=f"jane-{uuid.uuid4().hex[:6]}@example.com",
                organization="State U",
                questionnaire_responses={"role": "ra"},
                title="Director of Research",
                settings=settings,
            )

        assert app.uuid is not None
        assert app.status == "pending"
        assert app.organization == "State U"

        reloaded = await DemoApplication.find_one(DemoApplication.uuid == app.uuid)
        assert reloaded is not None
        assert reloaded.name == "Jane Doe"

    async def test_submit_application_rejects_duplicate_email(self, mongo_client):
        from app.config import Settings
        from app.services import demo_service

        settings = Settings(jwt_secret_key="test", environment="development")
        email = f"dup-{uuid.uuid4().hex[:6]}@example.com"

        with patch("app.services.demo_service.send_email", new_callable=AsyncMock):
            await demo_service.submit_application(
                name="A", email=email, organization="X",
                questionnaire_responses={}, title="", settings=settings,
            )
            with pytest.raises(ValueError):
                await demo_service.submit_application(
                    name="B", email=email, organization="Y",
                    questionnaire_responses={}, title="", settings=settings,
                )

    async def test_get_waitlist_status_for_existing(self, mongo_client):
        from app.config import Settings
        from app.services import demo_service

        settings = Settings(jwt_secret_key="test", environment="development")

        with patch("app.services.demo_service.send_email", new_callable=AsyncMock):
            app = await demo_service.submit_application(
                name="K", email=f"k-{uuid.uuid4().hex[:6]}@example.com",
                organization="X", questionnaire_responses={}, title="", settings=settings,
            )

        result = await demo_service.get_waitlist_status(app.uuid)
        assert result is not None
        assert result.uuid == app.uuid

    async def test_get_waitlist_status_for_missing(self, mongo_client):
        from app.services import demo_service

        result = await demo_service.get_waitlist_status("nonexistent-uuid")
        assert result is None

    async def test_admin_promote_user_clears_demo_flags(self, mongo_client):
        import datetime
        from app.models.demo import DemoApplication
        from app.models.user import User
        from app.services import demo_service

        suffix = uuid.uuid4().hex[:6]
        user = User(
            user_id=f"u-promote-{suffix}",
            email=f"promote-{suffix}@example.com",
            is_demo_user=True,
            demo_status="active",
            demo_expires_at=datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(days=7),
        )
        await user.insert()

        app = DemoApplication(
            uuid=f"app-promote-{suffix}",
            name="Promote Me",
            email=user.email,
            organization="Test U",
            status="active",
            user_id=user.user_id,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )
        await app.insert()

        ok = await demo_service.admin_promote_user(app.uuid)
        assert ok is True

        reloaded_user = await User.find_one(User.user_id == user.user_id)
        assert reloaded_user is not None
        assert reloaded_user.is_demo_user is False
        assert reloaded_user.demo_status is None
        assert reloaded_user.demo_expires_at is None

        reloaded_app = await DemoApplication.find_one(DemoApplication.uuid == app.uuid)
        assert reloaded_app is not None
        assert reloaded_app.status == "completed"
        assert reloaded_app.admin_released is True

    async def test_admin_promote_user_missing_returns_false(self, mongo_client):
        from app.services import demo_service

        ok = await demo_service.admin_promote_user("nonexistent-uuid")
        assert ok is False
