"""Integration tests for documents router.

Verifies team membership validation and auth enforcement.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.services.access_control import TeamAccessContext
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="testuser", current_team=None):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = current_team
    user.is_demo_user = False
    user.demo_status = None
    return user


def _auth(user_id="testuser"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


def _make_document(
    doc_uuid="doc-uuid",
    *,
    user_id="testuser",
    team_id=None,
    title="Test Document",
    classification=None,
    retention_hold=False,
):
    doc = MagicMock()
    doc.uuid = doc_uuid
    doc.user_id = user_id
    doc.team_id = team_id
    doc.title = title
    doc.classification = classification
    doc.classification_confidence = None
    doc.classified_at = None
    doc.classified_by = None
    doc.retention_hold = retention_hold
    doc.retention_hold_reason = None
    doc.scheduled_deletion_at = "scheduled" if retention_hold else None
    doc.save = AsyncMock()
    return doc


def _team_access(*, roles_by_uuid=None):
    roles_by_uuid = roles_by_uuid or {}
    return TeamAccessContext(
        team_uuids=set(roles_by_uuid.keys()),
        team_object_ids=set(),
        roles_by_uuid=roles_by_uuid,
        roles_by_object_id={},
    )


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


class TestDocumentListAuth:
    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self, client):
        resp = await client.get("/api/documents/list")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_own_documents_allowed(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.documents.document_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.list_contents = AsyncMock(return_value={"folders": [], "documents": []})

            resp = await client.get(
                "/api/documents/list",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        # Verify the current user object was passed through
        mock_svc.list_contents.assert_called_once()
        call_kwargs = mock_svc.list_contents.call_args
        assert call_kwargs.kwargs.get("user") is user


class TestDocumentTeamValidation:
    @pytest.mark.asyncio
    async def test_non_member_team_uuid_rejected(self, client):
        """User not in a team cannot access that team's documents."""
        user = _make_user()
        cookies, headers = _auth()

        mock_team = MagicMock()
        mock_team.id = "team-obj-id"
        mock_team.uuid = "other-team-uuid"

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.documents.Team") as MockTeam, \
             patch("app.routers.documents.TeamMembership") as MockMembership:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=mock_team)
            MockMembership.find_one = AsyncMock(return_value=None)  # not a member

            resp = await client.get(
                "/api/documents/list?team_uuid=other-team-uuid",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert "Not a member" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_team_member_allowed(self, client):
        """User who is a team member can access that team's documents."""
        user = _make_user()
        cookies, headers = _auth()

        mock_team = MagicMock()
        mock_team.id = "team-obj-id"
        mock_team.uuid = "my-team-uuid"

        mock_membership = MagicMock()
        mock_membership.role = "member"

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.documents.Team") as MockTeam, \
             patch("app.routers.documents.TeamMembership") as MockMembership, \
             patch("app.routers.documents.document_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=mock_team)
            MockMembership.find_one = AsyncMock(return_value=mock_membership)
            mock_svc.list_contents = AsyncMock(return_value={"folders": [], "documents": []})

            resp = await client.get(
                "/api/documents/list?team_uuid=my-team-uuid",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200


class TestDocumentSearch:
    @pytest.mark.asyncio
    async def test_search_unauthenticated(self, client):
        resp = await client.get("/api/documents/search?q=test")
        assert resp.status_code == 401


class TestDocumentGovernanceAuth:
    @pytest.mark.asyncio
    async def test_owner_can_reclassify_personal_document(self, client):
        user = _make_user("owner1")
        doc = _make_document(doc_uuid="doc-1", user_id="owner1")
        cookies, headers = _auth("owner1")

        with patch("app.dependencies.decode_token", return_value={"sub": "owner1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access()

            resp = await client.patch(
                "/api/documents/doc-1/classify",
                json={"classification": "ferpa", "reason": "Contains student records"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["classification"] == "ferpa"
        assert resp.json()["classified_by"] == "owner1"
        assert doc.classification == "ferpa"
        assert doc.classified_by == "owner1"
        doc.save.assert_awaited_once()
        mock_log_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_other_users_personal_document_cannot_be_reclassified(self, client):
        user = _make_user("outsider")
        doc = _make_document(doc_uuid="doc-2", user_id="owner1")
        cookies, headers = _auth("outsider")

        with patch("app.dependencies.decode_token", return_value={"sub": "outsider", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access()

            resp = await client.patch(
                "/api/documents/doc-2/classify",
                json={"classification": "internal"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        doc.save.assert_not_awaited()
        mock_log_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_member_cannot_reclassify_other_teams_document(self, client):
        user = _make_user("outsider")
        doc = _make_document(doc_uuid="doc-3", user_id="owner1", team_id="team-abc")
        cookies, headers = _auth("outsider")

        with patch("app.dependencies.decode_token", return_value={"sub": "outsider", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access()

            resp = await client.patch(
                "/api/documents/doc-3/classify",
                json={"classification": "internal"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        doc.save.assert_not_awaited()
        mock_log_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_team_admin_can_reclassify_team_document(self, client):
        user = _make_user("team-admin")
        doc = _make_document(doc_uuid="doc-4", user_id="owner1", team_id="team-abc")
        cookies, headers = _auth("team-admin")

        with patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access(roles_by_uuid={"team-abc": "admin"})

            resp = await client.patch(
                "/api/documents/doc-4/classify",
                json={"classification": "cui", "reason": "Contains export-controlled details"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["classification"] == "cui"
        assert doc.classification == "cui"
        doc.save.assert_awaited_once()
        mock_log_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_admin_owner_cannot_apply_retention_hold(self, client):
        user = _make_user("owner1")
        cookies, headers = _auth("owner1")

        with patch("app.dependencies.decode_token", return_value={"sub": "owner1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.documents.access_control.get_authorized_document", new_callable=AsyncMock) as mock_get_doc:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/documents/doc-5/retention-hold",
                json={"reason": "Preserve for litigation"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin access required"
        mock_get_doc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_admin_team_admin_cannot_apply_retention_hold(self, client):
        user = _make_user("team-admin")
        cookies, headers = _auth("team-admin")

        with patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.documents.access_control.get_authorized_document", new_callable=AsyncMock) as mock_get_doc:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/documents/doc-6/retention-hold",
                json={"reason": "Preserve for litigation"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin access required"
        mock_get_doc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_admin_can_apply_retention_hold_to_another_users_document(self, client):
        user = _make_user("platform-admin")
        user.is_admin = True
        doc = _make_document(doc_uuid="doc-7", user_id="owner1")
        cookies, headers = _auth("platform-admin")

        with patch("app.dependencies.decode_token", return_value={"sub": "platform-admin", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access()

            resp = await client.post(
                "/api/documents/doc-7/retention-hold",
                json={"reason": "Preserve for litigation"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["retention_hold"] is True
        assert doc.retention_hold is True
        assert doc.retention_hold_reason == "Preserve for litigation"
        assert doc.scheduled_deletion_at is None
        doc.save.assert_awaited_once()
        mock_log_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_admin_can_remove_retention_hold_from_other_teams_document(self, client):
        user = _make_user("platform-admin")
        user.is_admin = True
        doc = _make_document(
            doc_uuid="doc-8",
            user_id="owner1",
            team_id="team-abc",
            retention_hold=True,
        )
        doc.retention_hold_reason = "Existing hold"
        cookies, headers = _auth("platform-admin")

        with patch("app.dependencies.decode_token", return_value={"sub": "platform-admin", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access()

            resp = await client.delete(
                "/api/documents/doc-8/retention-hold",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["retention_hold"] is False
        assert doc.retention_hold is False
        assert doc.retention_hold_reason is None
        doc.save.assert_awaited_once()
        mock_log_event.assert_awaited_once()
