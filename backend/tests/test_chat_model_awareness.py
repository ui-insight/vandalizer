"""Chat knows which model it runs on, and workflows can run on a named model.

Support ticket: asked to "recreate this workflow using the selected model
(kimi-k3)", chat said its tools "do not accept explicit model selection
arguments". It didn't know its own model, and no tool took one, so a workflow
couldn't be compared across two models.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_service import _build_model_block
from app.services.workflow_engine import build_workflow_engine
from tests.test_chat_tools import _make_context

MODELS = [
    {"name": "moonshot/kimi-k3", "tag": "kimi-k3"},
    {"name": "qwen3.8", "tag": "qwen3.8"},
    {"name": "gpt-5", "tag": ""},
]


def _sys_config():
    return SimpleNamespace(available_models=MODELS)


# --- the per-turn Model block ---------------------------------------------


def test_the_model_block_names_the_selected_model_and_the_others():
    block = _build_model_block("moonshot/kimi-k3", {"available_models": MODELS})
    assert "**kimi-k3 (moonshot/kimi-k3)**" in block
    assert "Other configured models: qwen3.8, gpt-5." in block
    assert "`model`" in block and "run_workflow" in block


def test_the_model_block_matches_the_selected_model_by_tag():
    block = _build_model_block("kimi-k3", {"available_models": MODELS})
    assert "**kimi-k3 (moonshot/kimi-k3)**" in block
    assert "kimi-k3 (moonshot/kimi-k3)," not in block.split("Other configured models:")[1]


def test_the_model_block_names_an_unlisted_model_as_is():
    block = _build_model_block("local-llm", {})
    assert "**local-llm**" in block
    assert "Other configured models" not in block


# --- run_workflow ---------------------------------------------------------


def _wf():
    wf = MagicMock()
    wf.name = "Compliance Scan"
    wf.verified = False
    wf.user_id = "user1"
    wf.team_id = "team1"
    wf.input_config = {}
    return wf


async def _run(**kwargs):
    from app.services.chat_tools import run_workflow

    ctx = _make_context(model_name="qwen3.8")
    with patch("app.services.chat_tools.Workflow") as MockWF, \
         patch("app.models.system_config.SystemConfig.get_config", new_callable=AsyncMock, return_value=_sys_config()), \
         patch("app.services.workflow_service.run_workflow", new_callable=AsyncMock, return_value="s-1") as launch:
        MockWF.get = AsyncMock(return_value=_wf())
        result = await run_workflow(ctx, "wf-1", ["doc-1"], **kwargs)
    return result, launch


@pytest.mark.asyncio
async def test_a_named_model_runs_every_step_on_it():
    result, launch = await _run(model="Kimi-K3", confirmed=True)
    assert launch.await_args.kwargs["model"] == "moonshot/kimi-k3"
    assert launch.await_args.kwargs["force_model"] is True
    assert result["model"] == "moonshot/kimi-k3"


@pytest.mark.asyncio
async def test_without_a_model_the_chat_model_is_only_the_default():
    result, launch = await _run(confirmed=True)
    assert launch.await_args.kwargs["model"] == "qwen3.8"
    assert launch.await_args.kwargs["force_model"] is False
    assert result["model"] == "qwen3.8"


@pytest.mark.asyncio
async def test_the_approval_card_names_the_model():
    result, launch = await _run(model="kimi-k3", confirmed=False)
    assert result["needs_confirmation"] is True
    assert "every step on moonshot/kimi-k3" in result["preview"]
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unconfigured_model_is_refused_with_the_configured_names():
    result, launch = await _run(model="gpt-9", confirmed=True)
    assert "not configured" in result["error"]
    assert "moonshot/kimi-k3" in str(result)
    launch.assert_not_awaited()


# --- create_workflow ------------------------------------------------------


@pytest.mark.asyncio
async def test_create_workflow_sets_its_steps_to_a_named_model():
    from app.services.chat_tools import create_workflow

    fake_wf = MagicMock()
    fake_wf.id = "wf-9"
    fake_wf.name = "Scan"
    ctx = _make_context(model_name="qwen3.8")
    steps = [{"name": "Summarize", "type": "summarize"}]
    with patch("app.models.system_config.SystemConfig.get_config", new_callable=AsyncMock, return_value=_sys_config()), \
         patch("app.services.workflow_service.create_workflow", new_callable=AsyncMock, return_value=fake_wf), \
         patch("app.services.workflow_service.add_step", new_callable=AsyncMock, return_value={"id": "s1"}), \
         patch("app.services.workflow_service.add_task", new_callable=AsyncMock, return_value={"id": "t1"}) as add_task:
        preview = await create_workflow(ctx, "Scan", steps, model="kimi-k3", confirmed=False)
        await create_workflow(ctx, "Scan", steps, model="kimi-k3", confirmed=True)

    assert "on moonshot/kimi-k3" in preview["preview"]
    assert add_task.await_args.kwargs["data"]["model"] == "moonshot/kimi-k3"


# --- the engine -----------------------------------------------------------


def _steps():
    return [
        {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
        {"name": "Summarize", "data": {}, "tasks": [
            {"name": "Prompt", "data": {"prompt": "Summarize", "model": "qwen3.8"}},
        ]},
    ]


def _step_model(engine):
    return engine.get_topological_order()[1].tasks[0].data["model"]


def test_a_step_with_its_own_model_keeps_it_by_default():
    engine = build_workflow_engine(_steps(), model="moonshot/kimi-k3")
    assert _step_model(engine) == "qwen3.8"


def test_a_forced_model_wins_over_the_step_and_the_optimizer():
    engine = build_workflow_engine(
        _steps(), model="moonshot/kimi-k3", force_model=True,
        config_override={"step_overrides": {"Summarize": {"model": "gpt-5"}}},
    )
    assert _step_model(engine) == "moonshot/kimi-k3"


# --- resumes --------------------------------------------------------------


def test_both_run_paths_read_the_forced_flag_from_the_run():
    """The flag lives on the run so a resume after an approval step keeps it."""
    import inspect

    from app.tasks import workflow_tasks

    source = inspect.getsource(workflow_tasks)
    assert source.count('force_model=bool(result_doc.get("model_forced"))') == 2
