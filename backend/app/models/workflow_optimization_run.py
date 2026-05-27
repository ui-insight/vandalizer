"""WorkflowOptimizationRun — tracks one execution of the workflow optimizer.

A single run sweeps candidate workflow configurations (per-step model + prompt
variant) against the same test inputs and records the trial outcomes plus the
winning per-step config. The UI polls this document for live progress and
(when status=completed) the comparison results.

Schema mirrors ``ExtractionOptimizationRun`` so the shared frontend components
can consume it with the same field names — the differences are workflow-specific
fields (``baseline_no_workflow_score``, ``step_breakdown``, ``best_per_step_config``)
and the trial config shape (per-step overrides rather than a flat config dict).
"""

from __future__ import annotations

import datetime
from typing import Literal, Optional
from uuid import uuid4

from beanie import Document
from pydantic import Field


WorkflowOptimizationStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class WorkflowOptimizationRun(Document):
    """A single optimization run for a Workflow."""

    uuid: str = ""
    workflow_id: str
    user_id: str
    status: WorkflowOptimizationStatus = "queued"

    started_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    completed_at: Optional[datetime.datetime] = None

    token_budget: int = 0
    tokens_used: int = 0
    estimated_cost_usd: Optional[float] = None
    actual_cost_usd: Optional[float] = None

    cancel_requested: bool = False

    phase: str = "queued"
    progress_message: str = ""
    current_trial_index: int = 0
    total_trials_planned: int = 0
    best_score_so_far: Optional[float] = None
    best_config_so_far: Optional[dict] = None

    # Final results (populated when status=completed)
    # ``baseline_no_workflow_score`` answers "is this workflow earning its
    # complexity?" — single-shot LLM call against the same plan checks.
    # ``baseline_default_score`` is the workflow as currently configured.
    # ``optimized_score`` is the best trial's score.
    baseline_no_workflow_score: Optional[float] = None
    baseline_default_score: Optional[float] = None
    optimized_score: Optional[float] = None
    # Train/holdout split — when the test input set is large enough
    # (>= HOLDOUT_MIN_INPUTS) we reserve a slice from winner selection and
    # re-score the winner + default on it for an unbiased ``optimized_score``.
    # ``optimized_score`` then holds the HOLDOUT score; ``optimized_score_train``
    # keeps the in-sample number for diagnostics. When N is too small to split,
    # ``overfitting_warning`` is set and the in-sample score is the headline.
    optimized_score_train: Optional[float] = None
    holdout_default_score: Optional[float] = None
    train_input_ids: list[str] = Field(default_factory=list)
    holdout_input_ids: list[str] = Field(default_factory=list)
    overfitting_warning: bool = False
    # Why the trial loop stopped: "budget_exhausted", "all_trials_complete",
    # "converged", "cancelled", "failed". Populated on terminal status.
    stopped_reason: Optional[str] = None

    judge_variance: Optional[float] = None
    judge_score_se: Optional[float] = None
    winner_selection_reason: Optional[str] = None
    tied_with_baseline: bool = False
    judge_model: Optional[str] = None

    # Per-step config of the winning trial. Shape:
    #   {step_name: {"model": str, "prompt_variant": str | None}}
    best_per_step_config: dict = Field(default_factory=dict)

    # Per-step pass-rate breakdown for the winning trial. Each entry:
    #   {step, score, pass, warn, fail, skip, total, evaluated}
    step_breakdown: list[dict] = Field(default_factory=list)

    # Deferred to 2C: list of step_names the optimizer flagged for removal.
    # Always empty in v1 — schema reservation only.
    removed_steps: list[str] = Field(default_factory=list)

    best_config: Optional[dict] = None
    trials: list[dict] = Field(default_factory=list)
    # Each trial dict shape:
    # {
    #   "trial_id": str,
    #   "config": {step_overrides: {step_name: {model, prompt_variant}}},
    #   "score": float, "weighted_pass_rate": float,
    #   "lift_vs_default": float | None,
    #   "tokens_used": int,
    #   "status": "completed|early_stopped|failed",
    #   "duration_seconds": float,
    #   "step_breakdown": list[dict],
    #   "error": str | None,
    # }

    suggestions: list[dict] = Field(default_factory=list)

    previous_override: Optional[dict] = None

    # Apply-preview rollup (Phase 2 loop closure). Per-STEP baseline-vs-winner
    # score deltas so the Apply confirmation modal can show "K of N steps will
    # change, R regress". Shape: see ``optimization_common.build_apply_preview``.
    apply_preview: Optional[dict] = None

    options: dict = Field(default_factory=dict)
    # Shape: {"apply_on_finish": bool, "include_judge": bool, "advanced": {...}}

    error_message: Optional[str] = None

    class Settings:
        name = "workflow_optimization_runs"
        indexes = [
            "uuid",
            "workflow_id",
            "status",
            ("workflow_id", "status"),
            "started_at",
        ]

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
