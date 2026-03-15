"""Integration tests for auth router endpoints.

All tests mock the database layer so they can run without MongoDB.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token, create_refresh_token, hash_password

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(**overrides):
    """Build a mock User object."""
    defaults = {
        "id": "fake-id",
        "user_id": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "is_admin": False,
        "is_examiner": False,
        "current_team": None,
        "password_hash": hash_password("correct-password"),
        "is_demo_user": False,
        "demo_status": None,
        "api_token": None,
        "api_token_created_at": None,
    }
    defaults.update(overrides)
    user = MagicMock()
    for k, v in defaults.items():
        setattr(user, k, v)
    user.save = AsyncMock()
    user.insert = AsyncMock()
    return user


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------


class TestAuthMe:
    @pytest.mark.asyncio
    async def test_me_unauthenticated(self, client):
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_valid_token(self, client):
        user = _make_user()
        token = create_access_token("testuser", _TEST_SETTINGS)

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get(
                "/api/auth/me",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "testuser"
        assert data["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_me_with_invalid_token(self, client):
        with patch("app.dependencies.decode_token", return_value=None):
            resp = await client.get(
                "/api/auth/me",
                cookies={"access_token": "bad-token"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_refresh_token_type_rejected(self, client):
        """Access endpoints reject refresh tokens."""
        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "refresh"}):
            resp = await client.get(
                "/api/auth/me",
                cookies={"access_token": "some-token"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_demo_locked_user_blocked(self, client):
        user = _make_user(is_demo_user=True, demo_status="locked")
        token = create_access_token("testuser", _TEST_SETTINGS)

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get(
                "/api/auth/me",
                cookies={"access_token": token},
            )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "DEMO_EXPIRED"


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------


class TestAuthLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, client):
        user = _make_user()

        with patch("app.routers.auth.auth_service") as mock_svc, \
             patch("app.routers.auth.get_settings", return_value=_TEST_SETTINGS):
            mock_svc.authenticate = AsyncMock(return_value=user)
            resp = await client.post("/api/auth/login", json={
                "user_id": "testuser",
                "password": "correct-password",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "testuser"

        # Verify cookies are set
        cookies = {c.name: c for c in resp.cookies.jar}
        assert "access_token" in cookies
        assert "refresh_token" in cookies

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client):
        with patch("app.routers.auth.auth_service") as mock_svc:
            mock_svc.authenticate = AsyncMock(return_value=None)
            resp = await client.post("/api/auth/login", json={
                "user_id": "testuser",
                "password": "wrong-password",
            })

        assert resp.status_code == 401
        assert "Invalid credentials" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/auth/logout
# ---------------------------------------------------------------------------


class TestAuthLogout:
    @pytest.mark.asyncio
    async def test_logout_clears_cookies(self, client):
        resp = await client.post("/api/auth/logout")
        assert resp.status_code == 200
        # Verify cookies are set in the response (clearing them)
        set_cookie_values = resp.headers.get_list("set-cookie")
        cookie_names = [h.split("=")[0] for h in set_cookie_values]
        assert "access_token" in cookie_names
        assert "refresh_token" in cookie_names


# ---------------------------------------------------------------------------
# POST /api/auth/refresh
# ---------------------------------------------------------------------------


class TestAuthRefresh:
    @pytest.mark.asyncio
    async def test_refresh_success(self, client):
        user = _make_user()
        refresh = create_refresh_token("testuser", _TEST_SETTINGS)

        with patch("app.routers.auth.decode_token", return_value={"sub": "testuser", "type": "refresh"}), \
             patch("app.routers.auth.User") as MockUser, \
             patch("app.routers.auth.get_settings", return_value=_TEST_SETTINGS):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/auth/refresh",
                cookies={"refresh_token": refresh},
            )

        assert resp.status_code == 200
        cookies = {c.name: c for c in resp.cookies.jar}
        assert "access_token" in cookies

    @pytest.mark.asyncio
    async def test_refresh_without_token(self, client):
        resp = await client.post("/api/auth/refresh")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_type_rejected(self, client):
        """Refresh endpoint rejects access tokens."""
        with patch("app.routers.auth.decode_token", return_value={"sub": "testuser", "type": "access"}):
            resp = await client.post(
                "/api/auth/refresh",
                cookies={"refresh_token": "some-token"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------


class TestAuthRegister:
    @pytest.mark.asyncio
    async def test_register_success(self, client):
        user = _make_user()

        with patch("app.routers.auth.auth_service") as mock_svc, \
             patch("app.routers.auth.get_settings", return_value=_TEST_SETTINGS):
            mock_svc.register = AsyncMock(return_value=user)
            resp = await client.post("/api/auth/register", json={
                "email": "new@example.com",
                "password": "strong-password",
                "name": "New User",
            })

        assert resp.status_code == 200
        cookies = {c.name: c for c in resp.cookies.jar}
        assert "access_token" in cookies

    @pytest.mark.asyncio
    async def test_register_duplicate_fails(self, client):
        with patch("app.routers.auth.auth_service") as mock_svc:
            mock_svc.register = AsyncMock(side_effect=ValueError("User already exists"))
            resp = await client.post("/api/auth/register", json={
                "email": "existing@example.com",
                "password": "password",
            })

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# CSRF protection
# ---------------------------------------------------------------------------


class TestCSRFProtection:
    @pytest.mark.asyncio
    async def test_csrf_cookie_set_on_get(self, client):
        resp = await client.get("/api/health")
        set_cookie_values = resp.headers.get_list("set-cookie")
        csrf_cookies = [h for h in set_cookie_values if h.startswith("csrf_token=")]
        assert len(csrf_cookies) >= 1
        # CSRF cookie must NOT be httponly (JS needs to read it)
        assert "httponly" not in csrf_cookies[0].lower()

    @pytest.mark.asyncio
    async def test_state_changing_request_without_csrf_rejected(self, client):
        """POST to a protected endpoint without CSRF token should be rejected."""
        user = _make_user()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.put(
                "/api/auth/profile",
                json={"name": "New Name"},
                cookies={"access_token": "valid-token"},
            )

        assert resp.status_code == 403
        assert "CSRF" in resp.text

    @pytest.mark.asyncio
    async def test_state_changing_request_with_csrf_succeeds(self, client):
        """POST with matching CSRF cookie + header should pass."""
        user = _make_user()
        csrf_token = secrets.token_urlsafe(32)

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.put(
                "/api/auth/profile",
                json={"name": "New Name"},
                cookies={"access_token": "valid-token", "csrf_token": csrf_token},
                headers={"X-CSRF-Token": csrf_token},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_csrf_exempt_endpoints_work_without_token(self, client):
        """Login and other exempt endpoints should work without CSRF."""
        with patch("app.routers.auth.auth_service") as mock_svc:
            mock_svc.authenticate = AsyncMock(return_value=None)
            resp = await client.post("/api/auth/login", json={
                "user_id": "test", "password": "test",
            })
        # Should get 401 (invalid creds), not 403 (CSRF)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_auth_bypasses_csrf(self, client):
        """Requests with X-API-Key should not require CSRF tokens."""
        user = _make_user()

        with patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/workflows/run-integrated",
                json={"workflow_id": "fake", "document_uuids": []},
                headers={"X-API-Key": "test-api-key"},
            )

        # Should get past CSRF (may fail on other grounds but not 403 CSRF)
        assert "CSRF" not in resp.text
