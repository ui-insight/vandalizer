"""Tests for the shared winner-selection helper used by KB / extraction /
workflow optimizers. Behaviour is covered domain-side too, but pinning the
algorithm here insulates against any one consumer's mock noise.
"""

from __future__ import annotations

import pytest

from app.services.optimization_common import (
    DEFAULT_JUDGE_NOISE_FLOOR,
    WINNER_TIE_SIGMAS,
    pick_winner_variance_aware,
)


def _no_distance(_t: dict) -> int:
    """Identity distance — every trial is equidistant. Used for tests that
    don't exercise the closest-to-default tie-breaker."""
    return 0


def test_no_completed_trials_returns_none_with_zero_cluster():
    trials = [{"trial_id": "X", "status": "failed", "score": None, "config": {}}]
    winner, reason, tied, cluster_size = pick_winner_variance_aware(
        trials,
        judge_variance=None,
        baseline_default_score=0.5,
        distance_from_default=_no_distance,
        n_items_for_se=1,
    )
    assert winner is None
    assert reason == "no_completed_trials"
    assert tied is False
    assert cluster_size == 0


def test_highest_score_when_leader_clears_band_by_a_mile():
    # σ=0.04, N=4 → SE=0.02, band=0.04. Top 0.90 beats #2 0.80 by 0.10.
    trials = [
        {"trial_id": "A", "status": "completed", "score": 0.90, "config": {}},
        {"trial_id": "B", "status": "completed", "score": 0.80, "config": {}},
    ]
    winner, reason, tied, cluster_size = pick_winner_variance_aware(
        trials,
        judge_variance=0.04,
        baseline_default_score=0.50,
        distance_from_default=_no_distance,
        n_items_for_se=4,
    )
    assert winner["trial_id"] == "A"
    assert reason == "highest_score"
    assert tied is False
    assert cluster_size == 1


def test_tied_with_baseline_flags_when_top_is_within_band_of_baseline():
    # σ=0.10, N=4 → SE=0.05, band=0.10. Top 0.71, baseline 0.69 → within band.
    trials = [
        {"trial_id": "A", "status": "completed", "score": 0.71, "config": {}},
        {"trial_id": "B", "status": "completed", "score": 0.70, "config": {}},
    ]
    winner, reason, tied, cluster_size = pick_winner_variance_aware(
        trials,
        judge_variance=0.10,
        baseline_default_score=0.69,
        distance_from_default=_no_distance,
        n_items_for_se=4,
    )
    assert tied is True
    assert reason == "tied_with_baseline"
    assert winner is not None  # caller still wants something to show
    assert cluster_size >= 1


def test_closest_to_default_breaks_ties_inside_the_cluster():
    # σ=0.04, N=4 → SE=0.02, band=0.04. Top 0.86 and 0.85 are both inside
    # the band; pick the one with smaller distance_from_default.
    trials = [
        {"trial_id": "far", "status": "completed", "score": 0.86, "config": {"d": 3}},
        {"trial_id": "close", "status": "completed", "score": 0.85, "config": {"d": 0}},
    ]
    winner, reason, tied, cluster_size = pick_winner_variance_aware(
        trials,
        judge_variance=0.04,
        baseline_default_score=0.50,  # well below the cluster
        distance_from_default=lambda t: int(t["config"]["d"]),
        n_items_for_se=4,
    )
    assert winner["trial_id"] == "close"
    assert reason == "closest_to_default"
    assert tied is False
    assert cluster_size == 2


def test_fallback_noise_floor_used_when_variance_unknown():
    # judge_variance=None means we fall back to the supplied floor (0.06).
    # σ=0.06, N=4 → SE=0.03, band=0.06. Top 0.55, runner-up 0.50 → inside band.
    trials = [
        {"trial_id": "A", "status": "completed", "score": 0.55, "config": {}},
        {"trial_id": "B", "status": "completed", "score": 0.50, "config": {}},
    ]
    winner, reason, _tied, cluster_size = pick_winner_variance_aware(
        trials,
        judge_variance=None,
        baseline_default_score=0.20,
        distance_from_default=_no_distance,
        n_items_for_se=4,
        fallback_noise_floor=0.06,
    )
    # Cluster size 2 confirms band picked up the second trial — wouldn't
    # happen if the default 0.02 floor was used (band would have been 0.02).
    assert cluster_size == 2
    assert winner is not None
    assert reason == "closest_to_default"


def test_completed_statuses_lets_callers_count_early_stopped_trials():
    # Workflow optimizer counts early-stopped trials too (they carry a partial
    # but real score). Default config rejects them.
    trials = [
        {"trial_id": "ok", "status": "completed", "score": 0.70, "config": {}},
        {"trial_id": "es", "status": "early_stopped", "score": 0.80, "config": {}},
    ]
    # Default: early_stopped is filtered out, ok wins.
    winner_default, _, _, _ = pick_winner_variance_aware(
        trials,
        judge_variance=0.01,
        baseline_default_score=0.20,
        distance_from_default=_no_distance,
        n_items_for_se=4,
    )
    assert winner_default["trial_id"] == "ok"
    # When the caller opts early_stopped in, the early-stopped trial's higher
    # score wins.
    winner_es, _, _, _ = pick_winner_variance_aware(
        trials,
        judge_variance=0.01,
        baseline_default_score=0.20,
        distance_from_default=_no_distance,
        n_items_for_se=4,
        completed_statuses=("completed", "early_stopped"),
    )
    assert winner_es["trial_id"] == "es"


def test_constants_are_what_callers_expect():
    """Sanity: constants haven't drifted out from under domain consumers."""
    assert WINNER_TIE_SIGMAS == 2.0
    assert DEFAULT_JUDGE_NOISE_FLOOR == 0.02


# --- The verdict must cover the scores the run reports ----------------------

from app.services.optimization_common import tie_band, tied_on_reported_scores  # noqa: E402


def test_tie_band_is_two_standard_errors():
    assert tie_band(0.1, 25) == pytest.approx(2 * 0.1 / 5)
    assert tie_band(None, 1) == pytest.approx(WINNER_TIE_SIGMAS * DEFAULT_JUDGE_NOISE_FLOOR)


def test_a_reported_lift_inside_the_band_is_a_tie():
    # Ticket: 94% vs 92%, a 2-pt band around it.
    assert tied_on_reported_scores(tied=False, optimized_score=0.94, baseline_score=0.92, band=0.022)
    assert not tied_on_reported_scores(tied=False, optimized_score=0.97, baseline_score=0.92, band=0.022)


def test_an_existing_tie_is_never_undone():
    assert tied_on_reported_scores(tied=True, optimized_score=0.99, baseline_score=0.50, band=0.01)


def test_missing_scores_leave_the_verdict_alone():
    assert not tied_on_reported_scores(tied=False, optimized_score=None, baseline_score=0.9, band=0.05)


def test_an_insignificant_paired_test_is_a_tie():
    ci = {"lower": -0.01, "upper": 0.06, "p_value": 0.2, "n_queries": 12}
    assert tied_on_reported_scores(tied=False, optimized_score=0.95, baseline_score=0.85, band=0.02, lift_ci=ci)
    significant = {**ci, "lower": 0.02, "p_value": 0.01}
    assert not tied_on_reported_scores(
        tied=False, optimized_score=0.95, baseline_score=0.85, band=0.02, lift_ci=significant,
    )


def test_a_paired_test_on_too_few_queries_does_not_decide():
    ci = {"lower": -0.2, "upper": 0.4, "p_value": 0.5, "n_queries": 3}
    assert not tied_on_reported_scores(tied=False, optimized_score=0.95, baseline_score=0.85, band=0.02, lift_ci=ci)
