"""A stored UTC instant must mean the same thing in every event response."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from starlette.responses import JSONResponse

from app.models.activity import ActivityEvent
from app.routers.automations import _trigger_event_status
from app.services.automation_history import list_runs
from app.utils.timestamps import utc_iso


@pytest.mark.parametrize("stamp", [
    datetime(2026, 10, 29, 22, 28),
    datetime(2026, 10, 29, 22, 28, tzinfo=timezone.utc),
    datetime(2026, 10, 29, 15, 28, tzinfo=timezone(timedelta(hours=-7))),
])
def test_naive_utc_and_explicit_offsets_serialize_to_the_same_instant(stamp):
    assert utc_iso(stamp) == "2026-10-29T22:28:00+00:00"
    activity = ActivityEvent.model_construct(
        type="conversation", user_id="owner", status="failed",
        started_at=stamp, finished_at=stamp, last_updated_at=stamp,
    )
    for key in ("started_at", "finished_at", "last_updated_at"):
        assert activity.to_dict()[key] == "2026-10-29T22:28:00+00:00"


def test_absent_timestamps_stay_absent():
    assert utc_iso(None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["workflow", "extraction"])
@pytest.mark.parametrize("status", ["completed", "running"])
async def test_run_list_and_details_agree_for_database_timestamps(kind, status):
    created = datetime(2026, 10, 29, 21, 38)
    started = created + timedelta(seconds=5)
    completed = started + timedelta(seconds=40) if status == "completed" else None
    oid = ObjectId()
    event = dict(_id=oid, status=status, created_at=created, started_at=started,
                 completed_at=completed, error=None)
    stored = SimpleNamespace(**event, trigger_context={"automation_id": "auto"},
                             automation_id="auto", user_id="owner", workflow_result=None, result=None)
    def query(rows):
        result = MagicMock()
        result.to_list = AsyncMock(return_value=rows)
        return result
    with patch("app.routers.automations.WorkflowTriggerEvent.find_one", new=AsyncMock(return_value=stored if kind == "workflow" else None)), \
         patch("app.routers.automations.ExtractionTriggerEvent.find_one", new=AsyncMock(return_value=stored if kind == "extraction" else None)), \
         patch("app.services.automation_history.WorkflowTriggerEvent.aggregate", return_value=query([event] if kind == "workflow" else [])), \
         patch("app.services.automation_history.ExtractionTriggerEvent.aggregate", return_value=query([event] if kind == "extraction" else [])):
        listing = (await list_runs("auto", 10))["items"][0]
        response = await _trigger_event_status(str(oid), may_view=AsyncMock(return_value=True))
    detail = json.loads(response.body) if isinstance(response, JSONResponse) else response.model_dump()
    for key in ("created_at", "started_at", "completed_at"):
        assert detail[key] == listing[key] == utc_iso(event[key])
    assert detail["created_at"] == "2026-10-29T21:38:00+00:00"
