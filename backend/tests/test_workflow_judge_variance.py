"""Tests for ``_sample_workflow_judge_variance`` (Phase 2A).

Re-evaluates the most-recent workflow run and measures how often check
verdicts flip — gives the UI a confidence interval for the grade.

LLM is mocked. We verify orchestration: when the helper skips, when it
computes variance, how SKIP verdicts are handled.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import workflow_service
from app.services.workflow_service import _sample_workflow_judge_variance


def _plan():
    return [
        {"id": "c1", "category": "content"},
        {"id": "c2", "category": "content"},
        {"id": "c3", "category": "content"},
    ]


def _last_result(final_output: str = "workflow output text"):
    wr = MagicMock()
    wr.final_output = {"text": final_output}
    wr.steps_output = {}
    return wr


# ---------------------------------------------------------------------------
# Skip paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_none_with_no_plan():
    assert await _sample_workflow_judge_variance(
        plan=[], last_result=_last_result(), wf_data={},
        original_checks_per_run=[[{"check_id": "c1", "status": "PASS"}]],
    ) is None


@pytest.mark.asyncio
async def test_returns_none_with_no_runs():
    assert await _sample_workflow_judge_variance(
        plan=_plan(), last_result=_last_result(), wf_data={},
        original_checks_per_run=[],
    ) is None


@pytest.mark.asyncio
async def test_returns_none_with_no_last_result():
    assert await _sample_workflow_judge_variance(
        plan=_plan(), last_result=None, wf_data={},
        original_checks_per_run=[[{"check_id": "c1", "status": "PASS"}]],
    ) is None


@pytest.mark.asyncio
async def test_returns_none_when_output_not_serializable():
    wr = MagicMock(); wr.final_output = None
    out = await _sample_workflow_judge_variance(
        plan=_plan(), last_result=wr, wf_data={},
        original_checks_per_run=[[{"check_id": "c1", "status": "PASS"}]],
    )
    assert out is None


@pytest.mark.asyncio
async def test_returns_none_when_replay_errors():
    """Replay LLM failure surfaces as None, not an exception."""
    with patch.object(
        workflow_service,
        "_evaluate_checks_against_output",
        new=AsyncMock(side_effect=RuntimeError("model down")),
    ):
        out = await _sample_workflow_judge_variance(
            plan=_plan(), last_result=_last_result(), wf_data={},
            original_checks_per_run=[[
                {"check_id": "c1", "status": "PASS"},
                {"check_id": "c2", "status": "PASS"},
            ]],
        )
    assert out is None


@pytest.mark.asyncio
async def test_returns_none_when_fewer_than_two_comparable_verdicts():
    """Need ≥2 (orig, replay) pairs to compute stddev. One pair = not enough."""
    with patch.object(
        workflow_service,
        "_evaluate_checks_against_output",
        new=AsyncMock(return_value=[{"check_id": "c1", "status": "PASS"}]),
    ):
        out = await _sample_workflow_judge_variance(
            plan=_plan(), last_result=_last_result(), wf_data={},
            original_checks_per_run=[[{"check_id": "c1", "status": "PASS"}]],
        )
    assert out is None


@pytest.mark.asyncio
async def test_skip_verdicts_excluded_from_samples():
    """When original or replay says SKIP for a check, drop it — judge couldn't
    evaluate, so we have no signal about variance for that check."""
    original_checks = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "SKIP"},
        {"check_id": "c3", "status": "PASS"},
    ]
    replay = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "PASS"},
        {"check_id": "c3", "status": "SKIP"},
    ]
    # After filtering, only c1 remains (c2 SKIPped in original, c3 SKIPped in replay)
    # — that's 1 sample, below the 2-required minimum, so returns None.
    with patch.object(
        workflow_service,
        "_evaluate_checks_against_output",
        new=AsyncMock(return_value=replay),
    ):
        out = await _sample_workflow_judge_variance(
            plan=_plan(), last_result=_last_result(), wf_data={},
            original_checks_per_run=[original_checks],
        )
    assert out is None


# ---------------------------------------------------------------------------
# Variance computation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_variance_when_replay_matches_originals():
    """All verdicts identical between original and replay → stddev of deltas is 0."""
    checks_both = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "PASS"},
        {"check_id": "c3", "status": "FAIL"},
    ]
    with patch.object(
        workflow_service,
        "_evaluate_checks_against_output",
        new=AsyncMock(return_value=[dict(c) for c in checks_both]),
    ):
        out = await _sample_workflow_judge_variance(
            plan=_plan(), last_result=_last_result(), wf_data={},
            original_checks_per_run=[checks_both],
        )
    assert out == 0.0


@pytest.mark.asyncio
async def test_nonzero_variance_when_verdicts_flip():
    """One verdict flips PASS→FAIL between original and replay → nonzero variance."""
    original = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "PASS"},
        {"check_id": "c3", "status": "PASS"},
    ]
    replay = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "FAIL"},  # flipped — delta = 1.0
        {"check_id": "c3", "status": "PASS"},
    ]
    with patch.object(
        workflow_service,
        "_evaluate_checks_against_output",
        new=AsyncMock(return_value=replay),
    ):
        out = await _sample_workflow_judge_variance(
            plan=_plan(), last_result=_last_result(), wf_data={},
            original_checks_per_run=[original],
        )
    # Signed deltas (replay − original) are [0, -1.0, 0]. mean = -0.333;
    # sample variance (n-1) = (0.111 + 0.444 + 0.111) / 2 = 0.333;
    # stddev = sqrt(0.333) ≈ 0.577.
    assert out is not None
    assert 0.5 < out < 0.65


@pytest.mark.asyncio
async def test_warn_to_pass_flip_produces_smaller_variance_than_pass_to_fail():
    """WARN (0.5) → PASS (1.0) is a smaller flip than PASS → FAIL. Variance
    should reflect the magnitude of the disagreement."""
    original = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "PASS"},
    ]
    # Replay 1: PASS → WARN (delta 0.5)
    replay_small = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "WARN"},
    ]
    # Replay 2: PASS → FAIL (delta 1.0)
    replay_big = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "FAIL"},
    ]

    with patch.object(
        workflow_service,
        "_evaluate_checks_against_output",
        new=AsyncMock(return_value=replay_small),
    ):
        var_small = await _sample_workflow_judge_variance(
            plan=_plan(), last_result=_last_result(), wf_data={},
            original_checks_per_run=[original],
        )

    with patch.object(
        workflow_service,
        "_evaluate_checks_against_output",
        new=AsyncMock(return_value=replay_big),
    ):
        var_big = await _sample_workflow_judge_variance(
            plan=_plan(), last_result=_last_result(), wf_data={},
            original_checks_per_run=[original],
        )

    assert var_small is not None and var_big is not None
    assert var_small < var_big


@pytest.mark.asyncio
async def test_replay_uses_most_recent_run_output():
    """Variance is sampled against the first (most-recent) run's checks, not
    averaged across all runs."""
    most_recent = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "PASS"},
    ]
    older_run = [
        {"check_id": "c1", "status": "FAIL"},  # very different from most_recent
        {"check_id": "c2", "status": "FAIL"},
    ]
    # Replay matches most_recent → variance should be 0 (not high, which it
    # would be if we compared replay to older_run)
    with patch.object(
        workflow_service,
        "_evaluate_checks_against_output",
        new=AsyncMock(return_value=[dict(c) for c in most_recent]),
    ):
        out = await _sample_workflow_judge_variance(
            plan=_plan(), last_result=_last_result(), wf_data={},
            original_checks_per_run=[most_recent, older_run],  # [0] is most recent
        )
    assert out == 0.0
