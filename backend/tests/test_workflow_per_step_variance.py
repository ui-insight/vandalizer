"""Tests for per-step judge variance: ``_compute_per_step_variance``.

Per-step variance buckets the (original, replay) verdict pairs by each
check's ``target_step`` and computes stddev within each bucket so the UI
can render a ±N pts CI on each step's score instead of just the
workflow-level grade.
"""

from app.services.workflow_service import (
    _compute_per_step_variance,
    _stddev_of_deltas,
)


def _pair(check_id: str, orig_status: str, replay_status: str):
    return (
        {"check_id": check_id, "status": orig_status},
        {"check_id": check_id, "status": replay_status},
    )


def test_stddev_of_deltas_returns_none_without_samples():
    assert _stddev_of_deltas(None) is None
    assert _stddev_of_deltas([]) is None
    assert _stddev_of_deltas([_pair("c1", "PASS", "PASS")]) is None


def test_stddev_of_deltas_zero_for_identical_verdicts():
    samples = [
        _pair("c1", "PASS", "PASS"),
        _pair("c2", "PASS", "PASS"),
    ]
    assert _stddev_of_deltas(samples) == 0.0


def test_stddev_of_deltas_nonzero_when_verdicts_flip():
    """One pair flips PASS→FAIL (delta = -1), one stays (delta = 0).
    Sample stddev of [-1, 0] = 0.7071..."""
    samples = [
        _pair("c1", "PASS", "FAIL"),
        _pair("c2", "PASS", "PASS"),
    ]
    var = _stddev_of_deltas(samples)
    assert var is not None
    assert abs(var - 0.7071) < 0.001


def test_per_step_variance_groups_by_target_step():
    plan = [
        {"id": "c1", "target_step": "Extract"},
        {"id": "c2", "target_step": "Extract"},
        {"id": "c3", "target_step": "Summarize"},
        {"id": "c4", "target_step": "Summarize"},
    ]
    samples = [
        _pair("c1", "PASS", "FAIL"),    # Extract: delta -1
        _pair("c2", "PASS", "PASS"),    # Extract: delta 0
        _pair("c3", "PASS", "PASS"),    # Summarize: delta 0
        _pair("c4", "PASS", "PASS"),    # Summarize: delta 0
    ]
    out = _compute_per_step_variance(samples, plan)
    assert set(out.keys()) == {"Extract", "Summarize"}
    assert out["Extract"] > 0  # Verdicts flipped here
    assert out["Summarize"] == 0.0  # Stable


def test_per_step_variance_omits_buckets_with_too_few_samples():
    """A step with only 1 check can't have variance computed — omit it."""
    plan = [
        {"id": "c1", "target_step": "Solo"},
        {"id": "c2", "target_step": "Paired"},
        {"id": "c3", "target_step": "Paired"},
    ]
    samples = [
        _pair("c1", "PASS", "FAIL"),
        _pair("c2", "PASS", "PASS"),
        _pair("c3", "PASS", "PASS"),
    ]
    out = _compute_per_step_variance(samples, plan)
    assert "Solo" not in out
    assert "Paired" in out


def test_per_step_variance_empty_with_no_inputs():
    assert _compute_per_step_variance(None, None) == {}
    assert _compute_per_step_variance([], []) == {}
    assert _compute_per_step_variance(None, [{"id": "c1", "target_step": "x"}]) == {}


def test_per_step_variance_ignores_samples_with_missing_target_step():
    """A plan entry without target_step contributes nothing to any bucket."""
    plan = [
        {"id": "c1", "target_step": ""},
        {"id": "c2", "target_step": ""},
    ]
    samples = [
        _pair("c1", "PASS", "FAIL"),
        _pair("c2", "PASS", "PASS"),
    ]
    assert _compute_per_step_variance(samples, plan) == {}
