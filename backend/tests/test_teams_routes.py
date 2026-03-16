"""Integration tests for teams router (/api/teams).

All tests mock the database layer so they can run without MongoDB.
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


class TestListTeams:
    @pytest.mark.asyncio
    async def test_list_teams_authenticated(self, client):
        """GET /api/teams/ returns the user's teams."""
        user = _make_user()
        cookies, headers = _auth()

        teams_data = [
            {"id": "t1", "uuid": "uuid-1", "name": "Team Alpha", "owner_user_id": "testuser", "role": "owner"},
        ]

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.teams.team_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_user_teams = AsyncMock(return_value=teams_data)

            resp = await client.get("/api/teams/", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Team Alpha"

    @pytest.mark.asyncio
    async def test_list_teams_unauthenticated(self, client):
        """GET /api/teams/ without auth returns 401."""
        resp = await client.get("/api/teams/")
        assert resp.status_code == 401


class TestCreateTeam:
    @pytest.mark.asyncio
    async def test_create_team(self, client):
        """POST /api/teams/create creates a new team."""
        user = _make_user()
        cookies, headers = _auth()

        mock_team = MagicMock()
        mock_team.id = "new-team-id"
        mock_team.uuid = "new-uuid"
        mock_team.name = "New Team"

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.teams.team_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.create_team = AsyncMock(return_value=mock_team)

            resp = await client.post(
                "/api/teams/create",
                json={"name": "New Team"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Team"
        assert data["uuid"] == "new-uuid"
        mock_svc.create_team.assert_called_once_with("New Team", "testuser")

    @pytest.mark.asyncio
    async def test_create_team_unauthenticated(self, client):
        """POST /api/teams/create without auth returns 401 or 403 (CSRF)."""
        resp = await client.post("/api/teams/create", json={"name": "Nope"})
        assert resp.status_code in (401, 403)
