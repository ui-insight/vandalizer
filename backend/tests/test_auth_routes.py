"""Integration tests for auth router endpoints.

All tests mock the database layer so they can run without MongoDB.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.schemas.auth import UserResponse
from app.utils.security import create_access_token, create_refresh_token, hash_password

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")

_MOCK_USER_RESPONSE_DATA = {
    "id": "fake-id",
    "user_id": "testuser",
    "email": "test@example.com",
    "name": "Test User",
    "is_admin": False,
    "is_examiner": False,
    "is_support_agent": False,
    "current_team": None,
    "current_team_uuid": None,
}


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
        "api_token_hash": None,
        "api_token_created_at": None,
        "api_token_expires_at": None,
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
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.auth._user_response", new_callable=AsyncMock, return_value=_MOCK_USER_RESPONSE_DATA):
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

        mock_user_resp = UserResponse(**_MOCK_USER_RESPONSE_DATA)

        with patch("app.routers.auth.auth_service") as mock_svc, \
             patch("app.routers.auth.audit_service") as mock_audit, \
             patch("app.routers.auth.get_settings", return_value=_TEST_SETTINGS), \
             patch("app.routers.auth._user_response", new_callable=AsyncMock, return_value=mock_user_resp):
            mock_svc.authenticate = AsyncMock(return_value=user)
            mock_audit.log_event = AsyncMock()
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
             patch("app.routers.auth.get_settings", return_value=_TEST_SETTINGS), \
             patch("app.routers.auth._user_response", new_callable=AsyncMock, return_value=_MOCK_USER_RESPONSE_DATA):
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
             patch("app.routers.auth.get_settings", return_value=_TEST_SETTINGS), \
             patch("app.routers.auth._user_response", new_callable=AsyncMock, return_value=_MOCK_USER_RESPONSE_DATA):
            mock_svc.register = AsyncMock(return_value=user)
            resp = await client.post("/api/auth/register", json={
                "email": "new@example.com",
                "password": "StrongPass1",
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
                "password": "StrongPass1",
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
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.auth._user_response", new_callable=AsyncMock, return_value=_MOCK_USER_RESPONSE_DATA):
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


# ---------------------------------------------------------------------------
# Coverage expansion - profile, account delete, API tokens, auth config
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    @pytest.mark.asyncio
    async def test_update_profile_name(self, client):
        user = _make_user()
        csrf_token = secrets.token_urlsafe(32)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.auth._user_response", new_callable=AsyncMock, return_value=_MOCK_USER_RESPONSE_DATA),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.put(
                "/api/auth/profile",
                json={"name": "New Name"},
                cookies={"access_token": "valid-token", "csrf_token": csrf_token},
                headers={"X-CSRF-Token": csrf_token},
            )

        assert resp.status_code == 200
        assert user.name == "New Name"
        user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_profile_email(self, client):
        user = _make_user()
        csrf_token = secrets.token_urlsafe(32)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.auth._user_response", new_callable=AsyncMock, return_value=_MOCK_USER_RESPONSE_DATA),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.put(
                "/api/auth/profile",
                json={"email": "new@example.com"},
                cookies={"access_token": "valid-token", "csrf_token": csrf_token},
                headers={"X-CSRF-Token": csrf_token},
            )

        assert resp.status_code == 200
        assert user.email == "new@example.com"

    @pytest.mark.asyncio
    async def test_update_profile_requires_auth(self, client):
        csrf_token = secrets.token_urlsafe(32)
        resp = await client.put(
            "/api/auth/profile",
            json={"name": "Test"},
            cookies={"csrf_token": csrf_token},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert resp.status_code == 401


class TestDeleteAccountPreflight:
    @pytest.mark.asyncio
    async def test_preflight_success(self, client):
        user = _make_user()
        csrf_token = secrets.token_urlsafe(32)

        summary = {"can_delete": True, "blocking_reason": None, "document_count": 5}

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.services.account_deletion_service.get_deletion_summary", new_callable=AsyncMock, return_value=summary) as mock_summary,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/auth/account/delete/preflight",
                cookies={"access_token": "valid-token", "csrf_token": csrf_token},
                headers={"X-CSRF-Token": csrf_token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["can_delete"] is True
        assert "has_password" in data


class TestDeleteAccount:
    @pytest.mark.asyncio
    async def test_delete_account_wrong_confirmation(self, client):
        user = _make_user()
        csrf_token = secrets.token_urlsafe(32)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/auth/account/delete",
                json={"confirmation": "wrong text", "password": "correct-password"},
                cookies={"access_token": "valid-token", "csrf_token": csrf_token},
                headers={"X-CSRF-Token": csrf_token},
            )

        assert resp.status_code == 400
        assert "Confirmation text" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_account_wrong_password(self, client):
        user = _make_user()
        csrf_token = secrets.token_urlsafe(32)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.auth.auth_service") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.authenticate = AsyncMock(return_value=None)

            resp = await client.post(
                "/api/auth/account/delete",
                json={"confirmation": "DELETE MY ACCOUNT", "password": "wrong-password"},
                cookies={"access_token": "valid-token", "csrf_token": csrf_token},
                headers={"X-CSRF-Token": csrf_token},
            )

        assert resp.status_code == 401
        assert "Incorrect password" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_account_requires_password_when_set(self, client):
        user = _make_user()
        csrf_token = secrets.token_urlsafe(32)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/auth/account/delete",
                json={"confirmation": "DELETE MY ACCOUNT"},
                cookies={"access_token": "valid-token", "csrf_token": csrf_token},
                headers={"X-CSRF-Token": csrf_token},
            )

        assert resp.status_code == 400
        assert "Password is required" in resp.json()["detail"]


class TestAPITokenEndpoints:
    @pytest.mark.asyncio
    async def test_generate_api_token(self, client):
        user = _make_user()
        csrf_token = secrets.token_urlsafe(32)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/auth/api-token/generate",
                cookies={"access_token": "valid-token", "csrf_token": csrf_token},
                headers={"X-CSRF-Token": csrf_token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "api_token" in data
        assert "created_at" in data
        assert "expires_at" in data
        user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_revoke_api_token(self, client):
        user = _make_user(api_token_hash="somehash")
        csrf_token = secrets.token_urlsafe(32)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/auth/api-token/revoke",
                cookies={"access_token": "valid-token", "csrf_token": csrf_token},
                headers={"X-CSRF-Token": csrf_token},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert user.api_token_hash is None
        user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_api_token_status_no_token(self, client):
        user = _make_user()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get(
                "/api/auth/api-token/status",
                cookies={"access_token": "valid-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_token"] is False
        assert data["created_at"] is None

    @pytest.mark.asyncio
    async def test_api_token_status_with_token(self, client):
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(days=365)
        user = _make_user(
            api_token_hash="somehash",
            api_token_created_at=now,
            api_token_expires_at=expires,
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get(
                "/api/auth/api-token/status",
                cookies={"access_token": "valid-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_token"] is True
        assert data["expired"] is False

    @pytest.mark.asyncio
    async def test_api_token_requires_auth(self, client):
        resp = await client.get("/api/auth/api-token/status")
        assert resp.status_code == 401


@pytest.mark.skip(reason="Auth config route accesses Beanie models directly; needs Tier 2 integration test")
class TestAuthConfig:
    @pytest.mark.asyncio
    async def test_auth_config_returns_methods(self, client):
        mock_config = MagicMock()
        mock_config.auth_methods = ["local"]
        mock_config.oauth_providers = []

        with patch("app.routers.auth.SystemConfig") as MockConfig:
            MockConfig.get_config = AsyncMock(return_value=mock_config)
            resp = await client.get("/api/auth/config")

        assert resp.status_code == 200
        data = resp.json()
        assert "auth_methods" in data
        assert data["auth_methods"] == ["local"]

    @pytest.mark.asyncio
    async def test_auth_config_with_oauth(self, client):
        mock_config = MagicMock()
        mock_config.auth_methods = ["local", "oauth"]
        mock_config.oauth_providers = [
            {
                "provider": "azure",
                "enabled": True,
                "client_id": "id",
                "client_secret": "secret",
                "tenant_id": "tenant",
                "label": "Sign in with Azure",
            }
        ]

        with patch("app.routers.auth.SystemConfig") as MockConfig:
            MockConfig.get_config = AsyncMock(return_value=mock_config)
            resp = await client.get("/api/auth/config")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["oauth_providers"]) == 1
        assert data["oauth_providers"][0]["configured"] is True
        assert data["oauth_providers"][0]["display_name"] == "Sign in with Azure"

    @pytest.mark.asyncio
    async def test_auth_config_with_unconfigured_oauth(self, client):
        mock_config = MagicMock()
        mock_config.auth_methods = ["local", "oauth"]
        mock_config.oauth_providers = []

        with patch("app.routers.auth.SystemConfig") as MockConfig:
            MockConfig.get_config = AsyncMock(return_value=mock_config)
            resp = await client.get("/api/auth/config")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["oauth_providers"]) == 1
        assert data["oauth_providers"][0]["configured"] is False


class TestPasswordValidation:
    @pytest.mark.asyncio
    async def test_register_weak_password_rejected(self, client):
        """Password missing uppercase/digit should be rejected by Pydantic."""
        resp = await client.post("/api/auth/register", json={
            "email": "new@example.com",
            "password": "weakpass",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_short_password_rejected(self, client):
        resp = await client.post("/api/auth/register", json={
            "email": "new@example.com",
            "password": "Ab1",
        })
        assert resp.status_code == 422
