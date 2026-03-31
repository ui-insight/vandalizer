"""Tests for app.services.auth_service — authentication, registration, and OAuth/SAML user resolution.

Covers: authenticate, register, resolve_oauth_user, resolve_saml_user, _auto_join_default_team.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(user_id="alice", email="alice@example.com", password_hash="hashed", is_demo_user=False, **extra):
    u = MagicMock()
    u.user_id = user_id
    u.email = email
    u.password_hash = password_hash
    u.name = extra.get("name", "Alice")
    u.is_demo_user = is_demo_user
    u.current_team = extra.get("current_team", None)
    u.organization_id = extra.get("organization_id", None)
    u.save = AsyncMock()
    u.insert = AsyncMock()
    u.delete = AsyncMock()
    return u


def _make_team(uuid="team-uuid", owner_user_id="alice"):
    t = MagicMock()
    t.id = "team-oid"
    t.uuid = uuid
    t.name = f"{owner_user_id}'s Team"
    t.owner_user_id = owner_user_id
    t.insert = AsyncMock()
    return t


def _make_config(default_team_id=None):
    cfg = MagicMock()
    cfg.default_team_id = default_team_id
    return cfg


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------


class TestAuthenticate:
    @pytest.mark.asyncio
    async def test_successful_login_by_user_id(self):
        user = _make_user()

        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.services.auth_service._auto_join_default_team", new_callable=AsyncMock),
            patch("app.services.team_service.ensure_current_team", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            from app.services.auth_service import authenticate

            result = await authenticate("alice", "password123")

        assert result is user

    @pytest.mark.asyncio
    async def test_normalizes_user_id_to_lowercase(self):
        user = _make_user()

        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.services.auth_service._auto_join_default_team", new_callable=AsyncMock),
            patch("app.services.team_service.ensure_current_team", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            from app.services.auth_service import authenticate

            result = await authenticate("  ALICE  ", "password123")

        assert result is user

    @pytest.mark.asyncio
    async def test_falls_back_to_email_lookup(self):
        user = _make_user()

        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.services.auth_service._auto_join_default_team", new_callable=AsyncMock),
            patch("app.services.team_service.ensure_current_team", new_callable=AsyncMock),
        ):
            # First find_one (by user_id) returns None, second (by email) returns user
            MockUser.find_one = AsyncMock(side_effect=[None, user])

            from app.services.auth_service import authenticate

            result = await authenticate("alice@example.com", "password123")

        assert result is user

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_user(self):
        with (
            patch("app.services.auth_service.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=None)

            from app.services.auth_service import authenticate

            result = await authenticate("nobody", "password123")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_password(self):
        user = _make_user()

        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service.verify_password", return_value=False),
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            from app.services.auth_service import authenticate

            result = await authenticate("alice", "wrongpassword")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_password_hash(self):
        user = _make_user(password_hash=None)

        with (
            patch("app.services.auth_service.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            from app.services.auth_service import authenticate

            result = await authenticate("alice", "password123")

        assert result is None

    @pytest.mark.asyncio
    async def test_skips_default_team_for_demo_users(self):
        user = _make_user(is_demo_user=True)

        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.services.auth_service._auto_join_default_team", new_callable=AsyncMock) as mock_auto_join,
            patch("app.services.team_service.ensure_current_team", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            from app.services.auth_service import authenticate

            await authenticate("alice", "password123")

        mock_auto_join.assert_not_called()


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


class TestRegister:
    @pytest.mark.asyncio
    async def test_successful_registration(self):
        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service.Team") as MockTeam,
            patch("app.services.auth_service.TeamMembership") as MockMembership,
            patch("app.services.auth_service.hash_password", return_value="hashed-pw"),
            patch("app.services.auth_service._auto_join_default_team", new_callable=AsyncMock),
        ):
            # No existing user
            MockUser.find_one = AsyncMock(return_value=None)
            mock_user = _make_user(user_id="newuser", email="new@test.com")
            MockUser.return_value = mock_user

            mock_team = _make_team()
            MockTeam.return_value = mock_team
            mock_team.insert = AsyncMock()

            mock_membership = MagicMock()
            mock_membership.insert = AsyncMock()
            MockMembership.return_value = mock_membership

            from app.services.auth_service import register

            result = await register("NewUser", "New@Test.com", "securepass", "New User")

        assert result is mock_user
        mock_user.insert.assert_awaited_once()
        mock_team.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejects_duplicate_user_id(self):
        with (
            patch("app.services.auth_service.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=_make_user())

            from app.services.auth_service import register

            with pytest.raises(ValueError, match="User ID already taken"):
                await register("alice", "other@test.com", "pass")

    @pytest.mark.asyncio
    async def test_rejects_duplicate_email(self):
        with (
            patch("app.services.auth_service.User") as MockUser,
        ):
            # First find (user_id) returns None, second (email) returns existing
            MockUser.find_one = AsyncMock(side_effect=[None, _make_user()])

            from app.services.auth_service import register

            with pytest.raises(ValueError, match="Email already registered"):
                await register("newuser", "alice@example.com", "pass")

    @pytest.mark.asyncio
    async def test_normalizes_user_id_and_email(self):
        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service.Team") as MockTeam,
            patch("app.services.auth_service.TeamMembership") as MockMembership,
            patch("app.services.auth_service.hash_password", return_value="hashed"),
            patch("app.services.auth_service._auto_join_default_team", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=None)
            mock_user = _make_user()
            MockUser.return_value = mock_user

            mock_team = _make_team()
            MockTeam.return_value = mock_team
            mock_team.insert = AsyncMock()

            mock_membership = MagicMock()
            mock_membership.insert = AsyncMock()
            MockMembership.return_value = mock_membership

            from app.services.auth_service import register

            await register("  ALICE  ", "  Alice@Test.COM  ", "pass")

        # The User constructor should have been called with normalized values
        call_kwargs = MockUser.call_args
        assert call_kwargs.kwargs["user_id"] == "alice"
        assert call_kwargs.kwargs["email"] == "alice@test.com"

    @pytest.mark.asyncio
    async def test_cleans_up_user_on_team_creation_failure(self):
        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service.Team") as MockTeam,
            patch("app.services.auth_service.hash_password", return_value="hashed"),
        ):
            MockUser.find_one = AsyncMock(return_value=None)
            mock_user = _make_user()
            MockUser.return_value = mock_user

            mock_team = MagicMock()
            mock_team.insert = AsyncMock(side_effect=RuntimeError("DB error"))
            MockTeam.return_value = mock_team

            from app.services.auth_service import register

            with pytest.raises(RuntimeError, match="DB error"):
                await register("newuser", "new@test.com", "pass")

        # User should have been deleted (cleanup)
        mock_user.delete.assert_awaited_once()


# ---------------------------------------------------------------------------
# resolve_oauth_user
# ---------------------------------------------------------------------------


class TestResolveOAuthUser:
    @pytest.mark.asyncio
    async def test_returns_existing_user_by_upn(self):
        user = _make_user()

        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service._auto_join_default_team", new_callable=AsyncMock),
            patch("app.services.team_service.ensure_current_team", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            from app.services.auth_service import resolve_oauth_user

            result = await resolve_oauth_user("alice@corp.com", "alice@corp.com", "Alice")

        assert result is user

    @pytest.mark.asyncio
    async def test_updates_name_and_email_if_changed(self):
        user = _make_user(name="Old Name", email="old@corp.com")

        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service._auto_join_default_team", new_callable=AsyncMock),
            patch("app.services.team_service.ensure_current_team", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            from app.services.auth_service import resolve_oauth_user

            await resolve_oauth_user("alice@corp.com", "new@corp.com", "New Name")

        assert user.name == "New Name"
        assert user.email == "new@corp.com"
        user.save.assert_awaited()

    @pytest.mark.asyncio
    async def test_creates_new_user_when_not_found(self):
        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service.Team") as MockTeam,
            patch("app.services.auth_service.TeamMembership") as MockMembership,
            patch("app.services.auth_service._auto_join_default_team", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=None)
            new_user = _make_user(user_id="newguy@corp.com", password_hash=None)
            MockUser.return_value = new_user

            mock_team = _make_team()
            MockTeam.return_value = mock_team
            mock_team.insert = AsyncMock()

            mock_membership = MagicMock()
            mock_membership.insert = AsyncMock()
            MockMembership.return_value = mock_membership

            from app.services.auth_service import resolve_oauth_user

            result = await resolve_oauth_user("newguy@corp.com", "newguy@corp.com", "New Guy")

        assert result is new_user
        new_user.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleans_up_on_team_creation_failure(self):
        with (
            patch("app.services.auth_service.User") as MockUser,
            patch("app.services.auth_service.Team") as MockTeam,
        ):
            MockUser.find_one = AsyncMock(return_value=None)
            new_user = _make_user()
            MockUser.return_value = new_user

            mock_team = MagicMock()
            mock_team.insert = AsyncMock(side_effect=RuntimeError("fail"))
            MockTeam.return_value = mock_team

            from app.services.auth_service import resolve_oauth_user

            with pytest.raises(RuntimeError):
                await resolve_oauth_user("user@corp.com", None, None)

        new_user.delete.assert_awaited_once()


# ---------------------------------------------------------------------------
# _auto_join_default_team
# ---------------------------------------------------------------------------


class TestAutoJoinDefaultTeam:
    @pytest.mark.asyncio
    async def test_does_nothing_when_no_default_team_configured(self):
        user = _make_user()

        with (
            patch("app.models.system_config.SystemConfig") as MockConfig,
        ):
            MockConfig.get_config = AsyncMock(return_value=_make_config(default_team_id=None))

            from app.services.auth_service import _auto_join_default_team

            await _auto_join_default_team(user)

        user.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_membership_and_sets_current_team(self):
        user = _make_user()
        team = _make_team(uuid="default-team")

        with (
            patch("app.models.system_config.SystemConfig") as MockConfig,
            patch("app.services.auth_service.Team") as MockTeam,
            patch("app.services.auth_service.TeamMembership") as MockMembership,
        ):
            MockConfig.get_config = AsyncMock(return_value=_make_config(default_team_id="default-team"))
            MockTeam.find_one = AsyncMock(return_value=team)
            MockMembership.find_one = AsyncMock(return_value=None)  # no existing membership

            mock_membership = MagicMock()
            mock_membership.insert = AsyncMock()
            MockMembership.return_value = mock_membership

            from app.services.auth_service import _auto_join_default_team

            await _auto_join_default_team(user, set_current=True)

        mock_membership.insert.assert_awaited_once()
        assert user.current_team == team.id
        user.save.assert_awaited()

    @pytest.mark.asyncio
    async def test_skips_if_already_member(self):
        user = _make_user()
        team = _make_team()

        with (
            patch("app.models.system_config.SystemConfig") as MockConfig,
            patch("app.services.auth_service.Team") as MockTeam,
            patch("app.services.auth_service.TeamMembership") as MockMembership,
        ):
            MockConfig.get_config = AsyncMock(return_value=_make_config(default_team_id="team-uuid"))
            MockTeam.find_one = AsyncMock(return_value=team)
            MockMembership.find_one = AsyncMock(return_value=MagicMock())  # existing membership

            from app.services.auth_service import _auto_join_default_team

            await _auto_join_default_team(user)

        user.save.assert_not_awaited()
