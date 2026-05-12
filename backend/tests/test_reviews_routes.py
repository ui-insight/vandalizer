"""Unit tests for the /api/reviews router and approval_service helpers."""

import datetime
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.services.approval_service import detect_artifact_kind
from app.utils.security import create_access_token


_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="reviewer1", is_admin=False, current_team=None):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = user_id.title()
    user.is_admin = is_admin
    user.is_examiner = False
    user.current_team = current_team
    user.organization_id = None
    user.is_demo_user = False
    user.demo_status = None
    return user


def _make_approval(uuid="appr-1", status="pending", assigned=("reviewer1",)):
    a = MagicMock()
    a.uuid = uuid
    a.workflow_result_id = "wfr-id"
    a.workflow_id = "wf-id"
    a.step_index = 1
    a.step_name = "Approval"
    a.workflow_name = "Test workflow"
    a.requester_user_id = "owner1"
    a.team_id = None
    a.source_doc_uuids = []
    a.artifact_kind = "json"
    a.data_for_review = {"value": "raw"}
    a.edited_artifact = None
    a.review_instructions = "check it"
    a.assignee_role = "specific_users"
    a.assigned_to_user_ids = list(assigned)
    a.expires_at = None
    a.timeout_action = "none"
    a.escalation_user_ids = []
    a.status = status
    a.reviewer_user_id = None
    a.reviewer_comments = ""
    a.decision_at = None
    a.expired_at = None
    a.escalated_at = None
    a.created_at = datetime.datetime(2026, 5, 5, tzinfo=datetime.timezone.utc)
    a.save = AsyncMock()
    return a


def _auth(user_id="reviewer1"):
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
# detect_artifact_kind
# ---------------------------------------------------------------------------


class TestDetectArtifactKind:
    def test_string_plain(self):
        assert detect_artifact_kind("hello world") == "text"

    def test_string_markdown(self):
        assert detect_artifact_kind("# Title\n\nbody") == "markdown"

    def test_dict_extraction(self):
        assert detect_artifact_kind({"pi": "Smith", "amount": "$100"}) == "extraction_table"

    def test_dict_nested_json(self):
        assert detect_artifact_kind({"items": [1, 2]}) == "json"

    def test_list_of_dicts_extraction(self):
        assert detect_artifact_kind([{"a": "1"}, {"a": "2"}]) == "extraction_table"

    def test_document_render(self):
        assert detect_artifact_kind({"type": "file_download", "url": "u"}) == "document_render"

    def test_none_unknown(self):
        assert detect_artifact_kind(None) == "unknown"


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


class TestReviewAuthorization:
    @pytest.mark.asyncio
    async def test_assignee_can_view(self, client):
        user = _make_user("reviewer1")
        approval = _make_approval(assigned=("reviewer1",))
        cookies, headers = _auth("reviewer1")

        with patch("app.dependencies.decode_token", return_value={"sub": "reviewer1", "type": "access"}), \
             patch("app.dependencies.User") as MockDepUser, \
             patch("app.routers.reviews.User") as MockReviewsUser, \
             patch("app.routers.reviews.ApprovalRequest") as MockApproval, \
             patch("app.routers.reviews.SmartDocument") as MockDoc:
            MockDepUser.find_one = AsyncMock(return_value=user)
            MockReviewsUser.find_one = AsyncMock(return_value=user)
            MockReviewsUser.user_id = MagicMock()
            MockApproval.find_one = AsyncMock(return_value=approval)
            doc_q = MagicMock(); doc_q.to_list = AsyncMock(return_value=[])
            MockDoc.find = MagicMock(return_value=doc_q)

            resp = await client.get(
                f"/api/reviews/{approval.uuid}",
                cookies=cookies,
                headers=headers,
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["uuid"] == approval.uuid
        assert body["artifact_kind"] == "json"

    @pytest.mark.asyncio
    async def test_non_assignee_gets_404(self, client):
        user = _make_user("randomuser")
        approval = _make_approval(assigned=("reviewer1",))
        cookies, headers = _auth("randomuser")

        with patch("app.dependencies.decode_token", return_value={"sub": "randomuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.reviews.ApprovalRequest") as MockApproval, \
             patch(
                 "app.routers.reviews.access_control.get_authorized_workflow",
                 new_callable=AsyncMock,
                 return_value=None,
             ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find_one = AsyncMock(return_value=approval)

            resp = await client.get(
                f"/api/reviews/{approval.uuid}",
                cookies=cookies,
                headers=headers,
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Approve endpoint with edited_artifact
# ---------------------------------------------------------------------------


class TestApproveWithEdit:
    @pytest.mark.asyncio
    async def test_approve_persists_edited_artifact_and_resumes(self, client):
        from app.celery_app import celery

        user = _make_user("reviewer1")
        approval = _make_approval(assigned=("reviewer1",))
        cookies, headers = _auth("reviewer1")

        with patch("app.dependencies.decode_token", return_value={"sub": "reviewer1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.reviews.ApprovalRequest") as MockApproval, \
             patch("app.routers.reviews.audit_service") as mock_audit, \
             patch("app.routers.reviews._notify_owner", new_callable=AsyncMock), \
             patch.object(celery, "send_task") as mock_send:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find_one = AsyncMock(return_value=approval)
            mock_audit.log_event = AsyncMock()

            resp = await client.post(
                f"/api/reviews/{approval.uuid}/approve",
                json={"comments": "fix LGTM", "edited_artifact": {"pi": "Dr. Smith"}},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        assert approval.status == "approved"
        assert approval.reviewer_user_id == "reviewer1"
        assert approval.edited_artifact == {"pi": "Dr. Smith"}
        approval.save.assert_awaited()
        mock_send.assert_called_once_with(
            "tasks.workflow.resume_after_approval",
            kwargs={"approval_uuid": approval.uuid},
            queue="workflows",
        )

    @pytest.mark.asyncio
    async def test_cannot_approve_resolved(self, client):
        user = _make_user("reviewer1")
        approval = _make_approval(status="approved", assigned=("reviewer1",))
        cookies, headers = _auth("reviewer1")

        with patch("app.dependencies.decode_token", return_value={"sub": "reviewer1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.reviews.ApprovalRequest") as MockApproval:
            MockUser.find_one = AsyncMock(return_value=user)
            MockApproval.find_one = AsyncMock(return_value=approval)

            resp = await client.post(
                f"/api/reviews/{approval.uuid}/approve",
                json={"comments": "x"},
                cookies=cookies,
                headers=headers,
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Assignee resolution (sync, used by Celery worker)
# ---------------------------------------------------------------------------


class TestAssigneeResolutionSync:
    def test_specific_users(self):
        from app.services.approval_service import resolve_assignees_sync
        db = MagicMock()
        wf = {"user_id": "owner1", "team_id": None}
        out = resolve_assignees_sync(db, "specific_users", wf, ["a", "b"])
        assert out == ["a", "b"]

    def test_workflow_owner(self):
        from app.services.approval_service import resolve_assignees_sync
        db = MagicMock()
        wf = {"user_id": "owner1", "team_id": None}
        out = resolve_assignees_sync(db, "workflow_owner", wf, [])
        assert out == ["owner1"]

    def test_team_admins_with_no_team_falls_back_to_owner(self):
        from app.services.approval_service import resolve_assignees_sync
        db = MagicMock()
        wf = {"user_id": "owner1", "team_id": None}
        out = resolve_assignees_sync(db, "team_admins", wf, [])
        assert out == ["owner1"]

    def test_team_admins_filters_membership(self):
        from app.services.approval_service import resolve_assignees_sync
        from bson import ObjectId

        team_oid = ObjectId()
        db = MagicMock()
        db.team_membership.find = MagicMock(return_value=iter([
            {"user_id": "a", "role": "owner"},
            {"user_id": "b", "role": "admin"},
            {"user_id": "c", "role": "member"},
        ]))
        wf = {"user_id": "owner1", "team_id": str(team_oid)}
        out = resolve_assignees_sync(db, "team_admins", wf, [])
        assert set(out) == {"a", "b"}
