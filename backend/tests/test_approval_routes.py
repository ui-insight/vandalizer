"""Integration tests for the approvals router (app.routers.approvals).

Verifies listing, approve, reject behavior, authorization, and edge cases.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(**overrides):
    defaults = {
        "id": "fake-id",
        "user_id": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "is_admin": False,
        "current_team": None,
        "organization_id": None,
        "is_demo_user": False,
        "demo_status": None,
    }
    defaults.update(overrides)
    user = MagicMock()
    for k, v in defaults.items():
        setattr(user, k, v)
    user.save = AsyncMock()
    return user


def _make_approval(**overrides):
    defaults = {
        "uuid": "approval-uuid-1",
        "workflow_result_id": "wfr-id-1",
        "workflow_id": "wf-id-1",
        "step_index": 0,
        "step_name": "Review Step",
        "data_for_review": {},
        "review_instructions": "Please review",
        "status": "pending",
        "assigned_to_user_ids": [],
        "reviewer_user_id": None,
        "reviewer_comments": "",
        "decision_at": None,
        "created_at": None,
    }
    defaults.update(overrides)
    approval = MagicMock()
    for k, v in defaults.items():
        setattr(approval, k, v)
    approval.save = AsyncMock()
    return approval


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


class TestListApprovals:
    @pytest.mark.asyncio
    async def test_list_as_user_sees_assigned(self, client):
        """Non-admin user sees approvals assigned to them (or unassigned)."""
        user = _make_user(user_id="alice")
        cookies, headers = _auth("alice")

        approval = _make_approval(assigned_to_user_ids=["alice"])
        mock_query = MagicMock()
        mock_query.sort = MagicMock(return_value=mock_query)
        mock_query.to_list = AsyncMock(return_value=[approval])

        with patch("app.dependencies.decode_token", return_value={"sub": "alice", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.approvals.ApprovalRequest") as MockApproval:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find = MagicMock(return_value=mock_query)
            MockApproval.created_at = MagicMock()  # supports unary negation

            resp = await client.get(
                "/api/approvals/",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "approvals" in data
        assert len(data["approvals"]) == 1
        assert data["approvals"][0]["uuid"] == "approval-uuid-1"

    @pytest.mark.asyncio
    async def test_list_as_admin_sees_all(self, client):
        """Admin user sees all approvals regardless of assignment."""
        user = _make_user(user_id="admin1", is_admin=True)
        cookies, headers = _auth("admin1")

        approval1 = _make_approval(uuid="a1", assigned_to_user_ids=["bob"])
        approval2 = _make_approval(uuid="a2", assigned_to_user_ids=[])
        mock_query = MagicMock()
        mock_query.sort = MagicMock(return_value=mock_query)
        mock_query.to_list = AsyncMock(return_value=[approval1, approval2])

        with patch("app.dependencies.decode_token", return_value={"sub": "admin1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.approvals.ApprovalRequest") as MockApproval:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find = MagicMock(return_value=mock_query)
            MockApproval.created_at = MagicMock()  # supports unary negation

            resp = await client.get(
                "/api/approvals/",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["approvals"]) == 2


class TestApprove:
    @pytest.mark.asyncio
    async def test_approve_pending(self, client):
        """Approving a pending approval succeeds and dispatches a task."""
        user = _make_user(user_id="reviewer1")
        cookies, headers = _auth("reviewer1")

        approval = _make_approval(
            status="pending",
            assigned_to_user_ids=["reviewer1"],
        )

        with patch("app.dependencies.decode_token", return_value={"sub": "reviewer1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.approvals.ApprovalRequest") as MockApproval, \
             patch("app.routers.approvals.audit_service") as mock_audit, \
             patch("app.celery_app.celery") as mock_celery:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find_one = AsyncMock(return_value=approval)
            mock_audit.log_event = AsyncMock()

            resp = await client.post(
                "/api/approvals/approval-uuid-1/approve",
                json={"comments": "Looks good"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert approval.status == "approved"
        assert approval.reviewer_user_id == "reviewer1"
        approval.save.assert_awaited_once()
        mock_celery.send_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_non_pending_returns_400(self, client):
        """Attempting to approve an already-decided approval returns 400."""
        user = _make_user(user_id="reviewer1")
        cookies, headers = _auth("reviewer1")

        approval = _make_approval(
            status="approved",
            assigned_to_user_ids=["reviewer1"],
        )

        with patch("app.dependencies.decode_token", return_value={"sub": "reviewer1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.approvals.ApprovalRequest") as MockApproval:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find_one = AsyncMock(return_value=approval)

            resp = await client.post(
                "/api/approvals/approval-uuid-1/approve",
                json={"comments": ""},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert "Cannot approve" in resp.json()["detail"]


class TestReject:
    @pytest.mark.asyncio
    async def test_reject_pending(self, client):
        """Rejecting a pending approval succeeds and marks workflow as failed."""
        user = _make_user(user_id="reviewer1")
        cookies, headers = _auth("reviewer1")

        approval = _make_approval(
            status="pending",
            assigned_to_user_ids=["reviewer1"],
        )
        mock_wf_result = MagicMock()
        mock_wf_result.save = AsyncMock()

        with patch("app.dependencies.decode_token", return_value={"sub": "reviewer1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.approvals.ApprovalRequest") as MockApproval, \
             patch("app.routers.approvals.WorkflowResult") as MockWFResult, \
             patch("app.routers.approvals.audit_service") as mock_audit:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find_one = AsyncMock(return_value=approval)
            MockWFResult.get = AsyncMock(return_value=mock_wf_result)
            mock_audit.log_event = AsyncMock()

            resp = await client.post(
                "/api/approvals/approval-uuid-1/reject",
                json={"comments": "Not ready"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert approval.status == "rejected"
        assert approval.reviewer_user_id == "reviewer1"
        approval.save.assert_awaited_once()
        assert mock_wf_result.status == "failed"

    @pytest.mark.asyncio
    async def test_reject_non_pending_returns_400(self, client):
        """Attempting to reject an already-decided approval returns 400."""
        user = _make_user(user_id="reviewer1")
        cookies, headers = _auth("reviewer1")

        approval = _make_approval(status="rejected")

        with patch("app.dependencies.decode_token", return_value={"sub": "reviewer1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.approvals.ApprovalRequest") as MockApproval:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find_one = AsyncMock(return_value=approval)

            resp = await client.post(
                "/api/approvals/approval-uuid-1/reject",
                json={"comments": ""},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert "Cannot reject" in resp.json()["detail"]


class TestAuthorizationChecks:
    @pytest.mark.asyncio
    async def test_unassigned_user_on_assigned_approval_gets_403(self, client):
        """A non-admin user not assigned and not managing the workflow is rejected."""
        user = _make_user(user_id="outsider", is_admin=False)
        cookies, headers = _auth("outsider")

        approval = _make_approval(
            status="pending",
            assigned_to_user_ids=["reviewer1", "reviewer2"],
        )

        with patch("app.dependencies.decode_token", return_value={"sub": "outsider", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.approvals.ApprovalRequest") as MockApproval, \
             patch(
                 "app.routers.approvals.access_control.get_authorized_workflow",
                 new_callable=AsyncMock,
             ) as mock_get_workflow:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find_one = AsyncMock(return_value=approval)
            mock_get_workflow.return_value = None

            resp = await client.post(
                "/api/approvals/approval-uuid-1/approve",
                json={"comments": ""},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert "Not authorized" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_unrelated_user_cannot_view_unassigned_approval(self, client):
        user = _make_user(user_id="outsider", is_admin=False)
        cookies, headers = _auth("outsider")
        approval = _make_approval(status="pending", assigned_to_user_ids=[])

        with patch("app.dependencies.decode_token", return_value={"sub": "outsider", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.approvals.ApprovalRequest") as MockApproval, \
             patch(
                 "app.routers.approvals.access_control.get_authorized_workflow",
                 new_callable=AsyncMock,
             ) as mock_get_workflow:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find_one = AsyncMock(return_value=approval)
            mock_get_workflow.return_value = None

            resp = await client.get(
                "/api/approvals/approval-uuid-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_workflow_manager_can_approve_unassigned_approval(self, client):
        user = _make_user(user_id="owner", is_admin=False)
        cookies, headers = _auth("owner")
        approval = _make_approval(status="pending", assigned_to_user_ids=[])

        with patch("app.dependencies.decode_token", return_value={"sub": "owner", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.approvals.ApprovalRequest") as MockApproval, \
             patch("app.routers.approvals.audit_service") as mock_audit, \
             patch("app.celery_app.celery") as mock_celery, \
             patch(
                 "app.routers.approvals.access_control.get_authorized_workflow",
                 new_callable=AsyncMock,
             ) as mock_get_workflow:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find_one = AsyncMock(return_value=approval)
            mock_get_workflow.return_value = object()
            mock_audit.log_event = AsyncMock()

            resp = await client.post(
                "/api/approvals/approval-uuid-1/approve",
                json={"comments": "Owner approved"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert approval.status == "approved"
        approval.save.assert_awaited_once()
        mock_celery.send_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_excludes_unrelated_unassigned_approvals(self, client):
        user = _make_user(user_id="outsider", is_admin=False)
        cookies, headers = _auth("outsider")
        approval = _make_approval(status="pending", assigned_to_user_ids=[])
        mock_query = MagicMock()
        mock_query.to_list = AsyncMock(return_value=[approval])

        with patch("app.dependencies.decode_token", return_value={"sub": "outsider", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.approvals.ApprovalRequest") as MockApproval, \
             patch(
                 "app.routers.approvals.access_control.get_authorized_workflow",
                 new_callable=AsyncMock,
             ) as mock_get_workflow:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find = MagicMock(return_value=mock_query)
            mock_get_workflow.return_value = None

            resp = await client.get(
                "/api/approvals/count",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
