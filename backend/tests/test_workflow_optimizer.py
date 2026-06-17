"""Tests for app.services.workflow_optimizer — the workflow autovalidate
orchestrator.

Covers the pure helpers (candidate construction, scoring, winner selection,
suggestions) plus a heavily-mocked end-to-end exercise of ``run_optimization``
that walks the full lifecycle without touching MongoDB or LLM endpoints.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import workflow_optimizer
from app.services.optimization_common import pick_winner_variance_aware
from app.services.workflow_optimizer import (
    _aggregate_step_breakdown,
    _build_candidates,
    _compute_workflow_variance,
    _enumerate_llm_steps,
    _extract_model_names,
    _generate_suggestions,
    _override_distance,
    _to_trial_summary,
    _weighted_pass_rate,
)


# ---------------------------------------------------------------------------
# Pure helpers — scoring & aggregation
# ---------------------------------------------------------------------------


def test_weighted_pass_rate_applies_category_weights():
    plan = [
        {"id": "c1", "category": "completeness"},  # weight 1.5
        {"id": "c2", "category": "formatting"},    # weight 0.7
    ]
    checks = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "FAIL"},
    ]
    # (1.0 * 1.5) / (1.5 + 0.7) = 0.6818...
    assert _weighted_pass_rate(plan, checks) == pytest.approx(0.6818, abs=1e-3)


def test_weighted_pass_rate_skips_unscored():
    plan = [{"id": "c1", "category": "content"}, {"id": "c2", "category": "content"}]
    checks = [{"check_id": "c1", "status": "PASS"}, {"check_id": "c2", "status": "SKIP"}]
    assert _weighted_pass_rate(plan, checks) == 1.0


def test_weighted_pass_rate_zero_when_no_evaluable():
    plan = [{"id": "c1", "category": "content"}]
    checks = [{"check_id": "c1", "status": "SKIP"}]
    assert _weighted_pass_rate(plan, checks) == 0.0


def test_aggregate_step_breakdown_groups_by_target_step():
    plan = [
        {"id": "c1", "target_step": "Extract", "category": "completeness"},
        {"id": "c2", "target_step": "Extract", "category": "completeness"},
        {"id": "c3", "target_step": "Summarize", "category": "content"},
    ]
    checks_per_input = [
        [
            {"check_id": "c1", "status": "PASS"},
            {"check_id": "c2", "status": "FAIL"},
            {"check_id": "c3", "status": "PASS"},
        ],
        [
            {"check_id": "c1", "status": "PASS"},
            {"check_id": "c2", "status": "PASS"},
            {"check_id": "c3", "status": "PASS"},
        ],
    ]
    breakdown = _aggregate_step_breakdown(plan=plan, checks_per_input=checks_per_input)
    steps = {b["step"]: b for b in breakdown}
    assert set(steps.keys()) == {"Extract", "Summarize"}
    # Extract: 3 PASS + 1 FAIL across both inputs, all completeness (weight 1.5)
    # weighted_sum = 3 * 1.5 = 4.5; weight_total = 4 * 1.5 = 6 → 75.0
    assert steps["Extract"]["score"] == 75.0
    assert steps["Extract"]["pass"] == 3
    assert steps["Extract"]["fail"] == 1
    # Summarize: 2 PASS, content (weight 1.0) → 100
    assert steps["Summarize"]["score"] == 100.0


def test_aggregate_step_breakdown_suppressed_when_single_step():
    plan = [{"id": "c1", "target_step": "Solo", "category": "content"}]
    checks = [[{"check_id": "c1", "status": "PASS"}]]
    # One distinct step → return empty (UI would otherwise duplicate the
    # overall grade).
    assert _aggregate_step_breakdown(plan=plan, checks_per_input=checks) == []


# ---------------------------------------------------------------------------
# Variance + winner
# ---------------------------------------------------------------------------


def test_compute_workflow_variance_returns_none_under_two_samples():
    assert _compute_workflow_variance([]) is None
    assert _compute_workflow_variance([({"status": "PASS"}, {"status": "PASS"})]) is None


def test_compute_workflow_variance_picks_up_verdict_flips():
    # All flips of PASS↔FAIL → deltas = [-1, -1, +1, +1]
    samples = [
        ({"status": "PASS"}, {"status": "FAIL"}),
        ({"status": "PASS"}, {"status": "FAIL"}),
        ({"status": "FAIL"}, {"status": "PASS"}),
        ({"status": "FAIL"}, {"status": "PASS"}),
    ]
    sigma = _compute_workflow_variance(samples)
    # Bessel-corrected stddev of [-1,-1,+1,+1] with mean 0 is sqrt(4/3)
    assert sigma == pytest.approx(1.1547, abs=1e-3)


def test_override_distance_counts_diffs():
    default = {"S1": {"model": "haiku", "prompt_variant": "default"}}
    override_same = {"S1": {"model": "haiku", "prompt_variant": "default"}}
    override_model_diff = {"S1": {"model": "sonnet", "prompt_variant": "default"}}
    override_both_diff = {"S1": {"model": "sonnet", "prompt_variant": "concise"}}

    assert _override_distance(override_same, default) == 0
    assert _override_distance(override_model_diff, default) == 1
    assert _override_distance(override_both_diff, default) == 2
    assert _override_distance(None, default) == 0


def _workflow_distance(default_overrides: dict[str, dict]):
    """Adapter that mirrors how workflow_optimizer wires up the shared helper."""
    return lambda t: _override_distance(
        (t.get("config") or {}).get("step_overrides"), default_overrides,
    )


def test_winner_variance_aware_highest_score_when_clearly_above():
    # SE = 0.04 / sqrt(4) = 0.02, band = 0.04. Top score 0.90 beats #2 0.80
    # by 0.10 — well outside the band.
    trials = [
        {"trial_id": "B", "status": "completed", "score": 0.90, "config": {"step_overrides": {}}},
        {"trial_id": "A", "status": "completed", "score": 0.80, "config": {"step_overrides": {}}},
    ]
    winner, reason, tied, _ = pick_winner_variance_aware(
        trials, judge_variance=0.04,
        baseline_default_score=0.50,
        distance_from_default=_workflow_distance({}),
        n_items_for_se=4,
        completed_statuses=("completed", "early_stopped"),
    )
    assert winner is not None
    assert winner["trial_id"] == "B"
    assert reason == "highest_score"
    assert tied is False


def test_winner_variance_aware_tied_with_baseline_suppresses_apply():
    # All trials and the baseline cluster inside the band — apply should be
    # suppressed.
    trials = [
        {"trial_id": "A", "status": "completed", "score": 0.71, "config": {"step_overrides": {}}},
        {"trial_id": "B", "status": "completed", "score": 0.70, "config": {"step_overrides": {}}},
    ]
    winner, reason, tied, _ = pick_winner_variance_aware(
        trials, judge_variance=0.10,
        baseline_default_score=0.69,
        distance_from_default=_workflow_distance({}),
        n_items_for_se=4,
        completed_statuses=("completed", "early_stopped"),
    )
    assert tied is True
    assert reason == "tied_with_baseline"
    assert winner is not None  # caller still wants something to show


def test_winner_variance_aware_no_completed_trials_returns_none():
    trials = [{"trial_id": "X", "status": "failed", "score": None, "config": {}}]
    winner, reason, _tied, _ = pick_winner_variance_aware(
        trials, judge_variance=None,
        baseline_default_score=0.5,
        distance_from_default=_workflow_distance({}),
        n_items_for_se=1,
        completed_statuses=("completed", "early_stopped"),
    )
    assert winner is None
    assert reason == "no_completed_trials"


# ---------------------------------------------------------------------------
# Trial summary
# ---------------------------------------------------------------------------


def test_to_trial_summary_includes_lift_and_status():
    result = {
        "label": "swap-extract-sonnet",
        "step_overrides": {"Extract": {"model": "sonnet", "prompt_variant": "default"}},
        "score": 0.84,
        "weighted_pass_rate": 0.84,
        "tokens_used": 1500,
        "duration_seconds": 12.3,
        "step_breakdown": [],
        "status": "completed",
        "num_inputs_run": 3,
        "num_inputs_total": 3,
    }
    summary = _to_trial_summary(result, baseline_default_score=0.70)
    assert summary["trial_id"] == "swap-extract-sonnet"
    assert summary["lift_vs_default"] == pytest.approx(0.14, abs=1e-4)
    assert summary["status"] == "completed"
    assert summary["config"]["step_overrides"]["Extract"]["model"] == "sonnet"


def test_to_trial_summary_handles_failed_trial():
    result = {"label": "x", "step_overrides": {}, "score": 0.0, "status": "failed", "error": "boom"}
    summary = _to_trial_summary(result, baseline_default_score=0.5)
    assert summary["status"] == "failed"
    assert summary["error"] == "boom"


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------


def _wf_data_with_steps(*step_names_and_tasks):
    """Helper: build a wf_data dict with the given (step_name, [task_names]) pairs."""
    return {
        "steps": [
            {"name": sn, "tasks": [{"name": tn} for tn in tasks]}
            for sn, tasks in step_names_and_tasks
        ],
    }


def test_enumerate_llm_steps_skips_non_llm():
    wf = _wf_data_with_steps(
        ("Extract", ["Extraction"]),
        ("Summarize", ["Prompt"]),
        ("Export", ["DataExport"]),  # not LLM — should be filtered out
    )
    steps = _enumerate_llm_steps(wf)
    names = {s["name"] for s in steps}
    assert names == {"Extract", "Summarize"}


def test_enumerate_llm_steps_marks_variant_eligibility():
    wf = _wf_data_with_steps(
        ("Extract", ["Extraction"]),       # model swap only
        ("Summarize", ["Prompt"]),         # variant eligible
    )
    by_name = {s["name"]: s for s in _enumerate_llm_steps(wf)}
    assert by_name["Extract"]["variant_eligible"] is False
    assert by_name["Summarize"]["variant_eligible"] is True


def test_extract_model_names_handles_dict_and_pydantic_shapes():
    class _M:
        name = "opus"

    available = [{"name": "haiku"}, _M()]
    assert _extract_model_names(available) == ["haiku", "opus"]


def test_build_candidates_generates_diverse_trials():
    wf = _wf_data_with_steps(
        ("Extract", ["Extraction"]),
        ("Summarize", ["Prompt"]),
    )
    available = [{"name": "haiku"}, {"name": "sonnet"}, {"name": "opus"}]
    candidates = _build_candidates(
        wf_data=wf,
        available_models=available,
        baseline_model="haiku",
        max_candidates=8,
        rng_seed=42,
    )
    assert 1 <= len(candidates) <= 8
    # Each candidate has step_overrides for at least one step
    for c in candidates:
        assert c["step_overrides"]
    # Trial labels are unique
    labels = [c["label"] for c in candidates]
    assert len(set(labels)) == len(labels)


def test_build_candidates_empty_when_no_llm_steps():
    wf = _wf_data_with_steps(("Export", ["DataExport"]))
    candidates = _build_candidates(
        wf_data=wf,
        available_models=[{"name": "haiku"}],
        baseline_model="haiku",
        max_candidates=4,
        rng_seed=1,
    )
    assert candidates == []


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------


def test_generate_suggestions_flags_weak_steps_with_recommended_config():
    suggestions = _generate_suggestions(
        step_breakdown=[
            {"step": "Extract", "score": 35.0},
            {"step": "Summarize", "score": 90.0},
        ],
        baseline_no_workflow=0.4,
        baseline_default=0.5,
        optimized=0.7,
        best_per_step_config={"Extract": {"model": "sonnet", "prompt_variant": "detailed"}},
    )
    weak = [s for s in suggestions if s["kind"] == "weak_step"]
    assert len(weak) == 1
    assert weak[0]["step"] == "Extract"
    assert weak[0]["severity"] == "critical"
    assert "sonnet" in weak[0]["message"]
    assert "detailed" in weak[0]["message"]


def test_generate_suggestions_flags_redundant_workflow():
    suggestions = _generate_suggestions(
        step_breakdown=[],
        baseline_no_workflow=0.85,  # no-workflow nearly matches optimized
        baseline_default=0.85,
        optimized=0.87,
        best_per_step_config={},
    )
    kinds = [s["kind"] for s in suggestions]
    assert "redundant_workflow" in kinds


def test_generate_suggestions_ordered_by_severity():
    suggestions = _generate_suggestions(
        step_breakdown=[
            {"step": "A", "score": 30.0},
            {"step": "B", "score": 55.0},
        ],
        baseline_no_workflow=None,
        baseline_default=0.8,
        optimized=0.81,
        best_per_step_config={},
    )
    severities = [s["severity"] for s in suggestions]
    assert severities == sorted(severities, key=lambda x: {"critical": 0, "warning": 1, "info": 2}.get(x, 9))


# ---------------------------------------------------------------------------
# End-to-end (heavily mocked)
# ---------------------------------------------------------------------------


def _make_run_doc(uuid: str = "opt-wf-1") -> MagicMock:
    rd = MagicMock()
    rd.uuid = uuid
    rd.workflow_id = "wf-1"
    rd.user_id = "u1"
    rd.status = "queued"
    rd.phase = "queued"
    rd.cancel_requested = False
    rd.trials = []
    rd.baseline_no_workflow_score = None
    rd.baseline_default_score = None
    rd.optimized_score = None
    rd.judge_variance = None
    rd.judge_model = None
    rd.best_score_so_far = None
    rd.best_config_so_far = None
    rd.best_config = None
    rd.best_per_step_config = {}
    rd.step_breakdown = []
    rd.suggestions = []
    rd.previous_override = None
    rd.completed_at = None
    rd.judge_score_se = None
    rd.winner_selection_reason = None
    rd.tied_with_baseline = False
    rd.total_trials_planned = 0
    rd.current_trial_index = 0
    rd.tokens_used = 0
    rd.token_budget = 0
    rd.save = AsyncMock()
    return rd


@pytest.mark.asyncio
async def test_run_optimization_missing_run_raises():
    with patch.object(
        workflow_optimizer.WorkflowOptimizationRun, "find_one",
        AsyncMock(return_value=None),
    ):
        with pytest.raises(ValueError, match="not found"):
            await workflow_optimizer.run_optimization(
                workflow_id="507f1f77bcf86cd799439011",
                user_id="u1",
                run_uuid="missing",
            )


@pytest.mark.asyncio
async def test_run_optimization_fails_when_no_validation_plan():
    run_doc = _make_run_doc()
    wf = MagicMock()
    wf.validation_plan = []
    wf.validation_inputs = []
    wf.config_override = None

    with patch.object(
        workflow_optimizer.WorkflowOptimizationRun, "find_one",
        AsyncMock(return_value=run_doc),
    ), patch.object(
        workflow_optimizer.Workflow, "get", AsyncMock(return_value=wf),
    ):
        result = await workflow_optimizer.run_optimization(
            workflow_id="507f1f77bcf86cd799439011", user_id="u1", run_uuid="opt-wf-1",
        )

    assert result.status == "failed"
    assert "validation plan" in (result.error_message or "")


@pytest.mark.asyncio
async def test_run_optimization_fails_when_no_test_inputs():
    run_doc = _make_run_doc()
    wf = MagicMock()
    wf.validation_plan = [{"id": "c1", "category": "content"}]
    wf.validation_inputs = []
    wf.config_override = None

    with patch.object(
        workflow_optimizer.WorkflowOptimizationRun, "find_one",
        AsyncMock(return_value=run_doc),
    ), patch.object(
        workflow_optimizer.Workflow, "get", AsyncMock(return_value=wf),
    ):
        result = await workflow_optimizer.run_optimization(
            workflow_id="507f1f77bcf86cd799439011", user_id="u1", run_uuid="opt-wf-1",
        )

    assert result.status == "failed"
    assert "test inputs" in (result.error_message or "").lower()


# ---------------------------------------------------------------------------
# Cancellation — the cancel endpoint flips ``cancel_requested`` on a separate
# DB copy, so the worker must read the flag from the DB (not its stale,
# long-lived in-memory ``run_doc``) and must not clobber it on save.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_cancelled_reads_db_not_stale_in_memory_copy():
    """A cancel requested after the worker loaded run_doc is still detected."""
    run_doc = _make_run_doc()
    run_doc.cancel_requested = False  # worker's stale view

    db_copy = _make_run_doc()
    db_copy.cancel_requested = True  # endpoint flipped it in the DB

    with patch.object(
        workflow_optimizer.WorkflowOptimizationRun, "find_one",
        AsyncMock(return_value=db_copy),
    ):
        assert await workflow_optimizer._is_cancelled(run_doc) is True

    # The fresh flag is synced forward so subsequent saves preserve it.
    assert run_doc.cancel_requested is True


@pytest.mark.asyncio
async def test_save_preserves_concurrently_requested_cancel():
    """A full-document save must not revert a cancel set by the endpoint."""
    run_doc = _make_run_doc()
    run_doc.cancel_requested = False

    db_copy = _make_run_doc()
    db_copy.cancel_requested = True

    with patch.object(
        workflow_optimizer.WorkflowOptimizationRun, "find_one",
        AsyncMock(return_value=db_copy),
    ):
        await workflow_optimizer._save(run_doc)

    assert run_doc.cancel_requested is True  # not clobbered back to False
    run_doc.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_single_trial_stops_at_input_boundary_when_cancelled():
    """An in-flight trial aborts at the next input instead of running them all."""
    run_doc = _make_run_doc()
    run_doc.cancel_requested = True  # already cancelled

    wf = MagicMock()
    wf.id = "wf-1"
    test_inputs = [{"id": "a", "doc_uuids": ["d1"]}, {"id": "b", "doc_uuids": ["d2"]}]

    execute = AsyncMock(return_value=(None, [], 0, 0))
    with patch.object(
        workflow_optimizer, "_execute_and_score", execute,
    ):
        result = await workflow_optimizer._run_single_trial(
            wf=wf,
            wf_data={"validation_plan": []},
            user_id="u1",
            step_overrides={},
            test_inputs=test_inputs,
            baseline_score=None,
            label="trial-1",
            run_doc=run_doc,
        )

    assert result["status"] == "cancelled"
    assert result["num_inputs_run"] == 0
    execute.assert_not_called()  # bailed before running any input


@pytest.mark.asyncio
async def test_run_single_trial_runs_all_inputs_when_not_cancelled():
    """The cancel check is a no-op when no cancel is pending."""
    run_doc = _make_run_doc()
    run_doc.cancel_requested = False

    wf = MagicMock()
    wf.id = "wf-1"
    test_inputs = [{"id": "a", "doc_uuids": ["d1"]}, {"id": "b", "doc_uuids": ["d2"]}]

    execute = AsyncMock(return_value=(None, [], 0, 0))
    with patch.object(
        workflow_optimizer.WorkflowOptimizationRun, "find_one",
        AsyncMock(return_value=run_doc),  # DB agrees: not cancelled
    ), patch.object(
        workflow_optimizer, "_execute_and_score", execute,
    ):
        result = await workflow_optimizer._run_single_trial(
            wf=wf,
            wf_data={"validation_plan": []},
            user_id="u1",
            step_overrides={},
            test_inputs=test_inputs,
            baseline_score=None,
            label="trial-1",
            run_doc=run_doc,
        )

    assert result["status"] == "completed"
    assert result["num_inputs_run"] == 2
    assert execute.await_count == 2
