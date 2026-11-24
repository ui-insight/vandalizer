"""Chat reports a workflow run as it ended, not as it was a moment after it started.

Support ticket: after run_workflow, chat checked the run straight away and
wrote "Running · 0/3 steps … currently on step 1", while the run card beside
it updated live to "Workflow complete · 3/3 steps" with the result.
get_workflow_status now waits for the run to settle before answering.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.test_chat_tools import _make_context


def _status(status, done, **extra):
    return {
        "status": status, "num_steps_completed": done, "num_steps_total": 3,
        "current_step_name": "Summarize", "current_step_detail": None, "current_step_preview": None,
        "final_output": None, "steps_output": {}, "approval_request_id": None, "error": None, **extra,
    }


async def _check(sequence, **kwargs):
    from app.services import chat_tools

    lookup = AsyncMock(side_effect=sequence)
    with patch("app.services.workflow_service.get_workflow_status", lookup), \
         patch.object(chat_tools, "_RUN_POLL_SECONDS", 0), \
         patch.object(chat_tools, "_workflow_quality_sidecar", AsyncMock(return_value=None)):
        result = await chat_tools.get_workflow_status(_make_context(), "session-1", **kwargs)
    return result, lookup


@pytest.mark.asyncio
async def test_waits_for_the_run_to_finish_and_returns_its_result():
    done = _status("completed", 3, final_output={"output": "Subaward summary: NIFA, $250,000."}, workflow_id="wf-1")
    result, lookup = await _check([_status("running", 0), _status("running", 2), done])
    assert result["status"] == "completed" and result["steps_completed"] == 3
    assert result["output"] == "Subaward summary: NIFA, $250,000."
    assert "message" not in result
    assert lookup.await_count == 3


@pytest.mark.asyncio
async def test_a_run_still_going_after_the_wait_is_reported_as_a_snapshot():
    from app.services import chat_tools

    with patch.object(chat_tools, "_RUN_WAIT_SECONDS", 0):
        result, _ = await _check([_status("running", 1)])
    assert result["status"] == "running"
    assert "snapshot" in result["message"] and "run card" in result["message"]
    assert 'now on "Summarize"' in result["message"]


@pytest.mark.asyncio
async def test_a_failed_run_reports_why():
    # WorkflowResult records a failed run as "error"; the tool only looked for "failed".
    result, lookup = await _check([_status("error", 1, error="Step 2 timed out")])
    assert result["error_detail"] == "Step 2 timed out"
    assert "message" not in result
    assert lookup.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending_approval", "canceled"])
async def test_a_run_waiting_on_a_person_or_canceled_is_not_waited_on(status):
    _, lookup = await _check([_status(status, 1)])
    assert lookup.await_count == 1


@pytest.mark.asyncio
async def test_a_quick_check_does_not_wait():
    result, lookup = await _check([_status("running", 1)], wait=False)
    assert lookup.await_count == 1 and result["status"] == "running"
