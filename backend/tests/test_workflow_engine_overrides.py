"""Tests for the workflow engine's per-step config_override application.

Covers ``_apply_step_override`` directly (the helper that mutates task_data)
plus ``build_workflow_engine`` end-to-end to confirm overrides reach the
constructed Node instances.
"""

from __future__ import annotations

from app.services.workflow_engine import _apply_step_override, build_workflow_engine
from app.services.workflow_prompt_variants import apply_prompt_variant


# ---------------------------------------------------------------------------
# apply_prompt_variant — variant wrapping
# ---------------------------------------------------------------------------


def test_apply_prompt_variant_default_returns_original():
    assert apply_prompt_variant("hello", "default") == "hello"
    assert apply_prompt_variant("hello", None) == "hello"


def test_apply_prompt_variant_unknown_returns_original():
    # Unknown variant names mustn't raise — the optimizer expects forward
    # compat with stale overrides referring to retired variants.
    assert apply_prompt_variant("hello", "fictional-variant") == "hello"


def test_apply_prompt_variant_concise_wraps_with_prefix_and_suffix():
    out = apply_prompt_variant("Summarize this.", "concise")
    assert "Summarize this." in out
    assert out != "Summarize this."  # wrapper applied
    assert "concise" in out.lower() or "direct" in out.lower()


def test_apply_prompt_variant_preserves_empty():
    assert apply_prompt_variant("", "concise") == ""


# ---------------------------------------------------------------------------
# _apply_step_override
# ---------------------------------------------------------------------------


def test_apply_step_override_swaps_model():
    task_data = {"model": "haiku", "prompt": "go"}
    _apply_step_override("Prompt", task_data, {"model": "sonnet"})
    assert task_data["model"] == "sonnet"


def test_apply_step_override_wraps_prompt_for_prompt_task():
    task_data = {"model": "haiku", "prompt": "Answer concisely."}
    _apply_step_override("Prompt", task_data, {"prompt_variant": "concise"})
    assert "Answer concisely." in task_data["prompt"]
    assert task_data["prompt"] != "Answer concisely."  # wrapped


def test_apply_step_override_wraps_format_template_for_formatter():
    task_data = {"model": "haiku", "format_template": "JSON format"}
    _apply_step_override("Formatter", task_data, {"prompt_variant": "strict"})
    assert "JSON format" in task_data["format_template"]
    assert task_data["format_template"] != "JSON format"


def test_apply_step_override_uses_prompt_fallback_when_format_template_empty():
    # FormatNode falls back to data.prompt when format_template is empty;
    # the override should wrap that field too.
    task_data = {"model": "haiku", "format_template": "", "prompt": "as a list"}
    _apply_step_override("Formatter", task_data, {"prompt_variant": "concise"})
    assert "as a list" in task_data["prompt"]
    assert task_data["prompt"] != "as a list"


def test_apply_step_override_no_op_for_non_llm_task():
    task_data = {"model": "haiku"}
    _apply_step_override("DataExport", task_data, {"model": "sonnet", "prompt_variant": "concise"})
    # Model still swaps (override is unconditional); variant is silently ignored
    # because the task has no free-text prompt field.
    assert task_data["model"] == "sonnet"


def test_apply_step_override_none_is_noop():
    task_data = {"model": "haiku", "prompt": "x"}
    _apply_step_override("Prompt", task_data, None)
    assert task_data == {"model": "haiku", "prompt": "x"}


# ---------------------------------------------------------------------------
# build_workflow_engine — overrides propagate to Node instances
# ---------------------------------------------------------------------------


def test_build_workflow_engine_applies_step_override_to_node():
    steps_data = [
        {"name": "Document", "data": {"doc_uuids": ["d1"]}, "tasks": []},
        {
            "name": "Summarize",
            "data": {},
            "tasks": [{"name": "Prompt", "data": {"prompt": "summarize the input"}}],
        },
    ]
    engine = build_workflow_engine(
        steps_data=steps_data,
        model="haiku",
        config_override={
            "step_overrides": {
                "Summarize": {"model": "opus", "prompt_variant": "concise"},
            },
        },
    )
    nodes = engine.get_topological_order()
    # nodes[0] is the Document trigger, nodes[1] is the MultiTaskNode wrapping
    # the Prompt task.
    summarize_node = nodes[1]
    inner_task = summarize_node.tasks[0]
    assert inner_task.model == "opus"
    # Inner Prompt task's data.prompt is wrapped by the concise variant.
    assert "summarize the input" in inner_task.data["prompt"]
    assert inner_task.data["prompt"] != "summarize the input"


def test_build_workflow_engine_without_override_leaves_node_unchanged():
    steps_data = [
        {"name": "Document", "data": {"doc_uuids": ["d1"]}, "tasks": []},
        {
            "name": "Summarize",
            "data": {},
            "tasks": [{"name": "Prompt", "data": {"prompt": "summarize"}}],
        },
    ]
    engine = build_workflow_engine(steps_data=steps_data, model="haiku")
    nodes = engine.get_topological_order()
    inner_task = nodes[1].tasks[0]
    assert inner_task.model == "haiku"
    assert inner_task.data["prompt"] == "summarize"
