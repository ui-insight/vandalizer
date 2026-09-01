"""Auto-triggered ("shadow") optimizer runs must respect the same
preconditions the manual start routes enforce.

Without this gate a quality signal on a workflow that has no validation plan
or no test inputs created a run document, dispatched it, and let it die in the
worker — surfacing on the Tuning suggestions page as a "Tuning failed" row the
user can do nothing about.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import optimizer_signal_service as sig

_WF_OID = "507f1f77bcf86cd799439011"


_PLAN = {"checks": [{"id": "c1"}]}


def _workflow(validation_plan=_PLAN):
    wf = MagicMock()
    wf.validation_plan = validation_plan
    return wf


def _run_model():
    """Stand-in for a Beanie run Document class."""
    instance = MagicMock()
    instance.uuid = "run-uuid"
    instance.insert = AsyncMock()
    model = MagicMock(return_value=instance)
    model.find_one = AsyncMock(return_value=None)
    return model, instance


class TestWorkflowShadowPreflight:
    @pytest.mark.asyncio
    async def test_skips_when_no_test_inputs(self):
        model, instance = _run_model()

        with patch.object(sig, "WorkflowOptimizationRun", model), \
             patch.object(sig, "_already_recent", AsyncMock(return_value=False)), \
             patch("app.models.workflow.Workflow") as MockWf, \
             patch("app.services.workflow_optimizer._resolve_test_inputs",
                   AsyncMock(return_value=[])), \
             patch("app.tasks.workflow_optimization_tasks.optimize_workflow_task") as task:
            MockWf.get = AsyncMock(return_value=_workflow())

            result = await sig.enqueue_workflow_shadow_run(
                workflow_id=_WF_OID, user_id="u1", trigger="cross_field_failure",
            )

        assert result is None
        instance.insert.assert_not_awaited()
        task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_validation_plan(self):
        model, instance = _run_model()

        with patch.object(sig, "WorkflowOptimizationRun", model), \
             patch.object(sig, "_already_recent", AsyncMock(return_value=False)), \
             patch("app.models.workflow.Workflow") as MockWf, \
             patch("app.tasks.workflow_optimization_tasks.optimize_workflow_task") as task:
            MockWf.get = AsyncMock(return_value=_workflow(validation_plan=None))
            # Guard order matters: the plan check must short-circuit before the
            # (more expensive) test-input resolution.
            with patch("app.services.workflow_optimizer._resolve_test_inputs",
                       AsyncMock(side_effect=AssertionError("should not resolve"))):
                result = await sig.enqueue_workflow_shadow_run(
                    workflow_id=_WF_OID, user_id="u1", trigger="quality_alert",
                )

        assert result is None
        instance.insert.assert_not_awaited()
        task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_workflow_missing(self):
        model, instance = _run_model()

        with patch.object(sig, "WorkflowOptimizationRun", model), \
             patch.object(sig, "_already_recent", AsyncMock(return_value=False)), \
             patch("app.models.workflow.Workflow") as MockWf, \
             patch("app.tasks.workflow_optimization_tasks.optimize_workflow_task") as task:
            MockWf.get = AsyncMock(return_value=None)

            result = await sig.enqueue_workflow_shadow_run(
                workflow_id=_WF_OID, user_id="u1", trigger="quality_alert",
            )

        assert result is None
        task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueues_when_preconditions_hold(self):
        model, instance = _run_model()

        with patch.object(sig, "WorkflowOptimizationRun", model), \
             patch.object(sig, "_already_recent", AsyncMock(return_value=False)), \
             patch("app.models.workflow.Workflow") as MockWf, \
             patch("app.services.workflow_optimizer._resolve_test_inputs",
                   AsyncMock(return_value=[{"id": "vi-1", "doc_uuids": ["d1"]}])), \
             patch("app.tasks.workflow_optimization_tasks.optimize_workflow_task") as task:
            MockWf.get = AsyncMock(return_value=_workflow())

            result = await sig.enqueue_workflow_shadow_run(
                workflow_id=_WF_OID, user_id="u1", trigger="cross_field_failure",
            )

        assert result == "run-uuid"
        instance.insert.assert_awaited_once()
        task.delay.assert_called_once()


def _test_case(expected_values):
    return SimpleNamespace(expected_values=expected_values)


def _patch_test_cases(cases):
    model = MagicMock()
    model.find = MagicMock(return_value=SimpleNamespace(
        to_list=AsyncMock(return_value=cases),
    ))
    return model


class TestExtractionShadowPreflight:
    @pytest.mark.asyncio
    async def test_skips_when_no_expected_values(self):
        model, instance = _run_model()

        with patch.object(sig, "ExtractionOptimizationRun", model), \
             patch("app.services.search_set_service.get_extraction_keys",
                   AsyncMock(return_value=["field_a"])), \
             patch("app.models.extraction_test_case.ExtractionTestCase",
                   _patch_test_cases([_test_case({}), _test_case({"field_a": ""})])), \
             patch("app.tasks.extraction_tasks.optimize_extraction_task") as task:
            result = await sig.enqueue_extraction_shadow_run(
                search_set_uuid="ss-1", user_id="u1", trigger="quality_alert",
            )

        assert result is None
        instance.insert.assert_not_awaited()
        task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_fields(self):
        model, instance = _run_model()

        with patch.object(sig, "ExtractionOptimizationRun", model), \
             patch("app.services.search_set_service.get_extraction_keys",
                   AsyncMock(return_value=[])), \
             patch("app.tasks.extraction_tasks.optimize_extraction_task") as task:
            result = await sig.enqueue_extraction_shadow_run(
                search_set_uuid="ss-1", user_id="u1", trigger="quality_alert",
            )

        assert result is None
        task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueues_when_a_case_has_expected_values(self):
        model, instance = _run_model()

        with patch.object(sig, "ExtractionOptimizationRun", model), \
             patch("app.services.search_set_service.get_extraction_keys",
                   AsyncMock(return_value=["field_a"])), \
             patch("app.models.extraction_test_case.ExtractionTestCase",
                   _patch_test_cases([_test_case({"field_a": "Idaho"})])), \
             patch("app.tasks.extraction_tasks.optimize_extraction_task") as task:
            result = await sig.enqueue_extraction_shadow_run(
                search_set_uuid="ss-1", user_id="u1", trigger="quality_alert",
            )

        assert result == "run-uuid"
        instance.insert.assert_awaited_once()
        task.delay.assert_called_once()
