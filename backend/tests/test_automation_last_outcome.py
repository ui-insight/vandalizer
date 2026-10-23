"""List summaries use persisted events, bounded to authorized automation IDs."""
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.automations import _latest_run_summaries


@pytest.mark.asyncio
async def test_latest_event_merges_types_and_scopes_queries():
    older = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    newer = older + datetime.timedelta(days=1)
    wf_query = MagicMock()
    wf_query.to_list = AsyncMock(return_value=[{"_id": "visible", "status": "failed", "created_at": older}])
    ex_query = MagicMock()
    ex_query.to_list = AsyncMock(return_value=[{"_id": "visible", "status": "completed", "created_at": newer}])
    with patch("app.routers.automations.WorkflowTriggerEvent.aggregate", return_value=wf_query) as wf, \
         patch("app.routers.automations.ExtractionTriggerEvent.aggregate", return_value=ex_query) as ex:
        result = await _latest_run_summaries([SimpleNamespace(id="visible")])
    assert result["visible"]["status"] == "completed"
    assert wf.call_args.args[0][0] == {"$match": {"trigger_context.automation_id": {"$in": ["visible"]}}}
    assert ex.call_args.args[0][0] == {"$match": {"automation_id": {"$in": ["visible"]}}}
    assert wf.call_count == ex.call_count == 1


@pytest.mark.asyncio
async def test_empty_list_never_queries_event_history():
    with patch("app.routers.automations.WorkflowTriggerEvent.aggregate") as aggregate:
        assert await _latest_run_summaries([]) == {}
    aggregate.assert_not_called()
