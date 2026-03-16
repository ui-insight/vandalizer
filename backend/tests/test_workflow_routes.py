"""Integration tests for workflows router (/api/workflows).

All tests mock the database layer so they can run without MongoDB.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="testuser"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = None
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


class TestListWorkflows:
    @pytest.mark.asyncio
    async def test_list_workflows(self, client):
        """GET /api/workflows returns workflows list."""
        user = _make_user()
        cookies, headers = _auth()

        mock_wf = MagicMock()
        mock_wf.id = "wf-id-1"
        mock_wf.name = "Extract Names"
        mock_wf.description = "Extracts names from documents"
        mock_wf.user_id = "testuser"
        mock_wf.space = "default"
        mock_wf.num_executions = 5

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.list_workflows = AsyncMock(return_value=[mock_wf])

            resp = await client.get(
                "/api/workflows",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Extract Names"
        assert data[0]["num_executions"] == 5

    @pytest.mark.asyncio
    async def test_list_workflows_unauthenticated(self, client):
        """GET /api/workflows without auth returns 401."""
        resp = await client.get("/api/workflows")
        assert resp.status_code == 401


class TestCreateWorkflow:
    @pytest.mark.asyncio
    async def test_create_workflow(self, client):
        """POST /api/workflows creates a new workflow."""
        user = _make_user()
        cookies, headers = _auth()

        mock_wf = MagicMock()
        mock_wf.id = "new-wf-id"
        mock_wf.name = "New Workflow"
        mock_wf.description = "A test workflow"
        mock_wf.user_id = "testuser"
        mock_wf.space = "default"
        mock_wf.num_executions = 0

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.create_workflow = AsyncMock(return_value=mock_wf)

            resp = await client.post(
                "/api/workflows",
                json={"name": "New Workflow", "space": "default", "description": "A test workflow"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Workflow"
        assert data["description"] == "A test workflow"
        mock_svc.create_workflow.assert_called_once_with(
            "New Workflow", "testuser", "default", "A test workflow",
        )
