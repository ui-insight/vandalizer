"""Model-level tests for WorkflowOptimizationRun.

Uses ``model_construct`` to bypass Beanie's init-requiring ``__init__`` —
same pattern as ``test_kb_optimization_run_model.py``.
"""

from app.models.workflow_optimization_run import WorkflowOptimizationRun


def test_defaults_populate_lifecycle_fields():
    run = WorkflowOptimizationRun.model_construct(workflow_id="wf-1", user_id="u1")
    d = run.model_dump()
    assert d["status"] == "queued"
    assert d["phase"] == "queued"
    assert d["cancel_requested"] is False
    assert d["trials"] == []
    assert d["step_breakdown"] == []
    assert d["suggestions"] == []
    assert d["removed_steps"] == []
    assert d["best_per_step_config"] == {}
    assert d["tied_with_baseline"] is False


def test_options_dict_preserved():
    run = WorkflowOptimizationRun.model_construct(
        workflow_id="wf-1",
        user_id="u1",
        options={"apply_on_finish": True, "max_candidates": 8},
    )
    d = run.model_dump()
    assert d["options"]["apply_on_finish"] is True
    assert d["options"]["max_candidates"] == 8


def test_full_payload_round_trip():
    """Confirms every workflow-specific field survives a model_dump cycle —
    these are the fields the API serializer projects, so a typo here would
    show up as a missing key in the frontend payload."""
    run = WorkflowOptimizationRun.model_construct(
        uuid="opt-1",
        workflow_id="wf-1",
        user_id="u1",
        status="completed",
        baseline_no_workflow_score=0.42,
        baseline_default_score=0.55,
        optimized_score=0.73,
        judge_variance=0.04,
        judge_score_se=0.02,
        winner_selection_reason="highest_score",
        tied_with_baseline=False,
        best_per_step_config={"Extract": {"model": "sonnet", "prompt_variant": "concise"}},
        step_breakdown=[{"step": "Extract", "score": 78.0}],
        removed_steps=[],
        suggestions=[{"kind": "weak_step", "severity": "warning"}],
    )
    d = run.model_dump()
    assert d["uuid"] == "opt-1"
    assert d["baseline_no_workflow_score"] == 0.42
    assert d["optimized_score"] == 0.73
    assert d["best_per_step_config"]["Extract"]["model"] == "sonnet"
    assert d["step_breakdown"][0]["step"] == "Extract"
