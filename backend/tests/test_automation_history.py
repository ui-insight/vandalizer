import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.services.automation_history import list_runs

STAMP = datetime.datetime(2026, 9, 28, 12, tzinfo=datetime.timezone.utc)


def event(n, status="completed", at=STAMP):
    return {"_id": ObjectId(f"{n:024x}"), "status": status, "created_at": at, "error": "Failure details" if status == "failed" else None}


def query(rows):
    result = MagicMock()
    result.to_list = AsyncMock(return_value=rows)
    return result


@pytest.mark.asyncio
async def test_merges_types_with_stable_cursor_and_bounded_scoped_queries():
    with patch("app.services.automation_history.WorkflowTriggerEvent.aggregate", return_value=query([event(9), event(7, "failed")])) as workflow, \
         patch("app.services.automation_history.ExtractionTriggerEvent.aggregate", return_value=query([event(8), event(6)])) as extraction:
        page = await list_runs("authorized", 2)
    assert [r["trigger_event_id"] for r in page["items"]] == [f"{9:024x}", f"{8:024x}"]
    assert [r["action_type"] for r in page["items"]] == ["workflow", "extraction"]
    assert page["next_cursor"] == {"before": STAMP.isoformat(), "before_id": f"{8:024x}"}
    for call, field in ((workflow, "trigger_context.automation_id"), (extraction, "automation_id")):
        pipeline = call.call_args.args[0]
        assert pipeline[0] == {"$match": {field: "authorized"}}
        assert pipeline[1] == {"$sort": {"created_at": -1, "_id": -1}}
        assert pipeline[2] == {"$limit": 3}
        assert "result" not in pipeline[3]["$project"]
        assert "output" not in pipeline[3]["$project"]


@pytest.mark.asyncio
async def test_cursor_handles_equal_timestamps_and_last_page():
    with patch("app.services.automation_history.WorkflowTriggerEvent.aggregate", return_value=query([event(7, "failed")])) as workflow, \
         patch("app.services.automation_history.ExtractionTriggerEvent.aggregate", return_value=query([])):
        page = await list_runs("authorized", 2, STAMP, f"{8:024x}")
    assert page["next_cursor"] is None
    assert page["items"][0]["error"] == "Failure details"
    assert workflow.call_args.args[0][0]["$match"]["$or"] == [
        {"created_at": {"$lt": STAMP}},
        {"created_at": STAMP, "_id": {"$lt": ObjectId(f"{8:024x}")}},
    ]


@pytest.mark.asyncio
async def test_empty_history_and_naive_timestamps():
    with patch("app.services.automation_history.WorkflowTriggerEvent.aggregate", return_value=query([event(1, at=STAMP.replace(tzinfo=None))])), \
         patch("app.services.automation_history.ExtractionTriggerEvent.aggregate", return_value=query([])):
        assert (await list_runs("a", 20))["items"][0]["created_at"] == STAMP.isoformat()
    with patch("app.services.automation_history.WorkflowTriggerEvent.aggregate", return_value=query([])), \
         patch("app.services.automation_history.ExtractionTriggerEvent.aggregate", return_value=query([])):
        assert await list_runs("a", 20) == {"items": [], "next_cursor": None}


@pytest.fixture
async def client():
    from app.dependencies import get_current_user
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app
        user = SimpleNamespace(user_id="reader")
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                yield client, user
        finally:
            app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_route_authorizes_automation_before_loading_history(client):
    client, user = client
    with patch("app.routers.automations._load_authorized_automation", new=AsyncMock(return_value=(SimpleNamespace(id="allowed"), None))) as authorize, \
         patch("app.routers.automations.automation_history.list_runs", new=AsyncMock(return_value={"items": [], "next_cursor": None})) as history:
        response = await client.get("/api/automations/allowed/runs?limit=5")
    assert response.status_code == 200, response.text
    authorize.assert_awaited_once_with("allowed", user)
    history.assert_awaited_once_with("allowed", 5, None, None)


@pytest.mark.asyncio
async def test_denied_history_never_queries_events(client):
    client, _ = client
    with patch("app.routers.automations._load_authorized_automation", new=AsyncMock(side_effect=HTTPException(404, "Not found"))), \
         patch("app.routers.automations.automation_history.list_runs", new=AsyncMock()) as history:
        response = await client.get("/api/automations/foreign/runs")
    assert response.status_code == 404
    history.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("params,status", [("limit=101", 422), ("limit=0", 422), ("before_id=invalid", 422), ("before=2026-09-28T12:00:00Z", 400), ("before_id=000000000000000000000001", 400)])
async def test_invalid_pagination_never_queries_history(client, params, status):
    client, _ = client
    with patch("app.routers.automations._load_authorized_automation", new=AsyncMock(return_value=(SimpleNamespace(id="allowed"), None))), \
         patch("app.routers.automations.automation_history.list_runs", new=AsyncMock()) as history:
        response = await client.get(f"/api/automations/allowed/runs?{params}")
    assert response.status_code == status, response.text
    history.assert_not_awaited()
