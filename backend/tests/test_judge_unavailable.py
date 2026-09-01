"""A judge that cannot be reached must not score 0.0.

`judge_field_value` returned `{"score": 0.0, "verdict": "FAIL"}` on any
exception. A provider outage during an optimizer run was therefore
indistinguishable from a quality collapse: every field scored zero, the trial
recorded a catastrophic accuracy, and that number went into the quality history
permanently — where the next comparison reads it as a regression and fires an
alert about a problem that never existed.

The judge now reports `JUDGE_UNAVAILABLE` with `score=None`, aggregates exclude
it, and a trial the judge did not cover is discarded rather than published.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import extraction_judge
from app.services.extraction_judge import (
    JUDGE_UNAVAILABLE,
    is_judge_unavailable,
    judge_test_case_extraction,
)
from app.services.extraction_optimizer import (
    MIN_JUDGE_COVERAGE,
    _covered_score_to_unit,
    _judge_covered,
    _to_trial_summary,
)


class TestVerdict:
    @pytest.mark.asyncio
    async def test_outage_is_not_a_failing_score(self):
        agent = MagicMock()
        agent.run = AsyncMock(side_effect=RuntimeError("502 Bad Gateway"))
        with (
            # The deterministic pre-judge would resolve this pair without an
            # LLM call; this test is about the path that does reach the judge.
            patch("app.services.extraction_judge_router.prejudge", return_value=None),
            patch.object(extraction_judge, "_ensure_system_config_loaded",
                         new=AsyncMock(return_value=None)),
            patch.object(extraction_judge, "_get_agent", return_value=agent),
        ):
            out = await extraction_judge.judge_field_value(
                field_name="Award Amount", expected="$4,200,000",
                actual="$4,200,000", model_name="m",
            )
        assert out["verdict"] == JUDGE_UNAVAILABLE
        assert out["score"] is None
        assert out["comparator"] == "llm_error"

    def test_is_judge_unavailable_only_matches_the_outage_verdict(self):
        assert is_judge_unavailable({"verdict": JUDGE_UNAVAILABLE})
        assert not is_judge_unavailable({"verdict": "FAIL", "score": 0.0})
        assert not is_judge_unavailable({"verdict": "PASS", "score": 1.0})
        assert not is_judge_unavailable(None)


class TestTestCaseAggregate:
    @pytest.mark.asyncio
    async def test_unavailable_field_is_excluded_not_zeroed(self):
        """Two fields scored 1.0 and one unreachable is 1.0, not 0.67."""
        verdicts = {
            "PI Name": {"score": 1.0, "verdict": "PASS", "reasoning": "", "tokens_used": 5},
            "Amount": {"score": 1.0, "verdict": "PASS", "reasoning": "", "tokens_used": 5},
            "Award Date": {"score": None, "verdict": JUDGE_UNAVAILABLE,
                           "reasoning": "judge unavailable: timeout", "tokens_used": 0},
        }

        async def fake_judge(field_name, expected, actual, model_name, field_metadata=None):
            return verdicts[field_name]

        with patch.object(extraction_judge, "judge_field_value",
                          new=AsyncMock(side_effect=fake_judge)):
            out = await judge_test_case_extraction(
                keys=["PI Name", "Amount", "Award Date"],
                expected={"PI Name": "Smith", "Amount": "$1000", "Award Date": "2026-01-05"},
                actual={"PI Name": "Smith", "Amount": "$1000", "Award Date": "2026-01-05"},
                model_name="m",
            )

        assert out["avg_score"] == pytest.approx(1.0)
        assert out["num_fields_judged"] == 2
        assert out["num_fields_unavailable"] == 1
        assert out["judge_coverage"] == pytest.approx(2 / 3, abs=1e-4)

    @pytest.mark.asyncio
    async def test_full_coverage_when_every_field_answered(self):
        async def fake_judge(field_name, expected, actual, model_name, field_metadata=None):
            return {"score": 0.5, "verdict": "PARTIAL", "reasoning": "", "tokens_used": 1}

        with patch.object(extraction_judge, "judge_field_value",
                          new=AsyncMock(side_effect=fake_judge)):
            out = await judge_test_case_extraction(
                keys=["A", "B"], expected={"A": "1", "B": "2"},
                actual={"A": "1", "B": "2"}, model_name="m",
            )
        assert out["judge_coverage"] == 1.0
        assert out["num_fields_unavailable"] == 0


class TestCoverageFloor:
    def test_uncovered_trial_is_not_scored(self):
        summary = _to_trial_summary(
            {
                "label": "candidate-a", "model": "m", "config_override": {},
                "accuracy": 0.02, "consistency": 0.5, "score": 2.0,
                "judge_used": True, "judge_coverage": 0.1,
            },
            baseline_default_score=0.8,
        )
        assert summary["status"] == "judge_unavailable"
        assert summary["score"] is None
        assert summary["accuracy"] is None
        assert summary["lift_vs_default"] is None
        assert "10%" in summary["error"]

    def test_covered_trial_keeps_its_score(self):
        summary = _to_trial_summary(
            {
                "label": "candidate-b", "model": "m", "config_override": {},
                "accuracy": 0.9, "consistency": 0.9, "score": 90.0,
                "judge_used": True, "judge_coverage": 1.0,
            },
            baseline_default_score=0.8,
        )
        assert summary["status"] == "completed"
        assert summary["score"] == pytest.approx(0.9)
        assert summary["lift_vs_default"] == pytest.approx(0.1)

    def test_strict_match_trials_are_never_gated(self):
        """With no judge there is nothing to be unavailable — a strict-match
        trial must not be discarded for a coverage field it never sets."""
        summary = _to_trial_summary(
            {
                "label": "candidate-c", "model": "m", "config_override": {},
                "accuracy": 0.7, "consistency": 0.7, "score": 70.0,
                "judge_used": False,
            },
            baseline_default_score=None,
        )
        assert summary["status"] == "completed"
        assert summary["score"] == pytest.approx(0.7)

    def test_floor_is_the_boundary(self):
        at_floor = {"judge_used": True, "judge_coverage": MIN_JUDGE_COVERAGE}
        below = {"judge_used": True, "judge_coverage": MIN_JUDGE_COVERAGE - 0.01}
        assert _judge_covered(at_floor, "t")
        assert not _judge_covered(below, "t")

    def test_baseline_score_is_withheld_when_uncovered(self):
        """A baseline is the thing every later comparison is measured against —
        publishing an outage as the baseline poisons every one of them."""
        uncovered = {"score": 5.0, "judge_used": True, "judge_coverage": 0.2}
        covered = {"score": 80.0, "judge_used": True, "judge_coverage": 0.95}
        assert _covered_score_to_unit(uncovered, "baseline-default") is None
        assert _covered_score_to_unit(covered, "baseline-default") == pytest.approx(0.8)


class TestCoverageDenominator:
    """The gate has to be able to *see* the outage it exists for.

    The deterministic pre-judge resolves most comparisons without a model call
    and cannot be unavailable. Counting those in the denominator meant a total
    LLM-judge outage on a set where they dominate still cleared the 0.8 floor:
    the gate passed, and every ambiguous field silently vanished from the score.
    """

    @staticmethod
    async def _run(verdicts: list[dict], n_fields: int) -> dict:
        from app.services import extraction_tuning_service as tuning

        queue = list(verdicts)

        async def fake_judge(**kwargs):
            return queue.pop(0)

        tc = MagicMock(uuid="tc-1", source_type="text", document_uuid=None)
        tc.source_text = "some text"
        tc.expected_values = {f"F{i}": "x" for i in range(n_fields)}
        keys = list(tc.expected_values)

        engine = MagicMock()
        engine.extract.return_value = [{k: "x" for k in keys}]

        with (
            patch.object(tuning, "ExtractionEngine", return_value=engine),
            patch("app.services.extraction_judge.judge_field_value",
                  new=AsyncMock(side_effect=fake_judge)),
        ):
            return await tuning._run_single_config(
                candidate={"model": "m", "config_override": {}, "label": "t"},
                keys=keys,
                test_cases=[tc],
                sys_config_doc={},
                field_metadata=None,
                num_runs=1,
                judge_model="judge-m",
            )

    def _det(self):
        return {"score": 1.0, "verdict": "PASS", "reasoning": "",
                "tokens_used": 0, "comparator": "deterministic"}

    def _out(self):
        return {"score": None, "verdict": JUDGE_UNAVAILABLE,
                "reasoning": "judge unavailable: 502 Bad Gateway",
                "tokens_used": 0, "comparator": "llm_error"}

    def _llm(self):
        return {"score": 1.0, "verdict": "PASS", "reasoning": "",
                "tokens_used": 3, "comparator": "llm"}

    @pytest.mark.asyncio
    async def test_a_total_llm_outage_reads_as_zero_coverage(self):
        """8 deterministic + 2 LLM, both LLM calls dead. Counting the
        deterministic hits would give 0.8 and clear the floor."""
        out = await self._run([self._det()] * 8 + [self._out()] * 2, 10)
        assert out["judge_coverage"] == pytest.approx(0.0)
        assert out["judge_unavailable"] == 2

    @pytest.mark.asyncio
    async def test_a_fully_deterministic_set_is_fully_covered(self):
        """Nothing needed the LLM, so nothing is missing — coverage is 1.0,
        not a division by zero."""
        out = await self._run([self._det()] * 5, 5)
        assert out["judge_coverage"] == 1.0
        assert out["judge_unavailable"] == 0

    @pytest.mark.asyncio
    async def test_partial_llm_availability_is_measured_over_llm_calls_only(self):
        out = await self._run(
            [self._det()] * 6 + [self._llm()] * 3 + [self._out()], 10,
        )
        assert out["judge_coverage"] == pytest.approx(0.75)


class TestApplyGateNeedsABaseline:
    """`tied_with_baseline` is False both when the winner genuinely beat the
    baseline and when there IS no baseline — and withholding an uncovered
    baseline made the second case reachable, converting the significance gate
    into no gate at all."""

    def test_a_missing_baseline_is_not_a_significant_win(self):
        from app.services.optimization_common import pick_winner_variance_aware

        trials = [{"trial_id": "a", "status": "completed", "score": 0.97,
                   "config": {}, "total_comparisons": 10}]
        _winner, _reason, tied, _n = pick_winner_variance_aware(
            trials, judge_variance=0.02, baseline_default_score=None,
            distance_from_default=lambda t: 0, n_items_for_se=10,
        )
        # This is the value the apply gate used to read as "significant win".
        assert tied is False
