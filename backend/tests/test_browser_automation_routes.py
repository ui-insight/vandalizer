"""Authorization tests for browser automation routes."""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")
_WORKFLOW_RESULT_ID = "507f1f77bcf86cd799439011"


def _make_user(user_id="user1"):
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
    user.api_token_hash = None
    user.api_token_created_at = None
    user.api_token_expires_at = None
    return user


def _auth(user_id="user1"):
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


class TestBrowserAutomationSessionAuth:
    @pytest.mark.asyncio
    async def test_create_session_allows_visible_workflow_result(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        workflow_result = MagicMock()
        workflow_result.id = "workflow-result-oid"
        workflow_result.workflow = "workflow-oid"
        workflow = MagicMock()
        workflow.user_id = "user1"
        workflow.team_id = None
        session = MagicMock()
        session.session_id = "session-1"
        session.state.value = "created"
        mock_service = MagicMock()
        mock_service.create_session.return_value = session

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.browser_automation.WorkflowResult.get", new_callable=AsyncMock) as mock_get_result,
            patch("app.routers.browser_automation.Workflow.get", new_callable=AsyncMock) as mock_get_workflow,
            patch(
                "app.routers.browser_automation.access_control.get_team_access_context",
                new_callable=AsyncMock,
            ) as mock_team_access,
            patch(
                "app.services.browser_automation.BrowserAutomationService.get_instance",
                return_value=mock_service,
            ),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_result.return_value = workflow_result
            mock_get_workflow.return_value = workflow
            mock_team_access.return_value = MagicMock()

            resp = await client.post(
                "/api/browser-automation/sessions",
                json={
                    "workflow_result_id": _WORKFLOW_RESULT_ID,
                    "allowed_domains": ["example.com"],
                },
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"session_id": "session-1", "state": "created"}
        mock_service.create_session.assert_called_once_with(
            "user1",
            "workflow-result-oid",
            ["example.com"],
        )

    @pytest.mark.asyncio
    async def test_create_session_rejects_foreign_workflow_result(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")
        workflow_result = MagicMock()
        workflow_result.id = "workflow-result-oid"
        workflow_result.workflow = "workflow-oid"
        workflow = MagicMock()
        workflow.user_id = "owner"
        workflow.team_id = None
        mock_service = MagicMock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.browser_automation.WorkflowResult.get", new_callable=AsyncMock) as mock_get_result,
            patch("app.routers.browser_automation.Workflow.get", new_callable=AsyncMock) as mock_get_workflow,
            patch(
                "app.routers.browser_automation.access_control.get_team_access_context",
                new_callable=AsyncMock,
            ) as mock_team_access,
            patch(
                "app.services.browser_automation.BrowserAutomationService.get_instance",
                return_value=mock_service,
            ),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_result.return_value = workflow_result
            mock_get_workflow.return_value = workflow
            mock_team_access.return_value = MagicMock()

            resp = await client.post(
                "/api/browser-automation/sessions",
                json={"workflow_result_id": _WORKFLOW_RESULT_ID},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Workflow result not found"
        mock_service.create_session.assert_not_called()
