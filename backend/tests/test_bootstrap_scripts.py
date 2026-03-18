"""Focused tests for bootstrap helper scripts."""

from unittest.mock import MagicMock

import pytest

from create_admin import ensure_admin
from setup_default_team import select_reusable_team


def _make_team(name: str, owner_user_id: str, uuid: str):
    team = MagicMock()
    team.name = name
    team.owner_user_id = owner_user_id
    team.uuid = uuid
    return team


class TestSelectReusableTeam:
    def test_reuses_only_team_owned_by_bootstrap_admin(self):
        owned = _make_team("Research Administration", "bootstrap-admin", "team-owned")
        foreign = _make_team("Research Administration", "someone-else", "team-foreign")

        result = select_reusable_team([foreign, owned], "bootstrap-admin")

        assert result is owned

    def test_returns_none_when_only_foreign_teams_match(self):
        foreign = _make_team("Research Administration", "someone-else", "team-foreign")

        result = select_reusable_team([foreign], "bootstrap-admin")

        assert result is None


class TestEnsureAdmin:
    @pytest.mark.asyncio
    async def test_normalizes_email_lookup(self, monkeypatch):
        existing = MagicMock()
        existing.is_admin = True
        existing.is_examiner = True
        existing.user_id = "admin@example.edu"

        class FakeUser:
            email = "email-field"

            @staticmethod
            async def find_one(_query):
                return existing

        monkeypatch.setattr("create_admin.User", FakeUser)

        user, status = await ensure_admin(" Admin@Example.edu ", "ignored", "Admin")

        assert user is existing
        assert status == "unchanged"
