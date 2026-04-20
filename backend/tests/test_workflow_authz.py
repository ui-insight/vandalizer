"""Cross-tenant authorization tests for workflows router.

Verifies that workflow endpoints correctly enforce ownership checks by
passing ``user`` to the service layer and handling denial (None/False)
as HTTP 404.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="user1", is_admin=False, current_team=None):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = is_admin
    user.is_examiner = False
    user.current_team = current_team
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_workflow(wf_id="wf-1", user_id="user1", name="Test Workflow"):
    """Return a MagicMock that looks like a Workflow document."""
    wf = MagicMock()
    wf.id = wf_id
    wf.name = name
    wf.description = "A test workflow"
    wf.user_id = user_id
    wf.space = "default"
    wf.num_executions = 0
    wf.input_config = {}
    wf.steps = []
    return wf


# ---------------------------------------------------------------------------
# Workflow list scoping
# ---------------------------------------------------------------------------

class TestWorkflowListScoping:
    @pytest.mark.asyncio
    async def test_list_returns_only_owned_workflows(self, client):
        """The router should delegate filtering to the service layer."""
        user = _make_user("user1")
        cookies, headers = _auth("user1")

        wf = _mock_workflow(user_id="user1")

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.list_workflows = AsyncMock(return_value=[wf])

            resp = await client.get("/api/workflows", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["user_id"] == "user1"
        mock_svc.list_workflows.assert_called_once()


# ---------------------------------------------------------------------------
# Workflow GET authorization
# ---------------------------------------------------------------------------

class TestWorkflowGetAuthz:
    @pytest.mark.asyncio
    async def test_get_own_workflow_succeeds(self, client):
        """GET /api/workflows/{id} returns 200 when the service finds the workflow."""
        user = _make_user("user1")
        cookies, headers = _auth("user1")

        wf = _mock_workflow(wf_id="wf-1", user_id="user1")

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            # Service returns a dict for WorkflowResponse
            mock_svc.get_workflow = AsyncMock(return_value={
                "id": "wf-1", "name": "Test Workflow", "description": "desc",
                "user_id": "user1", "space": "default", "num_executions": 0,
            })

            resp = await client.get("/api/workflows/wf-1", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["id"] == "wf-1"

    @pytest.mark.asyncio
    async def test_get_other_users_workflow_returns_404(self, client):
        """GET /api/workflows/{id} returns 404 when the service denies access (returns None)."""
        user = _make_user("user2")
        cookies, headers = _auth("user2")

        with patch("app.dependencies.decode_token", return_value={"sub": "user2", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow = AsyncMock(return_value=None)

            resp = await client.get("/api/workflows/wf-1", cookies=cookies, headers=headers)

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Workflow UPDATE authorization
# ---------------------------------------------------------------------------

class TestWorkflowUpdateAuthz:
    @pytest.mark.asyncio
    async def test_update_own_workflow_succeeds(self, client):
        """PATCH /api/workflows/{id} returns 200 when update succeeds."""
        user = _make_user("user1")
        cookies, headers = _auth("user1")

        updated_wf = _mock_workflow(wf_id="wf-1", user_id="user1", name="Updated")

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc, \
             patch("app.services.verification_service.check_and_flag_stale_verification", new_callable=AsyncMock, return_value=False):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.update_workflow = AsyncMock(return_value=updated_wf)

            resp = await client.patch(
                "/api/workflows/wf-1",
                json={"name": "Updated"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    @pytest.mark.asyncio
    async def test_update_other_users_workflow_returns_404(self, client):
        """PATCH /api/workflows/{id} returns 404 when service returns None (unauthorized)."""
        user = _make_user("user2")
        cookies, headers = _auth("user2")

        with patch("app.dependencies.decode_token", return_value={"sub": "user2", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.update_workflow = AsyncMock(return_value=None)

            resp = await client.patch(
                "/api/workflows/wf-1",
                json={"name": "Hacked"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Workflow DELETE authorization
# ---------------------------------------------------------------------------

class TestWorkflowDeleteAuthz:
    @pytest.mark.asyncio
    async def test_delete_own_workflow_succeeds(self, client):
        """DELETE /api/workflows/{id} returns 200 when service confirms deletion."""
        user = _make_user("user1")
        cookies, headers = _auth("user1")

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.delete_workflow = AsyncMock(return_value=True)

            resp = await client.delete(
                "/api/workflows/wf-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_delete_other_users_workflow_returns_404(self, client):
        """DELETE /api/workflows/{id} returns 404 when service returns False (unauthorized)."""
        user = _make_user("user2")
        cookies, headers = _auth("user2")

        with patch("app.dependencies.decode_token", return_value={"sub": "user2", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.delete_workflow = AsyncMock(return_value=False)

            resp = await client.delete(
                "/api/workflows/wf-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Workflow step authorization
# ---------------------------------------------------------------------------

class TestWorkflowStepAuthz:
    @pytest.mark.asyncio
    async def test_add_step_to_unauthorized_workflow_returns_404(self, client):
        """POST /api/workflows/{id}/steps returns 404 when service returns None."""
        user = _make_user("user2")
        cookies, headers = _auth("user2")

        with patch("app.dependencies.decode_token", return_value={"sub": "user2", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.add_step = AsyncMock(return_value=None)

            resp = await client.post(
                "/api/workflows/wf-1/steps",
                json={"name": "New Step", "data": {}, "is_output": False},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_add_step_to_own_workflow_succeeds(self, client):
        """POST /api/workflows/{id}/steps returns 200 when service succeeds."""
        user = _make_user("user1")
        cookies, headers = _auth("user1")

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.add_step = AsyncMock(return_value={
                "id": "step-1", "name": "New Step", "data": {},
            })

            resp = await client.post(
                "/api/workflows/wf-1/steps",
                json={"name": "New Step", "data": {}, "is_output": False},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_step_from_unauthorized_workflow_returns_404(self, client):
        """DELETE /api/workflows/steps/{id} returns 404 when service returns False."""
        user = _make_user("user2")
        cookies, headers = _auth("user2")

        with patch("app.dependencies.decode_token", return_value={"sub": "user2", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.delete_step = AsyncMock(return_value=False)

            resp = await client.delete(
                "/api/workflows/steps/step-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Workflow run authorization
# ---------------------------------------------------------------------------

class TestWorkflowRunAuthz:
    """Tests for the POST /{workflow_id}/run endpoint.

    The run handler imports Workflow, PydanticObjectId, and activity_service
    locally, so we must patch at their source module paths.
    """

    _FAKE_OID = "6600000000000000000000aa"  # Valid 24-char hex for PydanticObjectId

    @pytest.mark.asyncio
    async def test_run_unauthorized_workflow_returns_404(self, client):
        """POST /api/workflows/{id}/run returns 404 when authorization fails."""
        user = _make_user("user2")
        cookies, headers = _auth("user2")

        with patch("app.dependencies.decode_token", return_value={"sub": "user2", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.get_authorized_workflow", new_callable=AsyncMock, return_value=None):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                f"/api/workflows/{self._FAKE_OID}/run",
                json={"document_uuids": ["doc-1"], "batch_mode": False},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_run_own_workflow_succeeds(self, client):
        """POST /api/workflows/{id}/run returns 200 when authorized."""
        user = _make_user("user1")
        cookies, headers = _auth("user1")

        # Mock the authorized workflow object returned by get_authorized_workflow
        mock_wf_doc = MagicMock()
        mock_wf_doc.name = "Test WF"
        mock_wf_doc.steps = [MagicMock(), MagicMock()]

        mock_activity_obj = AsyncMock()
        mock_activity_obj.id = "activity-1"

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc, \
             patch("app.routers.workflows._authorize_documents", new_callable=AsyncMock, return_value=["doc-1"]), \
             patch("app.routers.workflows.get_authorized_workflow", new_callable=AsyncMock, return_value=mock_wf_doc), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=mock_activity_obj), \
             patch("beanie.PydanticObjectId", side_effect=lambda x: x):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.run_workflow = AsyncMock(return_value="session-123")

            resp = await client.post(
                f"/api/workflows/{self._FAKE_OID}/run",
                json={"document_uuids": ["doc-1"], "batch_mode": False},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["session_id"] == "session-123"


# ---------------------------------------------------------------------------
# Duplicate authorization
# ---------------------------------------------------------------------------

class TestWorkflowDuplicateAuthz:
    @pytest.mark.asyncio
    async def test_duplicate_own_workflow_succeeds(self, client):
        """POST /api/workflows/{id}/duplicate returns 200 when service succeeds."""
        user = _make_user("user1")
        cookies, headers = _auth("user1")

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.duplicate_workflow = AsyncMock(return_value={
                "id": "wf-2", "name": "Test Workflow (copy)",
                "description": "desc", "user_id": "user1",
                "space": "default", "num_executions": 0,
            })

            resp = await client.post(
                "/api/workflows/wf-1/duplicate",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert "copy" in resp.json()["name"]

    @pytest.mark.asyncio
    async def test_duplicate_other_users_workflow_returns_404(self, client):
        """POST /api/workflows/{id}/duplicate returns 404 when service returns None."""
        user = _make_user("user2")
        cookies, headers = _auth("user2")

        with patch("app.dependencies.decode_token", return_value={"sub": "user2", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.duplicate_workflow = AsyncMock(return_value=None)

            resp = await client.post(
                "/api/workflows/wf-1/duplicate",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
