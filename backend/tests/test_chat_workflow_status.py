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


LABEL = "OMB Uniform Guidance — Subpart D · § 200.308 · part 2"


def _passage(label: str, n: int) -> dict:
    return {"label": label, "document_title": "Subpart D", "content": f"passage {n}", "chunk_id": f"d_chunk_{n}"}


@pytest.mark.asyncio
async def test_a_finished_run_hands_the_ui_the_passages_its_output_cites():
    """A workflow output shown in chat cites its knowledge-base passages by
    their source line. The passages it cites ride along for the chat's
    citation chips (the streaming layer moves them off the result before the
    model reads it); the ones it doesn't cite stay behind."""
    sources = [_passage("OMB Uniform Guidance — Subpart E · § 200.423", 1), _passage(LABEL, 2)]
    done = _status(
        "completed", 3, workflow_id="wf-1", retrieved_sources=sources,
        final_output={"output": f"Rebudgeting needs prior approval [{LABEL}]. Again [{LABEL}]. [Not a source]"},
    )
    result, _ = await _check([done])
    assert result["cited_sources"] == [sources[1]]


@pytest.mark.asyncio
async def test_an_output_citing_nothing_carries_no_passages():
    done = _status("completed", 3, workflow_id="wf-1", retrieved_sources=[_passage(LABEL, 1)],
                   final_output={"output": "Subaward summary: NIFA, $250,000."})
    result, _ = await _check([done])
    assert "cited_sources" not in result


def test_cited_passages_are_capped_and_in_citation_order():
    from app.services import chat_tools

    sources = [_passage(f"Subpart D · § 200.{300 + n}", n) for n in range(20)]
    output = " ".join(f"[Subpart D · § 200.{300 + n}]" for n in reversed(range(20)))
    picked = chat_tools._cited_passages(output, sources)
    assert len(picked) == chat_tools.CITED_PASSAGES_LIMIT
    assert picked[0] is sources[19]
