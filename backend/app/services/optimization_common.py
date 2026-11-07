"""Shared winner-selection logic for the autovalidate optimizers.

KB, extraction, and workflow optimizers all need to pick a defensible winner
from a list of trial dicts respecting judge noise. The math is identical; only
the per-domain bits (which fields make a config "default", which trial
statuses count as completed) vary. Callers inject those via a distance
callback.

Key statistical choice: tie-band uses **SE = σ/√N**, not raw σ. Trial scores
are means over N test items, so the standard error of the trial-score mean is
σ/√N (tighter than σ for any N>1). Using raw σ inflates the tie cluster and
under-selects clear winners — the exact failure mode we want to avoid.
"""

from __future__ import annotations

from typing import Callable

# 2σ ≈ 95% one-sided confidence; trials within that of the top score are
# statistically indistinguishable from the leader given judge noise.
WINNER_TIE_SIGMAS = 2.0

# Fallback noise floor (on the 0..1 score scale) when judge variance couldn't
# be measured (n<2 variance samples). 0.02 ≈ "2 pts on a 0..100 score" —
# conservatively wide so we don't crown winners on noise we never quantified.
DEFAULT_JUDGE_NOISE_FLOOR = 0.02


def tie_band(
    judge_variance: float | None,
    n_items_for_se: int,
    fallback_noise_floor: float = DEFAULT_JUDGE_NOISE_FLOOR,
) -> float:
    """How close two scores must be to count as the same: ``2 × SE``, SE = σ/√N."""
    sigma = judge_variance if judge_variance is not None else fallback_noise_floor
    se = sigma / max(1, n_items_for_se) ** 0.5 if n_items_for_se else sigma
    return WINNER_TIE_SIGMAS * se


# The paired test needs this many queries before its verdict counts (the
# comparison card's MIN_N_FOR_SIGNIFICANCE).
MIN_N_FOR_LIFT_CI = 5


def reported_baseline_score(
    *,
    holdout_optimized_score: float | None,
    holdout_default_score: float | None,
    baseline_default_score: float | None,
) -> float | None:
    """The current-settings score a run's headline is compared against.

    When the winner was re-scored on held-out cases, the headline is that
    held-out score, so the current settings must be the held-out score too.
    Paired with the training-case baseline instead, the editor showed
    Optimized 95% against Current 93% (a gap measured on different cases)
    and chat, the gate and the card each read the gap differently. Falls
    back to the training baseline when the held-out pair is incomplete.
    """
    if holdout_optimized_score is not None and holdout_default_score is not None:
        return holdout_default_score
    return baseline_default_score


def tied_on_reported_scores(
    *,
    tied: bool,
    optimized_score: float | None,
    baseline_score: float | None,
    band: float,
    lift_ci: dict | None = None,
) -> bool:
    """Whether the result a run reports is within noise of the current settings.

    ``pick_winner_variance_aware`` decides the tie on the winning trial's
    training score. The run then reports a different number: the winner
    re-scored on held-out cases, which drops when part of the training lead
    was best-of-N luck. Chat read the flag and called 94% against 92% "a
    real, if modest, gain", while the editor's card, looking at those same two
    numbers, said the +2 pts were inside the judge's noise. One verdict has to
    cover the numbers shown, so the tie is checked again on them: the
    reported lift must clear the same band, and, when a paired test ran on
    enough queries, that test must call it significant.
    """
    if tied:
        return True
    if (
        optimized_score is not None
        and baseline_score is not None
        and abs(optimized_score - baseline_score) <= band
    ):
        return True
    if lift_ci and (lift_ci.get("n_queries") or 0) >= MIN_N_FOR_LIFT_CI:
        lower, upper = lift_ci.get("lower"), lift_ci.get("upper")
        p_value = lift_ci.get("p_value")
        if lower is not None and upper is not None and p_value is not None:
            significant = (lower > 0 or upper < 0) and p_value < 0.05
            if not significant:
                return True
    return False


def pick_winner_variance_aware(
    trials: list[dict],
    *,
    judge_variance: float | None,
    baseline_default_score: float | None,
    distance_from_default: Callable[[dict], int],
    n_items_for_se: int,
    completed_statuses: tuple[str, ...] = ("completed",),
    fallback_noise_floor: float = DEFAULT_JUDGE_NOISE_FLOOR,
) -> tuple[dict | None, str, bool, int]:
    """Pick a defensible winner from ``trials`` respecting judge noise.

    Returns ``(winner_trial, reason, tied_with_baseline, cluster_size)``.
    ``cluster_size`` is the number of trials within ``2 × SE`` of the top
    score — a diagnostic some domains persist ("3 configs were statistically
    tied"). 0 when there are no completed trials.

    Algorithm:
      1. Filter to trials with status in ``completed_statuses`` and a score.
      2. SE of trial-score mean = σ / √N_items.
      3. Tie cluster = trials within ``2 × SE`` of the top score.
      4. If ``baseline_default_score`` is within ``2 × SE`` of top, declare
         ``tied_with_baseline=True``. Return the cluster member closest to
         default — apply should be suppressed by the caller, but the reported
         winner is still the gentlest config change.
      5. Otherwise pick the cluster member with the smallest
         ``distance_from_default`` (Occam: fewer knobs flipped = less surface
         for downstream surprises). Ties broken by raw score, then trial_id.

    ``distance_from_default`` receives the whole trial dict so callers can
    extract whatever shape their config takes (KB compares against hard-coded
    RAGConfig defaults; extraction compares against a default cfg dict;
    workflow looks inside ``config.step_overrides``).
    """
    completed = [
        t for t in trials
        if t.get("status") in completed_statuses
        and t.get("score") is not None
    ]
    if not completed:
        return (None, "no_completed_trials", False, 0)

    completed.sort(key=lambda t: (-float(t["score"]), str(t.get("trial_id", ""))))
    top_score = float(completed[0]["score"])

    band = tie_band(judge_variance, n_items_for_se, fallback_noise_floor)

    tied_with_baseline = (
        baseline_default_score is not None
        and abs(top_score - baseline_default_score) <= band
    )

    cluster = [t for t in completed if float(t["score"]) >= top_score - band]
    cluster_size = len(cluster)

    if tied_with_baseline:
        cluster.sort(key=lambda t: (
            distance_from_default(t),
            -float(t["score"]),
            str(t.get("trial_id", "")),
        ))
        return (cluster[0], "tied_with_baseline", True, cluster_size)

    if cluster_size == 1:
        return (cluster[0], "highest_score", False, 1)

    cluster.sort(key=lambda t: (
        distance_from_default(t),
        -float(t["score"]),
        str(t.get("trial_id", "")),
    ))
    return (cluster[0], "closest_to_default", False, cluster_size)


# ---------------------------------------------------------------------------
# Apply preview — Phase 2 of loop closure.
#
# Every optimizer "Apply" gesture currently lands as a leap of faith: the user
# sees the headline lift but not which items the new config will change, how
# many regress, or whether any regression exceeds judge noise. This helper
# computes a uniform per-item preview that all three optimizer surfaces can
# render in a confirmation modal before the actual mutation lands.
#
# The shape is the same across surfaces — the only thing that varies is what
# an "item" is (per-query for KB, per-test-case for extraction, per-step for
# workflow). Callers convert their per-item baseline/winner score pairs into
# the generic ``ApplyPreviewItem`` shape and this helper produces the rollup.
# ---------------------------------------------------------------------------


# Below this delta we consider the item "unchanged" — within judge noise on
# either direction. Matches the per-query indifference band the optimizers
# already use when classifying improved/regressed/unchanged counters.
APPLY_PREVIEW_EPSILON = 0.05


def build_apply_preview(
    items: list[dict],
    *,
    judge_variance: float | None,
) -> dict:
    """Roll a list of per-item {item_id, label, baseline, winner} dicts into
    an apply-preview document.

    Each input item must carry ``baseline`` and ``winner`` floats on the 0..1
    scale. ``label`` is optional (shown verbatim in the UI when present).
    ``item_id`` is opaque to this helper but persisted so the UI can deep-link
    rows to the underlying trace.

    Returned shape:
    ```
    {
      "total": int, "will_change": int,
      "improvements": int, "regressions": int,
      "significant_regressions": int,    # |delta| > 2σ on the down side
      "net_delta": float,                # mean(winner - baseline) over items
      "noise_sigma": float | None,
      "items": [
        {item_id, label, baseline, winner, delta, within_noise,
         is_regression, significant}, ...
      ],
    }
    ```

    Callers persist this as ``apply_preview`` on their optimization run model
    and the shared ``<ApplyPreviewModal>`` renders the rollup before commit.
    """
    sigma = judge_variance if judge_variance is not None else DEFAULT_JUDGE_NOISE_FLOOR
    band = WINNER_TIE_SIGMAS * sigma
    enriched: list[dict] = []
    deltas: list[float] = []
    will_change = improvements = regressions = significant_regressions = 0
    for raw in items:
        baseline = float(raw.get("baseline", 0.0) or 0.0)
        winner = float(raw.get("winner", 0.0) or 0.0)
        delta = winner - baseline
        within_noise = abs(delta) < APPLY_PREVIEW_EPSILON
        is_regression = delta < 0 and not within_noise
        significant = abs(delta) > band
        if not within_noise:
            will_change += 1
            if delta > 0:
                improvements += 1
            else:
                regressions += 1
                if significant:
                    significant_regressions += 1
        deltas.append(delta)
        enriched.append({
            "item_id": raw.get("item_id"),
            "label": raw.get("label"),
            "baseline": round(baseline, 4),
            "winner": round(winner, 4),
            "delta": round(delta, 4),
            "within_noise": within_noise,
            "is_regression": is_regression,
            "significant": significant,
        })
    net = sum(deltas) / len(deltas) if deltas else 0.0
    return {
        "total": len(enriched),
        "will_change": will_change,
        "improvements": improvements,
        "regressions": regressions,
        "significant_regressions": significant_regressions,
        "net_delta": round(net, 4),
        "noise_sigma": sigma,
        "items": enriched,
    }
