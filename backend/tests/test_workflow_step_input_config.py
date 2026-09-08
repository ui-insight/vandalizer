"""Input is configured on the step, and every task in the step receives it.

Covers ``apply_step_input_config`` directly, its reach through
``build_workflow_engine``, and the ordering guarantee the step editor's Output
tab makes about how a step's parallel tasks combine.
"""

from __future__ import annotations

import time

from app.services.workflow_engine import (
    MultiTaskNode,
    Node,
    _resolve_input_sources,
    apply_step_input_config,
    build_workflow_engine,
    step_defines_input,
)


# ---------------------------------------------------------------------------
# apply_step_input_config
# ---------------------------------------------------------------------------


def test_step_input_reaches_a_task_that_has_none():
    step = {"input_sources": ["workflow_documents"], "input_source": "workflow_documents"}
    task = {"prompt": "summarize"}

    apply_step_input_config(step, task)

    assert task["input_sources"] == ["workflow_documents"]
    assert task["prompt"] == "summarize"  # untouched


def test_step_input_replaces_a_task_s_own_stale_config():
    step = {"input_sources": ["step_input"]}
    task = {"input_sources": ["workflow_documents"], "selected_document_uuid": "doc-1"}

    apply_step_input_config(step, task)

    assert task["input_sources"] == ["step_input"]
    # The stale per-task document must not survive — the step did not select one.
    assert "selected_document_uuid" not in task


def test_step_input_carries_the_selected_document():
    step = {"input_sources": ["select_document"], "selected_document_uuid": "doc-9"}
    task = {}

    apply_step_input_config(step, task)

    assert task["selected_document_uuid"] == "doc-9"


def test_a_task_with_the_advanced_override_keeps_its_own_input():
    step = {"input_sources": ["step_input"]}
    task = {"override_step_input": True, "input_sources": ["select_document"], "selected_document_uuid": "doc-2"}

    apply_step_input_config(step, task)

    assert task["input_sources"] == ["select_document"]
    assert task["selected_document_uuid"] == "doc-2"


def test_a_legacy_step_leaves_its_tasks_alone():
    # Workflows authored before input moved to the step have nothing stored on
    # the step. Their per-task config is still what the run must honor.
    step = {}
    task = {"input_sources": ["workflow_documents"], "selected_document_uuid": "doc-3"}

    apply_step_input_config(step, task)

    assert task["input_sources"] == ["workflow_documents"]
    assert task["selected_document_uuid"] == "doc-3"


def test_a_legacy_step_with_unrelated_data_still_counts_as_unconfigured():
    step = {"note": "something else"}
    task = {"input_sources": ["workflow_documents"]}

    apply_step_input_config(step, task)

    assert task["input_sources"] == ["workflow_documents"]
    assert step_defines_input(step) is False


def test_applying_twice_is_a_no_op():
    step = {"input_sources": ["select_document"], "selected_document_uuid": "doc-4"}
    task = {"input_sources": ["step_input"]}

    apply_step_input_config(step, task)
    first = dict(task)
    apply_step_input_config(step, task)

    assert task == first


# ---------------------------------------------------------------------------
# Reaching the constructed nodes
# ---------------------------------------------------------------------------


def _steps_with(step_data, task_datas):
    return [
        {"name": "Document", "data": {"doc_uuids": []}, "tasks": []},
        {
            "name": "Analyze",
            "data": step_data,
            "tasks": [{"name": "Prompt", "data": d} for d in task_datas],
        },
    ]


def test_every_task_in_a_step_is_built_with_the_step_s_input():
    engine = build_workflow_engine(
        steps_data=_steps_with(
            {"input_sources": ["workflow_documents"]},
            [{"prompt": "a"}, {"prompt": "b", "input_sources": ["step_input"]}],
        ),
        model="test-model",
    )

    step_node = engine.get_topological_order()[1]
    assert len(step_node.tasks) == 2
    for task in step_node.tasks:
        assert _resolve_input_sources(task.data) == ["workflow_documents"]


def test_an_overriding_task_is_built_with_its_own_input():
    engine = build_workflow_engine(
        steps_data=_steps_with(
            {"input_sources": ["workflow_documents"]},
            [
                {"prompt": "a"},
                {"prompt": "b", "override_step_input": True, "input_sources": ["step_input"]},
            ],
        ),
        model="test-model",
    )

    shared, overriding = engine.get_topological_order()[1].tasks
    assert _resolve_input_sources(shared.data) == ["workflow_documents"]
    assert _resolve_input_sources(overriding.data) == ["step_input"]


# ---------------------------------------------------------------------------
# How the step's tasks combine
# ---------------------------------------------------------------------------


class _SlowNode(Node):
    """Returns ``value`` after ``delay`` seconds, so completion order != task order."""

    def __init__(self, name, value, delay):
        super().__init__(name)
        self.value = value
        self.delay = delay

    def process(self, inputs):
        time.sleep(self.delay)
        return {"step_name": self.name, "output": self.value, "input": inputs.get("input")}


def test_a_step_combines_its_tasks_outputs_in_task_order():
    # The step editor tells authors the outputs are collected in the order the
    # tasks are listed. The slow-first task makes that a real claim: under
    # completion ordering this returns ["second", "first"].
    step = MultiTaskNode("Analyze")
    step.add_tasks([
        _SlowNode("first", "first", 0.25),
        _SlowNode("second", "second", 0.0),
    ])

    result = step.process({"input": "x", "output": "x", "step_name": "Prev"})

    assert result["output"] == ["first", "second"]


def test_a_single_task_step_passes_its_output_through_unwrapped():
    step = MultiTaskNode("Analyze")
    step.add_task(_SlowNode("only", "value", 0.0))

    result = step.process({"input": "x", "output": "x", "step_name": "Prev"})

    assert result["output"] == "value"


class TestEveryPathThatBuildsStepsDataResolvesInput:
    """`apply_step_input_config` has to run before a path preloads documents,
    or the preload reads the task's keys while the engine resolves the step's.

    There are three places that assemble steps_data. Two go through the engine
    builder; `passive_tasks` keeps its own copy, which is how it missed both
    this and the workflow default model (#842). A structural test rather than
    a behavioural one, because standing up a folder-watch trigger end to end
    costs far more than it pins -- and the failure is not a crash, it is a
    scheduled run answering over the wrong document, or over no text at all,
    without erroring.
    """

    def test_the_scheduled_run_path_applies_step_input_before_preloading(self):
        import inspect

        from app.tasks import passive_tasks

        src = inspect.getsource(passive_tasks.execute_workflow_passive)
        assert "apply_step_input_config" in src, (
            "the scheduled/folder-watch path builds steps_data without "
            "resolving step-level input; its document preload would read the "
            "task's keys while the engine resolves the step's"
        )
        apply_at = src.index("apply_step_input_config")
        preload_at = src.index("_wants_selected_document")
        assert apply_at < preload_at, (
            "step input must be resolved BEFORE the selected-document preload, "
            "or the preload fetches the wrong document"
        )

    def test_the_celery_run_path_still_applies_it_before_preloading(self):
        import inspect

        from app.tasks import workflow_tasks

        src = inspect.getsource(workflow_tasks._build_steps_data)
        assert src.index("apply_step_input_config") < src.index("_wants_selected_document")
