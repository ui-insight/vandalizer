"""Module 7 (Output & Delivery) grading.

The third star asked for a Package Builder node, which is still "Coming Soon"
in the workflow editor palette, so no trainee could earn it. A run workflow
with 2+ steps marked "Include in deliverables" downloads as a ZIP bundle, and
now earns the star; a PackageBuilder task still counts for when it ships.

The model symbols are patched wholesale so the validator can run without an
initialized Beanie connection.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import certification_service as cs


def _workflow_model(workflows):
    q = MagicMock()
    q.to_list = AsyncMock(return_value=workflows)
    m = MagicMock()
    m.find.return_value = q
    return m


def _getter(records):
    m = MagicMock()
    m.get = AsyncMock(side_effect=lambda rid: records.get(rid))
    return m


async def _run(steps, tasks, *, executions=1):
    """One workflow with the given steps ({id: (is_output, [task ids])})."""
    wf = SimpleNamespace(steps=list(steps), num_executions=executions)
    step_docs = {
        sid: SimpleNamespace(is_output=is_output, tasks=task_ids)
        for sid, (is_output, task_ids) in steps.items()
    }
    task_docs = {tid: SimpleNamespace(name=name) for tid, name in tasks.items()}
    with patch.object(cs, "Workflow", _workflow_model([wf])), \
         patch.object(cs, "WorkflowStep", _getter(step_docs)), \
         patch.object(cs, "WorkflowStepTask", _getter(task_docs)):
        return await cs._validate_output_delivery("alice")


async def test_single_output_node_earns_one_star():
    out = await _run(
        {"s1": (False, ["t1"]), "s2": (False, ["t2"])},
        {"t1": "Prompt", "t2": "DocumentRenderer"},
    )
    assert out["passed"] is True
    assert out["stars"] == 1


async def test_two_deliverable_steps_earn_the_zip_star():
    out = await _run(
        {"s1": (True, ["t1"]), "s2": (True, ["t2"])},
        {"t1": "DataExport", "t2": "DocumentRenderer"},
    )
    assert out["stars"] == 3


async def test_zip_star_needs_the_workflow_to_have_run():
    out = await _run(
        {"s1": (True, ["t1"]), "s2": (True, ["t2"])},
        {"t1": "DataExport", "t2": "DocumentRenderer"},
        executions=0,
    )
    assert out["passed"] is False
    assert out["stars"] == 0


async def test_one_deliverable_step_is_not_a_zip():
    out = await _run(
        {"s1": (False, ["t1"]), "s2": (True, ["t2"])},
        {"t1": "Prompt", "t2": "DocumentRenderer"},
    )
    assert out["stars"] == 1


async def test_package_builder_still_earns_the_third_star():
    out = await _run({"s1": (False, ["t1"])}, {"t1": "PackageBuilder"})
    assert out["stars"] == 3
