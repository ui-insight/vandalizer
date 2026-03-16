"""Integration tests for organization router endpoints.

Verifies admin-only enforcement and correct service delegation.
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
    user.save = AsyncMock()
    return user


def _make_org(uuid="org-1", name="Test Org", org_type="department", parent_id=None):
    org = MagicMock()
    org.uuid = uuid
    org.name = name
    org.org_type = org_type
    org.parent_id = parent_id
    org.metadata = {}
    org.created_at = MagicMock()
    org.created_at.isoformat.return_value = "2024-01-01T00:00:00"
    org.updated_at = MagicMock()
    org.updated_at.isoformat.return_value = "2024-01-01T00:00:00"
    return org


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


class TestGetOrgTree:
    @pytest.mark.asyncio
    async def test_returns_tree(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.organizations.organization_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_org_tree = AsyncMock(return_value=[{"uuid": "root", "name": "Univ", "children": []}])

            resp = await client.get("/api/organizations/tree", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        assert "tree" in body
        assert len(body["tree"]) == 1
        assert body["tree"][0]["uuid"] == "root"


class TestCreateOrganization:
    @pytest.mark.asyncio
    async def test_admin_creates_org(self, client):
        user = _make_user(is_admin=True)
        org = _make_org(uuid="new-org")
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.organizations.organization_service") as mock_svc, \
             patch("app.routers.organizations.audit_service") as mock_audit:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.create_organization = AsyncMock(return_value=org)
            mock_audit.log_event = AsyncMock()

            resp = await client.post(
                "/api/organizations/",
                json={"name": "New Org", "org_type": "department"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["uuid"] == "new-org"

    @pytest.mark.asyncio
    async def test_non_admin_gets_403(self, client):
        user = _make_user(is_admin=False)
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/organizations/",
                json={"name": "New Org", "org_type": "department"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403


class TestUpdateOrganization:
    @pytest.mark.asyncio
    async def test_admin_updates(self, client):
        user = _make_user(is_admin=True)
        org = _make_org(uuid="org-1", name="Updated")
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.organizations.organization_service") as mock_svc, \
             patch("app.routers.organizations.audit_service") as mock_audit:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.update_organization = AsyncMock(return_value=org)
            mock_audit.log_event = AsyncMock()

            resp = await client.put(
                "/api/organizations/org-1",
                json={"name": "Updated"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"


class TestDeleteOrganization:
    @pytest.mark.asyncio
    async def test_admin_deletes(self, client):
        user = _make_user(is_admin=True)
        org = _make_org(uuid="org-1")
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.organizations.organization_service") as mock_svc, \
             patch("app.routers.organizations.audit_service") as mock_audit:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_organization = AsyncMock(return_value=org)
            mock_svc.delete_organization = AsyncMock()
            mock_audit.log_event = AsyncMock()

            resp = await client.delete(
                "/api/organizations/org-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["detail"] == "Organization deleted"

    @pytest.mark.asyncio
    async def test_non_admin_gets_403(self, client):
        user = _make_user(is_admin=False)
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.delete(
                "/api/organizations/org-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403


class TestAssignUserToOrg:
    @pytest.mark.asyncio
    async def test_admin_assigns_user(self, client):
        admin = _make_user(is_admin=True)
        org = _make_org(uuid="org-1")
        target_user = _make_user(user_id="target")
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.organizations.organization_service") as mock_svc, \
             patch("app.routers.organizations.User") as MockRouterUser:
            MockUser.find_one = AsyncMock(return_value=admin)
            mock_svc.get_organization = AsyncMock(return_value=org)
            MockRouterUser.find_one = AsyncMock(return_value=target_user)

            resp = await client.post(
                "/api/organizations/org-1/assign-user/target",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert "assigned" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_non_admin_gets_403(self, client):
        user = _make_user(is_admin=False)
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/organizations/org-1/assign-user/target",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
