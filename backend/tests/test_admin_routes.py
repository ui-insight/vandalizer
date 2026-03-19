"""Route tests for admin analytics scoping."""

import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(
    user_id: str = "team-admin",
    *,
    is_admin: bool = False,
    is_examiner: bool = False,
    current_team: str | None = None,
):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = is_admin
    user.is_examiner = is_examiner
    user.current_team = current_team
    user.is_demo_user = False
    user.demo_status = None
    return user


def _auth(user_id: str = "team-admin"):
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


class TestAdminAnalyticsScoping:
    @pytest.mark.asyncio
    async def test_non_admin_rejected(self, client):
        user = _make_user("testuser", is_admin=False)
        cookies, headers = _auth("testuser")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/admin/usage", cookies=cookies, headers=headers)

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, client):
        user = _make_user("testuser", is_admin=True)
        cookies, headers = _auth("testuser")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.ActivityEvent") as MockActivity,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_find = MagicMock()
            mock_find.to_list = AsyncMock(return_value=[])
            MockActivity.find = MagicMock(return_value=mock_find)
            MockActivity.find_one = AsyncMock(return_value=None)

            resp = await client.get("/api/admin/usage", cookies=cookies, headers=headers)

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_examiner_cannot_access_admin_dashboard(self, client):
        user = _make_user("testuser", is_examiner=True, is_admin=False)
        cookies, headers = _auth("testuser")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/admin/usage", cookies=cookies, headers=headers)

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self, client):
        resp = await client.get("/api/admin/usage")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_examiner_cannot_access_user_leaderboard(self, client):
        user = _make_user("testuser", is_examiner=True, is_admin=False)
        cookies, headers = _auth("testuser")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/admin/users", cookies=cookies, headers=headers)

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_team_admin_user_leaderboard_hides_platform_role_flags(self, client):
        team_admin = _make_user("team-admin", current_team="0123456789abcdef01234567")
        cookies, headers = _auth("team-admin")
        activity_event = SimpleNamespace(
            user_id="member-1",
            tokens_input=5,
            tokens_output=7,
            type="workflow_run",
            started_at=None,
        )
        team_membership = SimpleNamespace(user_id="member-1")
        target_user = SimpleNamespace(
            user_id="member-1",
            name="Member One",
            email="member-1@example.com",
            is_admin=True,
            is_examiner=True,
        )

        activity_find = MagicMock()
        activity_find.to_list = AsyncMock(return_value=[activity_event])
        memberships_find = MagicMock()
        memberships_find.to_list = AsyncMock(return_value=[team_membership])
        users_find = MagicMock()
        users_find.to_list = AsyncMock(return_value=[target_user])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.admin._require_admin_or_team_admin",
                new=AsyncMock(return_value=(team_admin, "0123456789abcdef01234567")),
            ),
            patch("app.routers.admin.ActivityEvent") as MockActivityEvent,
            patch("app.routers.admin.TeamMembership") as MockTeamMembership,
            patch("app.routers.admin.User") as MockRouteUser,
        ):
            MockUser.find_one = AsyncMock(return_value=team_admin)
            MockActivityEvent.find.return_value = activity_find
            MockTeamMembership.find.return_value = memberships_find
            MockRouteUser.find.return_value = users_find

            resp = await client.get("/api/admin/users", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["user_id"] == "member-1"
        assert data[0]["is_admin"] is False
        assert data[0]["is_examiner"] is False

    @pytest.mark.asyncio
    async def test_team_admin_user_detail_scopes_document_count_and_hides_platform_role_flags(self, client):
        team_admin = _make_user("team-admin", current_team="0123456789abcdef01234567")
        cookies, headers = _auth("team-admin")
        target_user = SimpleNamespace(
            user_id="member-1",
            name="Member One",
            email="member-1@example.com",
            is_admin=True,
            is_examiner=True,
        )
        team = SimpleNamespace(id="team-object-id", uuid="team-uuid", name="Team One")

        events_find = MagicMock()
        events_find.to_list = AsyncMock(return_value=[])
        recent_find = MagicMock()
        recent_find.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
        documents_find = MagicMock()
        documents_find.count = AsyncMock(return_value=3)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.admin._require_admin_or_team_admin",
                new=AsyncMock(return_value=(team_admin, "0123456789abcdef01234567")),
            ),
            patch("app.routers.admin.TeamMembership") as MockTeamMembership,
            patch("app.routers.admin.Team") as MockTeam,
            patch("app.routers.admin.User") as MockRouteUser,
            patch("app.routers.admin.ActivityEvent") as MockActivityEvent,
            patch("app.routers.admin.SmartDocument") as MockSmartDocument,
        ):
            MockUser.find_one = AsyncMock(return_value=team_admin)
            MockTeamMembership.find_one = AsyncMock(return_value=SimpleNamespace(user_id="member-1"))
            MockTeam.find_one = AsyncMock(return_value=team)
            MockRouteUser.find_one = AsyncMock(return_value=target_user)
            MockActivityEvent.find.side_effect = [events_find, recent_find]
            MockSmartDocument.find.return_value = documents_find

            resp = await client.get("/api/admin/users/member-1/detail", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_admin"] is False
        assert data["is_examiner"] is False
        assert data["document_count"] == 3
        query = MockSmartDocument.find.call_args.args[0]
        assert query["user_id"] == "member-1"
        assert query["team_id"]["$in"] == [
            "0123456789abcdef01234567",
            "team-object-id",
            "team-uuid",
        ]

    @pytest.mark.asyncio
    async def test_team_detail_counts_only_team_scoped_documents(self, client):
        team_admin = _make_user("team-admin", current_team="0123456789abcdef01234567")
        cookies, headers = _auth("team-admin")
        team = SimpleNamespace(id="team-object-id", uuid="team-uuid", name="Team One")
        team_membership = SimpleNamespace(user_id="member-1", role="admin")
        target_user = SimpleNamespace(user_id="member-1", name="Member One", email="member-1@example.com")

        events_find = MagicMock()
        events_find.to_list = AsyncMock(return_value=[])
        recent_find = MagicMock()
        recent_find.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
        memberships_find = MagicMock()
        memberships_find.to_list = AsyncMock(return_value=[team_membership])
        users_find = MagicMock()
        users_find.to_list = AsyncMock(return_value=[target_user])
        documents_find = MagicMock()
        documents_find.count = AsyncMock(return_value=7)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.admin._require_admin_or_team_admin",
                new=AsyncMock(return_value=(team_admin, "0123456789abcdef01234567")),
            ),
            patch("app.routers.admin.Team") as MockTeam,
            patch("app.routers.admin.TeamMembership") as MockTeamMembership,
            patch("app.routers.admin.User") as MockRouteUser,
            patch("app.routers.admin.ActivityEvent") as MockActivityEvent,
            patch("app.routers.admin.SmartDocument") as MockSmartDocument,
        ):
            MockUser.find_one = AsyncMock(return_value=team_admin)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTeamMembership.find.return_value = memberships_find
            MockRouteUser.find.return_value = users_find
            MockActivityEvent.find.side_effect = [events_find, recent_find]
            MockSmartDocument.find.return_value = documents_find

            resp = await client.get(
                "/api/admin/teams/0123456789abcdef01234567/detail",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["document_count"] == 7
        query = MockSmartDocument.find.call_args.args[0]
        assert query["team_id"]["$in"] == [
            "0123456789abcdef01234567",
            "team-object-id",
            "team-uuid",
        ]
