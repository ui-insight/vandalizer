"""Tests for the KBOptimizationRun Beanie document."""

import datetime

from app.models.kb_optimization_run import KBOptimizationRun


def test_kb_optimization_run_defaults():
    """Defaults should produce a valid run with sensible initial state."""
    run = KBOptimizationRun.model_construct(
        kb_uuid="kb-1",
        user_id="u1",
    )
    d = run.model_dump()
    assert d["status"] == "queued"
    assert d["phase"] == "queued"
    assert d["tokens_used"] == 0
    assert d["cancel_requested"] is False
    assert d["trials"] == []
    assert d["data_source_suggestions"] == []
    assert d["best_config_so_far"] is None
    assert d["completed_at"] is None
    assert d["judge_variance"] is None


def test_kb_optimization_run_full_payload_round_trip():
    started = datetime.datetime.now(tz=datetime.timezone.utc)
    run = KBOptimizationRun.model_construct(
        uuid="opt-1",
        kb_uuid="kb-1",
        user_id="u1",
        status="completed",
        started_at=started,
        completed_at=started + datetime.timedelta(minutes=12),
        token_budget=2_500_000,
        tokens_used=2_341_220,
        estimated_cost_usd=4.80,
        actual_cost_usd=4.62,
        cancel_requested=False,
        phase="done",
        progress_message="Optimization complete.",
        current_trial_index=25,
        total_trials_planned=25,
        best_score_so_far=0.87,
        best_config_so_far={"k": 12, "model": "claude-haiku-4-5", "prompt_variant": "strict"},
        baseline_no_kb_score=0.31,
        baseline_default_score=0.64,
        optimized_score=0.87,
        judge_variance=0.04,
        judge_model="claude-haiku-4-5",
        best_config={"k": 12, "model": "claude-haiku-4-5", "prompt_variant": "strict"},
        trials=[
            {
                "trial_id": "t1",
                "config": {"k": 8, "model": "claude-sonnet-4-6", "prompt_variant": "default"},
                "score": 0.65,
                "lift_vs_default": 0.01,
                "tokens_used": 95_000,
                "status": "completed",
            },
            {
                "trial_id": "t2",
                "config": {"k": 12, "model": "claude-haiku-4-5", "prompt_variant": "strict"},
                "score": 0.87,
                "lift_vs_default": 0.23,
                "tokens_used": 92_000,
                "status": "completed",
            },
        ],
        data_source_suggestions=[
            {"kind": "coverage_gap", "severity": "warning", "message": "No source covers payroll deadlines."},
        ],
        options={"include_indexing_track": False, "apply_on_finish": True},
        error_message=None,
    )
    d = run.model_dump()
    assert d["status"] == "completed"
    assert d["best_config"]["k"] == 12
    assert len(d["trials"]) == 2
    assert d["data_source_suggestions"][0]["kind"] == "coverage_gap"
    assert d["options"]["apply_on_finish"] is True
    assert d["judge_variance"] == 0.04


def test_kb_optimization_run_is_registered_for_beanie():
    """Sanity-check: the model is in ALL_MODELS so init_db will register the
    underlying collection."""
    from app.database import ALL_MODELS
    assert KBOptimizationRun in ALL_MODELS
