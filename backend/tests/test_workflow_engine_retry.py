"""Engine-level retry-on-empty + fallback-model tests (Phase D2).

The optimizer can set ``retry_on_empty=True`` + ``fallback_model="..."`` on a
step_override. The engine reads these as ``_retry_on_empty`` / ``_fallback_model``
on the task data and retries one time with the fallback when the primary
returns an empty or error-shaped output.

These tests cover the engine helpers directly — no model calls, no LLM
roundtrips. They verify the retry decision logic and the fallback mutation.
"""

from unittest.mock import MagicMock

import pytest

from app.services.workflow_engine import (
    _output_looks_empty_or_error,
    _retry_node_with_fallback,
    _should_retry_with_fallback,
)


# ---------------------------------------------------------------------------
# _output_looks_empty_or_error
# ---------------------------------------------------------------------------


def test_empty_dict_is_empty():
    assert _output_looks_empty_or_error({}) is True
    assert _output_looks_empty_or_error(None) is True


def test_none_output_is_empty():
    assert _output_looks_empty_or_error({"output": None}) is True


def test_empty_string_is_empty():
    assert _output_looks_empty_or_error({"output": ""}) is True
    assert _output_looks_empty_or_error({"output": "   \n  "}) is True


def test_empty_list_is_empty():
    assert _output_looks_empty_or_error({"output": []}) is True
    assert _output_looks_empty_or_error({"output": {}}) is True


def test_short_error_string_matches():
    assert _output_looks_empty_or_error({"output": "Error: rate limit exceeded"}) is True
    assert _output_looks_empty_or_error({"output": "Exception during execution"}) is True
    assert _output_looks_empty_or_error({"output": "Failed to call model"}) is True
    assert _output_looks_empty_or_error({"output": "Timeout reached"}) is True


def test_long_output_starting_with_error_is_not_flagged():
    """A 5KB document that happens to include 'Error' in its first line is
    not an error stub — the heuristic only fires on short outputs."""
    long_text = "Error: " + "x" * 1000  # 1007 chars total
    assert _output_looks_empty_or_error({"output": long_text}) is False


def test_normal_output_is_not_empty():
    assert _output_looks_empty_or_error({"output": "A real response"}) is False
    assert _output_looks_empty_or_error({"output": ["item"]}) is False
    assert _output_looks_empty_or_error({"output": {"key": "value"}}) is False


# ---------------------------------------------------------------------------
# _should_retry_with_fallback
# ---------------------------------------------------------------------------


def _node_with_task(task_data: dict, n_tasks: int = 1) -> MagicMock:
    """Build a fake Node whose .tasks each carry the given data dict."""
    node = MagicMock()
    tasks = []
    for _ in range(n_tasks):
        task = MagicMock()
        task.data = dict(task_data)
        tasks.append(task)
    node.tasks = tasks
    node.name = "TestStep"
    return node


def test_should_retry_when_empty_and_configured():
    node = _node_with_task({
        "model": "primary-model",
        "_retry_on_empty": True,
        "_fallback_model": "fallback-model",
    })
    assert _should_retry_with_fallback(node, {"output": ""}) is True


def test_should_not_retry_when_output_is_good():
    node = _node_with_task({
        "model": "primary-model",
        "_retry_on_empty": True,
        "_fallback_model": "fallback-model",
    })
    assert _should_retry_with_fallback(node, {"output": "A real response"}) is False


def test_should_not_retry_when_no_fallback_configured():
    node = _node_with_task({
        "model": "primary-model",
        "_retry_on_empty": True,
        # no _fallback_model
    })
    assert _should_retry_with_fallback(node, {"output": ""}) is False


def test_should_not_retry_when_retry_flag_unset():
    node = _node_with_task({
        "model": "primary-model",
        "_fallback_model": "fallback-model",
        # _retry_on_empty missing
    })
    assert _should_retry_with_fallback(node, {"output": ""}) is False


def test_should_not_retry_when_fallback_equals_primary():
    """Retry with the same model would just repeat the failure — skip."""
    node = _node_with_task({
        "model": "same-model",
        "_retry_on_empty": True,
        "_fallback_model": "same-model",
    })
    assert _should_retry_with_fallback(node, {"output": ""}) is False


def test_should_not_retry_multitask_node():
    """Multi-task nodes are out of scope — per-task isolation gets noisy."""
    node = _node_with_task({
        "model": "primary",
        "_retry_on_empty": True,
        "_fallback_model": "fallback",
    }, n_tasks=2)
    assert _should_retry_with_fallback(node, {"output": ""}) is False


def test_should_not_retry_node_without_tasks():
    """Document loader nodes have no .tasks — never retry."""
    node = MagicMock()
    node.tasks = []
    assert _should_retry_with_fallback(node, {"output": ""}) is False


# ---------------------------------------------------------------------------
# _retry_node_with_fallback
# ---------------------------------------------------------------------------


def test_retry_swaps_model_and_reruns_process():
    """The task's model gets mutated to the fallback, then process() is called again."""
    node = _node_with_task({
        "model": "primary",
        "_retry_on_empty": True,
        "_fallback_model": "fallback",
    })
    node.process = MagicMock(return_value={"output": "retry succeeded"})
    prev_input = {"output": "input text"}

    new_output = _retry_node_with_fallback(node, prev_input)

    assert new_output == {"output": "retry succeeded"}
    # Mutation is persistent — the task now references the fallback model
    assert node.tasks[0].data["model"] == "fallback"
    node.process.assert_called_once_with(prev_input)


def test_retry_returns_none_when_no_fallback_set():
    """Defensive — should never be reached normally, but the helper guards anyway."""
    node = _node_with_task({"model": "primary"})  # no _fallback_model
    node.process = MagicMock()
    assert _retry_node_with_fallback(node, {}) is None
    node.process.assert_not_called()
