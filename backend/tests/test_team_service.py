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
    @pytest.mark.skip(reason="Beanie field descriptors not available on MagicMock")
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
    @pytest.mark.skip(reason="Beanie field descriptors not available on MagicMock")
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
    @pytest.mark.skip(reason="Beanie field descriptors not available on MagicMock")
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
    @pytest.mark.skip(reason="Beanie field descriptors not available on MagicMock")
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


# ---------------------------------------------------------------------------
# Public join links
# ---------------------------------------------------------------------------

def _make_join_link(
    team_id=None,
    token="link-tok",
    role="member",
    revoked=False,
    max_uses=None,
    use_count=0,
    expires_at=None,
    created_by_user_id="alice",
):
    link = MagicMock()
    link.id = PydanticObjectId()
    link.team = team_id or TEAM_OID
    link.token = token
    link.role = role
    link.revoked = revoked
    link.max_uses = max_uses
    link.use_count = use_count
    link.expires_at = expires_at or (
        datetime.datetime.now() + datetime.timedelta(hours=48)
    )
    link.created_at = datetime.datetime.now()
    link.created_by_user_id = created_by_user_id
    link.save = AsyncMock()
    link.insert = AsyncMock()
    link.delete = AsyncMock()
    return link


class TestCreateJoinLink:
    @pytest.mark.asyncio
    async def test_rejects_owner_role(self):
        from app.services.team_service import create_join_link

        with pytest.raises(ValueError, match="Role must be 'admin' or 'member'"):
            await create_join_link("team-uuid", "alice", role="owner")

    @pytest.mark.asyncio
    async def test_rejects_negative_expiry(self):
        from app.services.team_service import create_join_link

        with pytest.raises(ValueError, match="expires_in_hours must be positive"):
            await create_join_link("team-uuid", "alice", expires_in_hours=0)

    @pytest.mark.asyncio
    async def test_rejects_excessive_expiry(self):
        from app.services.team_service import create_join_link

        with pytest.raises(ValueError, match="cannot exceed"):
            await create_join_link(
                "team-uuid", "alice", expires_in_hours=24 * 365
            )

    @pytest.mark.asyncio
    async def test_rejects_zero_max_uses(self):
        from app.services.team_service import create_join_link

        with pytest.raises(ValueError, match="max_uses must be positive"):
            await create_join_link("team-uuid", "alice", max_uses=0)

    @pytest.mark.asyncio
    async def test_member_cannot_create(self):
        team = _make_team()
        m = _make_membership(role="member", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=m)

            from app.services.team_service import create_join_link

            with pytest.raises(ValueError, match="Requires at least admin role"):
                await create_join_link("team-uuid", "alice")

    @pytest.mark.asyncio
    async def test_admin_creates_link(self):
        team = _make_team()
        m = _make_membership(role="admin", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.TeamJoinLink") as MockLink,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=m)

            link_inst = MagicMock()
            link_inst.insert = AsyncMock()
            MockLink.return_value = link_inst

            from app.services.team_service import create_join_link

            result = await create_join_link(
                "team-uuid", "alice", role="member", expires_in_hours=48
            )

        assert result is link_inst
        link_inst.insert.assert_awaited_once()
        # Verify the link was built with the right team and role
        kwargs = MockLink.call_args.kwargs
        assert kwargs["team"] == team.id
        assert kwargs["role"] == "member"
        assert kwargs["created_by_user_id"] == "alice"


class TestRevokeJoinLink:
    @pytest.mark.asyncio
    async def test_raises_when_link_not_found(self):
        with patch("app.services.team_service.TeamJoinLink") as MockLink:
            MockLink.find_one = AsyncMock(return_value=None)

            from app.services.team_service import revoke_join_link

            with pytest.raises(ValueError, match="Join link not found"):
                await revoke_join_link("missing", "alice")

    @pytest.mark.asyncio
    async def test_member_cannot_revoke(self):
        link = _make_join_link()
        m = _make_membership(role="member", user_id="alice")

        with (
            patch("app.services.team_service.TeamJoinLink") as MockLink,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockLink.find_one = AsyncMock(return_value=link)
            MockTM.find_one = AsyncMock(return_value=m)

            from app.services.team_service import revoke_join_link

            with pytest.raises(ValueError, match="Requires at least admin"):
                await revoke_join_link("link-tok", "alice")

    @pytest.mark.asyncio
    async def test_admin_revokes(self):
        link = _make_join_link()
        m = _make_membership(role="admin", user_id="alice")

        with (
            patch("app.services.team_service.TeamJoinLink") as MockLink,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockLink.find_one = AsyncMock(return_value=link)
            MockTM.find_one = AsyncMock(return_value=m)

            from app.services.team_service import revoke_join_link

            await revoke_join_link("link-tok", "alice")

        assert link.revoked is True
        link.save.assert_awaited_once()


class TestGetJoinLinkInfo:
    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        with patch("app.services.team_service.TeamJoinLink") as MockLink:
            MockLink.find_one = AsyncMock(return_value=None)

            from app.services.team_service import get_join_link_info

            result = await get_join_link_info("missing")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_status_revoked(self):
        link = _make_join_link(revoked=True)
        team = _make_team()
        creator = _make_user(user_id="alice", name="Alice")

        with (
            patch("app.services.team_service.TeamJoinLink") as MockLink,
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.User") as MockUser,
        ):
            MockLink.find_one = AsyncMock(return_value=link)
            MockTeam.get = AsyncMock(return_value=team)
            MockUser.find_one = AsyncMock(return_value=creator)

            from app.services.team_service import get_join_link_info

            result = await get_join_link_info("link-tok")

        assert result is not None
        assert result["status"] == "revoked"
        assert result["team_name"] == "Test Team"
        assert result["inviter_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_returns_status_expired(self):
        past = datetime.datetime.now() - datetime.timedelta(hours=1)
        link = _make_join_link(expires_at=past)
        team = _make_team()

        with (
            patch("app.services.team_service.TeamJoinLink") as MockLink,
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.User") as MockUser,
        ):
            MockLink.find_one = AsyncMock(return_value=link)
            MockTeam.get = AsyncMock(return_value=team)
            MockUser.find_one = AsyncMock(return_value=None)

            from app.services.team_service import get_join_link_info

            result = await get_join_link_info("link-tok")

        assert result["status"] == "expired"

    @pytest.mark.asyncio
    async def test_returns_status_exhausted(self):
        link = _make_join_link(max_uses=5, use_count=5)
        team = _make_team()

        with (
            patch("app.services.team_service.TeamJoinLink") as MockLink,
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.User") as MockUser,
        ):
            MockLink.find_one = AsyncMock(return_value=link)
            MockTeam.get = AsyncMock(return_value=team)
            MockUser.find_one = AsyncMock(return_value=None)

            from app.services.team_service import get_join_link_info

            result = await get_join_link_info("link-tok")

        assert result["status"] == "exhausted"

    @pytest.mark.asyncio
    async def test_returns_usable_when_valid(self):
        link = _make_join_link()
        team = _make_team()

        with (
            patch("app.services.team_service.TeamJoinLink") as MockLink,
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.User") as MockUser,
        ):
            MockLink.find_one = AsyncMock(return_value=link)
            MockTeam.get = AsyncMock(return_value=team)
            MockUser.find_one = AsyncMock(return_value=None)

            from app.services.team_service import get_join_link_info

            result = await get_join_link_info("link-tok")

        assert result["status"] is None


class TestAcceptJoinLink:
    @pytest.mark.asyncio
    async def test_rejects_invalid_token(self):
        user = _make_user()
        with patch("app.services.team_service.TeamJoinLink") as MockLink:
            MockLink.find_one = AsyncMock(return_value=None)

            from app.services.team_service import accept_join_link

            with pytest.raises(ValueError, match="Invalid join link"):
                await accept_join_link("nope", user)

    @pytest.mark.asyncio
    async def test_rejects_revoked(self):
        user = _make_user()
        link = _make_join_link(revoked=True)
        with patch("app.services.team_service.TeamJoinLink") as MockLink:
            MockLink.find_one = AsyncMock(return_value=link)

            from app.services.team_service import accept_join_link

            with pytest.raises(ValueError, match="revoked"):
                await accept_join_link("link-tok", user)

    @pytest.mark.asyncio
    async def test_rejects_expired(self):
        user = _make_user()
        past = datetime.datetime.now() - datetime.timedelta(hours=1)
        link = _make_join_link(expires_at=past)
        with patch("app.services.team_service.TeamJoinLink") as MockLink:
            MockLink.find_one = AsyncMock(return_value=link)

            from app.services.team_service import accept_join_link

            with pytest.raises(ValueError, match="expired"):
                await accept_join_link("link-tok", user)

    @pytest.mark.asyncio
    async def test_rejects_exhausted(self):
        user = _make_user()
        link = _make_join_link(max_uses=1, use_count=1)
        with patch("app.services.team_service.TeamJoinLink") as MockLink:
            MockLink.find_one = AsyncMock(return_value=link)

            from app.services.team_service import accept_join_link

            with pytest.raises(ValueError, match="use limit"):
                await accept_join_link("link-tok", user)

    @pytest.mark.asyncio
    async def test_existing_member_does_not_bump_count(self):
        user = _make_user(user_id="bob")
        link = _make_join_link(use_count=3)
        team = _make_team()
        existing_m = _make_membership(role="member", user_id="bob")

        with (
            patch("app.services.team_service.TeamJoinLink") as MockLink,
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockLink.find_one = AsyncMock(return_value=link)
            MockTeam.get = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=existing_m)

            from app.services.team_service import accept_join_link

            result = await accept_join_link("link-tok", user)

        assert result is team
        assert link.use_count == 3  # unchanged
        link.save.assert_not_awaited()
        assert user.current_team == team.id

    @pytest.mark.asyncio
    async def test_new_user_joins_and_count_increments(self):
        user = _make_user(user_id="charlie")
        link = _make_join_link(role="member", use_count=2)
        team = _make_team()

        with (
            patch("app.services.team_service.TeamJoinLink") as MockLink,
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockLink.find_one = AsyncMock(return_value=link)
            MockTeam.get = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=None)

            membership_inst = MagicMock()
            membership_inst.insert = AsyncMock()
            MockTM.return_value = membership_inst

            from app.services.team_service import accept_join_link

            result = await accept_join_link("link-tok", user)

        assert result is team
        membership_inst.insert.assert_awaited_once()
        MockTM.assert_called_once_with(team=team.id, user_id="charlie", role="member")
        assert link.use_count == 3
        link.save.assert_awaited_once()
        assert user.current_team == team.id


class TestGetTeamJoinLinks:
    @pytest.mark.asyncio
    async def test_member_cannot_list(self):
        team = _make_team()
        m = _make_membership(role="member", user_id="alice")

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=m)

            from app.services.team_service import get_team_join_links

            with pytest.raises(ValueError, match="Requires at least admin"):
                await get_team_join_links("team-uuid", "alice")

    @pytest.mark.asyncio
    async def test_admin_lists_active_links(self):
        team = _make_team()
        m = _make_membership(role="admin", user_id="alice")
        link = _make_join_link(token="abc", use_count=1)

        with (
            patch("app.services.team_service.Team") as MockTeam,
            patch("app.services.team_service.TeamMembership") as MockTM,
            patch("app.services.team_service.TeamJoinLink") as MockLink,
        ):
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTM.find_one = AsyncMock(return_value=m)

            find_mock = MagicMock()
            find_mock.to_list = AsyncMock(return_value=[link])
            MockLink.find = MagicMock(return_value=find_mock)

            from app.services.team_service import get_team_join_links

            result = await get_team_join_links("team-uuid", "alice")

        assert len(result) == 1
        assert result[0]["token"] == "abc"
        assert result[0]["use_count"] == 1
        assert result[0]["role"] == "member"
