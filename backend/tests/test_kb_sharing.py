"""Sharing retries preserve their explicit destination state and ownership."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.knowledge_service import share_with_team


def make_kb(**kwargs):
    return SimpleNamespace(uuid="kb-1", title="Research", save=AsyncMock(), **{
        "team_id": "team-a", "team_owned": False, "shared_with_team": False, **kwargs,
    })


@pytest.mark.asyncio
async def test_lost_share_response_can_be_retried_without_reversing_or_notifying_again():
    kb = make_kb()
    user = SimpleNamespace(current_team="team-a")
    with (
        patch("app.services.knowledge_service.get_knowledge_base", AsyncMock(return_value=kb)) as get,
        patch("app.models.team.Team.get", AsyncMock(return_value=object())),
        patch("app.services.team_service.notify_team_share", AsyncMock()) as notify,
    ):
        await share_with_team("kb-1", user, shared_with_team=True, comment="Read this")
        await share_with_team("kb-1", user, shared_with_team=True, comment="Read this")
    assert kb.shared_with_team is True
    kb.save.assert_awaited_once()
    notify.assert_awaited_once()
    assert get.call_args.kwargs["manage"] is True


@pytest.mark.asyncio
async def test_explicit_unshare_retry_stays_unshared():
    kb = make_kb(shared_with_team=True)
    with patch("app.services.knowledge_service.get_knowledge_base", AsyncMock(return_value=kb)):
        await share_with_team("kb-1", SimpleNamespace(current_team="team-a"), shared_with_team=False)
        await share_with_team("kb-1", SimpleNamespace(current_team="team-a"), shared_with_team=False)
    assert kb.shared_with_team is False
    kb.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_team_owned_kb_cannot_be_unshared_and_lost_from_both_lists():
    kb = make_kb(team_owned=True, shared_with_team=True)
    with patch("app.services.knowledge_service.get_knowledge_base", AsyncMock(return_value=kb)):
        with pytest.raises(ValueError, match="must remain shared"):
            await share_with_team("kb-1", SimpleNamespace(current_team="team-a"), shared_with_team=False)
    kb.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_personal_kb_gets_a_real_team_destination_when_shared():
    kb = make_kb(team_id=None)
    with (
        patch("app.services.knowledge_service.get_knowledge_base", AsyncMock(return_value=kb)),
        patch("app.models.team.Team.get", AsyncMock(return_value=object())),
        patch("app.services.team_service.notify_team_share", AsyncMock()),
    ):
        await share_with_team("kb-1", SimpleNamespace(current_team="team-b"), shared_with_team=True)
    assert kb.team_id == "team-b"
    assert kb.shared_with_team is True


@pytest.mark.asyncio
async def test_no_team_or_permission_means_no_write():
    kb = make_kb(team_id=None)
    with patch("app.services.knowledge_service.get_knowledge_base", AsyncMock(return_value=kb)):
        with pytest.raises(ValueError, match="Join or select"):
            await share_with_team("kb-1", SimpleNamespace(current_team=None), shared_with_team=True)
    kb.save.assert_not_awaited()
    with patch("app.services.knowledge_service.get_knowledge_base", AsyncMock(return_value=None)):
        assert await share_with_team("kb-1", SimpleNamespace(current_team="team-a"), shared_with_team=True) is None
