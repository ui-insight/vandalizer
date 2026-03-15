"""Integration tests for documents router.

Verifies team membership validation and auth enforcement.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
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
        resp = await client.get("/api/documents/list?space=default")
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
                "/api/documents/list?space=default",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        # Verify user_id was passed
        mock_svc.list_contents.assert_called_once()
        call_kwargs = mock_svc.list_contents.call_args
        assert call_kwargs.kwargs.get("user_id") == "testuser"


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
                "/api/documents/list?space=default&team_uuid=other-team-uuid",
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
                "/api/documents/list?space=default&team_uuid=my-team-uuid",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200


class TestDocumentSearch:
    @pytest.mark.asyncio
    async def test_search_unauthenticated(self, client):
        resp = await client.get("/api/documents/search?q=test")
        assert resp.status_code == 401
