from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.services import automation_launch as launch

SELECTION = {"documents": [{"uuid": "doc", "title": "Proposal"}], "source": "chosen", "matched": 1}


def receipt(**overrides):
    return SimpleNamespace(document_uuids=["doc"], action_type="workflow", selection=SELECTION, response=None, **overrides)


@pytest.mark.asyncio
async def test_missing_receipt_allows_first_reservation():
    with patch.object(launch.AutomationLaunch, "find_one", new=AsyncMock(return_value=None)) as find:
        assert await launch.recover("auto", "owner", "request", ["doc"]) is None
    find.assert_awaited_once_with({"automation_id": "auto", "user_id": "owner", "request_id": "request"})


@pytest.mark.asyncio
async def test_replay_returns_original_selection_without_dispatch_or_reselecting():
    saved = receipt()
    saved.response = launch.response_for(saved, "event").model_dump()
    with patch.object(launch.AutomationLaunch, "find_one", new=AsyncMock(return_value=saved)), \
         patch.object(launch.WorkflowTriggerEvent, "find_one", new=AsyncMock()) as event:
        result = await launch.recover("auto", "owner", "request", ["doc"])
    assert result.trigger_event_id == "event"
    assert result.documents[0].uuid == "doc"
    event.assert_not_awaited()


@pytest.mark.asyncio
async def test_reused_identity_cannot_change_documents():
    with patch.object(launch.AutomationLaunch, "find_one", new=AsyncMock(return_value=receipt())):
        with pytest.raises(HTTPException) as error:
            await launch.recover("auto", "owner", "request", ["different"])
    assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("action_type", ["workflow", "task", "extraction"])
async def test_lost_receipt_response_recovers_only_its_owned_event(action_type):
    saved = receipt()
    saved.action_type = action_type
    model = launch.ExtractionTriggerEvent if action_type == "extraction" else launch.WorkflowTriggerEvent
    with patch.object(launch.AutomationLaunch, "find_one", new=AsyncMock(return_value=saved)), \
         patch.object(model, "find_one", new=AsyncMock(return_value=SimpleNamespace(id="event", status="running"))) as event:
        result = await launch.recover("auto", "owner", "request", ["doc"])
    assert result.status == "running" and result.trigger_event_id == "event"
    scope = event.await_args.args[0]
    assert scope["trigger_context.launch_request_id"] == "request"
    assert scope.get("user_id", scope.get("trigger_context.run_by_user_id")) == "owner"
    assert scope.get("automation_id", scope.get("trigger_context.automation_id")) == "auto"


@pytest.mark.asyncio
async def test_uncertain_dispatch_never_releases_reservation():
    with patch.object(launch.AutomationLaunch, "find_one", new=AsyncMock(return_value=receipt())), \
         patch.object(launch.WorkflowTriggerEvent, "find_one", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as error:
            await launch.recover("auto", "owner", "request", ["doc"])
    assert error.value.status_code == 409
    assert "not yet confirmed" in error.value.detail


@pytest.mark.asyncio
async def test_competing_reservation_recovers_unique_index_winner():
    saved = receipt(insert=AsyncMock(side_effect=DuplicateKeyError("already reserved")))
    response = launch.response_for(saved, "original")
    with patch.object(launch, "AutomationLaunch", return_value=saved), \
         patch.object(launch, "recover", new=AsyncMock(return_value=response)) as recover:
        reserved, result = await launch.reserve("auto", "owner", "request", ["doc"], SELECTION, "workflow")
    assert reserved is None and result.trigger_event_id == "original"
    recover.assert_awaited_once_with("auto", "owner", "request", ["doc"])


@pytest.mark.asyncio
async def test_missing_winner_cannot_fall_through_to_dispatch():
    saved = receipt(insert=AsyncMock(side_effect=DuplicateKeyError("already reserved")))
    with patch.object(launch, "AutomationLaunch", return_value=saved), \
         patch.object(launch, "recover", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as error:
            await launch.reserve("auto", "owner", "request", ["doc"], SELECTION, "workflow")
    assert error.value.status_code == 409
