"""Tests for app.services.extraction_optimizer — the extraction autovalidate
orchestrator. Verifies baselines + sweep + apply-back integration; heavy
dependencies (tuning service, beanie models) are mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import extraction_optimizer
from app.services.extraction_optimizer import (
    _generate_suggestions,
    _score_to_unit,
    _to_trial_summary,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_score_to_unit_scales_to_zero_to_one():
    assert _score_to_unit(85.0) == 0.85
    assert _score_to_unit(0.0) == 0.0
    assert _score_to_unit(100.0) == 1.0


def test_score_to_unit_handles_none():
    assert _score_to_unit(None) is None


def test_to_trial_summary_computes_lift_vs_default():
    result = {
        "label": "claude-haiku-onepass",
        "model": "claude-haiku",
        "config_override": {"strategy": "one-pass"},
        "accuracy": 0.9,
        "consistency": 0.85,
        "score": 88.0,
        "elapsed_seconds": 4.5,
    }
    summary = _to_trial_summary(result, baseline_default_score=0.70)
    assert summary["trial_id"] == "claude-haiku-onepass"
    assert summary["score"] == 0.88
    assert summary["lift_vs_default"] == pytest.approx(0.18, abs=1e-4)
    assert summary["status"] == "completed"
    assert summary["config"]["model"] == "claude-haiku"
    assert summary["config"]["strategy"] == "one-pass"


def test_to_trial_summary_handles_failed_trial():
    result = {
        "label": "broken-config",
        "model": "claude-sonnet",
        "config_override": {},
        "accuracy": 0.0, "consistency": 0.0, "score": 0.0, "elapsed_seconds": 0.0,
        "error": "boom",
    }
    summary = _to_trial_summary(result, baseline_default_score=0.5)
    assert summary["status"] == "failed"
    assert summary["error"] == "boom"
    assert summary["score"] == 0.0


def test_to_trial_summary_no_lift_when_baseline_missing():
    result = {
        "label": "x", "model": "m", "config_override": {},
        "accuracy": 0.5, "consistency": 0.5, "score": 50.0, "elapsed_seconds": 1.0,
    }
    summary = _to_trial_summary(result, baseline_default_score=None)
    assert summary["lift_vs_default"] is None


# ---------------------------------------------------------------------------
# End-to-end run_optimization() (heavily mocked)
# ---------------------------------------------------------------------------


def _make_run_doc(uuid: str = "opt-1") -> MagicMock:
    """Mock ExtractionOptimizationRun supporting attribute access + async save."""
    rd = MagicMock()
    rd.uuid = uuid
    rd.search_set_uuid = "ss-1"
    rd.user_id = "u1"
    rd.status = "queued"
    rd.phase = "queued"
    rd.cancel_requested = False
    rd.trials = []
    rd.baseline_no_tool_score = None
    rd.baseline_default_score = None
    rd.optimized_score = None
    rd.judge_model = None
    rd.judge_variance = None
    rd.best_score_so_far = None
    rd.best_config_so_far = None
    rd.best_config = None
    rd.field_breakdown = []
    rd.previous_override = None
    rd.completed_at = None
    rd.save = AsyncMock()
    return rd


def _make_test_case(label: str = "tc-1", expected: dict | None = None) -> MagicMock:
    tc = MagicMock()
    tc.uuid = label
    tc.label = label
    tc.search_set_uuid = "ss-1"
    tc.source_type = "freetext"
    tc.source_text = "sample"
    tc.expected_values = expected or {"PI Name": "Smith"}
    return tc


def _make_search_set() -> MagicMock:
    ss = MagicMock()
    ss.uuid = "ss-1"
    ss.extraction_config = {"model": "claude-haiku"}
    ss.extraction_config_override = None
    ss.save = AsyncMock()
    return ss


@pytest.mark.asyncio
async def test_run_optimization_records_baselines_and_picks_winner():
    """End-to-end happy path: baselines are measured, trials run, best wins."""
    run_doc = _make_run_doc()
    ss = _make_search_set()
    tc = _make_test_case()

    # Tuning service results returned in order:
    # 1. baseline-no-tool
    # 2. baseline-default
    # 3..N. trial sweep (3 trials)
    results = [
        {"label": "baseline-no-tool", "model": "m", "config_override": {},
         "accuracy": 0.2, "consistency": 0.6, "score": 36.0, "elapsed_seconds": 1.0},
        {"label": "baseline-default", "model": "claude-haiku", "config_override": {"model": "claude-haiku"},
         "accuracy": 0.5, "consistency": 0.8, "score": 62.0, "elapsed_seconds": 1.0},
        {"label": "trial-1", "model": "m1", "config_override": {"strategy": "one-pass"},
         "accuracy": 0.6, "consistency": 0.9, "score": 72.0, "elapsed_seconds": 1.5},
        {"label": "trial-2", "model": "m2", "config_override": {"strategy": "two-pass"},
         "accuracy": 0.9, "consistency": 0.95, "score": 92.0, "elapsed_seconds": 2.0},  # WINNER
        {"label": "trial-3", "model": "m3", "config_override": {"thinking": True},
         "accuracy": 0.7, "consistency": 0.85, "score": 76.0, "elapsed_seconds": 3.0},
    ]
    call_iter = iter(results)

    async def fake_run_single_config(**kwargs):
        return next(call_iter)

    # Three trial candidates (mocked _build_candidate_configs output)
    candidates = [
        {"label": "trial-1", "model": "m1", "config_override": {"strategy": "one-pass"}},
        {"label": "trial-2", "model": "m2", "config_override": {"strategy": "two-pass"}},
        {"label": "trial-3", "model": "m3", "config_override": {"thinking": True}},
    ]

    with (
        patch.object(extraction_optimizer, "ExtractionOptimizationRun") as MockRun,
        patch.object(extraction_optimizer, "ExtractionTestCase") as MockTC,
        patch.object(extraction_optimizer, "SearchSet") as MockSS,
        patch.object(extraction_optimizer, "SystemConfig") as MockSC,
        patch.object(extraction_optimizer, "get_extraction_keys",
                     new=AsyncMock(return_value=["PI Name"])),
        patch.object(extraction_optimizer, "get_extraction_field_metadata",
                     new=AsyncMock(return_value=[])),
        patch.object(extraction_optimizer, "get_user_model_name",
                     new=AsyncMock(return_value="claude-haiku")),
        patch.object(extraction_optimizer, "_build_candidate_configs",
                     return_value=candidates),
        patch.object(extraction_optimizer, "_run_single_config",
                     new=AsyncMock(side_effect=fake_run_single_config)),
    ):
        MockRun.find_one = AsyncMock(return_value=run_doc)
        find_call = MagicMock(); find_call.to_list = AsyncMock(return_value=[tc])
        MockTC.find = MagicMock(return_value=find_call)
        MockSS.find_one = AsyncMock(return_value=ss)
        sys_cfg = MagicMock(); sys_cfg.available_models = [{"name": "m1"}]
        sys_cfg.model_dump = MagicMock(return_value={})
        MockSC.get_config = AsyncMock(return_value=sys_cfg)

        result = await extraction_optimizer.run_optimization(
            search_set_uuid="ss-1",
            user_id="u1",
            run_uuid="opt-1",
            budget_tokens=0,
            apply_on_finish=False,
            max_candidates=3,
        )

    assert result.status == "completed"
    assert result.baseline_no_tool_score == 0.36
    assert result.baseline_default_score == 0.62
    assert result.optimized_score == 0.92  # trial-2 won
    assert len(result.trials) == 3
    assert result.best_score_so_far == 0.92
    # apply_on_finish=False → override not written
    assert ss.extraction_config_override is None


@pytest.mark.asyncio
async def test_run_optimization_applies_on_finish_when_requested():
    """apply_on_finish=True writes best_config to ss.extraction_config_override."""
    run_doc = _make_run_doc()
    ss = _make_search_set()
    tc = _make_test_case()

    results = [
        # no-tool baseline
        {"label": "baseline-no-tool", "model": "m", "config_override": {},
         "accuracy": 0.1, "consistency": 0.5, "score": 26.0, "elapsed_seconds": 1.0},
        # default baseline
        {"label": "baseline-default", "model": "claude-haiku", "config_override": {"model": "claude-haiku"},
         "accuracy": 0.5, "consistency": 0.8, "score": 62.0, "elapsed_seconds": 1.0},
        # single trial — wins
        {"label": "winner", "model": "claude-sonnet", "config_override": {"strategy": "two-pass"},
         "accuracy": 0.9, "consistency": 0.95, "score": 92.0, "elapsed_seconds": 2.0},
    ]
    call_iter = iter(results)

    async def fake_run_single_config(**kwargs):
        return next(call_iter)

    candidates = [{"label": "winner", "model": "claude-sonnet", "config_override": {"strategy": "two-pass"}}]

    with (
        patch.object(extraction_optimizer, "ExtractionOptimizationRun") as MockRun,
        patch.object(extraction_optimizer, "ExtractionTestCase") as MockTC,
        patch.object(extraction_optimizer, "SearchSet") as MockSS,
        patch.object(extraction_optimizer, "SystemConfig") as MockSC,
        patch.object(extraction_optimizer, "get_extraction_keys",
                     new=AsyncMock(return_value=["PI Name"])),
        patch.object(extraction_optimizer, "get_extraction_field_metadata",
                     new=AsyncMock(return_value=[])),
        patch.object(extraction_optimizer, "get_user_model_name",
                     new=AsyncMock(return_value="claude-haiku")),
        patch.object(extraction_optimizer, "_build_candidate_configs",
                     return_value=candidates),
        patch.object(extraction_optimizer, "_run_single_config",
                     new=AsyncMock(side_effect=fake_run_single_config)),
    ):
        MockRun.find_one = AsyncMock(return_value=run_doc)
        find_call = MagicMock(); find_call.to_list = AsyncMock(return_value=[tc])
        MockTC.find = MagicMock(return_value=find_call)
        MockSS.find_one = AsyncMock(return_value=ss)
        sys_cfg = MagicMock(); sys_cfg.available_models = []
        sys_cfg.model_dump = MagicMock(return_value={})
        MockSC.get_config = AsyncMock(return_value=sys_cfg)

        await extraction_optimizer.run_optimization(
            search_set_uuid="ss-1", user_id="u1", run_uuid="opt-1",
            apply_on_finish=True, max_candidates=1,
        )

    # Override was applied
    assert ss.extraction_config_override is not None
    assert ss.extraction_config_override.get("strategy") == "two-pass"
    assert ss.extraction_config_override.get("model") == "claude-sonnet"
    # Previous override (None) is recorded so revert can restore
    assert run_doc.previous_override is None


@pytest.mark.asyncio
async def test_run_optimization_honors_test_case_selection():
    """When test_case_uuids is passed, only those cases reach the scorer."""
    run_doc = _make_run_doc()
    ss = _make_search_set()
    cases = [
        _make_test_case("tc-1"),
        _make_test_case("tc-2"),
        _make_test_case("tc-3"),
    ]

    results = [
        {"label": "baseline-no-tool", "model": "m", "config_override": {},
         "accuracy": 0.2, "consistency": 0.6, "score": 36.0, "elapsed_seconds": 1.0},
        {"label": "baseline-default", "model": "claude-haiku", "config_override": {"model": "claude-haiku"},
         "accuracy": 0.5, "consistency": 0.8, "score": 62.0, "elapsed_seconds": 1.0},
        {"label": "winner", "model": "m1", "config_override": {"strategy": "one-pass"},
         "accuracy": 0.9, "consistency": 0.95, "score": 92.0, "elapsed_seconds": 1.5},
    ]
    call_iter = iter(results)
    seen_case_uuids: list[set[str]] = []

    async def fake_run_single_config(**kwargs):
        seen_case_uuids.append({tc.uuid for tc in kwargs["test_cases"]})
        return next(call_iter)

    candidates = [{"label": "winner", "model": "m1", "config_override": {"strategy": "one-pass"}}]

    with (
        patch.object(extraction_optimizer, "ExtractionOptimizationRun") as MockRun,
        patch.object(extraction_optimizer, "ExtractionTestCase") as MockTC,
        patch.object(extraction_optimizer, "SearchSet") as MockSS,
        patch.object(extraction_optimizer, "SystemConfig") as MockSC,
        patch.object(extraction_optimizer, "get_extraction_keys",
                     new=AsyncMock(return_value=["PI Name"])),
        patch.object(extraction_optimizer, "get_extraction_field_metadata",
                     new=AsyncMock(return_value=[])),
        patch.object(extraction_optimizer, "get_user_model_name",
                     new=AsyncMock(return_value="claude-haiku")),
        patch.object(extraction_optimizer, "_build_candidate_configs",
                     return_value=candidates),
        patch.object(extraction_optimizer, "_run_single_config",
                     new=AsyncMock(side_effect=fake_run_single_config)),
    ):
        MockRun.find_one = AsyncMock(return_value=run_doc)
        find_call = MagicMock(); find_call.to_list = AsyncMock(return_value=cases)
        MockTC.find = MagicMock(return_value=find_call)
        MockSS.find_one = AsyncMock(return_value=ss)
        sys_cfg = MagicMock(); sys_cfg.available_models = []
        sys_cfg.model_dump = MagicMock(return_value={})
        MockSC.get_config = AsyncMock(return_value=sys_cfg)

        result = await extraction_optimizer.run_optimization(
            search_set_uuid="ss-1", user_id="u1", run_uuid="opt-1",
            max_candidates=1, test_case_uuids=["tc-2"],
        )

    assert result.status == "completed"
    # Every scorer call (baselines + trial) saw only the selected case.
    assert seen_case_uuids and all(s == {"tc-2"} for s in seen_case_uuids)
    assert run_doc.train_test_case_uuids == ["tc-2"]


@pytest.mark.asyncio
async def test_run_optimization_fails_with_no_test_cases():
    """Missing test cases must surface as a clear error, not a silent pass."""
    run_doc = _make_run_doc()

    with (
        patch.object(extraction_optimizer, "ExtractionOptimizationRun") as MockRun,
        patch.object(extraction_optimizer, "ExtractionTestCase") as MockTC,
        patch.object(extraction_optimizer, "get_extraction_keys",
                     new=AsyncMock(return_value=["PI Name"])),
    ):
        MockRun.find_one = AsyncMock(return_value=run_doc)
        find_call = MagicMock(); find_call.to_list = AsyncMock(return_value=[])
        MockTC.find = MagicMock(return_value=find_call)

        result = await extraction_optimizer.run_optimization(
            search_set_uuid="ss-1", user_id="u1", run_uuid="opt-1",
        )

    assert result.status == "failed"
    assert "test cases" in (result.error_message or "").lower()


@pytest.mark.asyncio
async def test_run_optimization_fails_with_no_fields():
    """No extraction fields = no work; surface as a failure not a no-op."""
    run_doc = _make_run_doc()

    with (
        patch.object(extraction_optimizer, "ExtractionOptimizationRun") as MockRun,
        patch.object(extraction_optimizer, "get_extraction_keys",
                     new=AsyncMock(return_value=[])),
    ):
        MockRun.find_one = AsyncMock(return_value=run_doc)

        result = await extraction_optimizer.run_optimization(
            search_set_uuid="ss-1", user_id="u1", run_uuid="opt-1",
        )

    assert result.status == "failed"
    assert "extraction fields" in (result.error_message or "").lower()


@pytest.mark.asyncio
async def test_run_optimization_raises_for_missing_run_doc():
    """The route pre-creates the run doc; missing one is a bug, not a recoverable state."""
    with patch.object(extraction_optimizer, "ExtractionOptimizationRun") as MockRun:
        MockRun.find_one = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await extraction_optimizer.run_optimization(
                search_set_uuid="ss-1", user_id="u1", run_uuid="ghost",
            )


@pytest.mark.asyncio
async def test_run_optimization_with_judge_threads_model_through_and_samples_variance():
    """include_judge=True: judge_model flows into _run_single_config + variance sampled."""
    run_doc = _make_run_doc()
    ss = _make_search_set()
    tc = _make_test_case()

    # Each result must include judge_samples for variance to sample from
    judge_sample = [
        {"field_name": "PI Name", "expected": "Smith", "actual": "John Smith", "score": 0.95},
        {"field_name": "Award Date", "expected": "2026-01-05", "actual": "Jan 5", "score": 0.9},
    ]
    results = [
        {"label": "baseline-no-tool", "model": "m", "config_override": {},
         "accuracy": 0.3, "consistency": 0.6, "score": 42.0, "elapsed_seconds": 1.0,
         "judge_used": True, "judge_samples": judge_sample},
        {"label": "baseline-default", "model": "claude-haiku", "config_override": {"model": "claude-haiku"},
         "accuracy": 0.7, "consistency": 0.85, "score": 76.0, "elapsed_seconds": 1.0,
         "judge_used": True, "judge_samples": judge_sample},
        {"label": "winner", "model": "claude-sonnet", "config_override": {"strategy": "two-pass"},
         "accuracy": 0.92, "consistency": 0.95, "score": 93.0, "elapsed_seconds": 2.0,
         "judge_used": True, "judge_samples": judge_sample},
    ]
    call_iter = iter(results)
    captured_judge_models: list = []

    async def fake_run_single_config(**kwargs):
        captured_judge_models.append(kwargs.get("judge_model"))
        return next(call_iter)

    candidates = [{"label": "winner", "model": "claude-sonnet", "config_override": {"strategy": "two-pass"}}]

    # Mock the variance sampler to verify it's called with our judge samples
    fake_variance = (0.025, 100)  # (stddev, tokens)
    fake_variance_call: dict[str, object] = {}

    async def fake_sample_variance(*, samples, judge_fn, original_score, max_samples):
        fake_variance_call["samples_count"] = len(samples)
        fake_variance_call["max_samples"] = max_samples
        return fake_variance

    # Mock judge_field_value too (gets called by the re-judge closure if exercised)
    async def fake_judge_field_value(**kwargs):
        return {"score": 0.92, "verdict": "PASS", "reasoning": "x", "tokens_used": 50}

    with (
        patch.object(extraction_optimizer, "ExtractionOptimizationRun") as MockRun,
        patch.object(extraction_optimizer, "ExtractionTestCase") as MockTC,
        patch.object(extraction_optimizer, "SearchSet") as MockSS,
        patch.object(extraction_optimizer, "SystemConfig") as MockSC,
        patch.object(extraction_optimizer, "get_extraction_keys",
                     new=AsyncMock(return_value=["PI Name"])),
        patch.object(extraction_optimizer, "get_extraction_field_metadata",
                     new=AsyncMock(return_value=[])),
        patch.object(extraction_optimizer, "get_user_model_name",
                     new=AsyncMock(return_value="claude-haiku")),
        patch.object(extraction_optimizer, "_build_candidate_configs",
                     return_value=candidates),
        patch.object(extraction_optimizer, "_run_single_config",
                     new=AsyncMock(side_effect=fake_run_single_config)),
        patch("app.services.judge_variance.sample_judge_variance",
              new=AsyncMock(side_effect=fake_sample_variance)),
        patch("app.services.extraction_judge.judge_field_value",
              new=AsyncMock(side_effect=fake_judge_field_value)),
    ):
        MockRun.find_one = AsyncMock(return_value=run_doc)
        find_call = MagicMock(); find_call.to_list = AsyncMock(return_value=[tc])
        MockTC.find = MagicMock(return_value=find_call)
        MockSS.find_one = AsyncMock(return_value=ss)
        sys_cfg = MagicMock(); sys_cfg.available_models = [{"name": "m1"}]
        sys_cfg.model_dump = MagicMock(return_value={})
        MockSC.get_config = AsyncMock(return_value=sys_cfg)

        result = await extraction_optimizer.run_optimization(
            search_set_uuid="ss-1", user_id="u1", run_uuid="opt-1",
            include_judge=True, max_candidates=1,
        )

    # judge_model flowed into every _run_single_config call (3 calls: 2 baselines + 1 trial)
    assert captured_judge_models == ["claude-haiku", "claude-haiku", "claude-haiku"]
    # judge_model recorded on the run doc
    assert result.judge_model == "claude-haiku"
    # Variance was sampled from the default baseline's judge_samples. The
    # max_samples is the shared DEFAULT_VARIANCE_SAMPLES (5) — n=2 was a
    # point-measurement, not a noise estimate; the new default gives the
    # sample-stddev estimator enough degrees of freedom to mean anything.
    from app.services.judge_variance import DEFAULT_VARIANCE_SAMPLES
    assert fake_variance_call["samples_count"] == 2
    assert fake_variance_call["max_samples"] == DEFAULT_VARIANCE_SAMPLES
    # Variance value persisted
    assert result.judge_variance == 0.025
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_run_optimization_without_judge_skips_variance():
    """include_judge=False (default): no judge calls, no variance sampling."""
    run_doc = _make_run_doc()
    ss = _make_search_set()
    tc = _make_test_case()

    results = [
        {"label": "baseline-no-tool", "model": "m", "config_override": {},
         "accuracy": 0.2, "consistency": 0.6, "score": 36.0, "elapsed_seconds": 1.0},
        {"label": "baseline-default", "model": "claude-haiku", "config_override": {"model": "claude-haiku"},
         "accuracy": 0.5, "consistency": 0.8, "score": 62.0, "elapsed_seconds": 1.0},
        {"label": "trial-1", "model": "m1", "config_override": {},
         "accuracy": 0.7, "consistency": 0.9, "score": 78.0, "elapsed_seconds": 1.0},
    ]
    call_iter = iter(results)
    captured_judge_models: list = []

    async def fake_run_single_config(**kwargs):
        captured_judge_models.append(kwargs.get("judge_model"))
        return next(call_iter)

    candidates = [{"label": "trial-1", "model": "m1", "config_override": {}}]
    variance_called = False

    async def fake_sample_variance(**kwargs):
        nonlocal variance_called
        variance_called = True
        return (0.01, 0)

    with (
        patch.object(extraction_optimizer, "ExtractionOptimizationRun") as MockRun,
        patch.object(extraction_optimizer, "ExtractionTestCase") as MockTC,
        patch.object(extraction_optimizer, "SearchSet") as MockSS,
        patch.object(extraction_optimizer, "SystemConfig") as MockSC,
        patch.object(extraction_optimizer, "get_extraction_keys",
                     new=AsyncMock(return_value=["PI Name"])),
        patch.object(extraction_optimizer, "get_extraction_field_metadata",
                     new=AsyncMock(return_value=[])),
        patch.object(extraction_optimizer, "get_user_model_name",
                     new=AsyncMock(return_value="claude-haiku")),
        patch.object(extraction_optimizer, "_build_candidate_configs",
                     return_value=candidates),
        patch.object(extraction_optimizer, "_run_single_config",
                     new=AsyncMock(side_effect=fake_run_single_config)),
        patch("app.services.judge_variance.sample_judge_variance",
              new=AsyncMock(side_effect=fake_sample_variance)),
    ):
        MockRun.find_one = AsyncMock(return_value=run_doc)
        find_call = MagicMock(); find_call.to_list = AsyncMock(return_value=[tc])
        MockTC.find = MagicMock(return_value=find_call)
        MockSS.find_one = AsyncMock(return_value=ss)
        sys_cfg = MagicMock(); sys_cfg.available_models = []
        sys_cfg.model_dump = MagicMock(return_value={})
        MockSC.get_config = AsyncMock(return_value=sys_cfg)

        result = await extraction_optimizer.run_optimization(
            search_set_uuid="ss-1", user_id="u1", run_uuid="opt-1",
            include_judge=False, max_candidates=1,
        )

    # No judge — every _run_single_config got judge_model=None
    assert captured_judge_models == [None, None, None]
    assert result.judge_model is None
    # Variance NOT sampled (judge off)
    assert variance_called is False
    assert result.judge_variance is None


# ---------------------------------------------------------------------------
# Recommendations engine (_generate_suggestions)
# ---------------------------------------------------------------------------


def test_suggestions_empty_when_everything_is_strong():
    """Strong scores + no weak fields = no suggestions to show."""
    out = _generate_suggestions(
        field_breakdown=[
            {"field": "PI Name", "accuracy": 0.95, "consistency": 0.95},
            {"field": "Amount", "accuracy": 0.9, "consistency": 0.92},
        ],
        baseline_no_tool=0.4,
        baseline_default=0.7,
        optimized=0.93,
    )
    assert out == []


def test_suggestions_flags_weak_field_as_critical_below_30pct():
    out = _generate_suggestions(
        field_breakdown=[
            {"field": "Amount", "accuracy": 0.2, "consistency": 0.95},  # disaster
        ],
        baseline_no_tool=0.1,
        baseline_default=0.2,
        optimized=0.2,
    )
    weak = [s for s in out if s["kind"] == "weak_field"]
    assert len(weak) == 1
    assert weak[0]["severity"] == "critical"
    assert weak[0]["field"] == "Amount"
    assert "20%" in weak[0]["message"]


def test_suggestions_flags_weak_field_as_warning_between_30_and_50():
    out = _generate_suggestions(
        field_breakdown=[
            {"field": "Award Date", "accuracy": 0.4, "consistency": 0.9},
        ],
        baseline_no_tool=0.3,
        baseline_default=0.35,
        optimized=0.4,
    )
    weak = [s for s in out if s["kind"] == "weak_field"]
    assert len(weak) == 1
    assert weak[0]["severity"] == "warning"


def test_suggestions_flags_unstable_field_when_accuracy_acceptable():
    """Acceptable accuracy + low consistency = unstable, not weak."""
    out = _generate_suggestions(
        field_breakdown=[
            {"field": "Address", "accuracy": 0.75, "consistency": 0.4},
        ],
        baseline_no_tool=None, baseline_default=None, optimized=None,
    )
    unstable = [s for s in out if s["kind"] == "unstable_field"]
    assert len(unstable) == 1
    assert unstable[0]["field"] == "Address"
    assert "40%" in unstable[0]["message"]


def test_suggestions_skip_unstable_when_already_weak():
    """Weak fields don't double up with unstable suggestions — accuracy is the priority signal."""
    out = _generate_suggestions(
        field_breakdown=[
            {"field": "X", "accuracy": 0.2, "consistency": 0.3},  # both bad
        ],
        baseline_no_tool=None, baseline_default=None, optimized=None,
    )
    kinds_for_x = [s["kind"] for s in out if s.get("field") == "X"]
    assert "weak_field" in kinds_for_x
    assert "unstable_field" not in kinds_for_x


def test_suggestions_flags_redundant_tool_when_no_tool_matches_optimized():
    """no-tool ≈ optimized → extraction tool isn't earning its complexity."""
    out = _generate_suggestions(
        field_breakdown=[],
        baseline_no_tool=0.87,
        baseline_default=0.88,
        optimized=0.89,  # lift over no-tool is only 2pts
    )
    redundant = [s for s in out if s["kind"] == "redundant_tool"]
    assert len(redundant) == 1
    assert redundant[0]["severity"] == "info"
    assert "87%" in redundant[0]["message"]


def test_suggestions_skip_redundant_tool_when_baselines_low():
    """When everything is low quality, "redundant" isn't useful framing — the
    user has bigger problems than tool overhead."""
    out = _generate_suggestions(
        field_breakdown=[],
        baseline_no_tool=0.4,  # below the REDUNDANT_TOOL_MIN_SCORE floor
        baseline_default=0.45,
        optimized=0.5,
    )
    assert not any(s["kind"] == "redundant_tool" for s in out)


def test_suggestions_flags_already_good_when_optimizer_finds_no_lift():
    """Strong existing config + tiny lift = info that current is already good."""
    out = _generate_suggestions(
        field_breakdown=[],
        baseline_no_tool=0.5,
        baseline_default=0.85,
        optimized=0.86,  # 1pt lift from a strong baseline
    )
    info = [s for s in out if s["kind"] == "already_good"]
    assert len(info) == 1
    assert info[0]["severity"] == "info"
    assert "85%" in info[0]["message"]


def test_suggestions_ordered_critical_warning_info():
    """Critical issues surface first; info notes last. Within tier, insertion order preserved."""
    out = _generate_suggestions(
        field_breakdown=[
            {"field": "Strong", "accuracy": 0.95, "consistency": 0.95},  # no suggestion
            {"field": "Weak", "accuracy": 0.2, "consistency": 0.95},     # critical
            {"field": "Unstable", "accuracy": 0.75, "consistency": 0.3}, # warning
        ],
        baseline_no_tool=0.85,
        baseline_default=0.85,
        optimized=0.87,  # close to no-tool → redundant_tool (info)
    )
    severities = [s["severity"] for s in out]
    # Critical < warning < info ordering, strictly increasing rank
    rank = {"critical": 0, "warning": 1, "info": 2}
    ranks = [rank[s] for s in severities]
    assert ranks == sorted(ranks)


def test_suggestions_handles_none_baselines():
    """Missing baselines (mid-run snapshot) don't crash the suggestion engine."""
    out = _generate_suggestions(
        field_breakdown=[{"field": "X", "accuracy": 0.4, "consistency": 0.9}],
        baseline_no_tool=None,
        baseline_default=None,
        optimized=None,
    )
    # Only field-level suggestions surface; no run-level since baselines absent
    assert any(s["kind"] == "weak_field" for s in out)
    assert not any(s["kind"] in {"redundant_tool", "already_good"} for s in out)


def test_suggestions_skip_fields_with_no_accuracy():
    """Malformed field_breakdown entries (no accuracy key) are silently ignored."""
    out = _generate_suggestions(
        field_breakdown=[
            {"field": "X"},  # no accuracy — skip
            {"field": "Y", "accuracy": 0.2, "consistency": 0.5},  # real
        ],
        baseline_no_tool=None, baseline_default=None, optimized=None,
    )
    fields_flagged = {s.get("field") for s in out if s.get("field")}
    assert "Y" in fields_flagged
    assert "X" not in fields_flagged
