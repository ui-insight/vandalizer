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

    # Final results (populated when status=completed). All "score" fields are
    # the **blended quality score** on a 0..1 scale (judge 40% + retrieval 25%
    # + health 20% + coverage 15%) so the optimizer reports the same number
    # the validation header reports. Exception: ``baseline_no_kb_score`` is
    # the raw no-KB judge score (no KB → no retrieval/health/coverage to blend).
    baseline_no_kb_score: Optional[float] = None
    baseline_default_score: Optional[float] = None
    optimized_score: Optional[float] = None
    judge_variance: Optional[float] = None  # legacy sigma; richer info in judge_variance_meta
    judge_model: Optional[str] = None        # which model judged (regression-comparison metadata)

    # Config-invariant baselines captured once per run and reused across all
    # trials. Health + coverage depend only on KB content state; retrieval
    # precision currently uses a fixed k=8 in `check_retrieval_precision`, so
    # it's also invariant within a run. All three are 0..1 ratios.
    baseline_retrieval_score: Optional[float] = None
    baseline_health_score: Optional[float] = None
    baseline_coverage_score: Optional[float] = None

    # Raw default-config judge score (before blending). Persisted alongside
    # the blended ``baseline_default_score`` so per-query lift CI math (which
    # compares judge scores) still has the right reference point.
    baseline_default_judge_score: Optional[float] = None

    # Snapshot of the effective default RAGConfig used to compute the default
    # baseline. Surfaced in the UI so ``BestConfigCard`` can render a
    # default→winner diff. Includes the KB's current ``rag_config_override``
    # if any (so re-tuning a tuned KB compares against the live config, not
    # raw RAGConfig defaults).
    default_config: Optional[dict] = None

    # Train/holdout split (T2.1) — when the eval set is large enough (>=6
    # queries) we hold out ~1/3 of queries from winner selection and re-run
    # the winner + default on that slice for an unbiased ``optimized_score``.
    # ``optimized_score`` above holds the HOLDOUT score in that case;
    # ``optimized_score_train`` keeps the in-sample number for diagnostics.
    optimized_score_train: Optional[float] = None
    holdout_default_score: Optional[float] = None
    train_query_uuids: list[str] = Field(default_factory=list)
    holdout_query_uuids: list[str] = Field(default_factory=list)
    # True when N<6: no split was applied, so the headline score is in-sample.
    overfitting_warning: bool = False

    # Recorded stop reason — populated on terminal status so the UI can show
    # "converged after 18 trials" vs "ran out of budget" vs "user cancelled".
    # One of: "budget_exhausted", "all_trials_complete", "converged",
    # "cancelled", "failed".
    stopped_reason: Optional[str] = None

    # Variance-aware winner-selection diagnostics (T2.2).
    # ``tie_cluster_size`` counts how many trials scored within 2·SE of the
    # top — when >1 the headline winner is one of several configs the judge
    # can't reliably distinguish. ``winner_selection_reason`` records *why*
    # this trial won: "highest_score" (cluster size 1),
    # "tied_with_baseline" (top trial is within noise of the current config —
    # apply is suppressed), or "closest_to_default" (smallest L0 distance to
    # default within the tie cluster).
    tie_cluster_size: Optional[int] = None
    winner_selection_reason: Optional[str] = None
    # True when the top trial is statistically tied with the current applied
    # config: apply-on-finish is suppressed so we never change a config the
    # data can't justify. Frontend uses this to render the "no measurable
    # improvement" banner instead of the optimized banner.
    tied_with_baseline: bool = False

    best_config: Optional[dict] = None
    trials: list[dict] = Field(default_factory=list)
    # Each trial dict shape:
    # {
    #   "trial_id": str, "config": {...RAGConfig...},
    #   "score": float,            # BLENDED quality (judge*0.40 + R*0.25 + H*0.20 + C*0.15)
    #   "judge_score": float,      # raw judge avg, kept for lift CI + cross-judge audit
    #   "lift_vs_default": float | None,   # blended − blended (same units as score)
    #   "tokens_used": int, "status": "completed|early_stopped|failed",
    #   "started_at": str, "duration_seconds": float,
    #   "judge_breakdown": {avg_judge_score, num_passed, num_failed, ...},
    #   "per_query_results": [{query_uuid, query, category, score,
    #       baseline_score (default-config baseline at run start),
    #       delta_vs_default, actual_answer, judge_verdict, judge_reasoning,
    #       missing_facts, hallucinated_facts, retrieved_sources}],
    # }

    # Default-config per-query baseline (captured during _establish_baselines).
    # Used by per-query delta tables and the paired-bootstrap CI. Keyed by
    # query_uuid → {score, actual_answer, judge_verdict, judge_reasoning, ...}.
    default_per_query_results: list[dict] = Field(default_factory=list)
    # No-KB baseline per-query results (same shape, used for "lift over no-KB").
    no_kb_per_query_results: list[dict] = Field(default_factory=list)

    # Reproducibility — captured at run start so re-runs are diagnosable.
    rng_seed: Optional[int] = None
    judge_prompt_version: Optional[str] = None
    judge_temperature: Optional[float] = None

    # Snapshot of the eval set at run start. Composition info drives UI chips;
    # expected_answer_hashes let us detect drift between runs.
    # Shape: {
    #   "total": int, "query_uuids": list[str],
    #   "expected_answer_hashes": dict[uuid, sha256_hex],
    #   "auto_generated_count": int, "user_authored_count": int,
    #   "categories": dict[category_name, count],
    #   "sources_covered": list[source_uuid], "total_sources": int,
    # }
    test_query_snapshot: Optional[dict] = None

    # Richer judge_variance info — replaces the bare ``judge_variance`` field
    # for UIs that want to show n and which queries were sampled.
    # Shape: {"sigma": float | None, "n": int, "sampled_query_uuids": list[str]}.
    judge_variance_meta: Optional[dict] = None

    # Paired-bootstrap CI on the optimized-vs-default lift. Driven by per-query
    # data on the winning trial + ``default_per_query_results``.
    # Shape: {
    #   "lift": float, "lower": float, "upper": float, "p_value": float,
    #   "n_queries": int, "n_iterations": int, "method": "paired_bootstrap",
    #   "confidence_level": 0.95,
    # }
    lift_ci: Optional[dict] = None

    # Cross-judge sanity check (audit #12). When budget allows, re-score the
    # winning trial with an alternate judge model to surface judge self-bias.
    # Shape: {"model": str, "score": float, "tokens_used": int, "delta": float,
    #         "agreement_pct"?: float, "kappa_equivalent"?: float}.
    cross_judge: Optional[dict] = None

    # Candidate models excluded from the search space because they belong to
    # the same family as the pinned judge (self-preference guard). Empty list
    # is the typical case. Surfaced to the UI so users can see what was held
    # out and why.
    judge_family_excluded_models: list[str] = Field(default_factory=list)

    data_source_suggestions: list[dict] = Field(default_factory=list)
    # [{kind: "coverage_gap|redundant_source|retrieval_bottleneck",
    #   severity: "info|warning|critical", source_uuid?, message}]

    # Caller-supplied options (so re-runs and audits can see what was asked for)
    options: dict = Field(default_factory=dict)
    # Shape: {"include_indexing_track": bool, "apply_on_finish": bool, "advanced": {...}}

    # Apply/revert lifecycle. When the winning config is applied to the KB we
    # snapshot the prior ``rag_config_override`` here so a future Revert can
    # restore it. ``applied_at`` / ``reverted_at`` are set so the UI can tell
    # which runs are currently live and which have been rolled back.
    previous_override: Optional[dict] = None
    applied_at: Optional[datetime.datetime] = None
    reverted_at: Optional[datetime.datetime] = None

    # Apply-preview rollup (Phase 2). Computed once at run completion by
    # ``optimization_common.build_apply_preview`` from the per-query
    # default-vs-winner score deltas. Used by the Apply confirmation modal so
    # the user sees "K of N items will change, R regress" before committing.
    # Shape documented on ``build_apply_preview``.
    apply_preview: Optional[dict] = None

    error_message: Optional[str] = None
    # Structured failure classification — populated alongside ``error_message``
    # so the UI can render plain-English remediation (e.g. "Add documents to
    # this KB before tuning") instead of a raw exception string. Stable codes:
    # ``kb_not_found``, ``kb_empty``, ``test_set_too_small``, ``judge_unavailable``,
    # ``baselines_failed``, ``all_trials_failed``, ``budget_exhausted``, ``unknown``.
    error_code: Optional[str] = None
    # Free-form context attached to the failure (e.g. {"n_queries": 2,
    # "required": 5}) so the banner can plug specific numbers into the message.
    error_context: Optional[dict] = None

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
