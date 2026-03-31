"""Tests for app.services.team_service — team CRUD, membership, invitations, and access control.

Covers: get_user_teams, get_team_members, get_team_invites, create_team, update_team_name,
invite_member, accept_invite, switch_team, change_role, remove_member, ensure_current_team,
ensure_shared_folder, transfer_ownership, delete_team, _require_min_role.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEAM_OID = PydanticObjectId()
TEAM_OID_2 = PydanticObjectId()


def _make_team(uuid="team-uuid", name="Test Team", owner_user_id="alice", team_id=None):
    t = MagicMock()
    t.id = team_id or TEAM_OID
    t.uuid = uuid
    t.name = name
    t.owner_user_id = owner_user_id
    t.insert = AsyncMock()
    t.save = AsyncMock()
    t.delete = AsyncMock()
    return t


def _make_membership(team_id=None, user_id="alice", role="member"):
    m = MagicMock()
    m.id = PydanticObjectId()
    m.team = team_id or TEAM_OID
    m.user_id = user_id
    m.role = role
    m.save = AsyncMock()
    m.insert = AsyncMock()
    m.delete = AsyncMock()
    return m


def _make_user(user_id="alice", email="alice@example.com", name="Alice", current_team=None):
    u = MagicMock()
    u.user_id = user_id
    u.email = email
    u.name = name
    u.current_team = current_team
    u.save = AsyncMock()
    u.insert = AsyncMock()
    u.delete = AsyncMock()
    return u


def _make_invite(team_id=None, email="bob@example.com", role="member", accepted=False,
                 token="tok123", created_at=None, resend_count=0):
    inv = MagicMock()
    inv.id = PydanticObjectId()
    inv.team = team_id or TEAM_OID
    inv.email = email
    inv.role = role
    inv.accepted = accepted
    inv.token = token
    inv.created_at = created_at or datetime.datetime.now()
    inv.resend_count = resend_count
    inv.invited_by_user_id = "alice"
    inv.save = AsyncMock()
    inv.insert = AsyncMock()
    inv.delete = AsyncMock()
    return inv


def _make_folder(team_id="team-uuid", title="Shared", is_shared_team_root=True):
    f = MagicMock()
    f.id = PydanticObjectId()
    f.team_id = team_id
    f.title = title
    f.is_shared_team_root = is_shared_team_root
    f.uuid = "folder-uuid"
    f.insert = AsyncMock()
    return f


# ---------------------------------------------------------------------------
# _require_min_role (sync helper)
# ---------------------------------------------------------------------------

class TestRequireMinRole:
    def test_none_membership_raises(self):
        from app.services.team_service import _require_min_role

        with pytest.raises(ValueError, match="Not a member"):
            _require_min_role(None, "member")

    def test_insufficient_role_raises(self):
        from app.services.team_service import _require_min_role

        m = _make_membership(role="member")
        with pytest.raises(ValueError, match="Requires at least admin role"):
            _require_min_role(m, "admin")

    def test_exact_role_passes(self):
        from app.services.team_service import _require_min_role

        m = _make_membership(role="admin")
        _require_min_role(m, "admin")  # should not raise

    def test_higher_role_passes(self):
        from app.services.team_service import _require_min_role

        m = _make_membership(role="owner")
        _require_min_role(m, "admin")  # owner > admin, should pass


# ---------------------------------------------------------------------------
# get_user_teams
# ---------------------------------------------------------------------------

class TestGetUserTeams:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_memberships(self):
        with (
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            find_mock = MagicMock()
            find_mock.to_list = AsyncMock(return_value=[])
            MockTM.find = MagicMock(return_value=find_mock)

            from app.services.team_service import get_user_teams

            result = await get_user_teams("alice")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_teams_with_roles(self):
        team = _make_team()
        m1 = _make_membership(team_id=team.id, user_id="alice", role="admin")

        with (
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.Team") as MockTeam,
        ):
            find_mock = MagicMock()
            find_mock.to_list = AsyncMock(return_value=[m1])
            MockTM.find = MagicMock(return_value=find_mock)

            team_find_mock = MagicMock()
            team_find_mock.to_list = AsyncMock(return_value=[team])
            MockTeam.find = MagicMock(return_value=team_find_mock)

            from app.services.team_service import get_user_teams

            result = await get_user_teams("alice")

        assert len(result) == 1
        assert result[0]["name"] == "Test Team"
        assert result[0]["role"] == "admin"
        assert result[0]["uuid"] == "team-uuid"

    @pytest.mark.asyncio
    async def test_deduplicates_memberships_keeping_highest_role(self):
        """When a user has duplicate memberships for the same team, keep the one with the highest role."""
        m_member = _make_membership(team_id=TEAM_OID, user_id="alice", role="member")
        m_admin = _make_membership(team_id=TEAM_OID, user_id="alice", role="admin")
        team = _make_team(team_id=TEAM_OID)

        with (
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.Team") as MockTeam,
        ):
            find_mock = MagicMock()
            find_mock.to_list = AsyncMock(return_value=[m_member, m_admin])
            MockTM.find = MagicMock(return_value=find_mock)

            team_find_mock = MagicMock()
            team_find_mock.to_list = AsyncMock(return_value=[team])
            MockTeam.find = MagicMock(return_value=team_find_mock)

            from app.services.team_service import get_user_teams

            result = await get_user_teams("alice")

        assert len(result) == 1
        assert result[0]["role"] == "admin"
        # The lower-ranked membership (member) should have been deleted
        m_member.delete.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_team_members
# ---------------------------------------------------------------------------

class TestGetTeamMembers:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_members(self):
        with (
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            find_mock = MagicMock()
            find_mock.to_list = AsyncMock(return_value=[])
            MockTM.find = MagicMock(return_value=find_mock)

            from app.services.team_service import get_team_members

            result = await get_team_members(TEAM_OID)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_members_with_user_info(self):
        m = _make_membership(user_id="alice", role="owner")
        user = _make_user(user_id="alice", email="alice@example.com", name="Alice")

        with (
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.User") as MockUser,
        ):
            find_mock = MagicMock()
            find_mock.to_list = AsyncMock(return_value=[m])
            MockTM.find = MagicMock(return_value=find_mock)

            user_find_mock = MagicMock()
            user_find_mock.to_list = AsyncMock(return_value=[user])
            MockUser.find = MagicMock(return_value=user_find_mock)

            from app.services.team_service import get_team_members

            result = await get_team_members(TEAM_OID)

        assert len(result) == 1
        assert result[0]["user_id"] == "alice"
        assert result[0]["name"] == "Alice"
        assert result[0]["role"] == "owner"


# ---------------------------------------------------------------------------
# create_team
# ---------------------------------------------------------------------------

class TestCreateTeam:
    @pytest.mark.asyncio
    async def test_creates_team_and_owner_membership(self):
        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            team_inst = MagicMock()
            team_inst.id = TEAM_OID
            team_inst.insert = AsyncMock()
            MockTeam.return_value = team_inst

            membership_inst = MagicMock()
            membership_inst.insert = AsyncMock()
            MockTM.return_value = membership_inst

            from app.services.team_service import create_team

            result = await create_team("My Team", "alice")

        assert result is team_inst
        team_inst.insert.assert_awaited_once()
        membership_inst.insert.assert_awaited_once()
        # Verify membership was created with owner role
        MockTM.assert_called_once_with(team=TEAM_OID, user_id="alice", role="owner")


# ---------------------------------------------------------------------------
# update_team_name
# ---------------------------------------------------------------------------

class TestUpdateTeamName:
    @pytest.mark.asyncio
    async def test_raises_when_team_not_found(self):
        with (
            patch("app.services.team_service.Team") as MockTeam,
        ):
            MockTeam.find_one = AsyncMock(return_value=None)

            from app.services.team_service import update_team_name

            with pytest.raises(ValueError, match="Team not found"):
                await update_team_name("no-such-uuid", "New Name", "alice")

    @pytest.mark.asyncio
    async def test_raises_when_actor_is_member_only(self):
        team = _make_team()
        m = _make_membership(role="member", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=m)

            from app.services.team_service import update_team_name

            with pytest.raises(ValueError, match="Requires at least admin role"):
                await update_team_name("team-uuid", "New Name", "alice")

    @pytest.mark.asyncio
    async def test_admin_can_rename(self):
        team = _make_team()
        m = _make_membership(role="admin", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=m)

            from app.services.team_service import update_team_name

            result = await update_team_name("team-uuid", "Renamed", "alice")

        assert result.name == "Renamed"
        team.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# invite_member
# ---------------------------------------------------------------------------

class TestInviteMember:
    @pytest.mark.asyncio
    async def test_raises_when_team_not_found(self):
        with (
            patch("app.services.team_service.Team") as MockTeam,
        ):
            MockTeam.find_one = AsyncMock(return_value=None)

            from app.services.team_service import invite_member

            with pytest.raises(ValueError, match="Team not found"):
                await invite_member("no-uuid", "bob@example.com", "member", "alice")

    @pytest.mark.asyncio
    async def test_member_cannot_invite(self):
        team = _make_team()
        m = _make_membership(role="member", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=m)

            from app.services.team_service import invite_member

            with pytest.raises(ValueError, match="Requires at least admin role"):
                await invite_member("team-uuid", "bob@example.com", "member", "alice")

    @pytest.mark.asyncio
    async def test_creates_new_invite(self):
        team = _make_team()
        m = _make_membership(role="admin", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.TeamInvite") as MockInvite,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=m)
            MockInvite.find_one = AsyncMock(return_value=None)

            invite_inst = MagicMock()
            invite_inst.insert = AsyncMock()
            MockInvite.return_value = invite_inst

            from app.services.team_service import invite_member

            result = await invite_member("team-uuid", "bob@example.com", "member", "alice")

        assert result is invite_inst
        invite_inst.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resends_existing_pending_invite(self):
        team = _make_team()
        m = _make_membership(role="admin", user_id="alice")
        existing_invite = _make_invite(accepted=False, role="member", resend_count=0)

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.TeamInvite") as MockInvite,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=m)
            MockInvite.find_one = AsyncMock(return_value=existing_invite)

            from app.services.team_service import invite_member

            result = await invite_member("team-uuid", "bob@example.com", "admin", "alice")

        assert result is existing_invite
        assert existing_invite.role == "admin"
        assert existing_invite.resend_count == 1
        existing_invite.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# accept_invite
# ---------------------------------------------------------------------------

class TestAcceptInvite:
    @pytest.mark.asyncio
    async def test_raises_on_invalid_token(self):
        with (
            patch("app.services.team_service.TeamInvite") as MockInvite,
        ):
            MockInvite.find_one = AsyncMock(return_value=None)

            from app.services.team_service import accept_invite

            with pytest.raises(ValueError, match="Invalid invite token"):
                await accept_invite("bad-token", _make_user())

    @pytest.mark.asyncio
    async def test_raises_on_expired_invite(self):
        expired_invite = _make_invite(
            created_at=datetime.datetime.now() - datetime.timedelta(days=60)
        )

        with (
            patch("app.services.team_service.TeamInvite") as MockInvite,
        ):
            MockInvite.find_one = AsyncMock(return_value=expired_invite)

            from app.services.team_service import accept_invite

            with pytest.raises(ValueError, match="Invite has expired"):
                await accept_invite("tok123", _make_user())

    @pytest.mark.asyncio
    async def test_creates_membership_and_sets_current_team(self):
        team = _make_team()
        invite = _make_invite(role="member")
        user = _make_user(user_id="bob")

        with (
            patch("app.services.team_service.TeamInvite") as MockInvite,
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockInvite.find_one = AsyncMock(return_value=invite)
            MockTeam.get = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=None)

            membership_inst = MagicMock()
            membership_inst.insert = AsyncMock()
            MockTM.return_value = membership_inst

            from app.services.team_service import accept_invite

            result = await accept_invite("tok123", user)

        assert result is team
        membership_inst.insert.assert_awaited_once()
        assert invite.accepted is True
        invite.save.assert_awaited_once()
        assert user.current_team == team.id
        user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updates_existing_membership_role(self):
        team = _make_team()
        invite = _make_invite(role="admin")
        user = _make_user(user_id="bob")
        existing_m = _make_membership(user_id="bob", role="member")

        with (
            patch("app.services.team_service.TeamInvite") as MockInvite,
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockInvite.find_one = AsyncMock(return_value=invite)
            MockTeam.get = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=existing_m)

            from app.services.team_service import accept_invite

            result = await accept_invite("tok123", user)

        assert result is team
        assert existing_m.role == "admin"
        existing_m.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# switch_team
# ---------------------------------------------------------------------------

class TestSwitchTeam:
    @pytest.mark.asyncio
    async def test_raises_when_team_not_found(self):
        with (
            patch("app.services.team_service.Team") as MockTeam,
        ):
            MockTeam.find_one = AsyncMock(return_value=None)

            from app.services.team_service import switch_team

            with pytest.raises(ValueError, match="Team not found"):
                await switch_team("no-uuid", _make_user())

    @pytest.mark.asyncio
    async def test_raises_when_not_a_member(self):
        team = _make_team()
        user = _make_user(user_id="bob")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=None)

            from app.services.team_service import switch_team

            with pytest.raises(ValueError, match="Not a member"):
                await switch_team("team-uuid", user)

    @pytest.mark.asyncio
    async def test_switches_current_team(self):
        team = _make_team()
        user = _make_user(user_id="alice")
        m = _make_membership(role="member", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=m)

            from app.services.team_service import switch_team

            result = await switch_team("team-uuid", user)

        assert result is team
        assert user.current_team == team.id
        user.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# change_role
# ---------------------------------------------------------------------------

class TestChangeRole:
    @pytest.mark.asyncio
    async def test_raises_when_team_not_found(self):
        with (
            patch("app.services.team_service.Team") as MockTeam,
        ):
            MockTeam.find_one = AsyncMock(return_value=None)

            from app.services.team_service import change_role

            with pytest.raises(ValueError, match="Team not found"):
                await change_role("no-uuid", "bob", "admin", "alice")

    @pytest.mark.asyncio
    async def test_member_cannot_change_roles(self):
        team = _make_team()
        actor_m = _make_membership(role="member", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=actor_m)

            from app.services.team_service import change_role

            with pytest.raises(ValueError, match="Requires at least admin role"):
                await change_role("team-uuid", "bob", "admin", "alice")

    @pytest.mark.asyncio
    async def test_admin_cannot_change_owner_role(self):
        team = _make_team()
        actor_m = _make_membership(role="admin", user_id="alice")
        target_m = _make_membership(role="owner", user_id="bob")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(side_effect=[actor_m, target_m])

            from app.services.team_service import change_role

            with pytest.raises(ValueError, match="Only owners can change another owner"):
                await change_role("team-uuid", "bob", "member", "alice")

    @pytest.mark.asyncio
    async def test_owner_cannot_demote_themselves(self):
        team = _make_team()
        actor_m = _make_membership(role="owner", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            # actor and target are the same user
            MockTM.find_one = AsyncMock(side_effect=[actor_m, actor_m])

            from app.services.team_service import change_role

            with pytest.raises(ValueError, match="Owner cannot demote themselves"):
                await change_role("team-uuid", "alice", "admin", "alice")

    @pytest.mark.asyncio
    async def test_admin_can_change_member_role(self):
        team = _make_team()
        actor_m = _make_membership(role="admin", user_id="alice")
        target_m = _make_membership(role="member", user_id="bob")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(side_effect=[actor_m, target_m])

            from app.services.team_service import change_role

            await change_role("team-uuid", "bob", "admin", "alice")

        assert target_m.role == "admin"
        target_m.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# remove_member
# ---------------------------------------------------------------------------

class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_raises_when_team_not_found(self):
        with (
            patch("app.services.team_service.Team") as MockTeam,
        ):
            MockTeam.find_one = AsyncMock(return_value=None)

            from app.services.team_service import remove_member

            with pytest.raises(ValueError, match="Team not found"):
                await remove_member("no-uuid", "bob", "alice")

    @pytest.mark.asyncio
    async def test_owner_cannot_leave(self):
        team = _make_team()
        owner_m = _make_membership(role="owner", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=owner_m)

            from app.services.team_service import remove_member

            with pytest.raises(ValueError, match="Owners cannot leave"):
                await remove_member("team-uuid", "alice", "alice")

    @pytest.mark.asyncio
    async def test_cannot_remove_owner(self):
        team = _make_team()
        actor_m = _make_membership(role="admin", user_id="alice")
        target_m = _make_membership(role="owner", user_id="bob")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(side_effect=[actor_m, target_m])

            from app.services.team_service import remove_member

            with pytest.raises(ValueError, match="Cannot remove a team owner"):
                await remove_member("team-uuid", "bob", "alice")

    @pytest.mark.asyncio
    async def test_member_can_leave_and_current_team_cleared(self):
        team = _make_team()
        m = _make_membership(role="member", user_id="bob")
        bob_user = _make_user(user_id="bob", current_team=TEAM_OID)

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.User") as MockUser,
            patch("app.services.team_service.ensure_current_team", new_callable=AsyncMock) as mock_ensure,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=m)
            MockUser.find_one = AsyncMock(return_value=bob_user)

            from app.services.team_service import remove_member

            await remove_member("team-uuid", "bob", "bob")

        m.delete.assert_awaited_once()
        assert bob_user.current_team is None
        bob_user.save.assert_awaited_once()
        mock_ensure.assert_awaited_once_with(bob_user)

    @pytest.mark.asyncio
    async def test_admin_removes_other_member(self):
        team = _make_team()
        actor_m = _make_membership(role="admin", user_id="alice")
        target_m = _make_membership(role="member", user_id="bob")
        bob_user = _make_user(user_id="bob", current_team=TEAM_OID_2)  # different team

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.User") as MockUser,
            patch("app.services.team_service.ensure_current_team", new_callable=AsyncMock),
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(side_effect=[actor_m, target_m])
            MockUser.find_one = AsyncMock(return_value=bob_user)

            from app.services.team_service import remove_member

            await remove_member("team-uuid", "bob", "alice")

        target_m.delete.assert_awaited_once()
        # current_team is a different team, so it should NOT be cleared
        bob_user.save.assert_not_awaited()


# ---------------------------------------------------------------------------
# ensure_current_team
# ---------------------------------------------------------------------------

class TestEnsureCurrentTeam:
    @pytest.mark.asyncio
    async def test_returns_existing_team_if_set(self):
        team = _make_team()
        user = _make_user(current_team=TEAM_OID)

        with (
            patch("app.services.team_service.Team") as MockTeam,
        ):
            MockTeam.get = AsyncMock(return_value=team)

            from app.services.team_service import ensure_current_team

            result = await ensure_current_team(user)

        assert result is team

    @pytest.mark.asyncio
    async def test_falls_back_to_first_membership(self):
        team = _make_team()
        user = _make_user(current_team=None)
        m = _make_membership(user_id="alice")

        with (
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.Team") as MockTeam,
        ):
            MockTM.find_one = AsyncMock(return_value=m)
            MockTeam.get = AsyncMock(return_value=team)

            from app.services.team_service import ensure_current_team

            result = await ensure_current_team(user)

        assert result is team
        assert user.current_team == team.id
        user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_personal_team_if_no_memberships(self):
        user = _make_user(user_id="alice", name="Alice", current_team=None)

        with (
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.Team") as MockTeam,
        ):
            MockTM.find_one = AsyncMock(return_value=None)

            team_inst = MagicMock()
            team_inst.id = TEAM_OID
            team_inst.insert = AsyncMock()
            MockTeam.return_value = team_inst

            membership_inst = MagicMock()
            membership_inst.insert = AsyncMock()
            MockTM.return_value = membership_inst

            from app.services.team_service import ensure_current_team

            result = await ensure_current_team(user)

        assert result is team_inst
        team_inst.insert.assert_awaited_once()
        membership_inst.insert.assert_awaited_once()
        assert user.current_team == TEAM_OID


# ---------------------------------------------------------------------------
# ensure_shared_folder
# ---------------------------------------------------------------------------

class TestEnsureSharedFolder:
    @pytest.mark.asyncio
    async def test_returns_existing_shared_folder(self):
        team = _make_team()
        folder = _make_folder()

        with (
            patch("app.services.team_service.SmartFolder") as MockFolder,
        ):
            MockFolder.find_one = AsyncMock(return_value=folder)

            from app.services.team_service import ensure_shared_folder

            result = await ensure_shared_folder(team)

        assert result is folder

    @pytest.mark.asyncio
    async def test_creates_shared_folder_if_missing(self):
        team = _make_team()

        with (
            patch("app.services.team_service.SmartFolder") as MockFolder,
        ):
            MockFolder.find_one = AsyncMock(return_value=None)

            folder_inst = MagicMock()
            folder_inst.insert = AsyncMock()
            MockFolder.return_value = folder_inst

            from app.services.team_service import ensure_shared_folder

            result = await ensure_shared_folder(team)

        assert result is folder_inst
        folder_inst.insert.assert_awaited_once()


# ---------------------------------------------------------------------------
# transfer_ownership
# ---------------------------------------------------------------------------

class TestTransferOwnership:
    @pytest.mark.asyncio
    async def test_raises_when_not_owner(self):
        team = _make_team()
        admin_m = _make_membership(role="admin", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=admin_m)

            from app.services.team_service import transfer_ownership

            with pytest.raises(ValueError, match="Only the team owner can transfer"):
                await transfer_ownership("team-uuid", "alice", "bob")

    @pytest.mark.asyncio
    async def test_raises_when_new_owner_not_member(self):
        team = _make_team()
        owner_m = _make_membership(role="owner", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(side_effect=[owner_m, None])

            from app.services.team_service import transfer_ownership

            with pytest.raises(ValueError, match="New owner must be a member"):
                await transfer_ownership("team-uuid", "alice", "charlie")

    @pytest.mark.asyncio
    async def test_successful_transfer(self):
        team = _make_team(owner_user_id="alice")
        owner_m = _make_membership(role="owner", user_id="alice")
        new_m = _make_membership(role="admin", user_id="bob")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(side_effect=[owner_m, new_m])

            from app.services.team_service import transfer_ownership

            result = await transfer_ownership("team-uuid", "alice", "bob")

        assert result is team
        assert owner_m.role == "admin"
        assert new_m.role == "owner"
        assert team.owner_user_id == "bob"
        owner_m.save.assert_awaited_once()
        new_m.save.assert_awaited_once()
        team.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# delete_team
# ---------------------------------------------------------------------------

class TestDeleteTeam:
    @pytest.mark.asyncio
    async def test_raises_when_team_not_found(self):
        with (
            patch("app.services.team_service.Team") as MockTeam,
        ):
            MockTeam.find_one = AsyncMock(return_value=None)

            from app.services.team_service import delete_team

            with pytest.raises(ValueError, match="Team not found"):
                await delete_team("no-uuid", "alice")

    @pytest.mark.asyncio
    async def test_raises_when_not_owner(self):
        team = _make_team()
        admin_m = _make_membership(role="admin", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=admin_m)

            from app.services.team_service import delete_team

            with pytest.raises(ValueError, match="Only the team owner can delete"):
                await delete_team("team-uuid", "alice")

    @pytest.mark.asyncio
    async def test_successful_delete_clears_user_current_teams(self):
        team = _make_team()
        owner_m = _make_membership(role="owner", user_id="alice")
        affected_user = _make_user(user_id="bob", current_team=TEAM_OID)

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.TeamInvite") as MockInvite,
            patch("app.services.team_service.User") as MockUser,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=owner_m)

            # Set up chained .find().delete() and .find().to_list()
            membership_find = MagicMock()
            membership_find.delete = AsyncMock()
            MockTM.find = MagicMock(return_value=membership_find)

            invite_find = MagicMock()
            invite_find.delete = AsyncMock()
            MockInvite.find = MagicMock(return_value=invite_find)

            user_find = MagicMock()
            user_find.to_list = AsyncMock(return_value=[affected_user])
            MockUser.find = MagicMock(return_value=user_find)

            from app.services.team_service import delete_team

            result = await delete_team("team-uuid", "alice")

        assert result is True
        membership_find.delete.assert_awaited_once()
        invite_find.delete.assert_awaited_once()
        assert affected_user.current_team is None
        affected_user.save.assert_awaited_once()
        team.delete.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_team_invites
# ---------------------------------------------------------------------------

class TestGetTeamInvites:
    @pytest.mark.asyncio
    async def test_returns_pending_invites(self):
        inv = _make_invite(email="bob@example.com", role="member", token="abc")

        with (
            patch("app.services.team_service.TeamInvite") as MockInvite,
        ):
            find_mock = MagicMock()
            find_mock.to_list = AsyncMock(return_value=[inv])
            MockInvite.find = MagicMock(return_value=find_mock)

            from app.services.team_service import get_team_invites

            result = await get_team_invites(TEAM_OID)

        assert len(result) == 1
        assert result[0]["email"] == "bob@example.com"
        assert result[0]["token"] == "abc"
        assert result[0]["role"] == "member"
        assert result[0]["accepted"] is False
