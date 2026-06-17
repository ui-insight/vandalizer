"""Tests for ``_compute_step_breakdown`` (Phase 2A per-step diagnostic).

Pure aggregation — no LLM, no DB. Verifies grouping, score computation,
weight handling, suppression heuristics.
"""

from app.services.workflow_service import _compute_step_breakdown


# ---------------------------------------------------------------------------
# Suppression heuristics
# ---------------------------------------------------------------------------


def test_returns_empty_when_no_checks():
    assert _compute_step_breakdown([], []) == []


def test_returns_empty_when_only_one_step_in_plan():
    """Single-step workflow → per-step would just restate the overall grade.
    Suppress to keep the UI clean."""
    plan = [
        {"id": "c1", "target_step": "Extract", "category": "content"},
        {"id": "c2", "target_step": "Extract", "category": "content"},
    ]
    checks = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "FAIL"},
    ]
    assert _compute_step_breakdown(plan, checks) == []


def test_returns_empty_when_no_target_step_anywhere():
    """No step targets set → everything would bucket under 'Unassigned' alone,
    which adds nothing. Suppress."""
    plan = [
        {"id": "c1", "category": "content"},
        {"id": "c2", "category": "content"},
    ]
    checks = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "PASS"},
    ]
    assert _compute_step_breakdown(plan, checks) == []


# ---------------------------------------------------------------------------
# Grouping + score computation
# ---------------------------------------------------------------------------


def test_groups_checks_by_target_step():
    plan = [
        {"id": "c1", "target_step": "Extract", "category": "content"},
        {"id": "c2", "target_step": "Extract", "category": "content"},
        {"id": "c3", "target_step": "Summarize", "category": "content"},
        {"id": "c4", "target_step": "Summarize", "category": "content"},
    ]
    checks = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "PASS"},
        {"check_id": "c3", "status": "FAIL"},
        {"check_id": "c4", "status": "FAIL"},
    ]
    out = _compute_step_breakdown(plan, checks)
    by_step = {b["step"]: b for b in out}
    assert set(by_step.keys()) == {"Extract", "Summarize"}
    assert by_step["Extract"]["pass"] == 2
    assert by_step["Extract"]["fail"] == 0
    assert by_step["Extract"]["score"] == 100.0
    assert by_step["Summarize"]["pass"] == 0
    assert by_step["Summarize"]["fail"] == 2
    assert by_step["Summarize"]["score"] == 0.0


def test_warn_counts_as_half_in_score():
    """WARN = 0.5 weighted — matches the workflow scorer's behavior."""
    plan = [
        {"id": "c1", "target_step": "Extract", "category": "content"},
        {"id": "c2", "target_step": "Summarize", "category": "content"},
    ]
    checks = [
        {"check_id": "c1", "status": "WARN"},
        {"check_id": "c2", "status": "PASS"},
    ]
    out = _compute_step_breakdown(plan, checks)
    by_step = {b["step"]: b for b in out}
    assert by_step["Extract"]["score"] == 50.0
    assert by_step["Extract"]["warn"] == 1
    assert by_step["Summarize"]["score"] == 100.0


def test_skip_excluded_from_score():
    """SKIP doesn't pull the score down — it's just absent from the denominator."""
    plan = [
        {"id": "c1", "target_step": "Extract", "category": "content"},
        {"id": "c2", "target_step": "Extract", "category": "content"},
        {"id": "c3", "target_step": "Summarize", "category": "content"},
    ]
    checks = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "SKIP"},
        {"check_id": "c3", "status": "PASS"},
    ]
    out = _compute_step_breakdown(plan, checks)
    by_step = {b["step"]: b for b in out}
    # Extract has 1 PASS + 1 SKIP → score reflects only PASS = 100
    assert by_step["Extract"]["score"] == 100.0
    assert by_step["Extract"]["skip"] == 1
    assert by_step["Extract"]["evaluated"] == 1
    assert by_step["Extract"]["total"] == 2


def test_category_weights_applied_per_step():
    """completeness (weight 1.5) outranks formatting (weight 0.7). A passing
    completeness check + failing formatting check shouldn't average to 50."""
    plan = [
        {"id": "c1", "target_step": "Extract", "category": "completeness"},  # weight 1.5
        {"id": "c2", "target_step": "Extract", "category": "formatting"},    # weight 0.7
        {"id": "c3", "target_step": "Summarize", "category": "content"},
    ]
    checks = [
        {"check_id": "c1", "status": "PASS"},  # contributes 1.5
        {"check_id": "c2", "status": "FAIL"},  # contributes 0
        {"check_id": "c3", "status": "PASS"},
    ]
    out = _compute_step_breakdown(plan, checks)
    by_step = {b["step"]: b for b in out}
    # Weighted: PASS*1.5 + FAIL*0.7 = 1.5; total weight = 2.2 → 68.18%
    assert by_step["Extract"]["score"] == round(1.5 / 2.2 * 100, 1)
    assert by_step["Summarize"]["score"] == 100.0


def test_checks_with_missing_target_step_bucket_under_unassigned():
    """Plan items without target_step → 'Unassigned' bucket. As long as
    there's at least one real step present, the breakdown surfaces."""
    plan = [
        {"id": "c1", "target_step": "Extract", "category": "content"},
        {"id": "c2", "category": "content"},  # no target_step
    ]
    checks = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "PASS"},
    ]
    out = _compute_step_breakdown(plan, checks)
    steps = {b["step"] for b in out}
    assert steps == {"Extract", "Unassigned"}


def test_checks_with_missing_plan_entry_bucket_under_unassigned():
    """Check IDs not found in plan still get bucketed — never lose verdicts."""
    plan = [{"id": "c1", "target_step": "Extract", "category": "content"}]
    checks = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "phantom", "status": "FAIL"},  # not in plan
    ]
    out = _compute_step_breakdown(plan, checks)
    steps = {b["step"] for b in out}
    assert "Unassigned" in steps
    by_step = {b["step"]: b for b in out}
    assert by_step["Unassigned"]["fail"] == 1


def test_output_ordered_by_step_name():
    """Stable alphabetical order — UI gets a predictable ordering with no
    state of its own."""
    plan = [
        {"id": "c1", "target_step": "Zebra", "category": "content"},
        {"id": "c2", "target_step": "Alpha", "category": "content"},
        {"id": "c3", "target_step": "Mango", "category": "content"},
    ]
    checks = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "PASS"},
        {"check_id": "c3", "status": "PASS"},
    ]
    out = _compute_step_breakdown(plan, checks)
    assert [b["step"] for b in out] == ["Alpha", "Mango", "Zebra"]


def test_total_and_evaluated_counts():
    plan = [
        {"id": "c1", "target_step": "Extract", "category": "content"},
        {"id": "c2", "target_step": "Extract", "category": "content"},
        {"id": "c3", "target_step": "Extract", "category": "content"},
        {"id": "c4", "target_step": "Summarize", "category": "content"},
    ]
    checks = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "WARN"},
        {"check_id": "c3", "status": "SKIP"},
        {"check_id": "c4", "status": "PASS"},
    ]
    out = _compute_step_breakdown(plan, checks)
    by_step = {b["step"]: b for b in out}
    assert by_step["Extract"]["total"] == 3
    assert by_step["Extract"]["evaluated"] == 2  # SKIP excluded
    assert by_step["Summarize"]["total"] == 1
    assert by_step["Summarize"]["evaluated"] == 1


def test_handles_none_plan_and_none_checks():
    """Defensive — None inputs (could happen mid-construction) shouldn't crash."""
    # type: ignore reassurance — runtime tolerates None
    assert _compute_step_breakdown(None, None) == []  # type: ignore[arg-type]
    assert _compute_step_breakdown(None, [{"check_id": "c1", "status": "PASS"}]) == []  # type: ignore[arg-type]
