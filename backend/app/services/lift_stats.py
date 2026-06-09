"""Paired-bootstrap CI + permutation p-value for autovalidate lift readouts.

The optimizer's "+13 pts vs default" headline is the difference of two means
computed over the same N test queries (paired). Treating the two arms as
independent samples (e.g. ``2σ`` of judge-replay noise as in the legacy
QualityComparisonCard) overstates uncertainty and ignores the per-query
correlation — the only honest CI here uses paired resampling.

We keep the math dependency-free (no numpy) so this can run inside the Celery
worker without pulling extra wheels into the container.
"""

from __future__ import annotations

import math
import random
from typing import Iterable


def paired_lift_bootstrap_ci(
    paired: list[tuple[float, float]],
    *,
    confidence: float = 0.95,
    iterations: int = 2000,
    rng_seed: int | None = None,
) -> dict | None:
    """Compute a paired-bootstrap CI and permutation p-value on the lift.

    Args:
        paired: list of ``(baseline_score, optimized_score)`` tuples — one per
            query, scored on the same eval set with the same judge.
        confidence: two-sided confidence level (default 0.95).
        iterations: bootstrap resamples + permutations to run (default 2000).
        rng_seed: optional seed for reproducibility.

    Returns:
        ``{lift, lower, upper, p_value, n_queries, n_iterations, method,
        confidence_level}`` or ``None`` when n < 2 (no CI is meaningful).
    """
    if len(paired) < 2:
        return None

    rng = random.Random(rng_seed)
    deltas = [opt - base for base, opt in paired]
    n = len(deltas)
    observed_lift = sum(deltas) / n

    # --- Bootstrap CI on the mean lift ---
    boot_means: list[float] = []
    for _ in range(iterations):
        sample = [deltas[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    alpha = (1.0 - confidence) / 2.0
    lower = boot_means[int(alpha * iterations)]
    upper = boot_means[min(iterations - 1, int((1.0 - alpha) * iterations))]

    # --- Permutation test: how often would we see a |lift| at least this big
    # if the assignment of "baseline vs optimized" were random per query? ---
    # Per-query sign flip is the natural paired permutation under the null
    # "no difference between configs" — flip the sign of each delta with
    # probability 0.5 and recompute the mean.
    extreme = 0
    abs_observed = abs(observed_lift)
    for _ in range(iterations):
        sign_flipped_sum = 0.0
        for d in deltas:
            sign_flipped_sum += d if rng.random() >= 0.5 else -d
        if abs(sign_flipped_sum / n) >= abs_observed:
            extreme += 1
    # Add-one smoothing so we never report a literal 0 p-value from a finite
    # number of permutations (the truth is "p < 1/iterations").
    p_value = (extreme + 1) / (iterations + 1)

    return {
        "lift": round(observed_lift, 4),
        "lower": round(lower, 4),
        "upper": round(upper, 4),
        "p_value": round(p_value, 4),
        "n_queries": n,
        "n_iterations": iterations,
        "method": "paired_bootstrap",
        "confidence_level": confidence,
    }


def per_query_delta_summary(
    paired: Iterable[tuple[float, float]],
    *,
    epsilon: float = 0.01,
) -> dict:
    """Count improved / regressed / unchanged from per-query (base, opt) pairs.

    ``epsilon`` is the indifference band — deltas within ±epsilon are treated
    as unchanged so noise-floor flips don't dominate the readout. 0.01 means
    "1 point or less on a 0..1 score". Tune per domain if needed.
    """
    improved = regressed = unchanged = 0
    for base, opt in paired:
        d = opt - base
        if d > epsilon:
            improved += 1
        elif d < -epsilon:
            regressed += 1
        else:
            unchanged += 1
    return {
        "improved": improved,
        "regressed": regressed,
        "unchanged": unchanged,
        "epsilon": epsilon,
    }


def paired_signed_rank_p_value(deltas: list[float]) -> float | None:
    """Wilcoxon signed-rank approximation — kept here for completeness.

    Not currently called by the optimizer (we use the permutation test in
    ``paired_lift_bootstrap_ci`` instead) but useful for offline analysis or
    callers that want a non-parametric paired test without bootstrapping.
    """
    nonzero = [d for d in deltas if d != 0.0]
    n = len(nonzero)
    if n < 6:
        return None
    abs_vals = sorted((abs(d), 1 if d > 0 else -1) for d in nonzero)
    # Assign ranks with mid-rank for ties.
    ranks: list[float] = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs_vals[j + 1][0] == abs_vals[i][0]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    w_pos = sum(r for r, (_, s) in zip(ranks, abs_vals) if s > 0)
    w_neg = sum(r for r, (_, s) in zip(ranks, abs_vals) if s < 0)
    w = min(w_pos, w_neg)
    mean = n * (n + 1) / 4.0
    sd = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sd == 0:
        return None
    z = (w - mean) / sd
    # Two-sided normal-approx p-value.
    return round(2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0)))), 4)
