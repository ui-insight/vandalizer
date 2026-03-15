"""Integration tests for admin router authorization.

Verifies that admin endpoints enforce proper role checks and data scoping.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="testuser", is_admin=False, is_examiner=False, current_team=None):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = is_admin
    user.is_examiner = is_examiner
    user.current_team = current_team
    user.is_demo_user = False
    user.demo_status = None
    return user


def _auth(user_id="testuser"):
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


class TestAdminAccessControl:
    @pytest.mark.asyncio
    async def test_non_admin_rejected(self, client):
        """Regular users cannot access admin endpoints."""
        user = _make_user(is_admin=False)
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get(
                "/api/admin/usage",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, client):
        """Admin users can access admin endpoints."""
        user = _make_user(is_admin=True)
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.admin.ActivityEvent") as MockActivity:
            MockUser.find_one = AsyncMock(return_value=user)
            # Mock the ActivityEvent query chain
            mock_find = MagicMock()
            mock_find.to_list = AsyncMock(return_value=[])
            MockActivity.find = MagicMock(return_value=mock_find)
            MockActivity.find_one = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/admin/usage",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_examiner_cannot_access_admin_dashboard(self, client):
        """is_examiner should NOT grant access to admin-only endpoints."""
        user = _make_user(is_examiner=True, is_admin=False)
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            # The _require_admin function (not _require_admin_or_team_admin)
            # is used on the usage endpoint — examiner should be rejected
            resp = await client.get(
                "/api/admin/usage",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self, client):
        resp = await client.get("/api/admin/usage")
        assert resp.status_code == 401


class TestAdminUserLeaderboard:
    @pytest.mark.asyncio
    async def test_examiner_cannot_access_user_leaderboard(self, client):
        """is_examiner no longer grants access to _require_admin_or_team_admin."""
        user = _make_user(is_examiner=True, is_admin=False)
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get(
                "/api/admin/users",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
