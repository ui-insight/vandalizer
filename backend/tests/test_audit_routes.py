"""Integration tests for audit log router endpoints.

Verifies admin-only enforcement, query parameter handling, and CSV export.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="testuser", is_admin=False):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = is_admin
    user.is_examiner = False
    user.current_team = None
    user.organization_id = None
    user.is_demo_user = False
    user.demo_status = None
    return user


def _make_audit_entry(uuid="entry-1", action="document.create"):
    entry = MagicMock()
    entry.uuid = uuid
    entry.timestamp = MagicMock()
    entry.timestamp.isoformat.return_value = "2024-01-01T00:00:00"
    entry.actor_user_id = "user-1"
    entry.actor_type = "user"
    entry.action = action
    entry.resource_type = "document"
    entry.resource_id = "doc-1"
    entry.resource_name = "test.pdf"
    entry.team_id = None
    entry.organization_id = None
    entry.detail = {}
    entry.ip_address = "127.0.0.1"
    return entry


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


class TestQueryAuditLog:
    @pytest.mark.asyncio
    async def test_non_admin_gets_403(self, client):
        user = _make_user(is_admin=False)
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get("/api/audit/", cookies=cookies, headers=headers)

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_returns_entries(self, client):
        user = _make_user(is_admin=True)
        entry = _make_audit_entry()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.audit.audit_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.query_audit_log = AsyncMock(return_value=([entry], 1))

            resp = await client.get("/api/audit/", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["entries"]) == 1
        assert body["entries"][0]["uuid"] == "entry-1"

    @pytest.mark.asyncio
    async def test_invalid_start_time_returns_400(self, client):
        user = _make_user(is_admin=True)
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                "/api/audit/?start_time=invalid",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert "start_time" in resp.json()["detail"]


class TestExportAuditLog:
    @pytest.mark.asyncio
    async def test_export_returns_csv(self, client):
        user = _make_user(is_admin=True)
        entry = _make_audit_entry()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.audit.audit_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.query_audit_log = AsyncMock(return_value=([entry], 1))

            resp = await client.get("/api/audit/export", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "timestamp" in resp.text  # CSV header row
