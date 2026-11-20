"""Optimizer results read the same in chat, the editor and the Apply gate.

Support ticket: for one extraction run the editor showed Optimized 95% against
Current 93% and called it "+1pts"; chat said "final 94%, best trial 88%",
quoted "tied_on_reported_score" and "Tokens used 281102", and offered to apply
a run whose Apply button the editor disables.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.extraction_optimization_run import ExtractionOptimizationRun
from app.services.optimization_common import reported_baseline_score, tied_on_reported_scores
from app.services.optimization_summary import summarize_run


def _run(**fields) -> ExtractionOptimizationRun:
    base = dict(
        uuid="run-1", search_set_uuid="ss-1", status="completed",
        optimized_score=0.946, optimized_score_train=0.88,
        baseline_default_score=0.80, holdout_default_score=0.934,
        holdout_optimized_score=0.946, tied_with_baseline=True,
        winner_selection_reason="tied_on_reported_score", tokens_used=281102,
        best_trial_id="t1", best_config={"model": "m"},
        trials=[{"trial_id": "t1", "status": "completed", "score": 0.88, "config": {"model": "m"}}],
        previous_override=None, options={},
    )
    base.update(fields)
    return ExtractionOptimizationRun.model_construct(**base)


class TestReportedBaseline:
    def test_held_out_headline_is_compared_with_held_out_current_settings(self):
        assert reported_baseline_score(
            holdout_optimized_score=0.946, holdout_default_score=0.934, baseline_default_score=0.80,
        ) == 0.934

    def test_incomplete_held_out_pair_falls_back_to_training_baseline(self):
        assert reported_baseline_score(
            holdout_optimized_score=None, holdout_default_score=0.934, baseline_default_score=0.80,
        ) == 0.80
        assert reported_baseline_score(
            holdout_optimized_score=0.946, holdout_default_score=None, baseline_default_score=0.80,
        ) == 0.80

    def test_tie_is_decided_on_the_pair_the_run_reports(self):
        # Against the training baseline (0.80) this cleared the band; against
        # the same-cases score (0.934) it is inside it.
        baseline = reported_baseline_score(
            holdout_optimized_score=0.946, holdout_default_score=0.934, baseline_default_score=0.80,
        )
        assert tied_on_reported_scores(tied=False, optimized_score=0.946, baseline_score=baseline, band=0.02)


class TestSummary:
    def test_summary_shows_the_editor_pair_and_their_difference(self):
        s = summarize_run(_run())
        assert (s["score_percent"], s["baseline_score_percent"]) == (95, 93)
        assert s["difference_points"] == 2
        assert s["compared_on_held_out_cases"] is True

    def test_runs_from_before_the_field_are_recognised(self):
        s = summarize_run(_run(holdout_optimized_score=None))
        assert s["baseline_score_percent"] == 93

    def test_training_headline_keeps_training_baseline(self):
        s = summarize_run(_run(holdout_optimized_score=None, optimized_score=0.88))
        assert s["baseline_score_percent"] == 80
        assert s["compared_on_held_out_cases"] is False


def _context():
    from tests.test_chat_tools import _make_context
    return _make_context()


@pytest.mark.asyncio
async def test_chat_reports_plain_reasons_formatted_tokens_and_no_apply_offer():
    from app.services import chat_tools

    with (
        patch("app.services.optimization_summary.get_run_by_uuid", new=AsyncMock(return_value=_run())),
        patch.object(chat_tools, "_get_optimizable_item", new=AsyncMock(return_value=(MagicMock(), "NSF Subaward", None))),
    ):
        out = await chat_tools.get_optimization_run(_context(), "extraction", "run-1")

    text = json.dumps(out)
    assert "tied_on_reported_score" not in text
    assert out["why_this_result"].startswith("The best setup led on the cases used to pick it")
    assert out["tokens_used"] == "281,102"
    assert "best_trial_score_percent" not in out
    assert out["best_trial_score_percent_on_selection_cases"] == 88
    assert (out["score_percent"], out["baseline_score_percent"], out["difference_points"]) == (95, 93, 2)
    assert "Do not offer apply_optimization" in out["note"]


@pytest.mark.asyncio
async def test_apply_refuses_a_run_the_editor_will_not_apply():
    from app.services import chat_tools

    with (
        patch("app.services.optimization_summary.get_run_by_uuid", new=AsyncMock(return_value=_run())),
        patch.object(chat_tools, "_get_optimizable_item", new=AsyncMock(return_value=(MagicMock(), "NSF Subaward", None))),
    ):
        out = await chat_tools.apply_optimization(_context(), "extraction", "run-1")

    assert "error" in out
    assert "no meaningful difference" in out["error"]
    assert "needs_confirmation" not in out
