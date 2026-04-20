"""Cross-tenant authorization tests for teams and organizations routers.

Verifies that team membership endpoints enforce membership checks and that
organization admin endpoints reject non-admin users.
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
    user.organization_id = None
    user.api_token_hash = None
    user.api_token_created_at = None
    user.api_token_expires_at = None
    return user


def _auth(user_id="user1"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


def _mock_team(team_id="team-obj-id", uuid="team-uuid-1", name="Test Team"):
    """Return a MagicMock that looks like a Team document."""
    team = MagicMock()
    team.id = team_id
    team.uuid = uuid
    team.name = name
    return team


def _mock_membership(user_id="user1", role="member"):
    """Return a MagicMock that looks like a TeamMembership document."""
    membership = MagicMock()
    membership.user_id = user_id
    membership.role = role
    return membership


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
# List members authorization
# ---------------------------------------------------------------------------

class TestListMembersAuthz:
    @pytest.mark.asyncio
    async def test_member_can_list_members(self, client):
        """GET /api/teams/{uuid}/members returns 200 for a team member."""
        user = _make_user("user1")
        cookies, headers = _auth("user1")
        team = _mock_team()
        membership = _mock_membership("user1", role="member")

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.teams.Team") as MockTeam, \
             patch("app.routers.teams.TeamMembership") as MockMembership, \
             patch("app.routers.teams.team_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockMembership.find_one = AsyncMock(return_value=membership)
            mock_svc.get_team_members = AsyncMock(return_value=[
                {"user_id": "user1", "role": "member", "email": "user1@example.com"},
            ])

            resp = await client.get(
                "/api/teams/team-uuid-1/members",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, client):
        """GET /api/teams/{uuid}/members returns 403 for a non-member."""
        user = _make_user("outsider", is_admin=False)
        cookies, headers = _auth("outsider")
        team = _mock_team()

        with patch("app.dependencies.decode_token", return_value={"sub": "outsider", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.teams.Team") as MockTeam, \
             patch("app.routers.teams.TeamMembership") as MockMembership:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockMembership.find_one = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/teams/team-uuid-1/members",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert "not a member" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_admin_can_list_any_team_members(self, client):
        """GET /api/teams/{uuid}/members returns 200 for a global admin even without membership."""
        user = _make_user("admin-user", is_admin=True)
        cookies, headers = _auth("admin-user")
        team = _mock_team()

        with patch("app.dependencies.decode_token", return_value={"sub": "admin-user", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.teams.Team") as MockTeam, \
             patch("app.routers.teams.TeamMembership") as MockMembership, \
             patch("app.routers.teams.team_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=team)
            # Admin has no membership record for this team
            MockMembership.find_one = AsyncMock(return_value=None)
            mock_svc.get_team_members = AsyncMock(return_value=[
                {"user_id": "someone", "role": "owner", "email": "someone@example.com"},
            ])

            resp = await client.get(
                "/api/teams/team-uuid-1/members",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_nonexistent_team_returns_404(self, client):
        """GET /api/teams/{uuid}/members returns 404 if the team does not exist."""
        user = _make_user("user1")
        cookies, headers = _auth("user1")

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.teams.Team") as MockTeam:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/teams/nonexistent-uuid/members",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List invites authorization
# ---------------------------------------------------------------------------

class TestListInvitesAuthz:
    @pytest.mark.asyncio
    async def test_team_admin_can_list_invites(self, client):
        """GET /api/teams/{uuid}/invites returns 200 for a team admin."""
        user = _make_user("team-admin")
        cookies, headers = _auth("team-admin")
        team = _mock_team()
        membership = _mock_membership("team-admin", role="admin")

        with patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.teams.Team") as MockTeam, \
             patch("app.routers.teams.TeamMembership") as MockMembership, \
             patch("app.routers.teams.team_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockMembership.find_one = AsyncMock(return_value=membership)
            mock_svc.get_team_invites = AsyncMock(return_value=[])

            resp = await client.get(
                "/api/teams/team-uuid-1/invites",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_team_owner_can_list_invites(self, client):
        """GET /api/teams/{uuid}/invites returns 200 for a team owner."""
        user = _make_user("team-owner")
        cookies, headers = _auth("team-owner")
        team = _mock_team()
        membership = _mock_membership("team-owner", role="owner")

        with patch("app.dependencies.decode_token", return_value={"sub": "team-owner", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.teams.Team") as MockTeam, \
             patch("app.routers.teams.TeamMembership") as MockMembership, \
             patch("app.routers.teams.team_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockMembership.find_one = AsyncMock(return_value=membership)
            mock_svc.get_team_invites = AsyncMock(return_value=[])

            resp = await client.get(
                "/api/teams/team-uuid-1/invites",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_team_member_cannot_list_invites(self, client):
        """GET /api/teams/{uuid}/invites returns 403 for a regular member (not admin/owner)."""
        user = _make_user("regular-member")
        cookies, headers = _auth("regular-member")
        team = _mock_team()
        membership = _mock_membership("regular-member", role="member")

        with patch("app.dependencies.decode_token", return_value={"sub": "regular-member", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.teams.Team") as MockTeam, \
             patch("app.routers.teams.TeamMembership") as MockMembership:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockMembership.find_one = AsyncMock(return_value=membership)

            resp = await client.get(
                "/api/teams/team-uuid-1/invites",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert "admin or owner" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, client):
        """GET /api/teams/{uuid}/invites returns 403 for a non-member."""
        user = _make_user("outsider", is_admin=False)
        cookies, headers = _auth("outsider")
        team = _mock_team()

        with patch("app.dependencies.decode_token", return_value={"sub": "outsider", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.teams.Team") as MockTeam, \
             patch("app.routers.teams.TeamMembership") as MockMembership:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockMembership.find_one = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/teams/team-uuid-1/invites",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_global_admin_can_list_invites_without_membership(self, client):
        """GET /api/teams/{uuid}/invites returns 200 for a global admin even without membership."""
        user = _make_user("super-admin", is_admin=True)
        cookies, headers = _auth("super-admin")
        team = _mock_team()

        with patch("app.dependencies.decode_token", return_value={"sub": "super-admin", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.teams.Team") as MockTeam, \
             patch("app.routers.teams.TeamMembership") as MockMembership, \
             patch("app.routers.teams.team_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockMembership.find_one = AsyncMock(return_value=None)
            mock_svc.get_team_invites = AsyncMock(return_value=[])

            resp = await client.get(
                "/api/teams/team-uuid-1/invites",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Organization authorization (admin-only endpoints)
# ---------------------------------------------------------------------------

class TestOrganizationAuthz:
    @pytest.mark.asyncio
    async def test_non_admin_cannot_access_org_tree(self, client):
        """GET /api/organizations/tree returns 403 for a non-admin user."""
        user = _make_user("regular-user", is_admin=False)
        cookies, headers = _auth("regular-user")

        with patch("app.dependencies.decode_token", return_value={"sub": "regular-user", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                "/api/organizations/tree",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert "admin" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_admin_can_access_org_tree(self, client):
        """GET /api/organizations/tree returns 200 for an admin user."""
        user = _make_user("admin-user", is_admin=True)
        cookies, headers = _auth("admin-user")

        with patch("app.dependencies.decode_token", return_value={"sub": "admin-user", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.organizations.organization_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_org_tree = AsyncMock(return_value=[])

            resp = await client.get(
                "/api/organizations/tree",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["tree"] == []

    @pytest.mark.asyncio
    async def test_non_admin_cannot_access_org_flat(self, client):
        """GET /api/organizations/flat returns 403 for a non-admin user."""
        user = _make_user("regular-user", is_admin=False)
        cookies, headers = _auth("regular-user")

        with patch("app.dependencies.decode_token", return_value={"sub": "regular-user", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                "/api/organizations/flat",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert "admin" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_non_admin_cannot_list_orgs(self, client):
        """GET /api/organizations/ returns 403 for a non-admin user."""
        user = _make_user("regular-user", is_admin=False)
        cookies, headers = _auth("regular-user")

        with patch("app.dependencies.decode_token", return_value={"sub": "regular-user", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                "/api/organizations/",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert "admin" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_non_admin_cannot_create_org(self, client):
        """POST /api/organizations/ returns 403 for a non-admin user."""
        user = _make_user("regular-user", is_admin=False)
        cookies, headers = _auth("regular-user")

        with patch("app.dependencies.decode_token", return_value={"sub": "regular-user", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/organizations/",
                json={"name": "Evil Org", "org_type": "department"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_delete_org(self, client):
        """DELETE /api/organizations/{uuid} returns 403 for a non-admin user."""
        user = _make_user("regular-user", is_admin=False)
        cookies, headers = _auth("regular-user")

        with patch("app.dependencies.decode_token", return_value={"sub": "regular-user", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.delete(
                "/api/organizations/org-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_import_orgs(self, client):
        """POST /api/organizations/import returns 403 for a non-admin user."""
        user = _make_user("regular-user", is_admin=False)
        cookies, headers = _auth("regular-user")

        with patch("app.dependencies.decode_token", return_value={"sub": "regular-user", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/organizations/import",
                json={"nodes": [{"name": "Evil Dept", "org_type": "department"}]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_assign_user_to_org(self, client):
        """POST /api/organizations/{uuid}/assign-user/{user_id} returns 403 for a non-admin."""
        user = _make_user("regular-user", is_admin=False)
        cookies, headers = _auth("regular-user")

        with patch("app.dependencies.decode_token", return_value={"sub": "regular-user", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/organizations/org-1/assign-user/target-user",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_move_org(self, client):
        """PATCH /api/organizations/{uuid}/move returns 403 for a non-admin."""
        user = _make_user("regular-user", is_admin=False)
        cookies, headers = _auth("regular-user")

        with patch("app.dependencies.decode_token", return_value={"sub": "regular-user", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.patch(
                "/api/organizations/org-1/move",
                json={"new_parent_id": "org-2"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
