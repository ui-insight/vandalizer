"""ExtractionOptimizationRun - tracks one execution of the extraction optimizer.

A single run sweeps multiple extraction configurations (model, strategy,
prompt variant, etc.) against the same test cases and records the trial
outcomes plus the winning config. The UI polls this document for live
progress and (when status=completed) the optimization results.

Schema mirrors ``KBOptimizationRun`` so the shared frontend components can
consume it with the same field names — the differences are extraction-specific
fields (``baseline_no_tool_score``, ``field_breakdown``) and the trial config
shape (model/strategy/thinking/chunking rather than RAG knobs).
"""

from __future__ import annotations

import datetime
from typing import Literal, Optional
from uuid import uuid4

from beanie import Document
from pydantic import Field


ExtractionOptimizationStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class ExtractionOptimizationRun(Document):
    """A single optimization run for an extraction (SearchSet)."""

    uuid: str = ""
    search_set_uuid: str
    user_id: str
    status: ExtractionOptimizationStatus = "queued"

    # Lifecycle timestamps
    started_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    completed_at: Optional[datetime.datetime] = None

    # Budget enforcement (mirrors KBOptimizationRun)
    token_budget: int = 0
    tokens_used: int = 0
    estimated_cost_usd: Optional[float] = None
    actual_cost_usd: Optional[float] = None

    cancel_requested: bool = False
    # When the cancel was requested (UTC). The optimizer watchdog uses this to
    # decide that a worker which never honored the cancel is dead, and finalize
    # the run on the user's behalf instead of leaving it "Cancelling…" forever.
    cancel_requested_at: Optional[datetime.datetime] = None
    # Celery task id, recorded at dispatch so the cancel endpoint (and the
    # stale-run watchdog) can hard-revoke a wedged worker as a fallback to the
    # cooperative cancel flag.
    celery_task_id: Optional[str] = None

    # Live progress — UI polls these
    phase: str = "queued"
    progress_message: str = ""
    current_trial_index: int = 0
    total_trials_planned: int = 0
    best_score_so_far: Optional[float] = None
    best_config_so_far: Optional[dict] = None

    # Final results (populated when status=completed)
    # `baseline_no_tool_score`: 1-shot prompt without extraction config — the
    # "is this extraction earning its complexity?" floor.
    # `baseline_default_score`: current authored extraction_config.
    # `optimized_score`: best trial's score.
    baseline_no_tool_score: Optional[float] = None
    baseline_default_score: Optional[float] = None
    optimized_score: Optional[float] = None
    # Train/holdout split — when the test set is large enough (>= HOLDOUT_MIN_CASES)
    # we reserve a slice from winner selection and re-score the winner + default
    # on it for an unbiased ``optimized_score``. ``optimized_score`` then holds
    # the HOLDOUT score; ``optimized_score_train`` keeps the in-sample number
    # for diagnostics. When N is too small to split, ``overfitting_warning``
    # is set and the in-sample score is the headline.
    optimized_score_train: Optional[float] = None
    holdout_default_score: Optional[float] = None
    train_test_case_uuids: list[str] = Field(default_factory=list)
    holdout_test_case_uuids: list[str] = Field(default_factory=list)
    overfitting_warning: bool = False
    # Why the trial loop stopped: "budget_exhausted", "all_trials_complete",
    # "converged", "cancelled", "failed". Populated on terminal status.
    stopped_reason: Optional[str] = None
    # Per-item judge nondeterminism σ, measured by sample-resample on the
    # default baseline. Drives the significance-gated winner selection below.
    judge_variance: Optional[float] = None
    # Standard error of the per-trial mean score = σ / √N_items, where N_items
    # is the count of judged (test_case × field × run) triples in the trial.
    # This is what's actually compared against trial-score deltas.
    judge_score_se: Optional[float] = None
    # One of:
    #   "highest_score"           — winner beats runner-up by > 2 × SE
    #   "default_in_cluster"      — baseline default is statistically tied with
    #                               the highest-score trial; keep current config
    #   "closest_to_default"      — multiple non-default trials are tied; pick
    #                               the one structurally closest to default
    #   "no_judge_variance"       — could not measure σ; default noise floor used
    winner_selection_reason: Optional[str] = None
    # True when no trial beat baseline_default by >= 2 × SE. Suppresses
    # apply_on_finish so we don't write a config change that the data can't
    # justify.
    tied_with_baseline: bool = False
    judge_model: Optional[str] = None
    # Models excluded from the candidate sweep because they share a family
    # with judge_model (self-preference guard).
    excluded_models: list[str] = Field(default_factory=list)

    best_config: Optional[dict] = None
    trials: list[dict] = Field(default_factory=list)
    # Each trial dict shape:
    # {
    #   "trial_id": str, "config": {model, strategy, thinking, ...},
    #   "score": float, "accuracy": float, "consistency": float,
    #   "lift_vs_default": float | None,
    #   "tokens_used": int, "status": "completed|early_stopped|failed",
    #   "started_at": str, "duration_seconds": float,
    #   "cross_field_summary": {pass, fail, unparseable, pass_rate, ...} | None,
    # }

    # Per-field accuracy across the best trial — drives "which fields are
    # dragging the score" recommendations. Shape: list[{field, accuracy, consistency}].
    field_breakdown: list[dict] = Field(default_factory=list)

    # Cross-field rule outcome for the winning config — aggregate counts +
    # pass_rate ({pass, fail, unparseable, pass_rate, violation_rate, total}).
    # The optimizer already weights cross-field compliance into trial score
    # (20% when rules are present); this field makes the result visible to
    # the user so they can see *why* the winner won and gate apply on it.
    winner_cross_field_summary: Optional[dict] = None
    # Per-rule breakdown for the winning config, grouped from the flat
    # (test_case × run × rule) results: {rule_id, type, label, pass, fail,
    # unparseable, pass_rate}. Drives the per-rule "X failed on 4/6 cases"
    # suggestions and the apply-gate detail message.
    winner_cross_field_rule_breakdown: list[dict] = Field(default_factory=list)

    # Per-field suggestions surfaced to the user (e.g. "rewrite this field's
    # definition", "add few-shot examples"). Same shape as KB's data_source_suggestions.
    suggestions: list[dict] = Field(default_factory=list)

    # Preserved override from before this optimization applied (when apply_on_finish
    # is true OR a later apply call fires). Powers the revert button — restoring
    # this value clears the optimizer's applied config.
    previous_override: Optional[dict] = None

    # Snapshot of a validation run executed *after* the winning config was
    # applied — closes the loop back to the user by showing whether the
    # in-optimizer lift held up on a fresh full-test-set evaluation. Shape:
    # {accuracy, consistency, cross_field_pass_rate, score, ran_at,
    #  test_case_count, source: "apply_on_finish" | "explicit_apply"}.
    # Null until apply runs.
    post_apply_validation: Optional[dict] = None

    # Apply-preview rollup (Phase 2 loop closure). Per-FIELD baseline-vs-winner
    # deltas so the Apply confirmation modal can show "K of N fields will
    # change, R regress". Shape: see ``optimization_common.build_apply_preview``.
    apply_preview: Optional[dict] = None

    # Caller-supplied options
    options: dict = Field(default_factory=dict)
    # Shape: {"apply_on_finish": bool, "include_judge": bool, "advanced": {...}}

    error_message: Optional[str] = None

    class Settings:
        name = "extraction_optimization_runs"
        indexes = [
            "uuid",
            "search_set_uuid",
            "status",
            ("search_set_uuid", "status"),
            "started_at",
        ]

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
