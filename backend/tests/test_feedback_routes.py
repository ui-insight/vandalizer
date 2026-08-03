"""Coverage for the positive-feedback surface: admin-gating on the read feed
and the off-ticket ProductFeedback write path."""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id: str = "testuser", *, is_admin: bool = False, current_team=None):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = is_admin
    user.current_team = current_team
    user.is_demo_user = False
    user.token_version = 0
    user.demo_status = None
    return user


def _auth(user_id: str = "testuser"):
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


def _patch_auth(user):
    """Context managers that make get_current_user resolve to ``user``."""
    return (
        patch("app.dependencies.decode_token", return_value={"sub": user.user_id, "type": "access"}),
        patch("app.dependencies.User"),
    )


class TestPositiveFeedbackFeedAuthz:
    @pytest.mark.asyncio
    async def test_feed_forbidden_for_non_support(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")
        patch_decode, patch_user = _patch_auth(user)
        with (
            patch_decode,
            patch_user as MockUser,
            patch("app.routers.feedback_admin.support_service.is_support_user",
                  new=AsyncMock(return_value=False)),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/feedback/admin/positive", cookies=cookies, headers=headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_stats_forbidden_for_non_support(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")
        patch_decode, patch_user = _patch_auth(user)
        with (
            patch_decode,
            patch_user as MockUser,
            patch("app.routers.feedback_admin.support_service.is_support_user",
                  new=AsyncMock(return_value=False)),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/feedback/admin/stats", cookies=cookies, headers=headers)
        assert resp.status_code == 403


class TestProductFeedbackWrite:
    @pytest.mark.asyncio
    async def test_product_feedback_inserts_without_ticket(self, client):
        user = _make_user("author")
        cookies, headers = _auth("author")
        patch_decode, patch_user = _patch_auth(user)
        instance = MagicMock()
        instance.insert = AsyncMock()
        with (
            patch_decode,
            patch_user as MockUser,
            patch("app.routers.feedback.ProductFeedback", return_value=instance) as MockPF,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/feedback/product",
                json={"message": "The extraction saved me an hour!", "sentiment": "positive"},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        assert resp.json() == {"complete": True}
        instance.insert.assert_awaited_once()
        # It is a ProductFeedback, never a SupportTicket — praise stays off the queue.
        MockPF.assert_called_once()

    @pytest.mark.asyncio
    async def test_negative_sentiment_is_coerced_to_positive(self, client):
        """A negative sentiment must never ride this path — it is coerced, so
        the off-ticket collection only ever holds positive/idea signal."""
        user = _make_user("author")
        cookies, headers = _auth("author")
        patch_decode, patch_user = _patch_auth(user)
        instance = MagicMock()
        instance.insert = AsyncMock()
        with (
            patch_decode,
            patch_user as MockUser,
            patch("app.routers.feedback.ProductFeedback", return_value=instance) as MockPF,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/feedback/product",
                json={"message": "this is broken", "sentiment": "negative"},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        assert MockPF.call_args.kwargs["sentiment"] == "positive"
