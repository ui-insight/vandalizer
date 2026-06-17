"""Extraction optimizer — wraps the tuning service with baselines + persistence.

Where ``extraction_tuning_service.find_best_settings_stream`` is a primitive
(sweep N configs, stream results), this orchestrator builds the full
"Improve extraction quality" loop:

1. **Measure baselines** so the user can answer "is this extraction earning
   its complexity?":
   * ``baseline_no_tool`` — run extraction with no user config (just system
     defaults). The "what does the LLM do with no help?" floor.
   * ``baseline_default`` — run extraction with the user's currently-applied
     effective config (override-or-authored).
2. **Run the sweep** via the existing tuning service.
3. **Persist** baselines + trials + winner to ``ExtractionOptimizationRun``
   so the UI can poll progress and the optimizer can be cancelled/applied.
4. **Optionally apply** the best config back to the SearchSet.

Phase 1A: strict-match scoring only (no LLM judge — that's Phase 1B).
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
from typing import Any

from app.models.extraction_optimization_run import ExtractionOptimizationRun
from app.models.extraction_test_case import ExtractionTestCase
from app.models.search_set import SearchSet
from app.models.system_config import SystemConfig
from app.services.config_service import get_user_model_name
from app.services.extraction_tuning_service import (
    _build_candidate_configs,
    _run_single_config,
)
from app.services.optimization_common import (
    DEFAULT_JUDGE_NOISE_FLOOR,
    build_apply_preview,
    pick_winner_variance_aware,
)
from app.services.search_set_service import (
    effective_extraction_config,
    get_extraction_field_metadata,
    get_extraction_keys,
)

logger = logging.getLogger(__name__)

# Per-trial token estimate for budget bookkeeping (Phase 1A: rough — we don't
# yet measure per-trial tokens, so this is a pessimistic ceiling that controls
# how many trials fit in a tier).
EXTRACTION_PER_TRIAL_TOKEN_ESTIMATE = 50_000

# How many runs per trial for accuracy/consistency measurement.
DEFAULT_NUM_RUNS_PER_TRIAL = 2

# Train/holdout split. With fewer than this many test cases the holdout slice
# would be too thin to give a stable unbiased headline; we skip the split and
# flag ``overfitting_warning`` so the UI can caveat the optimized score.
HOLDOUT_MIN_CASES = 4
# Fraction of cases reserved for holdout. 1/3 mirrors KB and trades slightly
# noisier holdout estimates for more training signal in winner selection.
HOLDOUT_FRACTION = 1.0 / 3.0

# Convergence stopping. Need at least this many completed trials before we can
# claim convergence — early trials don't explore enough to pick a defensible
# winner.
CONVERGENCE_MIN_TRIALS = 6
# Patience window: trials in a row without improving the leader before we
# consider stopping. Larger = more conservative.
CONVERGENCE_PATIENCE = 4

# How often the trial guard wakes to re-check ``cancel_requested`` while a
# single config runs in the background. Small enough that a UI cancel feels
# instant; large enough not to hammer Mongo.
CANCEL_POLL_INTERVAL_SECONDS = 5.0

# Per-config wall-clock ceiling. A single hung / rate-limited LLM call must not
# wedge the whole run past this — we cancel that config, record it failed, and
# move on. Generous enough that a legitimately slow judged config (many cases ×
# fields × runs) finishes well within it.
PER_TRIAL_TIMEOUT_SECONDS = 900.0

# A run still "running"/"queued" this long after ``started_at`` has almost
# certainly lost its worker (Celery's hard time_limit on the task is 5460s).
# The watchdog flips such orphans to failed so the UI stops spinning forever
# and a fresh run can start.
STALE_RUN_TIMEOUT_SECONDS = 5460 + 240  # task hard time_limit + 4 min buffer

# A cancel the worker hasn't honored within this window means the worker is
# gone — a live worker honors cancel within one CANCEL_POLL_INTERVAL. The
# watchdog then finalizes the run as cancelled on the user's behalf.
CANCEL_REAP_GRACE_SECONDS = 180


class _TrialCancelled(Exception):
    """Raised inside the optimization loop when a user cancel lands mid-config.

    Distinct from a normal trial failure: the caller must finalize the whole
    run as cancelled rather than record a failed trial and continue.
    """


def _split_train_holdout(
    test_cases: list[ExtractionTestCase],
    search_set_uuid: str,
) -> tuple[list[ExtractionTestCase], list[ExtractionTestCase]]:
    """Deterministically partition test cases into (train, holdout).

    Mirrors KB's pattern: hash on ``(search_set_uuid, tc.uuid)`` so re-running
    the same SearchSet yields the same split — users comparing two runs see
    apples-to-apples numbers. Sort-by-hash is stable across reorderings of
    the input list, unlike ``random.shuffle``.
    """
    if len(test_cases) < HOLDOUT_MIN_CASES:
        return list(test_cases), []

    def _bucket(tc: ExtractionTestCase) -> str:
        uid = str(getattr(tc, "uuid", "") or "")
        return hashlib.sha256(f"{search_set_uuid}:{uid}".encode("utf-8")).hexdigest()

    ordered = sorted(test_cases, key=_bucket)
    n_holdout = max(1, int(round(len(ordered) * HOLDOUT_FRACTION)))
    # Holdout slice first in the sorted order so adding cases (which land at
    # arbitrary hash positions) tends to grow train, not holdout.
    holdout = ordered[:n_holdout]
    train = ordered[n_holdout:]
    return train, holdout


def _l0_distance_from_default(cfg: dict | None, default_cfg: dict | None) -> int:
    """Count axes where ``cfg`` deviates from ``default_cfg``.

    Used in tie-cluster resolution: when multiple configs are statistically
    tied with the leader, pick the one structurally closest to default. Fewer
    knobs flipped = less surface for downstream surprises.
    """
    if not cfg:
        return 0
    if default_cfg is None:
        default_cfg = {}
    distance = 0
    # Only count keys actually present in cfg — extra default keys would
    # otherwise inflate every distance equally.
    for key in ("mode", "prompt_variant", "chunking", "repetition", "one_pass", "two_pass", "model"):
        if cfg.get(key) != default_cfg.get(key):
            distance += 1
    return distance


def _model_family(model_name: str) -> str:
    """Coarse family bucket for self-preference exclusion.

    A judge of family X over-rates extractor outputs of family X (the
    self-preference bias). We exclude same-family candidates to keep the
    fitness function honest. The family is derived from the model name's
    prefix before the first ``-`` or ``/``; close enough for OpenAI's
    ``gpt-4o`` / ``gpt-4o-mini`` (same family), Anthropic's ``claude-...``
    (same family), and Google's ``gemini-...``.
    """
    if not model_name:
        return ""
    s = model_name.lower()
    # Strip provider/path prefix
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    # Family token: chars up to first separator or version digit
    out = []
    for ch in s:
        if ch in "-_." or ch.isdigit():
            break
        out.append(ch)
    return "".join(out) or s


def _candidates_excluding_judge_family(
    candidates: list[dict],
    judge_model: str | None,
) -> tuple[list[dict], list[str]]:
    """Drop candidates whose model is in the same family as ``judge_model``.

    Returns ``(kept, excluded_model_names)``. Falls back to keeping everything
    if exclusion would empty the candidate list (better to run with bias than
    have no trials at all).
    """
    if not judge_model:
        return (candidates, [])
    judge_family = _model_family(judge_model)
    kept: list[dict] = []
    excluded: list[str] = []
    for c in candidates:
        if _model_family(c.get("model", "")) == judge_family:
            excluded.append(c.get("model", ""))
        else:
            kept.append(c)
    if not kept:
        # All candidates are same-family as the judge — keep them; flag in the
        # excluded list so the UI can warn about self-preference risk.
        return (candidates, [])
    return (kept, list(dict.fromkeys(excluded)))


async def run_optimization(
    search_set_uuid: str,
    user_id: str,
    run_uuid: str,
    budget_tokens: int = 0,
    apply_on_finish: bool = False,
    max_candidates: int = 8,
    num_runs: int = DEFAULT_NUM_RUNS_PER_TRIAL,
    include_judge: bool = False,
    test_case_uuids: list[str] | None = None,
) -> ExtractionOptimizationRun:
    """Execute the full optimization loop. Caller pre-allocates the run doc.

    The optimizer flow mirrors KB Autovalidate:

    1. Allocate / fetch the pre-created ``ExtractionOptimizationRun``
    2. Establish baselines (no-tool, default-config)
    3. Sweep ``max_candidates`` configs from ``_build_candidate_configs``
       (budget-capped from ``budget_tokens`` if non-zero)
    4. Pick the winner; optionally apply back to ``SearchSet.extraction_config_override``
    5. Mark run completed

    Raises ``ValueError`` on missing keys / test cases. The caller wraps this
    in a Celery task that catches and marks the run failed.
    """
    run_doc = await ExtractionOptimizationRun.find_one(
        ExtractionOptimizationRun.uuid == run_uuid,
    )
    if not run_doc:
        raise ValueError(f"ExtractionOptimizationRun not found: {run_uuid}")

    try:
        await _update(run_doc, status="running", phase="preparing",
                      progress_message="Loading test cases…")

        keys = await get_extraction_keys(search_set_uuid)
        if not keys:
            raise ValueError("No extraction fields defined")

        test_cases = await ExtractionTestCase.find(
            ExtractionTestCase.search_set_uuid == search_set_uuid,
        ).to_list()
        # Honor the wizard's checkbox selection: when a subset was chosen, tune
        # against exactly those cases. None/empty = every case for the set.
        if test_case_uuids:
            wanted = set(test_case_uuids)
            test_cases = [tc for tc in test_cases if tc.uuid in wanted]
        test_cases = [tc for tc in test_cases if tc.expected_values
                      and any(v for v in tc.expected_values.values())]
        if not test_cases:
            raise ValueError(
                "No test cases with expected values found. "
                "Create test cases first (or use 'Create from extraction' to bootstrap).",
            )

        # Train/holdout split — winner selection happens on train, the
        # headline ``optimized_score`` is re-measured on holdout. Without this
        # best-of-N selection bias inflates the optimized score by ~2σ × √(2 ln N)
        # over the true value, turning judge noise into "lift".
        train_cases, holdout_cases = _split_train_holdout(test_cases, search_set_uuid)
        run_doc.train_test_case_uuids = [
            str(getattr(tc, "uuid", "") or "") for tc in train_cases
        ]
        run_doc.holdout_test_case_uuids = [
            str(getattr(tc, "uuid", "") or "") for tc in holdout_cases
        ]
        run_doc.overfitting_warning = not holdout_cases
        await run_doc.save()

        sys_config = await SystemConfig.get_config()
        sys_config_doc = sys_config.model_dump() if sys_config else {}
        field_metadata = await get_extraction_field_metadata(search_set_uuid)
        ss = await SearchSet.find_one(SearchSet.uuid == search_set_uuid)
        cross_field_rules = ss.normalized_cross_field_rules() if ss else []

        # Resolve a default model for baselines (the user's current model)
        baseline_model = await get_user_model_name(user_id)
        # Judge model: same as user's current. (Phase 1B uses the user's
        # model for both extraction and judging — Phase 2 could let admins
        # configure a separate, stronger judge.)
        judge_model = baseline_model if include_judge else None
        if include_judge:
            run_doc.judge_model = judge_model
            await run_doc.save()

        # --- Phase 1: baselines (no-tool, default) ---
        await _update(run_doc, phase="baselines",
                      progress_message="Measuring baselines…")

        try:
            no_tool_result = await _run_config_guarded(
                run_doc,
                candidate={
                    "label": "baseline-no-tool",
                    "model": baseline_model,
                    "config_override": {},
                },
                keys=keys,
                test_cases=train_cases,
                sys_config_doc=sys_config_doc,
                field_metadata=field_metadata,
                num_runs=num_runs,
                judge_model=judge_model,
                cross_field_rules=cross_field_rules,
            )
        except _TrialCancelled:
            return await _finalize_cancelled(run_doc)
        run_doc.baseline_no_tool_score = _score_to_unit(no_tool_result.get("score"))
        run_doc.tokens_used += int(no_tool_result.get("judge_tokens", 0) or 0)
        await run_doc.save()

        default_cfg = effective_extraction_config(ss)
        try:
            default_result = await _run_config_guarded(
                run_doc,
                candidate={
                    "label": "baseline-default",
                    "model": default_cfg.get("model") or baseline_model,
                    "config_override": default_cfg or {},
                },
                keys=keys,
                test_cases=train_cases,
                sys_config_doc=sys_config_doc,
                field_metadata=field_metadata,
                num_runs=num_runs,
                judge_model=judge_model,
                cross_field_rules=cross_field_rules,
            )
        except _TrialCancelled:
            return await _finalize_cancelled(run_doc)
        run_doc.baseline_default_score = _score_to_unit(default_result.get("score"))
        run_doc.tokens_used += int(default_result.get("judge_tokens", 0) or 0)
        await run_doc.save()

        # Judge variance — sample-resample boundary-band items from the
        # default baseline to estimate judge nondeterminism. Drives the ±N
        # pts CI display in the comparison card AND the significance-gated
        # winner selection below. Only meaningful when judge is on.
        if judge_model:
            raw_samples = default_result.get("judge_samples") or []
            # Skip deterministic comparator results — σ is 0 by construction
            # there, and including them would dilute the estimate of LLM
            # judge noise.
            samples = [
                s for s in raw_samples
                if s.get("comparator", "llm") not in ("deterministic", "llm_error")
            ]
            if len(samples) >= 2:
                from app.services.judge_variance import (
                    DEFAULT_VARIANCE_SAMPLES,
                    sample_judge_variance,
                )
                from app.services.extraction_judge import judge_field_value

                async def _rejudge(sample: dict) -> tuple[float, int]:
                    v = await judge_field_value(
                        field_name=sample["field_name"],
                        expected=sample["expected"],
                        actual=sample["actual"],
                        model_name=judge_model,
                        field_metadata=sample.get("field_metadata"),
                    )
                    return float(v["score"]), int(v.get("tokens_used", 0) or 0)

                # Default selector (boundary-band bias) makes σ reflect the
                # regime where optimizer decisions actually happen.
                variance, variance_tokens = await sample_judge_variance(
                    samples=samples,
                    judge_fn=_rejudge,
                    original_score=lambda s: float(s["score"]),
                    max_samples=DEFAULT_VARIANCE_SAMPLES,
                )
                run_doc.tokens_used += int(variance_tokens or 0)
                if variance is not None:
                    run_doc.judge_variance = variance
                    await run_doc.save()
                else:
                    await run_doc.save()

        if await _is_cancelled(run_doc):
            return await _finalize_cancelled(run_doc)

        # --- Phase 2: trial sweep ---
        await _update(run_doc, phase="sweep",
                      progress_message="Trying configurations…")

        candidates = _build_candidate_configs(
            sys_config.available_models if sys_config else [],
            len(keys),
        )
        # Self-preference guard: drop candidates whose model is in the same
        # family as the judge_model. An LLM judge of family X over-rates
        # outputs of family X (well-documented bias), so leaving same-family
        # trials in the sweep would let the optimizer pick a winner by
        # exploiting that bias rather than by genuine quality.
        if judge_model:
            candidates, excluded_models = _candidates_excluding_judge_family(
                candidates, judge_model,
            )
            if excluded_models:
                run_doc.excluded_models = excluded_models
                await run_doc.save()
        # Budget cap (Phase 1A: optional — caller may pass budget_tokens=0 to
        # use max_candidates directly)
        if budget_tokens > 0:
            from app.services.budget_enforcer import BudgetEnforcer
            enforcer = BudgetEnforcer(
                total_budget=budget_tokens,
                per_trial_estimate=EXTRACTION_PER_TRIAL_TOKEN_ESTIMATE,
                max_trial_count=max_candidates,
            )
            candidates = enforcer.sample_trials(candidates)
        else:
            candidates = candidates[:max_candidates]

        run_doc.total_trials_planned = len(candidates)
        await run_doc.save()

        trial_results: list[dict] = []
        # Parallel to trial_results, keyed by label — lets the finalize phase
        # retrieve the raw _run_single_config output (with field_breakdown +
        # judge_samples) for the winning trial.
        raw_by_label: dict[str, dict] = {}
        # Convergence tracking: count completed trials since the leader's
        # score improved. Combined with a runner-up-gap gate this avoids
        # declaring convergence on noise.
        trials_since_best_changed = 0
        stopped_reason: str | None = None
        for i, candidate in enumerate(candidates):
            if await _is_cancelled(run_doc):
                return await _finalize_cancelled(run_doc)

            # Convergence check (mirrors KB). Requires variance to have been
            # measured during the baseline phase so the runner-up gap is
            # judged against real noise, not just the fallback floor.
            if (
                run_doc.best_score_so_far is not None
                and len(trial_results) >= CONVERGENCE_MIN_TRIALS
                and trials_since_best_changed >= CONVERGENCE_PATIENCE
            ):
                sigma = run_doc.judge_variance if run_doc.judge_variance is not None else DEFAULT_JUDGE_NOISE_FLOOR
                completed_scores = sorted(
                    (float(t["score"]) for t in trial_results
                     if t.get("status") == "completed" and t.get("score") is not None),
                    reverse=True,
                )
                if len(completed_scores) >= 2:
                    top, runner_up = completed_scores[0], completed_scores[1]
                    # Use raw σ as the gap test here (matches KB) — the
                    # per-trial mean has already been smoothed by num_runs
                    # × num_cases × num_fields comparisons.
                    if (top - runner_up) > 2.0 * sigma:
                        logger.info(
                            "Extraction optimizer converged at trial %d: best %.3f, runner-up %.3f, σ %.3f",
                            i, top, runner_up, sigma,
                        )
                        stopped_reason = "converged"
                        break

            await _update(
                run_doc,
                current_trial_index=i + 1,
                progress_message=f"Trying {candidate['label']}…",
            )

            try:
                result = await _run_config_guarded(
                    run_doc,
                    candidate=candidate,
                    keys=keys,
                    test_cases=train_cases,
                    sys_config_doc=sys_config_doc,
                    field_metadata=field_metadata,
                    num_runs=num_runs,
                    judge_model=judge_model,
                    cross_field_rules=cross_field_rules,
                )
            except _TrialCancelled:
                # Cancel landed mid-trial — stop the whole run now rather than
                # finishing this config first.
                return await _finalize_cancelled(run_doc)
            except Exception as e:
                # Includes TimeoutError from the per-trial guard: a hung config
                # becomes a failed trial, not a wedged run.
                logger.warning("Trial %s failed: %s", candidate["label"], e)
                result = {
                    "label": candidate["label"],
                    "model": candidate["model"],
                    "config_override": candidate["config_override"],
                    "accuracy": 0.0,
                    "consistency": 0.0,
                    "score": 0.0,
                    "elapsed_seconds": 0.0,
                    "error": str(e),
                }

            trial_summary = _to_trial_summary(result, baseline_default_score=run_doc.baseline_default_score)
            trial_results.append(trial_summary)
            raw_by_label[trial_summary["trial_id"]] = result
            run_doc.tokens_used += int(trial_summary.get("tokens_used", 0) or 0)

            # Update best-so-far ticker + convergence counter
            score_unit = _score_to_unit(result.get("score"))
            improved = (
                score_unit is not None
                and (run_doc.best_score_so_far is None or score_unit > run_doc.best_score_so_far)
            )
            if improved:
                run_doc.best_score_so_far = score_unit
                run_doc.best_config_so_far = _trial_config_for_run(result)
                trials_since_best_changed = 0
            else:
                trials_since_best_changed += 1

            run_doc.trials = trial_results
            await run_doc.save()
        else:
            # for-else: hit only when the loop exhausts without `break`.
            stopped_reason = "all_trials_complete"

        run_doc.stopped_reason = stopped_reason
        await run_doc.save()

        # --- Phase 3: finalize (variance-aware winner selection) ---
        await _update(run_doc, phase="finalizing",
                      progress_message="Finalizing results…")

        # Tighten the variance estimate by also re-sampling the judge against
        # the top-2 trials' outputs and taking the max σ.
        #
        # The baseline-only σ implicitly assumes judge nondeterminism is the
        # same regardless of the candidate config. That's defensible on
        # average but can under-estimate σ when the winning config produces
        # boundary-band outputs the judge handles less confidently. Taking
        # the max keeps the significance gate conservative — we'd rather
        # decline to apply a marginal lift than over-claim one.
        if judge_model and run_doc.judge_variance is not None:
            top_trials = sorted(
                (t for t in trial_results if t.get("status") == "completed"),
                key=lambda t: (t.get("score") or 0.0),
                reverse=True,
            )[:2]
            await _tighten_variance_with_top_trials(
                run_doc=run_doc,
                top_trials=top_trials,
                raw_by_label=raw_by_label,
                judge_model=judge_model,
            )

        if trial_results:
            # N for SE: average ``total_comparisons`` across completed trials.
            # Per-trial N varies if some trials short-circuit on failures, but
            # the average is a reasonable single value for SE computation.
            ns = [
                t.get("total_comparisons", 0)
                for t in trial_results
                if t.get("status") == "completed" and t.get("total_comparisons")
            ]
            n_items = max(1, int(sum(ns) / len(ns))) if ns else 1
            run_doc.judge_score_se = round(
                (run_doc.judge_variance or DEFAULT_JUDGE_NOISE_FLOOR) / (n_items ** 0.5),
                4,
            )

            winner, reason, tied, _cluster_size = pick_winner_variance_aware(
                trial_results,
                judge_variance=run_doc.judge_variance,
                baseline_default_score=run_doc.baseline_default_score,
                distance_from_default=lambda t: _l0_distance_from_default(
                    t.get("config"), default_cfg,
                ),
                n_items_for_se=n_items,
            )
            run_doc.winner_selection_reason = (
                "no_judge_variance" if run_doc.judge_variance is None else reason
            )
            run_doc.tied_with_baseline = tied

            if winner is not None:
                # Preserve the in-sample (train) score for diagnostics. The
                # headline ``optimized_score`` may be overwritten below by the
                # holdout re-score when we have a holdout slice.
                run_doc.optimized_score_train = winner.get("score")
                run_doc.optimized_score = winner.get("score")
                run_doc.best_config = winner.get("config")
                best_raw = raw_by_label.get(winner["trial_id"]) or {}
                run_doc.field_breakdown = list(best_raw.get("field_breakdown") or [])

                # Cross-field outcome on the winning config: store the aggregate
                # summary (for the headline "Rules: N/M pass" stat + apply-gate)
                # and the per-rule breakdown (for the "which rules failed" panel
                # + per-rule suggestions).
                winner_cf_summary = best_raw.get("cross_field_summary")
                winner_cf_results = best_raw.get("cross_field_results") or []
                run_doc.winner_cross_field_summary = winner_cf_summary
                run_doc.winner_cross_field_rule_breakdown = (
                    _aggregate_cf_results_by_rule(winner_cf_results)
                )

                # Holdout re-evaluation: rerun the winning config AND the
                # default config on the held-out slice. The headline
                # ``optimized_score`` becomes the holdout number (unbiased by
                # best-of-N selection); ``optimized_score_train`` keeps the
                # in-sample number so the comparison card can show
                # train-vs-holdout side by side.
                if holdout_cases:
                    await _update(
                        run_doc,
                        progress_message="Re-scoring winner on held-out cases…",
                    )
                    winner_cfg = winner.get("config") or {}
                    try:
                        holdout_winner = await asyncio.wait_for(
                            _run_single_config(
                                candidate={
                                    "label": "holdout-winner",
                                    "model": winner_cfg.get("model") or baseline_model,
                                    "config_override": {
                                        k: v for k, v in winner_cfg.items() if k != "model"
                                    },
                                },
                                keys=keys,
                                test_cases=holdout_cases,
                                sys_config_doc=sys_config_doc,
                                field_metadata=field_metadata,
                                num_runs=num_runs,
                                judge_model=judge_model,
                                cross_field_rules=cross_field_rules,
                            ),
                            timeout=PER_TRIAL_TIMEOUT_SECONDS,
                        )
                        holdout_winner_score = _score_to_unit(holdout_winner.get("score"))
                        if holdout_winner_score is not None:
                            run_doc.optimized_score = holdout_winner_score
                    except Exception as e:
                        logger.warning("Holdout re-score (winner) failed: %s", e)

                    try:
                        holdout_default = await asyncio.wait_for(
                            _run_single_config(
                                candidate={
                                    "label": "holdout-default",
                                    "model": default_cfg.get("model") or baseline_model,
                                    "config_override": default_cfg or {},
                                },
                                keys=keys,
                                test_cases=holdout_cases,
                                sys_config_doc=sys_config_doc,
                                field_metadata=field_metadata,
                                num_runs=num_runs,
                                judge_model=judge_model,
                                cross_field_rules=cross_field_rules,
                            ),
                            timeout=PER_TRIAL_TIMEOUT_SECONDS,
                        )
                        run_doc.holdout_default_score = _score_to_unit(holdout_default.get("score"))
                    except Exception as e:
                        logger.warning("Holdout re-score (default) failed: %s", e)

                # Generate per-field + cross-field suggestions from the breakdown
                # + baselines + winner CF rule outcomes.
                run_doc.suggestions = _generate_suggestions(
                    field_breakdown=run_doc.field_breakdown,
                    baseline_no_tool=run_doc.baseline_no_tool_score,
                    baseline_default=run_doc.baseline_default_score,
                    optimized=run_doc.optimized_score,
                    cross_field_rule_breakdown=run_doc.winner_cross_field_rule_breakdown,
                )

                # Apply-preview rollup (Phase 2): per-field baseline-vs-winner
                # accuracy deltas so the Apply modal can disclose "K of N
                # fields will change, R regress" before the override flips.
                run_doc.apply_preview = _build_field_apply_preview(
                    winner_breakdown=run_doc.field_breakdown,
                    default_breakdown=list(default_result.get("field_breakdown") or []),
                    judge_variance=run_doc.judge_variance,
                )

        # Apply-on-finish: write best config to override — but ONLY when the
        # winner beat baseline by more than 2 × SE. Applying a config change
        # the data can't justify is exactly what the significance gate exists
        # to prevent.
        if (
            apply_on_finish
            and run_doc.best_config
            and not run_doc.tied_with_baseline
        ):
            await _apply_best(ss, run_doc)
            # Close the loop: re-validate the full test set with the applied
            # config so the completed-state UI can show "optimizer score → real
            # post-apply score" rather than asking the user to manually re-run.
            await run_post_apply_validation(
                run_doc=run_doc,
                search_set_uuid=search_set_uuid,
                user_id=user_id,
                source="apply_on_finish",
            )

        # --- Option A: put the headline on the certified score's scale ---
        # The official quality tile comes from the ValidationRun persisted by
        # ``persist_validation_run``, which discounts the score for small test
        # sets. The optimizer's raw scores carry no such discount, so on a small
        # set the card read HIGHER than the tile — and the moment apply kicked
        # off a certified validation, that gap looked like a regression. We now
        # apply the same discount here so "predicted" and "measured" live on one
        # scale.
        #
        # We mirror the certified path's *test-case* discount only: the certified
        # validation re-measures with >= 3 runs (see ``run_post_apply_validation``),
        # which clears the run-count factor, leaving test-case count as the binding
        # constraint. Discounting by the optimizer's own (smaller) num_runs would
        # over-penalize and just invert the mismatch. Per-trial measurement noise
        # is already accounted for separately by the judge-variance significance
        # gate (``tied_with_baseline``), so folding run count in here would
        # double-count it.
        #
        # This runs LAST, after winner selection + the significance gate, which
        # must compare raw scores — discounting ``baseline_default_score`` earlier
        # would corrupt ``tied_with_baseline``.
        from app.services.quality_service import _sample_size_factor
        _CERTIFIED_NUM_RUNS = 3  # run_post_apply_validation certifies with >= 3 runs
        n_cases = len(test_cases)
        ssf = _sample_size_factor(n_cases, _CERTIFIED_NUM_RUNS)
        run_doc.optimized_score = _discount_unit_score(run_doc.optimized_score, ssf)
        run_doc.optimized_score_train = _discount_unit_score(run_doc.optimized_score_train, ssf)
        run_doc.baseline_default_score = _discount_unit_score(run_doc.baseline_default_score, ssf)
        run_doc.baseline_no_tool_score = _discount_unit_score(run_doc.baseline_no_tool_score, ssf)
        run_doc.holdout_default_score = _discount_unit_score(run_doc.holdout_default_score, ssf)
        run_doc.score_sample_size = {
            "sample_size_factor": round(ssf, 3),
            "num_test_cases": n_cases,
            "num_runs": _CERTIFIED_NUM_RUNS,
            "test_cases_needed": max(0, 3 - n_cases),
        }

        run_doc.status = "completed"
        run_doc.phase = "done"
        run_doc.progress_message = "Optimization complete"
        run_doc.completed_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await run_doc.save()

        return run_doc

    except Exception as e:
        logger.exception("Optimization failed for %s", search_set_uuid)
        run_doc.status = "failed"
        run_doc.phase = "failed"
        run_doc.stopped_reason = "failed"
        run_doc.error_message = str(e)
        run_doc.completed_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await run_doc.save()
        return run_doc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _update(run_doc: ExtractionOptimizationRun, **fields: Any) -> None:
    for k, v in fields.items():
        setattr(run_doc, k, v)
    await run_doc.save()


async def _is_cancelled(run_doc: ExtractionOptimizationRun) -> bool:
    """Re-read the cancel flag from Mongo.

    The worker loads ``run_doc`` once at startup and reuses it for the whole
    run, but the Cancel endpoint writes ``cancel_requested`` on a *different*
    request — so the in-memory flag never flips on its own. Re-fetching the
    field each check is what makes Cancel actually take effect (mirrors the KB
    optimizer's per-trial re-fetch). We copy the fresh flag onto the in-memory
    doc so the subsequent ``_finalize_cancelled`` save stays consistent.
    """
    fresh = await ExtractionOptimizationRun.find_one(
        ExtractionOptimizationRun.uuid == run_doc.uuid,
    )
    if fresh and fresh.cancel_requested:
        run_doc.cancel_requested = True
        if fresh.cancel_requested_at and not run_doc.cancel_requested_at:
            run_doc.cancel_requested_at = fresh.cancel_requested_at
        return True
    return False


async def _abort_task(task: asyncio.Task) -> None:
    """Cancel a backgrounded config task and absorb whatever it raises.

    The underlying extraction may be parked in ``asyncio.to_thread`` whose
    OS thread can't be interrupted; cancelling here unblocks the awaiter and
    lets the worker proceed while that thread finishes and is discarded.
    """
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def _run_config_guarded(
    run_doc: ExtractionOptimizationRun,
    **single_config_kwargs: Any,
) -> dict:
    """Run one ``_run_single_config`` while staying cancel-responsive and bounded.

    Backgrounds the config and polls ``cancel_requested`` every
    ``CANCEL_POLL_INTERVAL_SECONDS`` so a UI cancel interrupts even a long
    in-flight config. Two early exits:

      * user cancel landed → raise ``_TrialCancelled`` (caller finalizes the run)
      * ``PER_TRIAL_TIMEOUT_SECONDS`` elapsed → raise ``TimeoutError`` (caller
        records a failed trial / fails the run)

    Otherwise returns the config result, re-raising any error it raised.
    """
    task: asyncio.Task[dict] = asyncio.ensure_future(_run_single_config(**single_config_kwargs))
    waited = 0.0
    while True:
        done, _pending = await asyncio.wait({task}, timeout=CANCEL_POLL_INTERVAL_SECONDS)
        if task in done:
            return task.result()
        waited += CANCEL_POLL_INTERVAL_SECONDS
        if await _is_cancelled(run_doc):
            await _abort_task(task)
            raise _TrialCancelled()
        if waited >= PER_TRIAL_TIMEOUT_SECONDS:
            await _abort_task(task)
            raise TimeoutError(
                f"Config exceeded the {int(PER_TRIAL_TIMEOUT_SECONDS)}s per-trial timeout"
            )


async def _finalize_cancelled(run_doc: ExtractionOptimizationRun) -> ExtractionOptimizationRun:
    run_doc.status = "cancelled"
    run_doc.phase = "cancelled"
    # Preserve a caller-set reason (e.g. the watchdog's "worker did not
    # respond"); otherwise use the default user-initiated message.
    if not run_doc.progress_message or not run_doc.progress_message.lower().startswith("cancel"):
        run_doc.progress_message = "Cancelled by user"
    run_doc.stopped_reason = "cancelled"
    run_doc.completed_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await run_doc.save()
    return run_doc


def _as_aware(dt: datetime.datetime | None) -> datetime.datetime | None:
    """Normalize to a tz-aware UTC datetime (Mongo round-trips can drop tzinfo)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _revoke_task(run_doc: ExtractionOptimizationRun) -> None:
    """Best-effort hard-kill of the run's Celery task.

    Mirrors ``workflow_service`` — ``revoke(terminate=True)`` kills the prefork
    child running this task id, or drops it from the queue if still pending.
    Cooperative cancel (the DB flag) remains the source of truth; this is the
    fallback for a worker too wedged to reach its next poll.
    """
    task_id = getattr(run_doc, "celery_task_id", None)
    if not task_id:
        return
    try:
        from app.celery_app import celery_app
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
    except Exception:
        logger.warning(
            "Failed to revoke Celery task %s for optimization run %s",
            task_id, run_doc.uuid, exc_info=True,
        )


async def reap_one(run_doc: ExtractionOptimizationRun | None) -> ExtractionOptimizationRun | None:
    """Recover a single orphaned run; no-op unless it's genuinely stuck.

    Two stuck shapes (items #3/#4 of the cancellation fix):

      * ``cancel_requested`` but no worker ever finalized it (dead worker) →
        once the grace window passes, revoke + finalize as cancelled.
      * running/queued well past the worker's hard time_limit (worker killed or
        crashed) → revoke + finalize as failed.

    Called opportunistically from the read endpoints so a forever-"Cancelling…"
    or forever-"Running…" run self-heals the next time the UI polls it. Returns
    the (possibly updated) run.
    """
    if run_doc is None or run_doc.status not in ("queued", "running"):
        return run_doc

    now = datetime.datetime.now(tz=datetime.timezone.utc)

    cancelled_at = _as_aware(getattr(run_doc, "cancel_requested_at", None))
    if run_doc.cancel_requested and cancelled_at is not None:
        if (now - cancelled_at).total_seconds() > CANCEL_REAP_GRACE_SECONDS:
            _revoke_task(run_doc)
            run_doc.progress_message = "Cancelled (the worker did not respond)."
            return await _finalize_cancelled(run_doc)

    started = _as_aware(run_doc.started_at)
    if started is not None and (now - started).total_seconds() > STALE_RUN_TIMEOUT_SECONDS:
        _revoke_task(run_doc)
        run_doc.status = "failed"
        run_doc.phase = "failed"
        run_doc.stopped_reason = "stale"
        run_doc.error_message = (
            "The optimization worker stopped responding (timed out or was "
            "killed). Start a new run to try again."
        )
        run_doc.completed_at = now
        await run_doc.save()

    return run_doc


async def reap_stale_runs(search_set_uuid: str) -> None:
    """Reap every orphaned run for a SearchSet.

    Called before starting a new run: the start endpoint 409s on any
    non-terminal run, so a dead run would otherwise block new runs forever.
    """
    runs = await ExtractionOptimizationRun.find(
        ExtractionOptimizationRun.search_set_uuid == search_set_uuid,
        {"status": {"$in": ["queued", "running"]}},
    ).to_list()
    for run in runs:
        await reap_one(run)


def _score_to_unit(score: float | None) -> float | None:
    """Tuning service returns scores 0..100; optimization run stores 0..1 for
    consistency with KB Autovalidate (so the same comparison-card UI works).
    """
    if score is None:
        return None
    return round(float(score) / 100.0, 4)


def _discount_unit_score(score: float | None, ssf: float) -> float | None:
    """Apply the certified ValidationRun's sample-size discount to a 0..1 score.

    Mirrors ``quality_service.persist_validation_run`` exactly, only in unit
    scale (its neutral midpoint of 50 is 0.5 here): pull the score toward 0.5 by
    ``(1 - ssf)``, but never *up* — a weak score is never inflated to look
    mediocre just because the sample was small. Returns the score unchanged when
    the sample already clears the discount (``ssf >= 1``) or is ``None``.
    """
    if score is None or ssf >= 1.0:
        return score
    blended = score * ssf + 0.5 * (1.0 - ssf)
    return round(min(score, blended), 4)


def _build_field_apply_preview(
    winner_breakdown: list[dict],
    default_breakdown: list[dict],
    *,
    judge_variance: float | None,
) -> dict | None:
    """Join winner + default per-field accuracy into an apply-preview rollup.

    For extraction, the natural "item" is a field — that's the granularity the
    user already thinks in (field-level definitions, field-level config
    overrides). We compare per-field accuracy (0..1) between the default
    config and the winning config so the Apply modal can disclose
    "K of N fields will change, R regress" before the override flips.
    """
    if not winner_breakdown and not default_breakdown:
        return None
    def_by_field = {b.get("field"): b for b in default_breakdown if b.get("field")}
    items: list[dict] = []
    for w in winner_breakdown:
        fname = w.get("field")
        if not fname:
            continue
        d = def_by_field.get(fname) or {}
        items.append({
            "item_id": fname,
            "label": fname,
            "baseline": float(d.get("accuracy", 0.0) or 0.0),
            "winner": float(w.get("accuracy", 0.0) or 0.0),
        })
    if not items:
        return None
    return build_apply_preview(items, judge_variance=judge_variance)


def _trial_config_for_run(result: dict) -> dict:
    """Project a tuning result into the per-trial config shape the UI consumes."""
    cfg = dict(result.get("config_override") or {})
    cfg["model"] = result.get("model")
    return cfg


def _to_trial_summary(result: dict, baseline_default_score: float | None) -> dict:
    """Normalize a tuning result into the trial-doc shape used by the run.

    Matches KB's per-trial shape so the shared TrialsTable can render it:
    {trial_id, config, score, lift_vs_default, tokens_used, status,
     duration_seconds, started_at, cross_field_summary}.
    """
    score_unit = _score_to_unit(result.get("score"))
    lift = None
    if score_unit is not None and baseline_default_score is not None:
        lift = round(score_unit - baseline_default_score, 4)

    status = "failed" if result.get("error") else "completed"
    cfg = _trial_config_for_run(result)

    return {
        "trial_id": result.get("label", ""),
        "config": cfg,
        "score": score_unit,
        "accuracy": result.get("accuracy"),
        "consistency": result.get("consistency"),
        "lift_vs_default": lift,
        # Real judge-token count from this trial (zero when the judge is off).
        # Sums up at run level into ``run_doc.tokens_used`` for the progress bar.
        "tokens_used": int(result.get("judge_tokens", 0) or 0),
        "status": status,
        "duration_seconds": result.get("elapsed_seconds"),
        "error": result.get("error"),
        # Cross-field rule outcome aggregate ({pass, fail, unparseable,
        # pass_rate, ...}). Null when no rules are configured. Surfaces in the
        # trials table so the user can see how each config compares on rules,
        # not just on accuracy.
        "cross_field_summary": result.get("cross_field_summary"),
        # Needed by the variance-aware winner selector to compute SE of the
        # trial-score mean: SE = σ / √N_items.
        "total_comparisons": int(result.get("total_comparisons", 0) or 0),
    }


def _aggregate_cf_results_by_rule(cf_results: list[dict]) -> list[dict]:
    """Group flat cross-field results by rule into per-rule pass/fail counts.

    The tuning service emits one cross_field result per (test_case × run × rule).
    For user-facing display and suggestions we want one row per rule with
    aggregate counts. ``unparseable`` is shown but excluded from the
    denominator of pass_rate (matches ``summarize_results`` policy).
    """
    bucket: dict[str, dict] = {}
    for r in cf_results or []:
        rule = r.get("rule") or {}
        rid = (
            r.get("rule_id")
            or rule.get("id")
            or f"{rule.get('type', '')}::{rule.get('label', '')}"
        )
        slot = bucket.setdefault(rid, {
            "rule_id": rid,
            "type": rule.get("type"),
            "label": rule.get("label") or rule.get("description") or "",
            "pass": 0,
            "fail": 0,
            "unparseable": 0,
        })
        status = r.get("status", "unparseable")
        if status in ("pass", "fail", "unparseable"):
            slot[status] += 1
    rows: list[dict] = []
    for slot in bucket.values():
        decisive = slot["pass"] + slot["fail"]
        slot["pass_rate"] = (slot["pass"] / decisive) if decisive > 0 else None
        rows.append(slot)
    # Worst-first so "rules to look at" surfaces the most violated rules first.
    rows.sort(key=lambda s: (s["pass_rate"] if s["pass_rate"] is not None else 1.0, -s["fail"]))
    return rows


async def _apply_best(ss: SearchSet | None, run_doc: ExtractionOptimizationRun) -> None:
    if ss is None or not run_doc.best_config:
        return
    run_doc.previous_override = ss.extraction_config_override
    ss.extraction_config_override = run_doc.best_config
    ss.extraction_config_override_set_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await ss.save()


async def _tighten_variance_with_top_trials(
    *,
    run_doc: ExtractionOptimizationRun,
    top_trials: list[dict],
    raw_by_label: dict[str, dict],
    judge_model: str,
) -> None:
    """Re-sample judge variance against the top-K trials' outputs; if any
    individual σ exceeds the baseline σ already on the run, raise judge_variance
    to the larger value and record which trial produced it.

    Baseline σ is sampled on the default config (see the baselines block of
    ``run_optimization``). Top-trial σ catches the case where the winning
    config emits more boundary-band values that the judge handles less
    confidently. Taking the max keeps the significance gate conservative.

    Failures are swallowed — the existing baseline σ is still usable; this is
    only meant to tighten it, not to be load-bearing.
    """
    try:
        from app.services.judge_variance import (
            DEFAULT_VARIANCE_SAMPLES,
            sample_judge_variance,
        )
        from app.services.extraction_judge import judge_field_value

        async def _rejudge(sample: dict) -> tuple[float, int]:
            v = await judge_field_value(
                field_name=sample["field_name"],
                expected=sample["expected"],
                actual=sample["actual"],
                model_name=judge_model,
                field_metadata=sample.get("field_metadata"),
            )
            return float(v["score"]), int(v.get("tokens_used", 0) or 0)

        for trial in top_trials:
            raw = raw_by_label.get(trial.get("trial_id", "")) or {}
            samples = [
                s for s in (raw.get("judge_samples") or [])
                if s.get("comparator", "llm") not in ("deterministic", "llm_error")
            ]
            if len(samples) < 2:
                continue
            variance, tokens = await sample_judge_variance(
                samples=samples,
                judge_fn=_rejudge,
                original_score=lambda s: float(s["score"]),
                max_samples=DEFAULT_VARIANCE_SAMPLES,
            )
            run_doc.tokens_used += int(tokens or 0)
            if variance is not None and (
                run_doc.judge_variance is None or variance > run_doc.judge_variance
            ):
                run_doc.judge_variance = variance
        await run_doc.save()
    except Exception as e:
        logger.warning(
            "Top-trial variance resampling failed for run %s: %s",
            run_doc.uuid, e,
        )


async def run_post_apply_validation(
    *,
    run_doc: ExtractionOptimizationRun,
    search_set_uuid: str,
    user_id: str,
    source: str,
    num_runs: int = 3,
) -> None:
    """Re-validate the test set with the freshly-applied config and persist a
    snapshot on ``run_doc.post_apply_validation``.

    This is the loop closure that lets the user trust the tuner without ever
    touching the standalone validation panel. ``run_validation`` already
    inserts the *authoritative* ``ValidationRun`` (the unified 0..100 score
    with the low-sample-size discount applied) and updates the item's official
    quality tier — so after this runs, the optimizer card and the quality tile
    are reading the same measurement. We mirror that certified number onto the
    run doc (converted to the 0..1 unit scale the panel's baselines use) rather
    than the raw accuracy we used to store, so the two surfaces never disagree.

    Defaults to ``num_runs=3`` so the certified score isn't dragged down by the
    sample-size penalty (which only fully clears at 3 runs); a 1-run check would
    look artificially worse than the optimizer's own headline.

    Failures are logged and swallowed — apply already succeeded; the delta
    is a nice-to-have, not a precondition for the run being valid.
    """
    try:
        from app.services.extraction_validation_service import run_validation
        result = await run_validation(
            search_set_uuid=search_set_uuid,
            user_id=user_id,
            num_runs=num_runs,
        )
        # ``score``/``score_breakdown``/``quality_tier`` are stamped onto the
        # result by run_validation from the authoritative ValidationRun it just
        # persisted. ``score`` is 0..100; the panel works in 0..1, so divide.
        breakdown = result.get("score_breakdown") or {}
        certified_pct = result.get("score")
        raw_pct = breakdown.get("raw_score", certified_pct)
        run_doc.post_apply_validation = {
            "accuracy": result.get("aggregate_accuracy"),
            "consistency": result.get("aggregate_consistency"),
            "cross_field_pass_rate": result.get("cross_field_score"),
            # Authoritative, sample-size–penalized score (0..1 unit) — identical
            # to the official quality tile so the two surfaces never disagree.
            "score": (
                certified_pct / 100.0 if certified_pct is not None
                else result.get("aggregate_accuracy")
            ),
            # Un-penalized score (0..1 unit). The optimizer's headline carries no
            # sample-size penalty, so the delta-vs-optimizer comparison uses this
            # to stay apples-to-apples; the penalty is disclosed separately.
            "raw_score": (raw_pct / 100.0) if raw_pct is not None else None,
            "score_breakdown": breakdown or None,
            "quality_tier": result.get("quality_tier"),
            "num_runs": num_runs,
            "test_case_count": len(result.get("test_cases") or []),
            "ran_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            "source": source,
        }
        await run_doc.save()
    except Exception as e:
        logger.warning("Post-apply validation failed for run %s: %s", run_doc.uuid, e)


async def get_active_run(search_set_uuid: str) -> ExtractionOptimizationRun | None:
    """Return the most-recent non-terminal run for this SearchSet, if any.

    Used by the UI on mount to detect "is something already running?" so it
    can polling-resume rather than start a fresh one.
    """
    return await ExtractionOptimizationRun.find_one(
        {
            "search_set_uuid": search_set_uuid,
            "status": {"$in": ["queued", "running"]},
        },
        sort=[("started_at", -1)],
    )


# ---------------------------------------------------------------------------
# Recommendations engine
#
# Generates actionable per-field suggestions from the winning trial's
# field_breakdown plus the run-level baselines. Each suggestion has the same
# shape as KB's data_source_suggestions so the shared SuggestionsList renders
# them without per-domain branching.
# ---------------------------------------------------------------------------


# Accuracy below this in the winning config means the optimizer couldn't
# reliably extract the field — the user needs to rewrite the field's
# definition or add hints, not just tune the engine knobs.
WEAK_FIELD_ACCURACY_THRESHOLD = 0.5

# Consistency below this means the field is unstable across runs — adding
# few-shot examples or pinning the model temperature would help.
UNSTABLE_FIELD_CONSISTENCY_THRESHOLD = 0.6

# Workflow shortcut: when the no-tool baseline ≈ the optimized score, the
# extraction tool isn't earning its complexity. Surface this only when both
# scores are decent enough that the user might consider simplifying.
REDUNDANT_TOOL_LIFT_THRESHOLD = 0.05
REDUNDANT_TOOL_MIN_SCORE = 0.7

# Cross-field rule fail-rate cutoffs for suggestions on the winning config.
# A rule that fails the majority of decisive evaluations is "critical"; a
# rule that fails between WARN and CRIT thresholds is a "warning". Below
# WARN we don't emit a suggestion — a single fail on a noisy field would
# otherwise generate alarm fatigue.
CROSS_FIELD_RULE_WARN_FAIL_RATE = 0.34
CROSS_FIELD_RULE_CRIT_FAIL_RATE = 0.5


def _generate_suggestions(
    *,
    field_breakdown: list[dict],
    baseline_no_tool: float | None,
    baseline_default: float | None,
    optimized: float | None,
    cross_field_rule_breakdown: list[dict] | None = None,
) -> list[dict]:
    """Produce ranked suggestion dicts for the run.

    Shape mirrors KB's data_source_suggestions for shared-component reuse:
        {kind, severity, message, [field]}

    Each suggestion is independent — the UI renders them in order. Critical
    first, then warnings, then info.

    ``cross_field_rule_breakdown`` carries per-rule pass/fail counts on the
    *winning* config — used to surface "rule X failed on 4/6 cases with the
    chosen config" so the user knows whether to revisit the rule or the
    underlying extraction quality on the involved fields.
    """
    suggestions: list[dict] = []

    for field in field_breakdown:
        name = field.get("field", "")
        accuracy = field.get("accuracy")
        consistency = field.get("consistency")
        if not name or accuracy is None:
            continue

        if accuracy < WEAK_FIELD_ACCURACY_THRESHOLD:
            suggestions.append({
                "kind": "weak_field",
                "severity": "critical" if accuracy < 0.3 else "warning",
                "field": name,
                "message": (
                    f'Field "{name}" was only right {int(accuracy * 100)}% of the time, even with '
                    "the best settings we tried. Try rewriting its description to be more specific, "
                    "adding example values, or marking it optional if it isn't always present."
                ),
            })
            continue  # Weak fields skip the unstable check (the priority signal is accuracy)

        if consistency is not None and consistency < UNSTABLE_FIELD_CONSISTENCY_THRESHOLD:
            suggestions.append({
                "kind": "unstable_field",
                "severity": "warning",
                "field": name,
                "message": (
                    f'Field "{name}" gave different answers on different runs '
                    f"(matched only {int(consistency * 100)}% of the time). Adding 1–2 example "
                    "values to its description usually helps the AI pick the same answer each time."
                ),
            })

    # Run-level: is the extraction tool earning its complexity?
    if (
        baseline_no_tool is not None
        and optimized is not None
        and optimized >= REDUNDANT_TOOL_MIN_SCORE
        and (optimized - baseline_no_tool) < REDUNDANT_TOOL_LIFT_THRESHOLD
    ):
        suggestions.append({
            "kind": "redundant_tool",
            "severity": "info",
            "message": (
                f"Even with no custom settings at all, the AI already scored "
                f"{int(baseline_no_tool * 100)}% — about the same as the optimized "
                f"settings ({int(optimized * 100)}%). For this kind of data, you may not "
                "need to fine-tune these settings."
            ),
        })

    # Run-level: did the optimizer actually beat the user's existing config?
    if (
        baseline_default is not None
        and optimized is not None
        and (optimized - baseline_default) < 0.02
        and baseline_default >= 0.7
    ):
        suggestions.append({
            "kind": "already_good",
            "severity": "info",
            "message": (
                f"Your current settings already scored {int(baseline_default * 100)}% — "
                "the optimizer barely found anything to improve. Your settings are in good shape."
            ),
        })

    # Cross-field rule failures on the winning config. A failing rule means
    # either (a) extraction is wrong on a related field — fixable by tuning or
    # re-prompting — or (b) the rule itself is wrong (false-positive). Both
    # are worth surfacing. Threshold: a rule that fails the majority of
    # decisive evaluations is critical; minority-fail is a warning.
    for rule_row in (cross_field_rule_breakdown or []):
        fail = int(rule_row.get("fail", 0) or 0)
        pass_ = int(rule_row.get("pass", 0) or 0)
        decisive = pass_ + fail
        if decisive == 0 or fail == 0:
            continue
        fail_rate = fail / decisive
        if fail_rate < CROSS_FIELD_RULE_WARN_FAIL_RATE:
            continue
        # Prefer the rule's label/type for display; fall back to type alone.
        rule_label = rule_row.get("label") or rule_row.get("type") or "rule"
        suggestions.append({
            "kind": "cross_field_rule",
            "severity": "critical" if fail_rate >= CROSS_FIELD_RULE_CRIT_FAIL_RATE else "warning",
            "rule_id": rule_row.get("rule_id"),
            "rule_type": rule_row.get("type"),
            "message": (
                f'Cross-field rule "{rule_label}" failed on {fail} of {decisive} '
                f"evaluation{'' if decisive == 1 else 's'} with the chosen config. "
                "Check whether the rule still describes your data correctly, or "
                "whether the involved fields need to be improved."
            ),
        })

    # Stable ordering: critical → warning → info; preserve insertion order within tier.
    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    suggestions.sort(key=lambda s: severity_rank.get(s.get("severity", "info"), 99))
    return suggestions
