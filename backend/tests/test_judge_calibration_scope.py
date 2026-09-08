"""A κ measured in CI belongs to the model CI measured it on.

`judge_contract` publishes `min_kappa=0.65` for the extraction judge. That
number was established by the weekly tier-3 job against
`INTEGRATION_LLM_MODEL`. A deployment whose judge is a local 8B has no claim on
it — but there was no way to ask "was this measured *here*", so the published
figure was the only figure, and inheriting it is how a quality number becomes
fiction.

The ledger itself could not accumulate either: the tier-3 job wrote one line to
an ephemeral runner disk with no commit-back step, `judge_drift_history.jsonl`
is 0 bytes, and `trailing_median` returns None below three entries — so drift
detection had never had a baseline and structurally never would.
"""

import json

import pytest

from app.services import judge_drift


@pytest.fixture
def ledger(tmp_path):
    def write(rows):
        path = tmp_path / "drift.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return path
    return write


def _row(model, kappa, ts, surface="extraction", accuracy=0.9):
    return {
        "timestamp": ts, "surface": surface, "judge_model": model,
        "kappa": kappa, "accuracy": accuracy,
    }


class TestCalibrationFor:
    def test_an_unmeasured_model_gets_nothing_not_someone_elses_number(self, ledger):
        path = ledger([_row("claude-sonnet-5", 0.81, "2026-08-01T06:00:00+00:00")])
        assert judge_drift.calibration_for("extraction", "llama-3.1-8b", path=path) is None

    def test_a_measured_model_gets_its_own_latest_figure(self, ledger):
        path = ledger([
            _row("llama-3.1-8b", 0.52, "2026-07-01T06:00:00+00:00"),
            _row("claude-sonnet-5", 0.81, "2026-08-01T06:00:00+00:00"),
            _row("llama-3.1-8b", 0.58, "2026-08-15T06:00:00+00:00"),
        ])
        got = judge_drift.calibration_for("extraction", "llama-3.1-8b", path=path)
        assert got["kappa"] == 0.58
        assert got["n_runs"] == 2
        assert got["measured_at"] == "2026-08-15T06:00:00+00:00"

    def test_a_measurement_on_another_surface_does_not_count(self, ledger):
        path = ledger([_row("llama-3.1-8b", 0.7, "2026-08-01T06:00:00+00:00", surface="kb")])
        assert judge_drift.calibration_for("extraction", "llama-3.1-8b", path=path) is None

    def test_an_empty_ledger_measures_nothing(self, tmp_path):
        missing = tmp_path / "nope.jsonl"
        assert judge_drift.calibration_for("extraction", "any-model", path=missing) is None


class TestCalibrationStatus:
    def test_each_deployment_model_is_judged_on_its_own_record(self, ledger):
        path = ledger([_row("claude-sonnet-5", 0.81, "2026-08-01T06:00:00+00:00")])
        status = judge_drift.calibration_status(
            "extraction", ["claude-sonnet-5", "llama-3.1-8b"],
            published_floor=0.65, path=path,
        )
        by_model = {m["judge_model"]: m for m in status["models"]}
        assert by_model["claude-sonnet-5"]["calibrated"] is True
        assert by_model["claude-sonnet-5"]["kappa"] == 0.81
        assert by_model["llama-3.1-8b"]["calibrated"] is False
        assert by_model["llama-3.1-8b"]["kappa"] is None
        assert status["published_floor"] == 0.65

    def test_drift_is_not_detectable_below_three_entries(self, ledger):
        """`trailing_median` returns None under three, so `assert_no_regression`
        returns silently — the panel has to say so rather than implying the
        check is live."""
        path = ledger([
            _row("m", 0.8, "2026-08-01T06:00:00+00:00"),
            _row("m", 0.8, "2026-08-08T06:00:00+00:00"),
        ])
        status = judge_drift.calibration_status("extraction", ["m"], path=path)
        assert status["drift_detectable"] is False
        assert status["ledger_entries"] == 2
        assert judge_drift.trailing_median("extraction", path=path) is None

    def test_three_entries_make_drift_detectable(self, ledger):
        path = ledger([
            _row("m", 0.8, "2026-08-01T06:00:00+00:00"),
            _row("m", 0.8, "2026-08-08T06:00:00+00:00"),
            _row("m", 0.8, "2026-08-15T06:00:00+00:00"),
        ])
        status = judge_drift.calibration_status("extraction", ["m"], path=path)
        assert status["drift_detectable"] is True
        assert judge_drift.trailing_median("extraction", path=path) == 0.8

    def test_measured_models_lists_history_not_configuration(self, ledger):
        path = ledger([
            _row("a", 0.8, "2026-08-01T06:00:00+00:00"),
            _row("b", 0.7, "2026-08-08T06:00:00+00:00"),
            _row("a", 0.9, "2026-08-15T06:00:00+00:00"),
        ])
        status = judge_drift.calibration_status("extraction", ["c"], path=path)
        assert status["measured_models"] == ["a", "b"]
        assert status["models"][0]["calibrated"] is False

    def test_no_configured_models_is_not_an_error(self, ledger):
        path = ledger([_row("a", 0.8, "2026-08-01T06:00:00+00:00")])
        status = judge_drift.calibration_status("extraction", [], path=path)
        assert status["models"] == []


class TestLedgerAccumulates:
    def test_recorded_entries_build_a_baseline(self, tmp_path):
        """The behavior the missing commit-back step denied the ledger: three
        runs and drift detection becomes possible."""
        path = tmp_path / "drift.jsonl"
        for kappa in (0.80, 0.82, 0.81):
            judge_drift.record("extraction", judge_model="m", kappa=kappa,
                               accuracy=0.9, path=path)
        assert judge_drift.trailing_median("extraction", path=path) == 0.81
        with pytest.raises(AssertionError, match="regression"):
            judge_drift.assert_no_regression("extraction", 0.60, path=path)


class TestTheGateIsScopedToTheModelToo:
    """`calibration_for` was scoped per model but `trailing_median` still
    pooled them. Once the ledger actually accumulates, the first run after
    `INTEGRATION_LLM_MODEL` rotates would be compared against the *previous*
    model's median — a spurious regression on the exact event ("the judge model
    is silently swapped") the ledger exists to detect."""

    def test_a_rotation_does_not_read_as_a_regression(self, ledger):
        path = ledger([
            _row("old-judge", 0.90, "2026-07-01T06:00:00+00:00"),
            _row("old-judge", 0.91, "2026-07-08T06:00:00+00:00"),
            _row("old-judge", 0.90, "2026-07-15T06:00:00+00:00"),
        ])
        # A new model measuring 0.70 is 0.20 below the old model's median.
        # Pooled, that trips MAX_KAPPA_REGRESSION; scoped, there is no baseline
        # for this model yet and the check correctly declines to fire.
        judge_drift.assert_no_regression(
            "extraction", 0.70, path=path, judge_model="new-judge",
        )
        with pytest.raises(AssertionError, match="regression"):
            judge_drift.assert_no_regression("extraction", 0.70, path=path)

    def test_a_real_regression_on_the_same_model_still_fires(self, ledger):
        path = ledger([
            _row("m", 0.90, "2026-07-01T06:00:00+00:00"),
            _row("m", 0.91, "2026-07-08T06:00:00+00:00"),
            _row("m", 0.90, "2026-07-15T06:00:00+00:00"),
        ])
        with pytest.raises(AssertionError, match="regression"):
            judge_drift.assert_no_regression(
                "extraction", 0.70, path=path, judge_model="m",
            )

    def test_the_median_is_per_model(self, ledger):
        path = ledger([
            _row("a", 0.90, "2026-07-01T06:00:00+00:00"),
            _row("a", 0.90, "2026-07-08T06:00:00+00:00"),
            _row("a", 0.90, "2026-07-15T06:00:00+00:00"),
            _row("b", 0.50, "2026-07-22T06:00:00+00:00"),
        ])
        assert judge_drift.trailing_median("extraction", path=path, judge_model="a") == 0.90
        assert judge_drift.trailing_median("extraction", path=path, judge_model="b") is None


class TestLatestMeansNewest:
    def test_an_out_of_order_ledger_still_reports_the_newest(self, ledger):
        """Line order is only chronological while the file is strictly
        appended; a conflict resolution in the PR flow can reorder it."""
        path = ledger([
            _row("m", 0.95, "2026-08-15T06:00:00+00:00"),
            _row("m", 0.60, "2026-07-01T06:00:00+00:00"),
        ])
        got = judge_drift.calibration_for("extraction", "m", path=path)
        assert got["kappa"] == 0.95
        assert got["measured_at"] == "2026-08-15T06:00:00+00:00"


class TestTheBaselineExcludesTheRunUnderTest:
    """The tier-3 job records before it asserts, so that a run tripping the
    absolute floor still reaches the ledger. That ordering puts the new entry
    inside the baseline it is judged against unless the caller captures the
    median first."""

    def test_a_recorded_run_would_otherwise_pad_its_own_baseline(self, tmp_path):
        led = tmp_path / "ledger.jsonl"
        for k in (0.80, 0.60):
            judge_drift.record(
                "extraction", judge_model="m1", kappa=k, accuracy=0.9,
                bias_metric_name="b", bias_rate=0.0, n_cases=10, path=led,
            )
        assert len(judge_drift.load_history("extraction", path=led)) == 2

        # Two prior runs: too thin for a baseline, so no check can be made.
        captured = judge_drift.trailing_median("extraction", path=led, judge_model="m1")
        assert captured is None

        # A fresh run measuring the same κ. Accuracy differs so the same-minute
        # idempotency guard (keyed on surface/model/κ/accuracy/minute) doesn't
        # fold it into the previous entry; a real weekly run differs by minute.
        judge_drift.record(
            "extraction", judge_model="m1", kappa=0.60, accuracy=0.91,
            bias_metric_name="b", bias_rate=0.0, n_cases=10, path=led,
        )
        assert len(judge_drift.load_history("extraction", path=led)) == 3
        # Recording made the ledger look deep enough — on its own value.
        assert judge_drift.trailing_median("extraction", path=led, judge_model="m1") == 0.60

        # Handed the captured baseline, the check correctly declines to fire.
        judge_drift.assert_no_regression(
            "extraction", 0.60, path=led, judge_model="m1", baseline=captured,
        )


class TestDriftDetectableIsScopedLikeTheCheck:
    """`assert_no_regression` is scoped to one model. A pooled count claimed
    drift was detectable while the check could never fire for any model."""

    def test_one_run_each_for_three_models_is_not_detectable(self, tmp_path):
        led = tmp_path / "ledger.jsonl"
        for model in ("m1", "m2", "m3"):
            judge_drift.record(
                "extraction", judge_model=model, kappa=0.8, accuracy=0.9,
                bias_metric_name="b", bias_rate=0.0, n_cases=10, path=led,
            )
        status = judge_drift.calibration_status(
            "extraction", ["m1", "m2", "m3"], path=led,
        )
        assert status["ledger_entries"] == 3
        assert status["drift_detectable"] is False
        assert all(m["drift_detectable"] is False for m in status["models"])
        # And the check itself agrees.
        for model in ("m1", "m2", "m3"):
            assert judge_drift.trailing_median(
                "extraction", path=led, judge_model=model,
            ) is None

    def test_three_runs_for_one_model_is_detectable_for_that_model_only(self, tmp_path):
        led = tmp_path / "ledger.jsonl"
        for k in (0.80, 0.82, 0.81):
            judge_drift.record(
                "extraction", judge_model="m1", kappa=k, accuracy=0.9,
                bias_metric_name="b", bias_rate=0.0, n_cases=10, path=led,
            )
        judge_drift.record(
            "extraction", judge_model="m2", kappa=0.8, accuracy=0.9,
            bias_metric_name="b", bias_rate=0.0, n_cases=10, path=led,
        )
        status = judge_drift.calibration_status("extraction", ["m1", "m2"], path=led)
        by_model = {m["judge_model"]: m for m in status["models"]}
        assert by_model["m1"]["drift_detectable"] is True
        assert by_model["m2"]["drift_detectable"] is False
        assert status["drift_detectable"] is True
