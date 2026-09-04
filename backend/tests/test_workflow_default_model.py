"""Model resolution for a workflow run.

Precedence: an explicit ``model`` argument wins, then the workflow's own
default (``input_config.default_model``, set via the canvas model selector),
then the user's configured default. ``run_workflow`` and ``run_workflow_batch``
carry the identical resolution line; this exercises it through ``run_workflow``.

No Mongo/Redis: the workflow fetch, the result insert, and the Celery dispatch
are all mocked, and we assert on the model that reaches the dispatched task and
the persisted ``WorkflowResult``.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import workflow_service

pytestmark = pytest.mark.asyncio

# Valid 24-hex ObjectId so ``PydanticObjectId(workflow_id)`` parses before the
# (mocked) ``Workflow.get`` is reached.
WF_ID = "507f1f77bcf86cd799439011"


def _fake_wf(input_config):
    wf = MagicMock()
    wf.id = WF_ID
    wf.steps = [MagicMock()]
    wf.input_config = input_config
    return wf


async def _run_and_capture(*, model=None, input_config=None):
    """Run with everything external mocked. Returns
    (model_dispatched_to_task, model_on_workflow_result, get_user_model_name_mock).
    """
    wf = _fake_wf(input_config)
    captured: dict = {}

    def _send_task(name, kwargs=None, **_):
        captured["model"] = (kwargs or {}).get("model")

    with (
        patch.object(workflow_service.Workflow, "get", AsyncMock(return_value=wf)),
        patch.object(
            workflow_service, "workflow_has_executable_steps",
            AsyncMock(return_value=True),
        ),
        patch.object(
            workflow_service, "get_user_model_name",
            AsyncMock(return_value="user-default"),
        ) as gumn,
        patch.object(workflow_service, "WorkflowResult") as WR,
        patch.object(
            workflow_service.celery_app, "send_task", side_effect=_send_task,
        ),
    ):
        WR.return_value.insert = AsyncMock()
        WR.return_value.id = "result-id"
        await workflow_service.run_workflow(
            workflow_id=WF_ID,
            document_uuids=[],
            user_id="u1",
            model=model,
            user=None,
        )

    return captured.get("model"), WR.call_args.kwargs.get("model"), gumn


async def test_explicit_model_wins_over_workflow_default():
    task_model, result_model, gumn = await _run_and_capture(
        model="explicit-model", input_config={"default_model": "wf-model"},
    )
    assert task_model == "explicit-model"
    assert result_model == "explicit-model"
    gumn.assert_not_awaited()


async def test_workflow_default_used_when_no_explicit_model():
    task_model, result_model, gumn = await _run_and_capture(
        model=None, input_config={"default_model": "wf-model"},
    )
    assert task_model == "wf-model"
    assert result_model == "wf-model"
    # The workflow default short-circuits before the user default is consulted.
    gumn.assert_not_awaited()


async def test_falls_back_to_user_default_when_no_workflow_default():
    task_model, result_model, gumn = await _run_and_capture(
        model=None, input_config={},
    )
    assert task_model == "user-default"
    assert result_model == "user-default"
    gumn.assert_awaited_once()


async def test_null_input_config_falls_back_to_user_default():
    task_model, result_model, gumn = await _run_and_capture(
        model=None, input_config=None,
    )
    assert task_model == "user-default"
    assert result_model == "user-default"
    gumn.assert_awaited_once()


async def test_blank_workflow_default_falls_back_to_user_default():
    # An empty-string default (e.g. the "Automatic (system default)" option)
    # must not be treated as a chosen model.
    task_model, result_model, gumn = await _run_and_capture(
        model=None, input_config={"default_model": ""},
    )
    assert task_model == "user-default"
    assert result_model == "user-default"
    gumn.assert_awaited_once()


class TestEveryPathHonoursTheWorkflowDefault:
    """The canvas states it without qualification -- "Runs every step on this
    model". It was true of the interactive and batch run paths only, so the
    same workflow used one model when a person clicked Run and another when a
    schedule fired, the optimizer measured it, or Test Step tested it."""

    @pytest.mark.asyncio
    async def test_resolver_prefers_the_workflow_default_over_the_user_default(self):
        from app.services.workflow_service import resolve_run_model

        with patch("app.services.workflow_service.get_user_model_name",
                   new=AsyncMock(return_value="user-default")):
            assert await resolve_run_model({"default_model": "wf-model"}, "u1") == "wf-model"

    @pytest.mark.asyncio
    async def test_resolver_falls_back_when_no_workflow_default(self):
        from app.services.workflow_service import resolve_run_model

        with patch("app.services.workflow_service.get_user_model_name",
                   new=AsyncMock(return_value="user-default")):
            for cfg in (None, {}, {"default_model": ""}, {"default_model": None}):
                assert await resolve_run_model(cfg, "u1") == "user-default", cfg

    @pytest.mark.asyncio
    async def test_test_step_uses_the_workflow_default(self):
        """A step whose selector reads "Use workflow default" must be TESTED on
        that model. Tuning against one model and running on another makes the
        selector's own label untrue."""
        from app.services import workflow_service

        task_data: dict = {}
        with patch.object(workflow_service, "get_user_model_name",
                          new=AsyncMock(return_value="user-default")), \
             patch.object(workflow_service.celery_app, "send_task") as send:
            send.return_value = MagicMock(id="t1")
            await workflow_service.test_step(
                "Prompt", task_data, [], "u1",
                workflow_input_config={"default_model": "wf-model"},
            )
        # test_step stamps the resolved model onto task_data before dispatch.
        assert task_data["model"] == "wf-model"
        assert send.call_args.kwargs["kwargs"]["task_data"]["model"] == "wf-model"

    @pytest.mark.asyncio
    async def test_test_step_still_falls_back_without_a_workflow_default(self):
        from app.services import workflow_service

        task_data: dict = {}
        with patch.object(workflow_service, "get_user_model_name",
                          new=AsyncMock(return_value="user-default")), \
             patch.object(workflow_service.celery_app, "send_task") as send:
            send.return_value = MagicMock(id="t1")
            await workflow_service.test_step("Prompt", task_data, [], "u1")
        assert task_data["model"] == "user-default"

    def test_the_automated_path_reads_the_workflow_default(self):
        """passive_tasks resolved the first configured model and never looked at
        the workflow -- so a nightly folder-watch run silently used a different
        model from the manual run of the same workflow."""
        import inspect

        from app.tasks import passive_tasks

        src = inspect.getsource(passive_tasks.execute_workflow_passive)
        assert '"default_model"' in src, (
            "the scheduled/automated run path does not consult the workflow's "
            "default model"
        )

    def test_the_optimizer_reads_the_workflow_default(self):
        """Measuring the workflow on a model it will not run on makes the score,
        and any tuning derived from it, describe a configuration that never
        executes."""
        import inspect

        from app.services import workflow_optimizer

        src = inspect.getsource(workflow_optimizer._execute_workflow_inproc)
        assert '"default_model"' in src, (
            "the optimizer's in-process run path does not consult the "
            "workflow's default model"
        )
