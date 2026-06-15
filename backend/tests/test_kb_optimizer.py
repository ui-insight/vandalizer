"""Tests for KBOptimizer — search space, sampling, trial loop, suggestions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import kb_optimizer
from app.services.kb_optimizer import (
    KBOptimizer,
    _build_search_space,
    _blended_quality_score,
    _sample_trial_configs,
    BLEND_WEIGHT_COVERAGE,
    BLEND_WEIGHT_HEALTH,
    BLEND_WEIGHT_JUDGE,
    BLEND_WEIGHT_RETRIEVAL,
    DEFAULT_TRIAL_TOKEN_ESTIMATE,
    MAX_TRIAL_COUNT,
)


# ---------------------------------------------------------------------------
# Search space + sampling
# ---------------------------------------------------------------------------


def test_build_search_space_with_no_models_uses_caller_default():
    """When the system has no enabled models, search space still has one
    'model=None' axis so the optimizer can sweep other knobs."""
    space = _build_search_space(enabled_models=None)
    assert all(c["model"] is None for c in space)
    # k × models × prompt × rewrite × labels × rerank × answer_temperature
    assert len(space) == 6 * 1 * 3 * 2 * 2 * 2 * 2


def test_build_search_space_with_three_models_multiplies_size():
    space = _build_search_space(enabled_models=["m1", "m2", "m3"])
    assert len(space) == 6 * 3 * 3 * 2 * 2 * 2 * 2


def test_build_search_space_includes_all_combinations():
    """Spot check: at least one config has every non-default knob set."""
    space = _build_search_space(enabled_models=["m1"])
    assert any(
        c["k"] == 16 and c["prompt_variant"] == "strict"
        and c["query_rewriting"] is True
        and c["source_label_visibility"] is False
        and c["rerank"] == "llm"
        and c["answer_temperature"] == 0.3
        for c in space
    )


def test_sample_trial_configs_respects_token_budget():
    """Budget of 500k tokens / 100k per trial → 5 trials."""
    space = _build_search_space(enabled_models=["m1"])
    sampled = _sample_trial_configs(space, token_budget=500_000)
    assert len(sampled) == 5


def test_sample_trial_configs_caps_at_max_trial_count():
    """Even an enormous budget can't blow past MAX_TRIAL_COUNT."""
    space = _build_search_space(enabled_models=["m1", "m2", "m3"])
    sampled = _sample_trial_configs(space, token_budget=10**12)
    assert len(sampled) <= MAX_TRIAL_COUNT


def test_sample_trial_configs_zero_budget_returns_empty():
    space = _build_search_space(enabled_models=None)
    assert _sample_trial_configs(space, token_budget=0) == []


def test_sample_trial_configs_no_duplicates():
    """Sampling without replacement — each config appears at most once."""
    import random as rnd
    space = _build_search_space(enabled_models=["m1"])
    sampled = _sample_trial_configs(
        space, token_budget=DEFAULT_TRIAL_TOKEN_ESTIMATE * 20, rng=rnd.Random(42),
    )
    seen = {tuple(sorted(c.items())) for c in sampled}
    assert len(seen) == len(sampled)


# ---------------------------------------------------------------------------
# Suggestion analyser
# ---------------------------------------------------------------------------


def test_analyse_suggestions_low_lift_baseline_emits_warning():
    """When KB barely beats no-retrieval, surface a warning."""
    out = KBOptimizer()._analyse_suggestions(
        # Judge-vs-judge comparison: default_kb_judge tracks raw judge so the
        # low-lift detector ignores invariants (health/coverage/retrieval).
        trials=[{"score": 0.65, "status": "completed"}],
        baselines={"no_kb": 0.60, "default_kb": 0.65, "default_kb_judge": 0.65},
        test_queries=[],
    )
    kinds = {s["kind"] for s in out}
    assert "low_lift_baseline" in kinds


def test_analyse_suggestions_low_lift_not_emitted_when_judge_lifts_clearly():
    """High invariants must not mask a real judge lift — the warning is
    keyed off the raw judge baseline, not the blended ``default_kb``."""
    out = KBOptimizer()._analyse_suggestions(
        trials=[{"score": 0.78, "status": "completed"}],
        baselines={
            "no_kb": 0.40,                # raw judge baseline (model alone)
            "default_kb": 0.78,           # blended (judge + healthy invariants)
            "default_kb_judge": 0.65,     # raw judge with default KB
        },
        test_queries=[],
    )
    kinds = {s["kind"] for s in out}
    assert "low_lift_baseline" not in kinds


def test_blended_quality_score_matches_validation_header_weights():
    """The optimizer's blend must match ``run_kb_validation``'s 40/25/20/15."""
    # Hand-computed expected value: 0.80 * 0.40 + 0.70 * 0.25 + 1.00 * 0.20 + 0.90 * 0.15
    #                             = 0.320 + 0.175 + 0.200 + 0.135 = 0.830
    assert _blended_quality_score(0.80, 0.70, 1.00, 0.90) == pytest.approx(0.830, abs=1e-9)
    # Weights themselves sum to 1.0.
    assert (
        BLEND_WEIGHT_JUDGE + BLEND_WEIGHT_RETRIEVAL
        + BLEND_WEIGHT_HEALTH + BLEND_WEIGHT_COVERAGE
    ) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_run_trial_early_stops_below_current_best():
    """A trial whose partial judge mean is > 2σ below the current best should
    short-circuit instead of running to completion. Verifies via the captured
    ``early_stop_reason="below_best"`` marker on the returned trial dict."""
    from app.services.kb_validation_service import RAGConfig
    tq_list = [MagicMock(uuid=f"q{i}", query=f"Q{i}", expected_answer="A") for i in range(8)]

    # Simulate judge_test_queries honouring the early_stop_callback: after
    # min_to_check queries with a low partial mean, return early_stopped=True.
    async def fake_judge(kb_uuid, queries, model, mode="judge", judge_model=None,
                          early_stop_callback=None, **_kw):
        partial: list[float] = []
        for _ in queries:
            partial.append(0.20)  # clearly below the best=0.80
            if early_stop_callback and early_stop_callback(partial):
                return {
                    "details": [],
                    "avg_judge_score": sum(partial) / len(partial),
                    "num_queries_judged": len(partial),
                    "early_stopped": True,
                    "tokens_used": 1000,
                }
        return {
            "details": [],
            "avg_judge_score": sum(partial) / len(partial),
            "num_queries_judged": len(partial),
            "tokens_used": 5000,
        }

    with patch.object(kb_optimizer.kb_validation_service, "judge_test_queries",
                       side_effect=fake_judge):
        result = await KBOptimizer()._run_trial(
            cfg_dict=RAGConfig().model_dump(),
            kb_uuid="kb-1", user_id="u1",
            test_queries=tq_list,
            fallback_model="m1",
            baseline_default_score=0.60,
            baseline_no_kb_score=0.10,  # very low → no_kb threshold won't trigger
            judge_variance=0.05,
            retrieval_score=1.0, health_score=1.0, coverage_score=1.0,
            current_best_judge_score=0.80,  # current best, 2σ band = [0.70, 0.90]
        )

    assert result["status"] == "early_stopped"
    assert result.get("early_stop_reason") == "below_best"
    # With min_to_check = max(2, 8//4) = 2 and partial mean 0.20 < 0.70 threshold,
    # the trial stops well before processing all 8 queries.
    assert result["num_queries_judged"] < len(tq_list)


def test_blended_quality_score_only_judge_varies_within_run():
    """When retrieval/health/coverage are fixed, two trials' blend deltas equal
    the judge delta scaled by BLEND_WEIGHT_JUDGE — this is the property that
    justifies σ_blended = 0.40 × σ_judge in convergence + winner-selection."""
    fixed = dict(retrieval_score=0.50, health_score=0.80, coverage_score=0.70)
    blended_a = _blended_quality_score(judge_score=0.60, **fixed)
    blended_b = _blended_quality_score(judge_score=0.80, **fixed)
    judge_delta = 0.80 - 0.60
    assert blended_b - blended_a == pytest.approx(BLEND_WEIGHT_JUDGE * judge_delta)


def test_analyse_suggestions_coverage_gap_when_best_score_low():
    out = KBOptimizer()._analyse_suggestions(
        trials=[{"score": 0.40, "status": "completed"}, {"score": 0.35, "status": "completed"}],
        baselines={"no_kb": 0.20, "default_kb": 0.35},
        test_queries=[],
    )
    kinds = {s["kind"] for s in out}
    assert "coverage_gap" in kinds


def test_analyse_suggestions_saturated_when_optimizer_finds_no_room():
    out = KBOptimizer()._analyse_suggestions(
        trials=[{"score": 0.86, "status": "completed"}, {"score": 0.85, "status": "completed"}],
        baselines={"no_kb": 0.30, "default_kb": 0.85},
        test_queries=[],
    )
    assert any(s["kind"] == "saturated" for s in out)


def test_analyse_suggestions_retrieval_bottleneck_when_high_variance():
    """Best trial much higher than median → fragile retrieval."""
    out = KBOptimizer()._analyse_suggestions(
        trials=[
            {"score": 0.85, "status": "completed"},
            {"score": 0.42, "status": "completed"},
            {"score": 0.40, "status": "completed"},
            {"score": 0.45, "status": "completed"},
        ],
        baselines={"no_kb": 0.30, "default_kb": 0.42},
        test_queries=[],
    )
    assert any(s["kind"] == "retrieval_bottleneck" for s in out)


def test_analyse_suggestions_empty_trials_returns_empty():
    out = KBOptimizer()._analyse_suggestions(
        trials=[], baselines={"no_kb": 0, "default_kb": 0}, test_queries=[],
    )
    assert out == []


# ---------------------------------------------------------------------------
# End-to-end run() (heavily mocked)
# ---------------------------------------------------------------------------


def _make_run_doc(uuid="opt-1", **kw) -> MagicMock:
    """Build a mock that supports both attribute access and async save()."""
    rd = MagicMock()
    rd.uuid = uuid
    rd.kb_uuid = kw.get("kb_uuid", "kb-1")
    rd.user_id = kw.get("user_id", "u1")
    rd.status = "queued"
    rd.phase = "queued"
    rd.tokens_used = 0
    rd.cancel_requested = False
    rd.trials = []
    rd.options = kw.get("options", {})
    rd.best_score_so_far = None
    rd.best_config_so_far = None
    rd.save = AsyncMock()
    return rd


def _patch_invariants(
    *,
    health: float = 1.0,
    coverage: float = 1.0,
    retrieval: float = 1.0,
):
    """Return a list of patch context managers that stub the config-invariant
    metrics ``_establish_baselines`` now reads at run start (health, coverage,
    retrieval precision, default RAGConfig). Tests compose them into their
    ``with`` blocks alongside the existing judge mocks."""
    from app.services.kb_validation_service import RAGConfig
    return [
        patch.object(kb_optimizer.kb_validation_service, "check_source_health",
                     new=AsyncMock(return_value={"ratio": health, "total": 1, "healthy": 1})),
        patch.object(kb_optimizer.kb_validation_service, "check_chunk_coverage",
                     new=AsyncMock(return_value={"ratio": coverage, "total": 1, "with_chunks": 1, "total_chunks": 1})),
        patch.object(kb_optimizer.kb_validation_service, "check_retrieval_precision",
                     new=AsyncMock(return_value={"avg_precision": retrieval, "total_queries": 1, "details": []})),
        patch.object(kb_optimizer.kb_validation_service, "_resolve_rag_config",
                     new=AsyncMock(return_value=RAGConfig())),
    ]


@pytest.mark.asyncio
async def test_run_completes_with_no_test_queries_triggers_autogen():
    """If the KB has no expected_answer queries, run() auto-generates them."""
    run_doc = _make_run_doc()
    fake_kb = MagicMock()
    fake_kb.uuid = "kb-1"
    fake_kb.title = "KB"
    generated_query = MagicMock()
    generated_query.uuid = "tq-gen"
    generated_query.query = "What is X?"
    generated_query.expected_answer = "X is foo."

    fake_gen = MagicMock()
    fake_gen.generate = AsyncMock(return_value=[generated_query])

    with patch.object(kb_optimizer, "KBOptimizationRun") as KBR, \
         patch.object(kb_optimizer, "KnowledgeBase") as KB, \
         patch.object(kb_optimizer, "KBTestQuery") as KBTQ, \
         patch.object(kb_optimizer, "SystemConfig") as SC, \
         patch("app.services.kb_question_generator.KBQuestionGenerator", return_value=fake_gen), \
         patch("app.services.workflow_validator._resolve_model_name", return_value="m1"), \
         patch.object(kb_optimizer.kb_validation_service, "judge_baselines_only", new=AsyncMock(return_value={
             "avg_baseline_score": 0.3, "num_baselines_judged": 1, "tokens_used": 0,
             "details": [{"query_uuid": "tq-gen", "baseline_judge": {"score": 0.3, "verdict": "FAIL"}}],
         })), \
         patch.object(kb_optimizer.kb_validation_service, "judge_test_queries", new=AsyncMock(return_value={
             "details": [{"query_uuid": "tq-gen", "judge": {"score": 0.7, "verdict": "PASS"}, "actual_answer": "x"}],
             "avg_judge_score": 0.7, "avg_baseline_score": 0.3, "avg_lift": 0.4,
             "num_queries_judged": 1, "num_queries_baselined": 1,
             "discrimination_summary": {"useful": 1, "redundant": 0, "failing": 0, "other": 0},
         })), \
         patch.object(kb_optimizer.kb_validation_service, "_judge_answer", new=AsyncMock(return_value={"score": 0.7})), \
         patch.object(kb_optimizer.kb_validation_service, "check_source_health",
                      new=AsyncMock(return_value={"ratio": 1.0, "total": 1, "healthy": 1})), \
         patch.object(kb_optimizer.kb_validation_service, "check_chunk_coverage",
                      new=AsyncMock(return_value={"ratio": 1.0, "total": 1, "with_chunks": 1, "total_chunks": 1})), \
         patch.object(kb_optimizer.kb_validation_service, "check_retrieval_precision",
                      new=AsyncMock(return_value={"avg_precision": 1.0, "total_queries": 1, "details": []})), \
         patch.object(kb_optimizer.kb_validation_service, "_resolve_rag_config",
                      new=AsyncMock(return_value=kb_optimizer.kb_validation_service.RAGConfig())):
        KBR.find_one = AsyncMock(return_value=run_doc)
        KB.find_one = AsyncMock(return_value=fake_kb)
        # No existing test queries
        find_call = MagicMock(); find_call.to_list = AsyncMock(return_value=[])
        KBTQ.find = MagicMock(return_value=find_call)
        sys_cfg = MagicMock(); sys_cfg.available_models = [{"name": "m1"}]
        SC.get_config = AsyncMock(return_value=sys_cfg)

        result = await KBOptimizer().run(
            kb_uuid="kb-1", user_id="u1", run_uuid="opt-1",
            token_budget=300_000,
        )

    fake_gen.generate.assert_awaited_once()
    assert result.status == "completed"
    # baseline_no_kb_score stays as raw judge (no KB → nothing to blend).
    assert result.baseline_no_kb_score == 0.3
    # baseline_default_score is now blended: 0.7*0.40 + 1.0*0.25 + 1.0*0.20 + 1.0*0.15 = 0.88.
    assert result.baseline_default_score == pytest.approx(0.88, abs=1e-4)
    # Raw judge default is persisted separately for lift CI math.
    assert result.baseline_default_judge_score == 0.7


@pytest.mark.asyncio
async def test_run_records_trials_and_picks_winner():
    """Optimizer should record every trial + pick the highest-scoring config."""
    run_doc = _make_run_doc()
    fake_kb = MagicMock(); fake_kb.uuid = "kb-1"; fake_kb.title = "KB"
    tq = MagicMock(); tq.uuid = "tq-1"; tq.query = "Q?"; tq.expected_answer = "A."

    # judge_test_queries returns different scores depending on the trial config.
    # We mark each call with the passed-in model name so we can track what won.
    call_count = {"n": 0}
    scores = [0.5, 0.7, 0.6, 0.9, 0.4]  # default-KB baseline + 4 trials

    async def fake_judge(kb_uuid, queries, model, mode="judge", judge_model=None, concurrency=4, **_kw):
        n = call_count["n"]
        call_count["n"] += 1
        s = scores[n] if n < len(scores) else 0.5
        return {
            "details": [{"query_uuid": "tq-1", "judge": {"score": s, "verdict": "PASS"}, "actual_answer": "x"}],
            "avg_judge_score": s, "num_queries_judged": 1,
            "discrimination_summary": {"useful": 1, "redundant": 0, "failing": 0, "other": 0},
        }

    with patch.object(kb_optimizer, "KBOptimizationRun") as KBR, \
         patch.object(kb_optimizer, "KnowledgeBase") as KB, \
         patch.object(kb_optimizer, "KBTestQuery") as KBTQ, \
         patch.object(kb_optimizer, "SystemConfig") as SC, \
         patch("app.services.workflow_validator._resolve_model_name", return_value="m1"), \
         patch.object(kb_optimizer.kb_validation_service, "judge_baselines_only", new=AsyncMock(return_value={
             "avg_baseline_score": 0.2, "num_baselines_judged": 1, "tokens_used": 0,
             "details": [{"query_uuid": "tq-1", "baseline_judge": {"score": 0.2, "verdict": "FAIL"}}],
         })), \
         patch.object(kb_optimizer.kb_validation_service, "judge_test_queries", side_effect=fake_judge), \
         patch.object(kb_optimizer.kb_validation_service, "_judge_answer", new=AsyncMock(return_value={"score": 0.5})), \
         patch.object(kb_optimizer.kb_validation_service, "check_source_health",
                      new=AsyncMock(return_value={"ratio": 1.0, "total": 1, "healthy": 1})), \
         patch.object(kb_optimizer.kb_validation_service, "check_chunk_coverage",
                      new=AsyncMock(return_value={"ratio": 1.0, "total": 1, "with_chunks": 1, "total_chunks": 1})), \
         patch.object(kb_optimizer.kb_validation_service, "check_retrieval_precision",
                      new=AsyncMock(return_value={"avg_precision": 1.0, "total_queries": 1, "details": []})), \
         patch.object(kb_optimizer.kb_validation_service, "_resolve_rag_config",
                      new=AsyncMock(return_value=kb_optimizer.kb_validation_service.RAGConfig())):
        KBR.find_one = AsyncMock(return_value=run_doc)
        KB.find_one = AsyncMock(return_value=fake_kb)
        find_call = MagicMock(); find_call.to_list = AsyncMock(return_value=[tq])
        KBTQ.find = MagicMock(return_value=find_call)
        sys_cfg = MagicMock(); sys_cfg.available_models = [{"name": "m1"}]
        SC.get_config = AsyncMock(return_value=sys_cfg)

        # Budget = 4× per-trial estimate. With real token accounting, mocked
        # agents report 0 tokens, so the baseline pass doesn't consume budget;
        # we expect 4 trials. (When the agents actually return usage, baseline
        # tokens reduce the trial count — covered by integration tests.)
        await KBOptimizer().run(
            kb_uuid="kb-1", user_id="u1", run_uuid="opt-1",
            token_budget=DEFAULT_TRIAL_TOKEN_ESTIMATE * 4,
            rng_seed=123,
        )

    assert run_doc.status == "completed"
    assert len(run_doc.trials) == 4
    # Best raw judge score is max(0.7, 0.6, 0.9, 0.4) = 0.9.
    # optimized_score is now BLENDED (judge 40% + retrieval 25% + health 20%
    # + coverage 15%): 0.4*0.9 + 0.25*1.0 + 0.2*1.0 + 0.15*1.0 = 0.96.
    assert run_doc.optimized_score == pytest.approx(0.96, abs=1e-4)
    assert run_doc.best_score_so_far == pytest.approx(0.96, abs=1e-4)
    assert run_doc.best_config is not None


@pytest.mark.asyncio
async def test_run_honours_cancellation_between_trials():
    """When cancel_requested flips mid-run, status flips to cancelled."""
    run_doc = _make_run_doc()
    fake_kb = MagicMock(); fake_kb.uuid = "kb-1"; fake_kb.title = "KB"
    tq = MagicMock(); tq.uuid = "tq-1"; tq.query = "Q?"; tq.expected_answer = "A."

    # Simulate cancellation after the first trial.
    fresh_doc_states = [
        MagicMock(cancel_requested=False),
        MagicMock(cancel_requested=True),  # second loop iteration sees cancellation
    ]

    async def find_run_one(*a, **kw):
        # First call returns the live run_doc itself (initial load).
        # Subsequent calls return the cancellation states.
        if not fresh_doc_states:
            return run_doc
        if find_run_one.first_call:
            find_run_one.first_call = False
            return run_doc
        return fresh_doc_states.pop(0)
    find_run_one.first_call = True

    async def fake_judge(kb_uuid, queries, model, mode="judge", judge_model=None, concurrency=4, **_kw):
        return {
            "details": [{"query_uuid": "tq-1", "judge": {"score": 0.5, "verdict": "WARN"}, "actual_answer": "x"}],
            "avg_judge_score": 0.5, "num_queries_judged": 1,
            "discrimination_summary": None,
        }

    with patch.object(kb_optimizer, "KBOptimizationRun") as KBR, \
         patch.object(kb_optimizer, "KnowledgeBase") as KB, \
         patch.object(kb_optimizer, "KBTestQuery") as KBTQ, \
         patch.object(kb_optimizer, "SystemConfig") as SC, \
         patch("app.services.workflow_validator._resolve_model_name", return_value="m1"), \
         patch.object(kb_optimizer.kb_validation_service, "judge_baselines_only", new=AsyncMock(return_value={
             "avg_baseline_score": 0.2, "num_baselines_judged": 1, "tokens_used": 0,
             "details": [{"query_uuid": "tq-1", "baseline_judge": {"score": 0.2, "verdict": "FAIL"}}],
         })), \
         patch.object(kb_optimizer.kb_validation_service, "judge_test_queries", side_effect=fake_judge), \
         patch.object(kb_optimizer.kb_validation_service, "_judge_answer", new=AsyncMock(return_value={"score": 0.5})), \
         patch.object(kb_optimizer.kb_validation_service, "check_source_health",
                      new=AsyncMock(return_value={"ratio": 1.0, "total": 1, "healthy": 1})), \
         patch.object(kb_optimizer.kb_validation_service, "check_chunk_coverage",
                      new=AsyncMock(return_value={"ratio": 1.0, "total": 1, "with_chunks": 1, "total_chunks": 1})), \
         patch.object(kb_optimizer.kb_validation_service, "check_retrieval_precision",
                      new=AsyncMock(return_value={"avg_precision": 1.0, "total_queries": 1, "details": []})), \
         patch.object(kb_optimizer.kb_validation_service, "_resolve_rag_config",
                      new=AsyncMock(return_value=kb_optimizer.kb_validation_service.RAGConfig())):
        KBR.find_one = AsyncMock(side_effect=find_run_one)
        KB.find_one = AsyncMock(return_value=fake_kb)
        find_call = MagicMock(); find_call.to_list = AsyncMock(return_value=[tq])
        KBTQ.find = MagicMock(return_value=find_call)
        sys_cfg = MagicMock(); sys_cfg.available_models = [{"name": "m1"}]
        SC.get_config = AsyncMock(return_value=sys_cfg)

        await KBOptimizer().run(
            kb_uuid="kb-1", user_id="u1", run_uuid="opt-1",
            token_budget=DEFAULT_TRIAL_TOKEN_ESTIMATE * 5,
            rng_seed=7,
        )

    assert run_doc.status == "cancelled"
    assert run_doc.phase == "cancelled"


@pytest.mark.asyncio
async def test_run_apply_on_finish_writes_kb_override():
    """When apply_on_finish=True, the winning config is written to KB."""
    run_doc = _make_run_doc()
    fake_kb = MagicMock(); fake_kb.uuid = "kb-1"; fake_kb.title = "KB"
    fake_kb.save = AsyncMock()
    tq = MagicMock(); tq.uuid = "tq-1"; tq.query = "Q?"; tq.expected_answer = "A."

    call_count = {"n": 0}

    async def fake_judge(kb_uuid, queries, model, mode="judge", judge_model=None, concurrency=4, **_kw):
        # First call is the default-KB baseline pass (score 0.4); subsequent
        # calls are per-trial and return the higher 0.85 winning score.
        n = call_count["n"]
        call_count["n"] += 1
        if n == 0:
            return {
                "details": [{"query_uuid": "tq-1", "judge": {"score": 0.4, "verdict": "WARN"}, "actual_answer": "x"}],
                "avg_judge_score": 0.4, "num_queries_judged": 1,
                "discrimination_summary": None,
            }
        return {
            "details": [{"query_uuid": "tq-1", "judge": {"score": 0.85, "verdict": "PASS"}, "actual_answer": "x"}],
            "avg_judge_score": 0.85, "num_queries_judged": 1,
            "discrimination_summary": None,
        }

    with patch.object(kb_optimizer, "KBOptimizationRun") as KBR, \
         patch.object(kb_optimizer, "KnowledgeBase") as KB, \
         patch.object(kb_optimizer, "KBTestQuery") as KBTQ, \
         patch.object(kb_optimizer, "SystemConfig") as SC, \
         patch("app.services.workflow_validator._resolve_model_name", return_value="m1"), \
         patch.object(kb_optimizer.kb_validation_service, "judge_baselines_only", new=AsyncMock(return_value={
             "avg_baseline_score": 0.1, "num_baselines_judged": 1, "tokens_used": 0,
             "details": [{"query_uuid": "tq-1", "baseline_judge": {"score": 0.1, "verdict": "FAIL"}}],
         })), \
         patch.object(kb_optimizer.kb_validation_service, "judge_test_queries", side_effect=fake_judge), \
         patch.object(kb_optimizer.kb_validation_service, "_judge_answer", new=AsyncMock(return_value={"score": 0.85})), \
         patch.object(kb_optimizer.kb_validation_service, "check_source_health",
                      new=AsyncMock(return_value={"ratio": 1.0, "total": 1, "healthy": 1})), \
         patch.object(kb_optimizer.kb_validation_service, "check_chunk_coverage",
                      new=AsyncMock(return_value={"ratio": 1.0, "total": 1, "with_chunks": 1, "total_chunks": 1})), \
         patch.object(kb_optimizer.kb_validation_service, "check_retrieval_precision",
                      new=AsyncMock(return_value={"avg_precision": 1.0, "total_queries": 1, "details": []})), \
         patch.object(kb_optimizer.kb_validation_service, "_resolve_rag_config",
                      new=AsyncMock(return_value=kb_optimizer.kb_validation_service.RAGConfig())):
        KBR.find_one = AsyncMock(return_value=run_doc)
        KB.find_one = AsyncMock(return_value=fake_kb)
        find_call = MagicMock(); find_call.to_list = AsyncMock(return_value=[tq])
        KBTQ.find = MagicMock(return_value=find_call)
        sys_cfg = MagicMock(); sys_cfg.available_models = [{"name": "m1"}]
        SC.get_config = AsyncMock(return_value=sys_cfg)

        await KBOptimizer().run(
            kb_uuid="kb-1", user_id="u1", run_uuid="opt-1",
            token_budget=DEFAULT_TRIAL_TOKEN_ESTIMATE * 2,
            apply_on_finish=True,
            rng_seed=1,
        )

    fake_kb.save.assert_awaited()
    assert fake_kb.rag_config_override is not None
    assert fake_kb.rag_config_override_run_uuid == "opt-1"


@pytest.mark.asyncio
async def test_run_marks_failed_with_kb_not_found_classification():
    """When the KB lookup fails, persist a classified error_code so the UI
    FailedBanner can render plain-English remediation instead of the raw
    exception."""
    run_doc = _make_run_doc()

    with patch.object(kb_optimizer, "KBOptimizationRun") as KBR, \
         patch.object(kb_optimizer, "KnowledgeBase") as KB:
        KBR.find_one = AsyncMock(return_value=run_doc)
        KB.find_one = AsyncMock(return_value=None)  # KB missing → KBOptimizerError

        with pytest.raises(kb_optimizer.KBOptimizerError, match="Knowledge base not found"):
            await KBOptimizer().run(
                kb_uuid="kb-missing", user_id="u1", run_uuid="opt-1",
                token_budget=100_000,
            )

    assert run_doc.status == "failed"
    assert "Knowledge base not found" in (run_doc.error_message or "")
    assert run_doc.error_code == "kb_not_found"
    assert run_doc.error_context == {"kb_uuid": "kb-missing"}


@pytest.mark.asyncio
async def test_run_raises_when_pre_allocated_run_doc_missing():
    with patch.object(kb_optimizer, "KBOptimizationRun") as KBR:
        KBR.find_one = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await KBOptimizer().run(
                kb_uuid="kb-1", user_id="u1", run_uuid="missing",
                token_budget=100_000,
            )


def test_describe_config_summarises_only_non_default_knobs():
    out = KBOptimizer._describe_config({
        "k": 12, "model": "claude-haiku-4-5",
        "prompt_variant": "strict", "query_rewriting": True,
        "source_label_visibility": False,
    })
    assert "k=12" in out
    assert "claude-haiku-4-5" in out
    assert "strict" in out
    assert "query-rewrite" in out
    assert "no-source-labels" in out


def test_describe_config_omits_defaults():
    out = KBOptimizer._describe_config({
        "k": 8, "model": None, "prompt_variant": "default",
        "query_rewriting": False, "source_label_visibility": True,
    })
    assert out == "k=8"  # only k stays; everything else is default


# ---------------------------------------------------------------------------
# Terminal-state notifications
# ---------------------------------------------------------------------------


def _terminal_run_doc(status: str, **fields) -> MagicMock:
    """Stub a KBOptimizationRun in a given terminal state."""
    rd = MagicMock()
    rd.uuid = fields.get("uuid", "opt-1")
    rd.kb_uuid = fields.get("kb_uuid", "kb-1")
    rd.user_id = fields.get("user_id", "user1")
    rd.status = status
    rd.trials = fields.get("trials", [])
    rd.baseline_default_score = fields.get("baseline_default_score", 0.5)
    rd.optimized_score = fields.get("optimized_score", 0.85)
    rd.error_message = fields.get("error_message")
    return rd


def _kb_stub(title="My KB", uuid="kb-1"):
    kb = MagicMock()
    kb.title = title
    kb.uuid = uuid
    return kb


@pytest.mark.asyncio
async def test_notify_terminal_emits_completion_notification_with_lift():
    rd = _terminal_run_doc(
        "completed",
        baseline_default_score=0.55,
        optimized_score=0.85,
        trials=[{"trial_id": "t1"}, {"trial_id": "t2"}],
    )
    kb = _kb_stub("Grants KB")
    captured = {}

    async def fake_create_notification(**kw):
        captured.update(kw)
        return {}

    with patch(
        "app.services.notification_service.create_notification",
        new=AsyncMock(side_effect=fake_create_notification),
    ):
        await KBOptimizer()._notify_terminal(rd, kb)

    assert captured["kind"] == "kb_optimization_completed"
    assert captured["user_id"] == "user1"
    assert "Grants KB" in captured["title"]
    assert "85%" in captured["body"]
    assert "+30pts" in captured["body"]  # 85 - 55
    assert captured["item_kind"] == "knowledge_base"
    assert captured["item_id"] == "kb-1"
    assert captured["link"] == "/?mode=knowledge&kb=kb-1"


@pytest.mark.asyncio
async def test_notify_terminal_emits_cancelled_notification():
    rd = _terminal_run_doc("cancelled", trials=[{"t": 1}])
    kb = _kb_stub("KB-Cancelled")

    captured = {}

    async def fake(**kw):
        captured.update(kw)
        return {}

    with patch(
        "app.services.notification_service.create_notification",
        new=AsyncMock(side_effect=fake),
    ):
        await KBOptimizer()._notify_terminal(rd, kb)

    assert captured["kind"] == "kb_optimization_cancelled"
    assert "Cancelled" in captured["title"]
    assert "1 trial" in captured["body"]


@pytest.mark.asyncio
async def test_notify_terminal_emits_failed_notification_with_error_text():
    rd = _terminal_run_doc("failed", error_message="ModelMissingError: no model configured")
    kb = _kb_stub("Broken KB")

    captured = {}

    async def fake(**kw):
        captured.update(kw)
        return {}

    with patch(
        "app.services.notification_service.create_notification",
        new=AsyncMock(side_effect=fake),
    ):
        await KBOptimizer()._notify_terminal(rd, kb)

    assert captured["kind"] == "kb_optimization_failed"
    assert "ModelMissingError" in captured["body"]


@pytest.mark.asyncio
async def test_notify_terminal_swallows_create_notification_errors():
    """A notification failure must never break the optimizer's terminal flow."""
    rd = _terminal_run_doc("completed")
    kb = _kb_stub()

    with patch(
        "app.services.notification_service.create_notification",
        new=AsyncMock(side_effect=RuntimeError("notification db down")),
    ):
        # Should NOT raise.
        await KBOptimizer()._notify_terminal(rd, kb)


@pytest.mark.asyncio
async def test_notify_terminal_skips_non_terminal_status():
    """Non-terminal status (e.g. 'running') doesn't produce a notification."""
    rd = _terminal_run_doc("running")
    kb = _kb_stub()
    fake = AsyncMock()

    with patch("app.services.notification_service.create_notification", new=fake):
        await KBOptimizer()._notify_terminal(rd, kb)

    fake.assert_not_called()


@pytest.mark.asyncio
async def test_notify_terminal_falls_back_to_default_title_when_kb_missing():
    """If kb is None (defensive), we still emit a notification."""
    rd = _terminal_run_doc("completed", optimized_score=0.7, baseline_default_score=0.5)

    captured = {}

    async def fake(**kw):
        captured.update(kw)
        return {}

    with patch(
        "app.services.notification_service.create_notification",
        new=AsyncMock(side_effect=fake),
    ):
        await KBOptimizer()._notify_terminal(rd, None)

    # Title falls back to the generic "Knowledge base" name.
    assert "Knowledge base" in captured["title"]
    # Link still points to the correct KB UUID.
    assert "kb=kb-1" in captured["link"]


# ---------------------------------------------------------------------------
# _ensure_test_queries — Test-set build mode (existing / generate / combine)
# ---------------------------------------------------------------------------


def _make_tq(uuid: str, *, expected_answer: str | None = "ans"):
    q = MagicMock()
    q.uuid = uuid
    q.query = f"Q {uuid}?"
    q.expected_answer = expected_answer
    return q


@pytest.mark.asyncio
async def test_ensure_test_queries_uses_explicit_uuid_selection():
    """When the wizard passes test_query_uuids, only those are graded — the
    authoritative path that lets 'generate only' exclude pre-existing saved
    questions and 'combine' mix a curated set."""
    run_doc = _make_run_doc(options={"test_query_uuids": ["a", "b"]})
    chosen = [_make_tq("a"), _make_tq("b")]
    find_obj = MagicMock()
    find_obj.to_list = AsyncMock(return_value=chosen)
    gen = MagicMock()
    gen.generate = AsyncMock()

    with patch.object(kb_optimizer, "KBTestQuery") as KBTQ, \
         patch("app.services.kb_question_generator.KBQuestionGenerator", return_value=gen):
        KBTQ.find = MagicMock(return_value=find_obj)
        out = await KBOptimizer()._ensure_test_queries("kb-1", "u1", run_doc)

    assert [q.uuid for q in out] == ["a", "b"]
    # Curated set is authoritative — never falls through to auto-generation.
    gen.generate.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_test_queries_explicit_selection_drops_unanswered():
    """Selected questions without an expected_answer can't be judged, so they
    are filtered out of the eval set."""
    run_doc = _make_run_doc(options={"test_query_uuids": ["a", "b"]})
    chosen = [_make_tq("a"), _make_tq("b", expected_answer=None)]
    find_obj = MagicMock()
    find_obj.to_list = AsyncMock(return_value=chosen)

    with patch.object(kb_optimizer, "KBTestQuery") as KBTQ:
        KBTQ.find = MagicMock(return_value=find_obj)
        out = await KBOptimizer()._ensure_test_queries("kb-1", "u1", run_doc)

    assert [q.uuid for q in out] == ["a"]


@pytest.mark.asyncio
async def test_ensure_test_queries_falls_back_to_existing_when_no_uuids():
    """Without an explicit selection (older clients / passive re-runs) the
    legacy behaviour stands: use all saved questions, no generation."""
    run_doc = _make_run_doc(options={})
    existing = [_make_tq("x"), _make_tq("y")]
    find_obj = MagicMock()
    find_obj.to_list = AsyncMock(return_value=existing)
    gen = MagicMock()
    gen.generate = AsyncMock()

    with patch.object(kb_optimizer, "KBTestQuery") as KBTQ, \
         patch("app.services.kb_question_generator.KBQuestionGenerator", return_value=gen):
        KBTQ.find = MagicMock(return_value=find_obj)
        out = await KBOptimizer()._ensure_test_queries("kb-1", "u1", run_doc)

    assert [q.uuid for q in out] == ["x", "y"]
    gen.generate.assert_not_called()


# ---------------------------------------------------------------------------
# Cancellation — the cancel endpoint flips ``cancel_requested`` on a separate
# DB copy, so the worker must read the flag from the DB (not its stale,
# long-lived in-memory ``run_doc``) and must not clobber it on save. Regression
# for the ticket where clicking Cancel briefly showed "Cancelling" but tuning
# resumed because every full-document save reverted the flag to False.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_cancelled_reads_db_not_stale_in_memory_copy():
    """A cancel requested after the worker loaded run_doc is still detected."""
    run_doc = _make_run_doc()
    run_doc.cancel_requested = False  # worker's stale view

    db_copy = _make_run_doc()
    db_copy.cancel_requested = True  # endpoint flipped it in the DB

    with patch.object(
        kb_optimizer.KBOptimizationRun, "find_one",
        AsyncMock(return_value=db_copy),
    ):
        assert await kb_optimizer._is_cancelled(run_doc) is True

    # The fresh flag is synced forward so subsequent saves preserve it.
    assert run_doc.cancel_requested is True


@pytest.mark.asyncio
async def test_is_cancelled_false_when_no_cancel_pending():
    """The check is a no-op when neither memory nor DB has a cancel."""
    run_doc = _make_run_doc()
    db_copy = _make_run_doc()  # cancel_requested defaults to False

    with patch.object(
        kb_optimizer.KBOptimizationRun, "find_one",
        AsyncMock(return_value=db_copy),
    ):
        assert await kb_optimizer._is_cancelled(run_doc) is False


@pytest.mark.asyncio
async def test_save_preserves_concurrently_requested_cancel():
    """A full-document save must not revert a cancel set by the endpoint — the
    core bug that let tuning resume after Cancel."""
    run_doc = _make_run_doc()
    run_doc.cancel_requested = False

    db_copy = _make_run_doc()
    db_copy.cancel_requested = True

    with patch.object(
        kb_optimizer.KBOptimizationRun, "find_one",
        AsyncMock(return_value=db_copy),
    ):
        await kb_optimizer._save(run_doc)

    assert run_doc.cancel_requested is True  # not clobbered back to False
    run_doc.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_cancelled_sets_terminal_state_and_notifies():
    """Every cancel checkpoint routes here — it must persist the cancelled
    terminal state and fire the terminal notification."""
    run_doc = _make_run_doc()
    run_doc.cancel_requested = True
    opt = KBOptimizer()

    with patch.object(
        kb_optimizer.KBOptimizationRun, "find_one",
        AsyncMock(return_value=run_doc),
    ), patch.object(opt, "_notify_terminal", new=AsyncMock()) as notify:
        out = await opt._finalize_cancelled(run_doc, kb=MagicMock())

    assert out.status == "cancelled"
    assert out.phase == "cancelled"
    assert out.stopped_reason == "cancelled"
    assert out.completed_at is not None
    notify.assert_awaited_once()
