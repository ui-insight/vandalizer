"""Budget enforcement for autovalidate optimization runs.

Shared across KB / extraction / workflow optimizers. Manages token-budget
bookkeeping plus the random-sample-without-replacement trial-count target.
"""

import random
from typing import Any

# Hard cap on planned trials per run, regardless of budget. Prevents
# unbounded DB document growth on very large budgets.
DEFAULT_MAX_TRIAL_COUNT = 100

# Conservative per-trial token estimate used for budget pacing when the
# caller hasn't measured a real per-trial cost yet.
DEFAULT_PER_TRIAL_TOKEN_ESTIMATE = 100_000


class BudgetEnforcer:
    """Stateful budget tracker.

    Caller pattern:
        be = BudgetEnforcer(total_budget=2_500_000, per_trial_estimate=100_000)
        for trial in be.sample_trials(search_space, rng=rng):
            if not be.can_afford_next_trial():
                break
            tokens_used = run_trial(trial)
            be.record_trial(tokens_used)
    """

    def __init__(
        self,
        total_budget: int,
        per_trial_estimate: int = DEFAULT_PER_TRIAL_TOKEN_ESTIMATE,
        max_trial_count: int = DEFAULT_MAX_TRIAL_COUNT,
    ) -> None:
        self.total_budget = max(0, total_budget)
        self.per_trial_estimate = max(1, per_trial_estimate)
        self.max_trial_count = max(0, max_trial_count)
        self.tokens_used = 0

    def remaining(self) -> int:
        return max(0, self.total_budget - self.tokens_used)

    def can_afford_next_trial(self) -> bool:
        """True iff the remaining budget plausibly covers another trial."""
        return self.remaining() >= self.per_trial_estimate

    def record_trial(self, tokens: int) -> None:
        self.tokens_used += max(0, tokens)

    def sample_trials(
        self,
        search_space: list[dict[str, Any]],
        rng: random.Random | None = None,
    ) -> list[dict[str, Any]]:
        """Random sample without replacement; capped by budget and max_trial_count.

        The cap is computed up-front from total_budget / per_trial_estimate so
        the trial roster is known before execution begins.
        """
        rng = rng or random.Random()
        target = min(
            self.max_trial_count,
            max(0, self.total_budget // self.per_trial_estimate),
        )
        if target <= 0:
            return []
        pool = list(search_space)
        rng.shuffle(pool)
        return pool[:target]

    def stratified_sample_trials(
        self,
        search_space: list[dict[str, Any]],
        axes: list[str],
        rng: random.Random | None = None,
    ) -> list[dict[str, Any]]:
        """Stratified sample without replacement — guarantees axis coverage.

        Pure uniform random sampling at small N can leave entire axis values
        unexplored (e.g. 5 trials all happen to be ``k=4``). Stratified
        sampling first picks one config per axis value (so every value gets
        tried at least once), then fills the remainder with random draws.

        The shuffled pool order makes within-axis-value selection random,
        and the axis iteration order is shuffled too, so no axis is
        systematically prioritized over another when the target count is
        small enough that not every axis fits.
        """
        rng = rng or random.Random()
        target = min(
            self.max_trial_count,
            max(0, self.total_budget // self.per_trial_estimate),
        )
        if target <= 0:
            return []
        if not axes:
            return self.sample_trials(search_space, rng=rng)

        pool = list(search_space)
        rng.shuffle(pool)

        # Collect unique values per axis from the actual search space.
        axis_values: dict[str, list[Any]] = {a: [] for a in axes}
        seen_per_axis: dict[str, set] = {a: set() for a in axes}
        for cfg in pool:
            for a in axes:
                v = cfg.get(a, _MISSING)
                if v is _MISSING:
                    continue
                # Set uses hashable types only; model can be None which is hashable.
                try:
                    if v not in seen_per_axis[a]:
                        seen_per_axis[a].add(v)
                        axis_values[a].append(v)
                except TypeError:
                    # Unhashable axis value — skip stratification for it.
                    continue

        chosen: list[dict[str, Any]] = []
        chosen_keys: set = set()

        def _key(cfg: dict[str, Any]) -> tuple:
            return tuple(sorted(cfg.items(), key=lambda kv: kv[0]))

        # Phase 1: at least one trial per axis value. Shuffle axis order so a
        # tight budget doesn't always favour the first-listed axis.
        ordered_axes = list(axes)
        rng.shuffle(ordered_axes)
        for axis in ordered_axes:
            for value in axis_values[axis]:
                if len(chosen) >= target:
                    return chosen
                # Prefer pool entries that match this axis value AND fill
                # axes we've under-sampled. For v1, a simple match is enough.
                for cfg in pool:
                    if cfg.get(axis) != value:
                        continue
                    k = _key(cfg)
                    if k in chosen_keys:
                        continue
                    chosen.append(cfg)
                    chosen_keys.add(k)
                    break

        # Phase 2: random fill the remainder from the unsampled pool.
        for cfg in pool:
            if len(chosen) >= target:
                break
            k = _key(cfg)
            if k in chosen_keys:
                continue
            chosen.append(cfg)
            chosen_keys.add(k)

        return chosen


_MISSING = object()
