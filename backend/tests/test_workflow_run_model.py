"""Every workflow run records and shows which model it used.

Support ticket: a workflow set to kimi-k3 in the editor was run from a chat
on VandalAI, and no screen said which model ran it. Chat passed its own model,
which beat the workflow's, and nothing recorded the models the steps used.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.workflows import WorkflowStatusResponse
from app.services.workflow_engine import build_workflow_engine
from app.tasks.workflow_tasks import _record_models_used
from tests.test_chat_tools import _make_context


def _steps():
    return [
        {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
        {"name": "Extract", "data": {}, "tasks": [{"name": "Extraction", "data": {"keys": ["FAIN"]}}]},
        {"name": "Review", "data": {}, "tasks": [{"name": "Approval", "data": {"model": "unused"}}]},
        {"name": "Memo", "data": {}, "tasks": [{"name": "Prompt", "data": {"prompt": "Memo", "model": "VandalAI"}}]},
    ]


def test_the_engine_records_the_models_its_steps_run_on():
    engine = build_workflow_engine(_steps(), model="moonshotai/kimi-k3", user_id="u")
    # The step override counts; an approval step's model is never used.
    assert engine.models_used == ["moonshotai/kimi-k3", "VandalAI"]


def test_a_forced_model_is_the_only_model_used():
    engine = build_workflow_engine(_steps(), model="moonshotai/kimi-k3", user_id="u", force_model=True)
    assert engine.models_used == ["moonshotai/kimi-k3"]


def test_the_run_stores_the_models_used():
    db = MagicMock()
    engine = MagicMock(models_used=["moonshotai/kimi-k3"])
    _record_models_used(db, "65f000000000000000000001", engine)
    update = db.workflow_result.update_one.call_args.args[1]
    assert update == {"$set": {"models_used": ["moonshotai/kimi-k3"]}}


def test_a_failed_record_does_not_stop_the_run():
    db = MagicMock()
    db.workflow_result.update_one.side_effect = RuntimeError("mongo down")
    _record_models_used(db, "65f000000000000000000001", MagicMock(models_used=[]))


def test_the_status_response_carries_the_models():
    body = WorkflowStatusResponse(status="completed", model="VandalAI", models_used=["moonshotai/kimi-k3"])
    assert body.model_dump()["models_used"] == ["moonshotai/kimi-k3"]


# --- chat runs the workflow on the workflow's model -------------------------


def _wf(default_model=None):
    wf = MagicMock()
    wf.name = "Test Approval gate"
    wf.verified = False
    wf.user_id = "user1"
    wf.team_id = "team1"
    wf.input_config = {"default_model": default_model} if default_model else {}
    return wf


async def _run(wf, **kwargs):
    from app.services.chat_tools import run_workflow

    ctx = _make_context(model_name="VandalAI")
    with patch("app.services.chat_tools.Workflow") as MockWF, \
         patch("app.services.workflow_service.run_workflow", new_callable=AsyncMock, return_value="s-1") as launch:
        MockWF.get = AsyncMock(return_value=wf)
        result = await run_workflow(ctx, "wf-1", ["doc-1"], **kwargs)
    return result, launch


@pytest.mark.asyncio
async def test_chat_runs_a_workflow_on_the_model_set_in_the_workflow():
    preview, _ = await _run(_wf("moonshotai/kimi-k3"), confirmed=False)
    assert "on moonshotai/kimi-k3 (the workflow's model)" in preview["preview"]

    result, launch = await _run(_wf("moonshotai/kimi-k3"), confirmed=True)
    assert launch.await_args.kwargs["model"] == "moonshotai/kimi-k3"
    assert launch.await_args.kwargs["force_model"] is False
    assert result["model"] == "moonshotai/kimi-k3"


@pytest.mark.asyncio
async def test_a_workflow_with_no_model_runs_on_the_chat_model_and_says_so():
    preview, _ = await _run(_wf(), confirmed=False)
    assert "on VandalAI (this chat's model)" in preview["preview"]
    _, launch = await _run(_wf(), confirmed=True)
    assert launch.await_args.kwargs["model"] == "VandalAI"


# --- the workflow's History tab ---------------------------------------------


def _query(items):
    q = MagicMock()
    q.sort.return_value = q
    q.limit.return_value = q
    q.to_list = AsyncMock(return_value=items)
    return q


def _history_event(model_usage):
    return MagicMock(
        id="ev1", status="completed", started_at=None, finished_at=None, duration_ms=10,
        error="", tokens_input=1, tokens_output=1, documents_touched=1, steps_completed=2,
        steps_total=2, workflow_session_id="s-1", result_snapshot={}, meta_summary={},
        model_usage=model_usage,
    )


@pytest.mark.asyncio
async def test_history_falls_back_to_the_recorded_models_for_an_unmetered_run():
    # Runs from before calls were metered have no model_usage; History still
    # names their model, in the same field a metered run uses.
    from app.routers import workflows as router

    run = MagicMock(session_id="s-1", model="VandalAI", models_used=["moonshotai/kimi-k3"])
    with patch.object(router, "get_authorized_workflow", new=AsyncMock(return_value=MagicMock(id="wf"))), \
         patch("app.models.activity.ActivityEvent") as AE, \
         patch("app.models.workflow.WorkflowResult") as WR:
        AE.find.return_value = _query([_history_event([])])
        WR.find.return_value = _query([run])
        body = await router.get_workflow_history("wf", limit=5, user=MagicMock(user_id="u"))

    row = body["runs"][0]
    assert row["models"] == ["moonshotai/kimi-k3"]
    assert "models_used" not in row and "model" not in row


@pytest.mark.asyncio
async def test_history_uses_the_metered_models_and_skips_the_result_lookup():
    from app.routers import workflows as router

    usage = [{"step_index": 0, "step": "Extract", "model": "gpt-oss-120b", "tokens_input": 5, "tokens_output": 1}]
    with patch.object(router, "get_authorized_workflow", new=AsyncMock(return_value=MagicMock(id="wf"))), \
         patch("app.models.activity.ActivityEvent") as AE, \
         patch("app.models.workflow.WorkflowResult") as WR:
        AE.find.return_value = _query([_history_event(usage)])
        body = await router.get_workflow_history("wf", limit=5, user=MagicMock(user_id="u"))

    WR.find.assert_not_called()
    assert body["runs"][0]["models"] == ["gpt-oss-120b"]
    assert "models_used" not in body["runs"][0]
