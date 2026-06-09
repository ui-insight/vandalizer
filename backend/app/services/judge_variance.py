"""Judge variance sampler — measures nondeterminism in LLM-judge scores.

Used by autovalidate runs to compute a confidence interval on lift readouts.
Without it, a "+3 pts" win could be entirely judge noise; with it, the UI can
flag "no significant change" when the lift is inside the noise floor.

Shared across KB / extraction / workflow optimizers. Each domain provides:
* a list of pre-judged samples (the optimizer's existing judge call results)
* a judge callable that re-evaluates one sample
* a uuid extractor so the caller can later say "σ was sampled on Q3 and Q7"

The sampler picks up to ``max_samples`` items, re-runs the judge once each,
and returns the stddev of the delta between original and replay scores.

Sampling strategy matters: judge variance is heteroscedastic. Items with
clean PASS (1.0) or clean FAIL (0.0) scores wobble much less than boundary-
region items in the PARTIAL band (0.4–0.7). To get a noise-floor estimate
that reflects where optimizer decisions actually happen, callers should bias
the sample toward boundary items via ``select_boundary_samples``.
"""

from dataclasses import dataclass, field
from typing import Awaitable, Callable, TypeVar

S = TypeVar("S")

# Default n for variance re-judging. n=5 gives sample-stddev 4 degrees of
# freedom — wide CI on σ but enough that downstream significance tests aren't
# operating on a single point measurement. Token cost: ~5 extra judge calls
# per run, which fits in all autovalidate budget tiers.
DEFAULT_VARIANCE_SAMPLES = 5

# PARTIAL band: judge scores in this range are where wobble lives. Boundary-
# bias sampling prefers items in this band, falling back to the closest
# scores when too few boundary items exist.
PARTIAL_BAND = (0.4, 0.7)


def select_boundary_samples(
    samples: list[S],
    score_of: Callable[[S], float],
    max_samples: int = DEFAULT_VARIANCE_SAMPLES,
    band: tuple[float, float] = PARTIAL_BAND,
) -> list[S]:
    """Return up to ``max_samples`` items biased toward the PARTIAL band.

    Strategy: take items inside ``band`` first (sorted by distance to the
    band midpoint, so the most-ambiguous come first); if still short, fill
    from outside the band, sorted by *distance to* the band — items just
    outside come before clean PASSes/FAILs.

    Rationale: judge σ at score=1.0 is near zero, at score=0.5 is meaningful.
    Sampling uniformly underestimates σ in the regime that drives winner
    selection.
    """
    if not samples:
        return []
    lo, hi = band
    mid = (lo + hi) / 2.0

    def dist_to_mid(s: S) -> float:
        return abs(score_of(s) - mid)

    def dist_to_band(s: S) -> float:
        sc = score_of(s)
        if lo <= sc <= hi:
            return 0.0
        return min(abs(sc - lo), abs(sc - hi))

    in_band = [s for s in samples if lo <= score_of(s) <= hi]
    out_band = [s for s in samples if not (lo <= score_of(s) <= hi)]
    in_band.sort(key=dist_to_mid)
    out_band.sort(key=dist_to_band)

    return (in_band + out_band)[:max_samples]


@dataclass
class JudgeVarianceResult:
    """Richer return shape that exposes the sample size + which queries were
    sampled, so UIs can render "σ from n=2 re-judgements on Q3, Q7" instead
    of a bare ±X with no provenance."""

    sigma: float | None
    n: int
    sampled_query_uuids: list[str] = field(default_factory=list)
    tokens_used: int = 0


async def sample_judge_variance_detailed(
    samples: list[S],
    judge_fn: Callable[[S], Awaitable[tuple[float, int]]],
    original_score: Callable[[S], float],
    sample_uuid: Callable[[S], str] | None = None,
    max_samples: int = DEFAULT_VARIANCE_SAMPLES,
    sample_selector: Callable[[list[S], Callable[[S], float], int], list[S]] | None = None,
) -> JudgeVarianceResult:
    """Re-judge a small sample to estimate judge nondeterminism (detailed).

    Returns provenance: n and the list of query_uuids sampled.

    Math: collects signed deltas ``replay - original`` (preserving sign so the
    stddev isn't folded around zero) and computes the sample stddev with the
    unbiased ``n-1`` denominator.

    ``sample_selector`` defaults to ``select_boundary_samples`` (boundary-band
    bias). Pass a different selector for domains where boundary bias doesn't
    apply (e.g. binary PASS/FAIL workflow checks where every score is 0 or 1).
    """
    if len(samples) < 2:
        return JudgeVarianceResult(sigma=None, n=0)

    if sample_selector is None:
        sample_subset = select_boundary_samples(samples, original_score, max_samples)
    else:
        sample_subset = sample_selector(samples, original_score, max_samples)
    if len(sample_subset) < 2:
        # Selector returned too few — fall back to prefix slice so we still
        # produce *some* estimate rather than collapsing to None.
        sample_subset = list(samples[:max_samples])
    deltas: list[float] = []
    sampled_uuids: list[str] = []
    tokens_used = 0
    for s in sample_subset:
        try:
            replay_score, replay_tokens = await judge_fn(s)
            deltas.append(replay_score - original_score(s))
            tokens_used += max(0, int(replay_tokens))
            if sample_uuid is not None:
                try:
                    uid = sample_uuid(s)
                    if uid:
                        sampled_uuids.append(uid)
                except Exception:
                    pass
        except Exception:
            continue

    if len(deltas) < 2:
        return JudgeVarianceResult(
            sigma=None, n=len(deltas), sampled_query_uuids=sampled_uuids,
            tokens_used=tokens_used,
        )

    mean = sum(deltas) / len(deltas)
    # Sample stddev (Bessel-corrected, n-1 denominator) — unbiased estimator
    # of population variance, which matters at the n=2..6 sizes we run here.
    variance = sum((x - mean) ** 2 for x in deltas) / (len(deltas) - 1)
    return JudgeVarianceResult(
        sigma=round(variance ** 0.5, 4),
        n=len(deltas),
        sampled_query_uuids=sampled_uuids,
        tokens_used=tokens_used,
    )


async def sample_judge_variance(
    samples: list[S],
    judge_fn: Callable[[S], Awaitable[tuple[float, int]]],
    original_score: Callable[[S], float],
    max_samples: int = DEFAULT_VARIANCE_SAMPLES,
    sample_selector: Callable[[list[S], Callable[[S], float], int], list[S]] | None = None,
) -> tuple[float | None, int]:
    """Legacy tuple-returning wrapper. New callers should use
    ``sample_judge_variance_detailed`` to get n and the sampled uuids."""
    result = await sample_judge_variance_detailed(
        samples=samples,
        judge_fn=judge_fn,
        original_score=original_score,
        sample_uuid=None,
        max_samples=max_samples,
        sample_selector=sample_selector,
    )
    return (result.sigma, result.tokens_used)
