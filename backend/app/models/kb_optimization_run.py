"""KBOptimizationRun - tracks one execution of the KB Autovalidate optimizer.

A single run sweeps multiple RAG configurations against the same test set and
records the trial outcomes plus the winning config. The UI polls this document
to show live progress and (when status=completed) the optimization results.
"""

from __future__ import annotations

import datetime
from typing import Literal, Optional
from uuid import uuid4

from beanie import Document
from pydantic import Field


KBOptimizationStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class KBOptimizationRun(Document):
    """A single optimization run for a knowledge base."""

    uuid: str = ""
    kb_uuid: str
    user_id: str
    status: KBOptimizationStatus = "queued"

    # Lifecycle timestamps
    started_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    completed_at: Optional[datetime.datetime] = None

    # Budget enforcement
    token_budget: int = 0
    tokens_used: int = 0
    estimated_cost_usd: Optional[float] = None
    actual_cost_usd: Optional[float] = None

    # Cancellation flag — set by the cancel route, checked by the worker
    # between trials. We avoid hard kills mid-trial so a partial trial doesn't
    # leave orphan tokens unaccounted-for.
    cancel_requested: bool = False

    # Live progress — UI polls these. Updated after each trial.
    phase: str = "queued"                 # queued | preparing | running | finalizing | done
    progress_message: str = ""
    current_trial_index: int = 0
    total_trials_planned: int = 0
    best_score_so_far: Optional[float] = None
    best_config_so_far: Optional[dict] = None

    # Final results (populated when status=completed)
    baseline_no_kb_score: Optional[float] = None
    baseline_default_score: Optional[float] = None
    optimized_score: Optional[float] = None
    judge_variance: Optional[float] = None  # for confidence interval reporting
    judge_model: Optional[str] = None        # which model judged (regression-comparison metadata)

    best_config: Optional[dict] = None
    trials: list[dict] = Field(default_factory=list)
    # Each trial dict shape:
    # {
    #   "trial_id": str, "config": {...RAGConfig...},
    #   "score": float, "lift_vs_default": float | None,
    #   "tokens_used": int, "status": "completed|early_stopped|failed",
    #   "started_at": str, "duration_seconds": float,
    #   "judge_breakdown": {avg_judge_score, num_passed, num_failed, ...},
    # }

    data_source_suggestions: list[dict] = Field(default_factory=list)
    # [{kind: "coverage_gap|redundant_source|retrieval_bottleneck",
    #   severity: "info|warning|critical", source_uuid?, message}]

    # Caller-supplied options (so re-runs and audits can see what was asked for)
    options: dict = Field(default_factory=dict)
    # Shape: {"include_indexing_track": bool, "apply_on_finish": bool, "advanced": {...}}

    error_message: Optional[str] = None

    class Settings:
        name = "kb_optimization_runs"
        indexes = [
            "uuid",
            "kb_uuid",
            "status",
            ("kb_uuid", "status"),
            "started_at",
        ]

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
