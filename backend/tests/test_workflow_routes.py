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
        mock_wf.team_id = None
        mock_wf.space = "default"
        mock_wf.num_executions = 5

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc, \
             patch("app.routers.workflows.resolve_authors", AsyncMock(return_value={})), \
             patch("app.routers.workflows.access_control") as mock_ac:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.list_workflows = AsyncMock(return_value=[mock_wf])
            mock_ac.get_team_access_context = AsyncMock(return_value=MagicMock())
            mock_ac.can_manage_workflow = MagicMock(return_value=True)

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
        assert data[0]["team_id"] is None
        assert data[0]["can_manage"] is True

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
        mock_wf.team_id = None
        mock_wf.space = "default"
        mock_wf.num_executions = 0

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc, \
             patch("app.routers.workflows.resolve_author", AsyncMock(return_value=None)):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.create_workflow = AsyncMock(return_value=mock_wf)

            resp = await client.post(
                "/api/workflows",
                json={"name": "New Workflow", "description": "A test workflow"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Workflow"
        assert data["description"] == "A test workflow"
        mock_svc.create_workflow.assert_called_once_with(
            "New Workflow", "testuser", "A test workflow", team_id=None,
        )


class TestRemoveWorkflowFromTeam:
    """DELETE /api/workflows/{id}/team — unset team_id without deleting the workflow."""

    @pytest.mark.asyncio
    async def test_remove_from_team_success(self, client):
        """A successful removal returns 200 with team_id=None on the response."""
        user = _make_user()
        cookies, headers = _auth()

        mock_wf = MagicMock()
        mock_wf.id = "wf-1"
        mock_wf.name = "Shared Workflow"
        mock_wf.description = None
        mock_wf.user_id = "testuser"
        mock_wf.team_id = None  # service has already unset it
        mock_wf.created_by_user_id = "testuser"
        mock_wf.num_executions = 0
        mock_wf.input_config = {}
        mock_wf.output_config = {}

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc, \
             patch("app.routers.workflows.resolve_author", AsyncMock(return_value=None)):
            MockUser.find_one = AsyncMock(return_value=user)
            # Important: re-export the exception class so the router can catch it
            from app.services.workflow_service import WorkflowNotInTeam
            mock_svc.WorkflowNotInTeam = WorkflowNotInTeam
            mock_svc.remove_workflow_from_team = AsyncMock(return_value=mock_wf)

            resp = await client.delete(
                "/api/workflows/wf-1/team",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "wf-1"
        assert data["team_id"] is None
        mock_svc.remove_workflow_from_team.assert_called_once_with("wf-1", user=user)

    @pytest.mark.asyncio
    async def test_remove_from_team_not_found_or_unauthorized(self, client):
        """Service returning None (missing or non-manager) surfaces as 404."""
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            from app.services.workflow_service import WorkflowNotInTeam
            mock_svc.WorkflowNotInTeam = WorkflowNotInTeam
            mock_svc.remove_workflow_from_team = AsyncMock(return_value=None)

            resp = await client.delete(
                "/api/workflows/wf-1/team",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Workflow not found"

    @pytest.mark.asyncio
    async def test_remove_from_team_when_not_in_team(self, client):
        """Removing from team when team_id is already None returns 400."""
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            from app.services.workflow_service import WorkflowNotInTeam
            mock_svc.WorkflowNotInTeam = WorkflowNotInTeam
            mock_svc.remove_workflow_from_team = AsyncMock(side_effect=WorkflowNotInTeam())

            resp = await client.delete(
                "/api/workflows/wf-1/team",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Workflow is not in a team"

    @pytest.mark.asyncio
    async def test_remove_from_team_unauthenticated(self, client):
        """DELETE without auth/CSRF is rejected. The CSRF middleware fires
        before auth here, so we expect 403 (not 401)."""
        resp = await client.delete("/api/workflows/wf-1/team")
        assert resp.status_code == 403
