"""Tests for app.services.account_deletion_service.get_deletion_summary.

The actual deletion flow (`delete_user_account`) does destructive Beanie+
ChromaDB+storage calls that are covered by integration tests. The preview
function is the one the UI hits on every settings page visit, so it
deserves unit coverage.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.account_deletion_service import get_deletion_summary


def _count_finder(n: int) -> MagicMock:
    """Builds a chainable Model.find(...) mock whose .count() awaits to *n*."""
    q = MagicMock()
    q.count = AsyncMock(return_value=n)
    return q


def _to_list_finder(items: list) -> MagicMock:
    """Builds a Model.find(...) mock whose .to_list() awaits to *items*."""
    q = MagicMock()
    q.to_list = AsyncMock(return_value=items)
    return q


@pytest.fixture
def patched_models():
    """Patch every Beanie model imported inside get_deletion_summary.

    The function does `from app.models.X import Y` inline, so patching the
    class at its module of origin (not the service module) is what
    intercepts the lookup.
    """
    with (
        patch("app.models.document.SmartDocument") as MockDoc,
        patch("app.models.folder.SmartFolder") as MockFolder,
        patch("app.models.chat.ChatConversation") as MockConv,
        patch("app.models.workflow.Workflow") as MockWf,
        patch("app.models.search_set.SearchSet") as MockSS,
        patch("app.models.knowledge.KnowledgeBase") as MockKB,
        patch("app.models.team.Team") as MockTeam,
        patch("app.models.team.TeamMembership") as MockTM,
    ):
        yield {
            "SmartDocument": MockDoc,
            "SmartFolder": MockFolder,
            "ChatConversation": MockConv,
            "Workflow": MockWf,
            "SearchSet": MockSS,
            "KnowledgeBase": MockKB,
            "Team": MockTeam,
            "TeamMembership": MockTM,
        }


class TestGetDeletionSummary:
    @pytest.mark.asyncio
    async def test_clean_user_can_delete(self, patched_models):
        """A user with no owned teams and no data can delete freely."""
        m = patched_models
        m["SmartDocument"].find = MagicMock(return_value=_count_finder(0))
        m["SmartFolder"].find = MagicMock(return_value=_count_finder(0))
        m["ChatConversation"].find = MagicMock(return_value=_count_finder(0))
        m["Workflow"].find = MagicMock(return_value=_count_finder(0))
        m["SearchSet"].find = MagicMock(return_value=_count_finder(0))
        m["KnowledgeBase"].find = MagicMock(return_value=_count_finder(0))
        m["TeamMembership"].find = MagicMock(return_value=_to_list_finder([]))
        m["Team"].find = MagicMock(return_value=_to_list_finder([]))

        summary = await get_deletion_summary("alice")

        assert summary["can_delete"] is True
        assert summary["blocking_reason"] is None
        assert summary["data_summary"]["documents"] == 0
        assert summary["owned_teams_with_members"] == []

    @pytest.mark.asyncio
    async def test_data_counts_propagated(self, patched_models):
        m = patched_models
        m["SmartDocument"].find = MagicMock(return_value=_count_finder(12))
        m["SmartFolder"].find = MagicMock(return_value=_count_finder(3))
        m["ChatConversation"].find = MagicMock(return_value=_count_finder(8))
        m["Workflow"].find = MagicMock(return_value=_count_finder(4))
        m["SearchSet"].find = MagicMock(return_value=_count_finder(2))
        m["KnowledgeBase"].find = MagicMock(return_value=_count_finder(1))
        m["TeamMembership"].find = MagicMock(return_value=_to_list_finder([
            MagicMock(), MagicMock(),  # member of two teams
        ]))
        m["Team"].find = MagicMock(return_value=_to_list_finder([]))

        summary = await get_deletion_summary("alice")

        data = summary["data_summary"]
        assert data["documents"] == 12
        assert data["folders"] == 3
        assert data["chat_conversations"] == 8
        assert data["workflows"] == 4
        assert data["search_sets"] == 2
        assert data["knowledge_bases"] == 1
        assert data["teams_owned"] == 0
        assert data["teams_member"] == 2

    @pytest.mark.asyncio
    async def test_solo_owned_team_does_not_block(self, patched_models):
        """An owner of a team with only themselves as member can still delete."""
        m = patched_models
        # Zero-out counts for brevity
        for name in ("SmartDocument", "SmartFolder", "ChatConversation",
                     "Workflow", "SearchSet", "KnowledgeBase"):
            m[name].find = MagicMock(return_value=_count_finder(0))
        m["TeamMembership"].find = MagicMock(return_value=_to_list_finder([]))

        solo_team = SimpleNamespace(uuid="team-solo", name="Solo", id="oid-solo")
        m["Team"].find = MagicMock(return_value=_to_list_finder([solo_team]))

        # The second TeamMembership.find() call checks for other members —
        # return a query whose .count() resolves to 0.
        def tm_find(*args, **kwargs):
            # First call returns memberships list; second is the per-team
            # "other members" count. Simplify: both return 0/empty.
            return _count_finder(0)

        m["TeamMembership"].find = MagicMock(
            side_effect=[_to_list_finder([]), _count_finder(0)]
        )

        summary = await get_deletion_summary("alice")

        assert summary["can_delete"] is True
        assert summary["owned_teams_with_members"] == []
        assert summary["data_summary"]["teams_owned"] == 1

    @pytest.mark.asyncio
    async def test_owned_team_with_other_members_blocks_deletion(self, patched_models):
        m = patched_models
        for name in ("SmartDocument", "SmartFolder", "ChatConversation",
                     "Workflow", "SearchSet", "KnowledgeBase"):
            m[name].find = MagicMock(return_value=_count_finder(0))

        shared_team = SimpleNamespace(uuid="team-shared", name="Research Group", id="oid-shared")
        m["Team"].find = MagicMock(return_value=_to_list_finder([shared_team]))
        # First TeamMembership.find() → user's memberships; second → other
        # members of the owned team (= 3 blocking members).
        m["TeamMembership"].find = MagicMock(
            side_effect=[_to_list_finder([]), _count_finder(3)]
        )

        summary = await get_deletion_summary("alice")

        assert summary["can_delete"] is False
        assert "Transfer ownership" in summary["blocking_reason"]
        blocking = summary["owned_teams_with_members"]
        assert len(blocking) == 1
        assert blocking[0]["uuid"] == "team-shared"
        assert blocking[0]["name"] == "Research Group"
        assert blocking[0]["member_count"] == 3
