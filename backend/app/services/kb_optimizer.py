"""KB Autovalidate optimizer service.

Treats the existing LLM judge as a fitness function and sweeps cheap-track RAG
configurations (k, model, prompt_variant, query_rewriting,
source_label_visibility) to find the best-scoring combination for a KB's
test query set. Persists per-trial detail and live progress to a
``KBOptimizationRun`` document so the UI can poll while it runs.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
import random
from typing import Any
from uuid import uuid4

from app.models.kb_optimization_run import KBOptimizationRun
from app.models.kb_test_query import KBTestQuery
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.models.system_config import SystemConfig
from app.services import kb_validation_service
from app.services.kb_validation_service import RAGConfig
from app.services.lift_stats import paired_lift_bootstrap_ci
from app.services.optimization_common import (
    DEFAULT_JUDGE_NOISE_FLOOR,
    WINNER_TIE_SIGMAS,
    build_apply_preview,
    pick_winner_variance_aware,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Search space — cheap track only (v1)
# ---------------------------------------------------------------------------

K_VALUES = [4, 6, 8, 10, 12, 16]
PROMPT_VARIANTS = ["default", "strict", "concise"]
QUERY_REWRITING = [False, True]
SOURCE_LABEL_VISIBILITY = [True, False]
# T4.1: include LLM reranking as a sweep axis.
RERANK_VALUES = ["off", "llm"]
# T4.2: answer-generation temperature. 0.0 = legacy deterministic; the
# higher values explore whether varied generation helps any KBs.
ANSWER_TEMPERATURE_VALUES = [0.0, 0.3]

# How many trials at most we plan, regardless of budget. Caps DB document size.
MAX_TRIAL_COUNT = 100

# Conservative per-trial token estimate used for budget pacing — overridden
# after each trial by the actual usage we record from pydantic-ai.
DEFAULT_TRIAL_TOKEN_ESTIMATE = 100_000

# Auto-generation fallback when the user has no test queries yet but the
# optimizer is invoked anyway (e.g. via direct API call).
DEFAULT_AUTOGEN_COVERAGE = "standard"

# Identifier for the current KB judge prompt — bumps whenever the prompt's
# text materially changes so historical runs can be compared by judge version.
# Today we hash the live prompt string so a code-only change of the rubric
# automatically invalidates the version label.
def _current_judge_prompt_version() -> str:
    prompt = getattr(kb_validation_service, "KB_JUDGE_SYSTEM_PROMPT", "")
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
    return f"kb-judge-{digest}"


# Indifference band for improved/regressed/unchanged counters. 0.05 ≈ "5 pts
# on a 0..1 score" — anything smaller than that is treated as noise-floor flip.
PER_QUERY_DELTA_EPSILON = 0.05


# Blended quality weights — must match ``kb_validation_service.run_kb_validation``
# (judge 40% + retrieval 25% + health 20% + coverage 15%). Keeping these in
# one place means the optimizer's reported score always matches the validation
# header. If the weights change in run_kb_validation, change them here too.
BLEND_WEIGHT_JUDGE = 0.40
BLEND_WEIGHT_RETRIEVAL = 0.25
BLEND_WEIGHT_HEALTH = 0.20
BLEND_WEIGHT_COVERAGE = 0.15


class KBOptimizerError(Exception):
    """Classified failure raised by the optimizer.

    The outer ``run()`` catch persists ``code`` and ``context`` to the run
    document so the UI's ``FailedBanner`` can render plain-English remediation
    instead of a raw exception string.
    """

    def __init__(self, code: str, message: str, context: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.context = context or {}


def _blended_quality_score(
    judge_score: float,
    retrieval_score: float,
    health_score: float,
    coverage_score: float,
) -> float:
    """Compute the same 0..1 quality blend ``run_kb_validation`` reports.

    All inputs are 0..1 ratios. With retrieval/health/coverage constant within
    a single optimization run, only the judge component varies per trial — so
    σ_blended ≈ ``BLEND_WEIGHT_JUDGE × σ_judge`` for downstream noise math.
    """
    return (
        BLEND_WEIGHT_JUDGE * float(judge_score)
        + BLEND_WEIGHT_RETRIEVAL * float(retrieval_score)
        + BLEND_WEIGHT_HEALTH * float(health_score)
        + BLEND_WEIGHT_COVERAGE * float(coverage_score)
    )


# Cross-judge sanity-check budget headroom. We only run the alternate-judge
# pass when at least this many tokens remain after all trials + variance + CI
# work has completed. Keeps a thorough run from blowing past its budget on
# a "nice to have" diagnostic.
CROSS_JUDGE_TOKEN_RESERVE = 50_000


# Train/holdout split threshold. With fewer than this many judgeable queries
# the split would leave too few in either slice to be meaningful; we skip the
# split and flag ``overfitting_warning`` so the UI can caveat the headline.
HOLDOUT_MIN_QUERIES = 6
# Fraction of queries reserved for holdout. 1/3 trades slightly noisier
# holdout estimates for more training signal in winner selection.
HOLDOUT_FRACTION = 1.0 / 3.0

# Convergence-stop (T3.2): need at least this many trials before we can
# claim convergence. Random sampling means the first few trials don't
# explore enough to pick a defensible winner.
CONVERGENCE_MIN_TRIALS = 10
# Patience window — how many trials in a row without improving the best
# score before we declare convergence. Larger = more conservative.
CONVERGENCE_PATIENCE = 8


def _l0_distance_to_default(cfg: dict) -> int:
    """Count how many non-model axes deviate from RAGConfig defaults.

    Lower = closer to default. Used to break ties in the noise-floor cluster:
    we prefer the simpler config when the judge can't tell which is actually
    better. ``model`` is excluded because the "default model" varies per user.
    """
    distance = 0
    if cfg.get("k") != kb_validation_service.DEFAULT_K:
        distance += 1
    if cfg.get("prompt_variant", "default") != "default":
        distance += 1
    if cfg.get("query_rewriting") is True:
        distance += 1
    if cfg.get("source_label_visibility") is False:
        distance += 1
    if cfg.get("rerank", "off") != "off":
        distance += 1
    if float(cfg.get("answer_temperature", 0.0) or 0.0) != 0.0:
        distance += 1
    return distance


def _split_train_holdout(
    queries: list,
    kb_uuid: str,
) -> tuple[list, list]:
    """Deterministically partition queries into (train, holdout).

    Determinism is keyed on (kb_uuid, query_uuid) so re-running the same KB
    yields the same split — users comparing two runs see apples-to-apples
    numbers. Sort-by-hash beats random.shuffle here because it's stable across
    re-orderings of the input list.
    """
    if len(queries) < HOLDOUT_MIN_QUERIES:
        return list(queries), []

    def _bucket(q) -> str:
        uid = str(getattr(q, "uuid", "") or "")
        return hashlib.sha256(f"{kb_uuid}:{uid}".encode("utf-8")).hexdigest()

    ordered = sorted(queries, key=_bucket)
    n_holdout = max(1, int(round(len(ordered) * HOLDOUT_FRACTION)))
    # Holdout first in the sorted order so adding queries (which appear at
    # arbitrary hash positions) tends to grow train, not holdout — keeps
    # winner-selection signal scaling more gracefully.
    holdout = ordered[:n_holdout]
    train = ordered[n_holdout:]
    return train, holdout


def _condense_per_query_details(details: list[dict]) -> list[dict]:
    """Strip judge_test_queries' per-query output to the fields the UI needs.

    judge_test_queries returns the full ``actual_answer`` (already 2k-truncated)
    plus the full judge verdict per query. We persist a compact slice on each
    trial so the trial document size stays manageable while the UI gets enough
    to render per-query delta tables, trace drawers, and regression counts.
    """
    out: list[dict] = []
    for d in details:
        j = d.get("judge") or {}
        score = float(j.get("score", 0.0) or 0.0) if j else 0.0
        out.append({
            "query_uuid": d.get("query_uuid") or "",
            "query": d.get("query") or "",
            "category": d.get("category"),
            "score": round(score, 4),
            "verdict": j.get("verdict") if j else None,
            "confidence": j.get("confidence") if j else None,
            "reasoning": (j.get("reasoning") or "")[:600] if j else "",
            "missing_facts": list(j.get("missing_facts") or []) if j else [],
            "hallucinated_facts": list(j.get("hallucinated_facts") or []) if j else [],
            "actual_answer": (d.get("actual_answer") or "")[:1200],
            "retrieved_sources": list(d.get("retrieved_sources") or [])[:20],
        })
    return out


def _condense_no_kb_details(details: list[dict]) -> list[dict]:
    """Strip ``judge_baselines_only`` per-query output to a compact shape.

    Baseline details carry ``baseline_judge`` + ``baseline_answer`` (different
    key names from the with-KB path); normalise into the same shape we use for
    optimized/default per-query results so the UI doesn't need two branches.
    """
    out: list[dict] = []
    for d in details:
        j = d.get("baseline_judge") or {}
        score = float(j.get("score", 0.0) or 0.0) if j else 0.0
        out.append({
            "query_uuid": d.get("query_uuid") or "",
            "query": d.get("query") or "",
            "score": round(score, 4),
            "verdict": j.get("verdict") if j else None,
            "confidence": j.get("confidence") if j else None,
            "reasoning": (j.get("reasoning") or "")[:600] if j else "",
            "missing_facts": list(j.get("missing_facts") or []) if j else [],
            "hallucinated_facts": list(j.get("hallucinated_facts") or []) if j else [],
            "actual_answer": (d.get("baseline_answer") or "")[:1200],
        })
    return out


async def _build_test_query_snapshot(
    test_queries: list[KBTestQuery],
    kb_uuid: str,
) -> dict:
    """Build the eval-set snapshot persisted on the run document.

    Captures composition (categories, auto/user, source coverage) plus
    expected-answer hashes so a later run can detect that the eval set
    drifted between runs (and therefore the comparison isn't apples-to-apples).
    """
    try:
        sources = await KnowledgeBaseSource.find(
            KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
        ).to_list()
        total_sources = len(sources)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Could not load sources for snapshot (kb=%s): %s", kb_uuid, e)
        total_sources = 0

    categories: dict[str, int] = {}
    sources_covered: set[str] = set()
    auto_generated = 0
    user_authored = 0
    query_uuids: list[str] = []
    expected_answer_hashes: dict[str, str] = {}
    for q in test_queries:
        uid = getattr(q, "uuid", "") or ""
        if uid:
            query_uuids.append(uid)
        cat = getattr(q, "category", None) or "uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
        if getattr(q, "auto_generated", False):
            auto_generated += 1
        else:
            user_authored += 1
        for src_uuid in (getattr(q, "source_chunk_ids", None) or []):
            if src_uuid:
                sources_covered.add(src_uuid)
        expected = getattr(q, "expected_answer", None)
        if expected and uid:
            expected_answer_hashes[uid] = hashlib.sha256(
                expected.encode("utf-8"),
            ).hexdigest()[:16]

    return {
        "total": len(test_queries),
        "query_uuids": query_uuids,
        "expected_answer_hashes": expected_answer_hashes,
        "auto_generated_count": auto_generated,
        "user_authored_count": user_authored,
        "categories": categories,
        "sources_covered": sorted(sources_covered),
        "total_sources": total_sources,
    }


def _enabled_model_names(sys_cfg: SystemConfig | None) -> list[str]:
    if not sys_cfg:
        return []
    out: list[str] = []
    for entry in sys_cfg.available_models or []:
        if isinstance(entry, dict) and entry.get("name"):
            out.append(str(entry["name"]))
    return out


def _exclude_judge_family_models(
    enabled_models: list[str],
    judge_model: str | None,
) -> tuple[list[str], list[str]]:
    """Drop candidate models in the same family as ``judge_model``.

    Mirrors ``extraction_optimizer._candidates_excluding_judge_family`` so the
    KB optimizer gets the same self-preference guard: an LLM judge of family X
    over-rates outputs of family X. Returns ``(kept, excluded)``. Falls back
    to keeping everything when exclusion would empty the candidate set —
    better to run with bias than have no trials. The excluded list is
    surfaced on the run document so the UI can warn about residual risk.
    """
    if not judge_model or not enabled_models:
        return (list(enabled_models), [])
    from app.services.extraction_optimizer import _model_family
    judge_family = _model_family(judge_model)
    kept: list[str] = []
    excluded: list[str] = []
    for m in enabled_models:
        if _model_family(m) == judge_family:
            excluded.append(m)
        else:
            kept.append(m)
    if not kept:
        return (list(enabled_models), [])
    return (kept, list(dict.fromkeys(excluded)))


def _build_search_space(
    enabled_models: list[str] | None,
) -> list[dict[str, Any]]:
    """Enumerate every cheap-track config. Optimizer samples a subset."""
    models: list[str | None] = list(enabled_models) if enabled_models else [None]
    space: list[dict[str, Any]] = []
    for k in K_VALUES:
        for model in models:
            for prompt_variant in PROMPT_VARIANTS:
                for query_rewriting in QUERY_REWRITING:
                    for source_label_visibility in SOURCE_LABEL_VISIBILITY:
                        for rerank in RERANK_VALUES:
                            for answer_temperature in ANSWER_TEMPERATURE_VALUES:
                                space.append({
                                    "k": k,
                                    "model": model,
                                    "prompt_variant": prompt_variant,
                                    "query_rewriting": query_rewriting,
                                    "source_label_visibility": source_label_visibility,
                                    "rerank": rerank,
                                    "answer_temperature": answer_temperature,
                                })
    return space


def _sample_trial_configs(
    search_space: list[dict],
    token_budget: int,
    per_trial_estimate: int = DEFAULT_TRIAL_TOKEN_ESTIMATE,
    rng: random.Random | None = None,
    *,
    stratified: bool = True,
) -> list[dict]:
    """Sample trial configs, capped by budget and MAX_TRIAL_COUNT.

    When ``stratified=True`` (default) uses ``BudgetEnforcer.stratified_sample_trials``
    so every axis value appears in at least one trial — important at small
    sample sizes where uniform random often leaves entire axis values
    unexplored. ``stratified=False`` preserves the legacy uniform random
    behaviour for any caller / test that relied on it.
    """
    from app.services.budget_enforcer import BudgetEnforcer

    enforcer = BudgetEnforcer(
        total_budget=token_budget,
        per_trial_estimate=per_trial_estimate,
        max_trial_count=MAX_TRIAL_COUNT,
    )
    if stratified:
        return enforcer.stratified_sample_trials(
            search_space,
            axes=["k", "prompt_variant", "query_rewriting",
                  "source_label_visibility", "model", "rerank",
                  "answer_temperature"],
            rng=rng,
        )
    return enforcer.sample_trials(search_space, rng=rng)


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------


class KBOptimizer:
    """Drive a KB optimization run end-to-end."""

    async def run(
        self,
        kb_uuid: str,
        user_id: str,
        run_uuid: str,
        token_budget: int,
        include_indexing_track: bool = False,
        apply_on_finish: bool = False,
        rng_seed: int | None = None,
    ) -> KBOptimizationRun:
        """Execute the optimization loop. Updates the pre-allocated
        ``KBOptimizationRun`` doc throughout. Returns the run doc when done.
        """
        if include_indexing_track:
            # v1 is cheap-track only.
            logger.info("include_indexing_track=True ignored in v1 (cheap-track only)")

        run_doc = await KBOptimizationRun.find_one(KBOptimizationRun.uuid == run_uuid)
        if not run_doc:
            raise ValueError(f"KBOptimizationRun not found: {run_uuid}")

        # Materialise the rng_seed even when caller passed None — otherwise
        # "re-run" produces a different trial sample with no way to reproduce
        # the prior one. A persisted seed makes any run replayable.
        if rng_seed is None:
            rng_seed = random.randint(0, 2**31 - 1)
        rng = random.Random(rng_seed)

        try:
            await self._update(
                run_doc, status="running", phase="preparing",
                progress_message="Loading KB and test queries…",
                rng_seed=rng_seed,
                judge_prompt_version=_current_judge_prompt_version(),
                judge_temperature=0.0,  # see kb_validation_service._judge_answer
            )
            kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
            if not kb:
                raise KBOptimizerError(
                    "kb_not_found",
                    "Knowledge base not found.",
                    {"kb_uuid": kb_uuid},
                )

            test_queries = await self._ensure_test_queries(kb_uuid, user_id, run_doc)
            if not test_queries:
                raise KBOptimizerError(
                    "test_set_too_small",
                    "Could not establish a test query set for this KB.",
                    {"kb_uuid": kb_uuid},
                )

            # Snapshot the eval set composition + expected-answer hashes so
            # the UI can render composition chips and detect drift between
            # this run and prior runs. Persisting hashes (not full text) keeps
            # the run document compact while still proving "you rescored on
            # the same questions".
            snapshot = await _build_test_query_snapshot(test_queries, kb_uuid)
            await self._update(run_doc, test_query_snapshot=snapshot)

            # Train/holdout split: winner selection happens on train, the
            # reported headline score is re-measured on holdout. Without this
            # the best-of-N selection bias inflates the "optimized" score by
            # roughly 2σ × √(2 ln N), turning judge noise into "lift".
            train_queries, holdout_queries = _split_train_holdout(
                test_queries, kb_uuid,
            )
            await self._update(
                run_doc,
                train_query_uuids=[
                    str(getattr(q, "uuid", "") or "") for q in train_queries
                ],
                holdout_query_uuids=[
                    str(getattr(q, "uuid", "") or "") for q in holdout_queries
                ],
                overfitting_warning=not holdout_queries,
            )

            # ----- Resolve model -----
            from app.services.workflow_validator import _resolve_model_name as _resolve_sync
            user_default_model = await asyncio.to_thread(_resolve_sync, user_id)
            if not user_default_model:
                raise KBOptimizerError(
                    "judge_unavailable",
                    "No LLM model is configured for this user — the optimizer "
                    "needs a judge model to score trials.",
                    {"user_id": user_id},
                )

            sys_cfg = await SystemConfig.get_config()
            enabled_models = _enabled_model_names(sys_cfg)
            # Optimizer treats the user's resolved model as the safe fallback.
            if user_default_model not in enabled_models:
                enabled_models = [user_default_model] + enabled_models
            # Same-family judge exclusion: the judge is pinned to
            # user_default_model; dropping candidates in the judge's family
            # removes self-preference bias on the model axis. The full
            # enabled_models list is preserved for cross-judge (which uses a
            # sibling judge that may be same-family as the dropped candidates).
            candidate_models, excluded_models = _exclude_judge_family_models(
                enabled_models, user_default_model,
            )
            if excluded_models:
                run_doc.judge_family_excluded_models = excluded_models

            # ----- Establish baselines (no-KB first, then default-KB) -----
            # Measure no-KB first and persist it before the heavier default-KB
            # pass, so the running tab can show users the target score to beat
            # while the rest of the optimization runs.
            # Baselines and trials run on the TRAIN slice so the holdout is
            # never seen until the post-loop re-evaluation.
            await self._update(run_doc, phase="running",
                               judge_model=user_default_model,
                               progress_message="Measuring no-KB baseline (score to beat)…")
            try:
                baselines = await self._establish_baselines(
                    run_doc, kb_uuid, user_id, train_queries, user_default_model,
                )
            except KBOptimizerError:
                raise
            except Exception as e:
                # Baseline failures usually mean the judge can't reach an LLM
                # or the KB has no chunks — both call for a different remediation
                # than a generic "something went wrong" banner.
                raise KBOptimizerError(
                    "baselines_failed",
                    "Couldn't establish a baseline score for this KB. The judge "
                    "model or retrieval pipeline likely failed.",
                    {"detail": f"{type(e).__name__}: {str(e)[:200]}"},
                ) from e

            # ----- Build & sample trials -----
            # NB: search space spans ``candidate_models`` (post-exclusion),
            # while cross-judge below uses ``enabled_models`` so a sibling
            # judge can still be picked even when its family is excluded as a
            # candidate.
            search_space = _build_search_space(candidate_models)
            remaining_budget = max(0, token_budget - run_doc.tokens_used)
            trial_configs = _sample_trial_configs(search_space, remaining_budget, rng=rng)
            await self._update(
                run_doc,
                total_trials_planned=len(trial_configs),
                progress_message=f"Planning complete · {len(trial_configs)} trials",
            )
            if not trial_configs:
                logger.info("No trials sampled (budget too small) — finalising with baseline only")

            # ----- Run trials in series -----
            best_trial: dict | None = None
            # Convergence tracking (T3.2): trials since best_score improved.
            trials_since_best_changed = 0
            stopped_reason: str | None = None
            for i, cfg_dict in enumerate(trial_configs, start=1):
                # Cancellation check — reads the flag from the DB so a UI
                # cancel propagates even though our in-memory run_doc is stale.
                if await _is_cancelled(run_doc):
                    return await self._finalize_cancelled(run_doc, kb)

                # Budget check.
                if run_doc.tokens_used >= token_budget:
                    logger.info("Token budget exhausted — stopping at trial %d", i - 1)
                    stopped_reason = "budget_exhausted"
                    break

                # Convergence check (T3.2): if we've seen enough trials and
                # the best hasn't improved in PATIENCE rounds AND the leader
                # is clearly ahead of the runner-up, stop early. The "clearly
                # ahead" gate uses the same 2σ noise floor as winner
                # selection, so we never declare convergence on noise.
                if (
                    best_trial is not None
                    and i > CONVERGENCE_MIN_TRIALS
                    and trials_since_best_changed >= CONVERGENCE_PATIENCE
                ):
                    # Trial scores are now blended (judge*0.40 + invariants).
                    # σ_blended ≈ BLEND_WEIGHT_JUDGE × σ_judge because only the
                    # judge component varies between trials within a run.
                    judge_sigma = (
                        baselines.get("judge_variance") or DEFAULT_JUDGE_NOISE_FLOOR
                    )
                    sigma = BLEND_WEIGHT_JUDGE * judge_sigma
                    completed_scores = sorted(
                        (float(t["score"]) for t in run_doc.trials
                         if t.get("status") == "completed" and t.get("score") is not None),
                        reverse=True,
                    )
                    if len(completed_scores) >= 2:
                        top, runner_up = completed_scores[0], completed_scores[1]
                        if top - runner_up > WINNER_TIE_SIGMAS * sigma:
                            logger.info(
                                "Converged at trial %d: best %.3f, runner-up %.3f, σ %.3f",
                                i - 1, top, runner_up, sigma,
                            )
                            stopped_reason = "converged"
                            break

                msg = self._describe_config(cfg_dict)
                await self._update(
                    run_doc,
                    current_trial_index=i,
                    progress_message=f"Trial {i} of {len(trial_configs)}: {msg}",
                )

                # Track the best JUDGE score so far (not blended) so the
                # per-trial early-stop can kill a clearly-worse trial without
                # redundant work. σ_blended = 0.40 × σ_judge, so the
                # 2σ-below-best comparison simplifies to "partial judge mean
                # < best_judge − 2σ_judge" — same calibration as no-KB stop.
                current_best_judge = (
                    float(best_trial["judge_score"])
                    if best_trial and best_trial.get("judge_score") is not None
                    else None
                )
                trial_result = await self._run_trial(
                    cfg_dict, kb_uuid, user_id, train_queries, user_default_model,
                    baseline_default_score=baselines["default_kb"],
                    baseline_no_kb_score=baselines.get("no_kb"),
                    judge_variance=baselines.get("judge_variance"),
                    retrieval_score=baselines.get("retrieval_score", 0.0),
                    health_score=baselines.get("health_score", 0.0),
                    coverage_score=baselines.get("coverage_score", 0.0),
                    current_best_judge_score=current_best_judge,
                )
                run_doc.trials.append(trial_result)
                run_doc.tokens_used += trial_result["tokens_used"]

                # Early-stopped trials carry partial scores and aren't
                # eligible to be "best so far" — they were killed precisely
                # because they were underperforming.
                eligible = trial_result.get("status") == "completed"
                if eligible and (
                    best_trial is None or trial_result["score"] > best_trial["score"]
                ):
                    best_trial = trial_result
                    trials_since_best_changed = 0
                    await self._update(
                        run_doc,
                        best_score_so_far=trial_result["score"],
                        best_config_so_far=trial_result["config"],
                        trials=run_doc.trials,
                        tokens_used=run_doc.tokens_used,
                    )
                else:
                    trials_since_best_changed += 1
                    await self._update(
                        run_doc, trials=run_doc.trials, tokens_used=run_doc.tokens_used,
                    )
            else:
                # for-else: hit when the loop exhausted without ``break``.
                stopped_reason = "all_trials_complete"

            # A cancel that landed during the final trial (after the loop's
            # top-of-iteration check) must stop here, before we select a
            # winner and re-score on the holdout slice.
            if await _is_cancelled(run_doc):
                return await self._finalize_cancelled(run_doc, kb)

            # ----- Variance-aware winner selection (T2.2) -----
            # The greedy ``best_trial`` from the loop is the highest raw
            # score, but with judge noise σ that "best" may be inside a
            # noise-floor cluster of statistically-tied configs. Recompute
            # the winner respecting noise: prefer closest-to-default within
            # the cluster (fewer knobs flipped = less surface for surprises).
            # SE for the band is computed from the leader trial's
            # num_queries_judged — the actual N behind the trial-score mean.
            n_items_for_se = 1
            if best_trial is not None and best_trial.get("num_queries_judged"):
                n_items_for_se = max(1, int(best_trial["num_queries_judged"]))
            # Trials and baseline_default_score are blended; pass σ scaled to
            # match (only the judge component varies between trials, so
            # σ_blended ≈ BLEND_WEIGHT_JUDGE × σ_judge).
            judge_sigma = baselines.get("judge_variance")
            blended_sigma = (
                BLEND_WEIGHT_JUDGE * judge_sigma if judge_sigma is not None else None
            )
            winner_trial, winner_reason, tied_with_baseline, tie_cluster_size = (
                pick_winner_variance_aware(
                    run_doc.trials,
                    judge_variance=blended_sigma,
                    baseline_default_score=baselines.get("default_kb"),
                    distance_from_default=lambda t: _l0_distance_to_default(
                        t.get("config", {}),
                    ),
                    n_items_for_se=n_items_for_se,
                )
            )
            if winner_trial is not None:
                best_trial = winner_trial
            await self._update(
                run_doc,
                tie_cluster_size=tie_cluster_size,
                winner_selection_reason=winner_reason,
                tied_with_baseline=tied_with_baseline,
            )

            # ----- Holdout re-evaluation (T2.1) -----
            # Re-run the winning config AND the default config on the holdout
            # slice. The headline ``optimized_score`` becomes the holdout
            # number (unbiased by winner-selection); the in-sample train score
            # is preserved as ``optimized_score_train`` for diagnostics.
            optimized_score_train = (
                best_trial["score"] if best_trial else baselines["default_kb"]
            )
            best_config = best_trial["config"] if best_trial else None
            holdout_default_per_query: list[dict] = []
            holdout_optimized_per_query: list[dict] = []
            holdout_default_score: float | None = None
            holdout_optimized_score: float | None = None

            if holdout_queries and best_config:
                await self._update(
                    run_doc, phase="finalizing",
                    progress_message="Re-scoring winner on held-out queries…",
                )
                try:
                    holdout_result = await self._score_config_on_queries(
                        kb_uuid, holdout_queries, best_config, user_default_model,
                        retrieval_score=baselines.get("retrieval_score", 0.0),
                        health_score=baselines.get("health_score", 0.0),
                        coverage_score=baselines.get("coverage_score", 0.0),
                    )
                    holdout_optimized_score = holdout_result["score"]
                    holdout_optimized_per_query = holdout_result["per_query_results"]
                    run_doc.tokens_used += holdout_result["tokens_used"]
                except Exception as e:
                    logger.warning("Holdout re-score (optimized) failed: %s", e)

                try:
                    default_holdout = await self._score_config_on_queries(
                        kb_uuid, holdout_queries, {}, user_default_model,
                        retrieval_score=baselines.get("retrieval_score", 0.0),
                        health_score=baselines.get("health_score", 0.0),
                        coverage_score=baselines.get("coverage_score", 0.0),
                    )
                    holdout_default_score = default_holdout["score"]
                    holdout_default_per_query = default_holdout["per_query_results"]
                    run_doc.tokens_used += default_holdout["tokens_used"]
                except Exception as e:
                    logger.warning("Holdout re-score (default) failed: %s", e)

            # Headline score: holdout when we have it (unbiased), otherwise
            # in-sample train (still useful when N<6 and we couldn't split).
            if holdout_optimized_score is not None:
                optimized_score = holdout_optimized_score
            else:
                optimized_score = optimized_score_train

            # A cancel arriving during holdout re-scoring must not silently
            # finish the run — honor it before the remaining finalize work
            # (suggestions, cross-judge re-score, and applying the winner).
            if await _is_cancelled(run_doc):
                return await self._finalize_cancelled(run_doc, kb)

            await self._update(run_doc, phase="finalizing",
                               progress_message="Generating data source suggestions…")
            suggestions = self._analyse_suggestions(
                run_doc.trials, baselines, test_queries,
                tie_cluster_size=tie_cluster_size,
                winner_reason=winner_reason,
            )

            # Paired-bootstrap CI: prefer holdout pairs (apples-to-apples
            # unbiased), fall back to train pairs when we couldn't split.
            if holdout_optimized_per_query and holdout_default_per_query:
                lift_ci = self._compute_lift_ci_from_pairs(
                    holdout_optimized_per_query,
                    holdout_default_per_query,
                    rng_seed=rng_seed,
                )
            else:
                lift_ci = self._compute_lift_ci(
                    best_trial,
                    baselines.get("default_per_query") or [],
                    rng_seed=rng_seed,
                )

            # Apply-preview rollup (Phase 2): join winner + default per-query
            # results on query_uuid and roll up so the UI can render
            # "K of N queries will change, R regress" before commit. Prefer
            # holdout pairs when available (unbiased), fall back to train.
            if holdout_optimized_per_query and holdout_default_per_query:
                _pre_winner = holdout_optimized_per_query
                _pre_default = holdout_default_per_query
            else:
                _pre_winner = (best_trial or {}).get("per_query_results") or []
                _pre_default = baselines.get("default_per_query") or []
            apply_preview = self._build_apply_preview(
                _pre_winner, _pre_default,
                judge_variance=baselines.get("judge_variance"),
            )

            await self._update(
                run_doc,
                optimized_score=round(optimized_score, 4),
                optimized_score_train=round(optimized_score_train, 4),
                holdout_default_score=(
                    round(holdout_default_score, 4)
                    if holdout_default_score is not None else None
                ),
                best_config=best_config,
                data_source_suggestions=suggestions,
                lift_ci=lift_ci,
                apply_preview=apply_preview,
                tokens_used=run_doc.tokens_used,
            )

            # ----- Cross-judge sanity check (audit #12) -----
            # When the user has multiple judge-capable models enabled AND the
            # budget can absorb one more pass, re-score the winning trial with
            # a sibling model to surface judge self-bias. Best-effort —
            # failures are logged and don't fail the run.
            # Run cross-judge on holdout when available so it's checking the
            # same thing the headline score reports on.
            await self._maybe_cross_judge(
                run_doc, kb_uuid, best_trial,
                holdout_queries if holdout_queries else train_queries,
                enabled_models=enabled_models,
                primary_judge=user_default_model,
                token_budget=token_budget,
            )

            # ----- Apply (if requested) -----
            # Suppress apply when statistically tied with the current config —
            # changing settings the judge can't tell apart adds churn without
            # measurable benefit. UI surfaces ``tied_with_baseline`` as a
            # "no measurable improvement" banner.
            # Final cancel gate: a cancel during the cross-judge pass must still
            # prevent mutating the KB's live config.
            if await _is_cancelled(run_doc):
                return await self._finalize_cancelled(run_doc, kb)

            if apply_on_finish and best_config and not tied_with_baseline:
                await self._apply_to_kb(kb_uuid, best_config, run_uuid, run_doc=run_doc)
                await self._update(
                    run_doc, progress_message="Applied optimized settings to KB.",
                )

            await self._update(
                run_doc, status="completed", phase="done",
                progress_message="Optimization complete.",
                stopped_reason=stopped_reason or "all_trials_complete",
                completed_at=_now(),
            )
            await self._notify_terminal(run_doc, kb)
            return run_doc

        except Exception as e:
            logger.exception("KB optimization failed (run %s): %s", run_uuid, e)
            if isinstance(e, KBOptimizerError):
                err_code = e.code
                err_msg = str(e)
                err_ctx: dict | None = e.context
            else:
                err_code = "unknown"
                err_msg = f"{type(e).__name__}: {str(e)[:500]}"
                err_ctx = {"exception_type": type(e).__name__}
            await self._update(
                run_doc, status="failed", phase="failed",
                error_message=err_msg,
                error_code=err_code,
                error_context=err_ctx,
                stopped_reason="failed",
                completed_at=_now(),
            )
            # Notify the user that their long-running run failed (best-effort —
            # we never block the failure path on a notification problem).
            try:
                await self._notify_terminal(run_doc, locals().get("kb"))
            except Exception:
                logger.warning("Could not emit failure notification for run %s", run_uuid)
            raise

    # -----------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------

    async def _ensure_test_queries(
        self, kb_uuid: str, user_id: str, run_doc: KBOptimizationRun,
    ) -> list[KBTestQuery]:
        """Build the eval set for this run.

        When the wizard passed an explicit reviewed set
        (``options.test_query_uuids``) we grade against exactly those. That's
        what makes the Test-set step's existing / generate / combine choice
        authoritative — e.g. "generate only" must exclude pre-existing saved
        questions even though they still live in the KB, and "combine" must mix
        both. Falls back to "use all saved, else auto-generate Standard" for
        callers that don't curate a set up front (passive re-runs, older clients).
        """
        opts = run_doc.options or {}
        selected_uuids = opts.get("test_query_uuids") or []
        if selected_uuids:
            chosen = await KBTestQuery.find(
                KBTestQuery.knowledge_base_uuid == kb_uuid,
                {"uuid": {"$in": list(selected_uuids)}},
            ).to_list()
            with_answers = [q for q in chosen if getattr(q, "expected_answer", None)]
            if with_answers:
                return with_answers
            # The curated set yielded nothing usable (all deleted, or none have
            # an expected answer). Fall through to the legacy path rather than
            # failing the run outright.

        existing = await KBTestQuery.find(
            KBTestQuery.knowledge_base_uuid == kb_uuid,
        ).to_list()
        with_answers = [q for q in existing if getattr(q, "expected_answer", None)]
        if with_answers:
            return with_answers

        await self._update(
            run_doc, phase="preparing",
            progress_message="No test queries yet — generating one for evaluation…",
        )
        from app.services.kb_question_generator import KBQuestionGenerator
        coverage = opts.get("autogen_coverage") or DEFAULT_AUTOGEN_COVERAGE
        created = await KBQuestionGenerator().generate(
            kb_uuid, user_id, coverage=coverage, persist=True,
        )
        return [q for q in created if getattr(q, "expected_answer", None)]

    async def _establish_baselines(
        self,
        run_doc: KBOptimizationRun,
        kb_uuid: str,
        user_id: str,
        test_queries: list[KBTestQuery],
        model_name: str,
    ) -> dict:
        """Establish no-KB and default-KB baselines in three visible phases.

        Phase 0 captures the **config-invariant** metrics (source health,
        chunk coverage, retrieval precision) that go into the blended quality
        score. These depend only on the KB's content state, not on RAG params,
        so they're computed once and reused by every trial — eliminating
        per-trial probe cost while keeping the optimizer's reported score on
        the same scale as the validation header.

        Phase 1 measures the no-KB target score (the bar the KB must beat) and
        persists it on ``run_doc`` immediately so the running tab can display
        it. Phase 2 then measures the default-KB score and runs a small judge
        variance sample on those results, then blends the result with the
        Phase 0 invariants for the headline ``baseline_default_score``.

        Token usage is read from real pydantic-ai usage on each agent run
        (no estimation). Variance sampling adds two extra judge calls whose
        tokens we also account for.
        """
        # --- Phase 0: config-invariant metrics + default config snapshot ---
        # These don't change as we sweep RAG knobs, so compute once. Running
        # them in parallel keeps the optimizer's start-up under ~1s even on
        # KBs with dozens of sources.
        health, coverage, retrieval, default_cfg = await asyncio.gather(
            kb_validation_service.check_source_health(kb_uuid),
            kb_validation_service.check_chunk_coverage(kb_uuid),
            kb_validation_service.check_retrieval_precision(kb_uuid, test_queries),
            kb_validation_service._resolve_rag_config(
                kb_uuid, None, kb_validation_service.DEFAULT_K,
            ),
        )
        health_score = float(health.get("ratio") or 0.0)
        coverage_score = float(coverage.get("ratio") or 0.0)
        retrieval_score = float(retrieval.get("avg_precision") or 0.0)
        default_config_dict = default_cfg.model_dump() if default_cfg else None
        await self._update(
            run_doc,
            baseline_health_score=round(health_score, 4),
            baseline_coverage_score=round(coverage_score, 4),
            baseline_retrieval_score=round(retrieval_score, 4),
            default_config=default_config_dict,
        )

        # --- Phase 1: no-KB baseline (the score to beat) ---
        baseline_result = await kb_validation_service.judge_baselines_only(
            test_queries, model_name,
        )
        no_kb = baseline_result.get("avg_baseline_score") or 0.0
        baseline_tokens = int(baseline_result.get("tokens_used", 0) or 0)
        no_kb_rounded = round(no_kb, 4)
        # Persist no-KB per-query results so the UI can render "without KB"
        # cells in the per-query delta table and the trace drawer.
        no_kb_per_query = _condense_no_kb_details(baseline_result.get("details", []))
        await self._update(
            run_doc,
            baseline_no_kb_score=no_kb_rounded,
            no_kb_per_query_results=no_kb_per_query,
            tokens_used=run_doc.tokens_used + baseline_tokens,
            progress_message=(
                f"No-KB baseline: {round(no_kb * 100)}% — measuring default-KB next…"
            ),
        )

        # --- Phase 2: default-KB score + variance ---
        result = await kb_validation_service.judge_test_queries(
            kb_uuid, test_queries, model_name, mode="judge",
        )
        default_kb = result.get("avg_judge_score") or 0.0
        judge_tokens = int(result.get("tokens_used", 0) or 0)
        default_per_query = _condense_per_query_details(result.get("details", []))

        # Light variance sample: re-judge two queries' KB answers and compare.
        # The detailed variant returns sigma, n, and the sampled uuids so the
        # UI can render "σ from n=2 re-judgements on Q3, Q7" instead of a
        # bare ±X. Token cost is the same as the legacy tuple call.
        by_uuid = {q.uuid: q for q in test_queries}
        variance_result = (
            await kb_validation_service._sample_judge_variance_detailed(
                kb_uuid, result.get("details", []), by_uuid, model_name,
            )
        )
        variance = variance_result.sigma
        variance_tokens = variance_result.tokens_used

        default_kb_judge_rounded = round(default_kb, 4)
        # Blend the default's judge score with the Phase 0 invariants so the
        # persisted ``baseline_default_score`` is on the same scale as the
        # validation header (and matches the optimizer's per-trial ``score``).
        default_blended = _blended_quality_score(
            default_kb, retrieval_score, health_score, coverage_score,
        )
        default_blended_rounded = round(default_blended, 4)
        await self._update(
            run_doc,
            baseline_default_score=default_blended_rounded,
            baseline_default_judge_score=default_kb_judge_rounded,
            default_per_query_results=default_per_query,
            judge_variance=variance,
            judge_variance_meta={
                "sigma": variance,
                "n": variance_result.n,
                "sampled_query_uuids": list(variance_result.sampled_query_uuids),
            },
            tokens_used=run_doc.tokens_used + judge_tokens + variance_tokens,
        )

        return {
            "no_kb": no_kb_rounded,
            "default_kb": default_blended_rounded,
            "default_kb_judge": default_kb_judge_rounded,
            "default_per_query": default_per_query,
            "judge_variance": variance,
            "retrieval_score": retrieval_score,
            "health_score": health_score,
            "coverage_score": coverage_score,
            "tokens_used": baseline_tokens + judge_tokens + variance_tokens,
        }

    async def _run_trial(
        self,
        cfg_dict: dict,
        kb_uuid: str,
        user_id: str,
        test_queries: list[KBTestQuery],
        fallback_model: str,
        baseline_default_score: float,
        *,
        baseline_no_kb_score: float | None = None,
        judge_variance: float | None = None,
        retrieval_score: float = 0.0,
        health_score: float = 0.0,
        coverage_score: float = 0.0,
        current_best_judge_score: float | None = None,
    ) -> dict:
        """Run judge_test_queries with a specific RAGConfig override per query.

        We monkey-patch ``_generate_kb_answer`` for the duration of this trial
        so the existing judge_test_queries helper (which doesn't know about
        RAGConfig) routes through the trial's config without further refactor.

        The returned ``score`` is the **blended** quality (judge*0.40 +
        retrieval*0.25 + health*0.20 + coverage*0.15) so it matches the
        validation header. ``judge_score`` keeps the raw judge mean for
        cross-judge audit + lift CI math (which compares paired judge scores).
        Caller passes the cached retrieval/health/coverage from
        ``_establish_baselines`` (all config-invariant within a run).

        ``baseline_no_kb_score`` + ``judge_variance`` enable per-trial
        early-stop (T3.1): when the partial-score mean falls more than 2σ
        below no-KB baseline after at least ~25% of queries, we cancel
        remaining work and mark the trial ``early_stopped``. The early-stop
        path compares JUDGE scores (not blended) since the partial-mean
        signal lives in the judge component. Without both signals we run the
        full trial (legacy behaviour).
        """
        cfg = RAGConfig(**cfg_dict)
        effective_model = cfg.model or fallback_model
        trial_id = uuid4().hex[:12]
        started = _now()

        # Wrap _generate_kb_answer with a closure that injects this trial's config.
        original_gen = kb_validation_service._generate_kb_answer

        async def trial_generate(kb_uuid_, query, model_name, k=kb_validation_service.DEFAULT_K, **kw):
            # Strip any inbound config — this trial's overrides win.
            kw.pop("config", None)
            return await original_gen(kb_uuid_, query, model_name, k, config=cfg)

        kb_validation_service._generate_kb_answer = trial_generate

        # Build the early-stop callback. Two stop signals share the same
        # min-checks gate so a single unlucky early query can't kill the trial:
        #   1. Partial mean falls > 2σ below the no-KB baseline → "this trial
        #      isn't even beating asking the model directly, abort."
        #   2. Partial mean falls > 2σ below the current best (judge units) →
        #      "this trial can't catch the leader, don't waste tokens."
        # Both comparisons live in judge-score units (the partial means are
        # raw judge scores from per-query verdicts).
        early_stop_callback = None
        early_stop_reason = {"reason": None}  # mutable closure capture
        if baseline_no_kb_score is not None or current_best_judge_score is not None:
            sigma = (
                judge_variance if judge_variance is not None
                else DEFAULT_JUDGE_NOISE_FLOOR
            )
            min_to_check = max(2, len(test_queries) // 4)
            no_kb_threshold = (
                baseline_no_kb_score - WINNER_TIE_SIGMAS * sigma
                if baseline_no_kb_score is not None else None
            )
            best_threshold = (
                current_best_judge_score - WINNER_TIE_SIGMAS * sigma
                if current_best_judge_score is not None else None
            )

            def _should_stop(partial_scores: list[float]) -> bool:
                if len(partial_scores) < min_to_check:
                    return False
                partial_mean = sum(partial_scores) / len(partial_scores)
                if no_kb_threshold is not None and partial_mean < no_kb_threshold:
                    early_stop_reason["reason"] = "below_no_kb"
                    return True
                if best_threshold is not None and partial_mean < best_threshold:
                    early_stop_reason["reason"] = "below_best"
                    return True
                return False

            early_stop_callback = _should_stop

        try:
            # Pin the judge to fallback_model regardless of cfg.model. Letting
            # each trial judge itself (self-confirmation) lets a model that
            # shares blind spots with its own judge artificially win on the
            # ``model`` axis.
            judge_result = await kb_validation_service.judge_test_queries(
                kb_uuid, test_queries, effective_model, mode="judge",
                judge_model=fallback_model,
                early_stop_callback=early_stop_callback,
            )
        except Exception as e:
            logger.exception("Trial %s failed: %s", trial_id, e)
            kb_validation_service._generate_kb_answer = original_gen
            return {
                "trial_id": trial_id,
                "config": cfg_dict,
                "score": 0.0,
                "judge_score": 0.0,
                "lift_vs_default": -baseline_default_score,
                "tokens_used": 0,
                "status": "failed",
                "error": str(e)[:200],
                "started_at": started.isoformat(),
                "duration_seconds": (_now() - started).total_seconds(),
            }
        finally:
            kb_validation_service._generate_kb_answer = original_gen

        judge_score = judge_result.get("avg_judge_score") or 0.0
        score = _blended_quality_score(
            judge_score, retrieval_score, health_score, coverage_score,
        )
        n_judged = judge_result.get("num_queries_judged", 0) or 0
        # Real token usage comes from judge_test_queries; fall back to the
        # estimate only when the upstream didn't report any (e.g. mocked tests
        # or a provider that doesn't expose usage).
        real_tokens = int(judge_result.get("tokens_used", 0) or 0)
        tokens_used = real_tokens if real_tokens > 0 else (n_judged * 5_000 or DEFAULT_TRIAL_TOKEN_ESTIMATE)

        # Capture per-query results so the UI can show per-query deltas,
        # regression counts, and trace replay. Without this the optimizer
        # winner is "trust me — it scored 84%" with no diagnosis path.
        per_query_results = _condense_per_query_details(
            judge_result.get("details", []),
        )
        was_early_stopped = bool(judge_result.get("early_stopped"))
        trial_dict = {
            "trial_id": trial_id,
            "config": cfg_dict,
            "score": round(score, 4),
            "judge_score": round(judge_score, 4),
            "lift_vs_default": round(score - baseline_default_score, 4),
            "num_queries_judged": n_judged,
            "discrimination_summary": judge_result.get("discrimination_summary"),
            "per_query_results": per_query_results,
            "tokens_used": tokens_used,
            # Early-stopped trials still record their partial score so the
            # UI can show "stopped at 25% — running mean was 12% below
            # no-KB baseline" (or "below current leader") without digging.
            "status": "early_stopped" if was_early_stopped else "completed",
            "started_at": started.isoformat(),
            "duration_seconds": round((_now() - started).total_seconds(), 2),
        }
        if was_early_stopped and early_stop_reason["reason"]:
            trial_dict["early_stop_reason"] = early_stop_reason["reason"]
        return trial_dict

    async def _score_config_on_queries(
        self,
        kb_uuid: str,
        queries: list[KBTestQuery],
        cfg_dict: dict,
        fallback_model: str,
        *,
        retrieval_score: float = 0.0,
        health_score: float = 0.0,
        coverage_score: float = 0.0,
    ) -> dict:
        """Run one config on a query slice — used for holdout re-evaluation.

        An empty ``cfg_dict`` means "default config". For non-empty configs we
        monkey-patch ``_generate_kb_answer`` the same way ``_run_trial`` does
        so the existing judge plumbing routes through this trial's RAGConfig.

        Returns both the blended quality score (``score``, on the same scale
        as the validation header and the per-trial ``score``) and the raw
        ``judge_score`` so the paired-bootstrap CI math can keep operating on
        judge units.
        """
        cfg = RAGConfig(**cfg_dict) if cfg_dict else RAGConfig()
        effective_model = cfg.model or fallback_model
        if cfg_dict:
            original_gen = kb_validation_service._generate_kb_answer

            async def holdout_generate(
                kb_uuid_, query, model_name,
                k=kb_validation_service.DEFAULT_K, **kw,
            ):
                kw.pop("config", None)
                return await original_gen(kb_uuid_, query, model_name, k, config=cfg)

            kb_validation_service._generate_kb_answer = holdout_generate
        else:
            original_gen = None

        try:
            judge_result = await kb_validation_service.judge_test_queries(
                kb_uuid, queries, effective_model, mode="judge",
                judge_model=fallback_model,
            )
        finally:
            if original_gen is not None:
                kb_validation_service._generate_kb_answer = original_gen

        judge_avg = float(judge_result.get("avg_judge_score") or 0.0)
        blended = _blended_quality_score(
            judge_avg, retrieval_score, health_score, coverage_score,
        )
        return {
            "score": blended,
            "judge_score": judge_avg,
            "per_query_results": _condense_per_query_details(
                judge_result.get("details", []),
            ),
            "tokens_used": int(judge_result.get("tokens_used", 0) or 0),
        }

    def _build_apply_preview(
        self,
        winner_per_query: list[dict],
        default_per_query: list[dict],
        *,
        judge_variance: float | None,
    ) -> dict | None:
        """Roll winner-vs-default per-query results into an apply preview.

        Joins on ``query_uuid`` and hands the resulting score pairs to the
        shared ``build_apply_preview`` helper. Returns ``None`` when neither
        side has per-query data so the UI knows to skip the modal (instead
        of showing an empty preview that misleads).
        """
        if not winner_per_query and not default_per_query:
            return None
        def_by_uuid = {
            r.get("query_uuid"): r
            for r in default_per_query if r.get("query_uuid")
        }
        items: list[dict] = []
        for w in winner_per_query:
            uid = w.get("query_uuid")
            if not uid:
                continue
            d = def_by_uuid.get(uid) or {}
            items.append({
                "item_id": uid,
                "label": (w.get("query") or d.get("query") or "")[:120],
                "baseline": float(d.get("score", 0.0) or 0.0),
                "winner": float(w.get("score", 0.0) or 0.0),
            })
        if not items:
            return None
        return build_apply_preview(items, judge_variance=judge_variance)

    def _compute_lift_ci_from_pairs(
        self,
        optimized_per_query: list[dict],
        default_per_query: list[dict],
        rng_seed: int | None,
    ) -> dict | None:
        """Same CI math as ``_compute_lift_ci`` but from explicit per-query lists.

        Used for holdout pairs where there's no ``best_trial`` wrapper.
        """
        opt_by_uuid = {
            r.get("query_uuid"): float(r.get("score", 0.0) or 0.0)
            for r in optimized_per_query
            if r.get("query_uuid")
        }
        def_by_uuid = {
            r.get("query_uuid"): float(r.get("score", 0.0) or 0.0)
            for r in default_per_query
            if r.get("query_uuid")
        }
        paired: list[tuple[float, float]] = [
            (def_by_uuid[uid], opt_by_uuid[uid])
            for uid in opt_by_uuid
            if uid in def_by_uuid
        ]
        if len(paired) < 2:
            return None
        return paired_lift_bootstrap_ci(paired, rng_seed=rng_seed)

    def _compute_lift_ci(
        self,
        best_trial: dict | None,
        default_per_query: list[dict],
        rng_seed: int | None,
    ) -> dict | None:
        """Paired-bootstrap CI on (optimized − default) per-query lift.

        Returns ``None`` when we lack per-query data from either arm — older
        runs without ``per_query_results`` will simply not get a CI rather
        than fall back to the broken σ × 1.96 heuristic.
        """
        if not best_trial:
            return None
        opt_by_uuid = {
            r.get("query_uuid"): float(r.get("score", 0.0) or 0.0)
            for r in (best_trial.get("per_query_results") or [])
            if r.get("query_uuid")
        }
        def_by_uuid = {
            r.get("query_uuid"): float(r.get("score", 0.0) or 0.0)
            for r in default_per_query
            if r.get("query_uuid")
        }
        paired: list[tuple[float, float]] = [
            (def_by_uuid[uid], opt_by_uuid[uid])
            for uid in opt_by_uuid
            if uid in def_by_uuid
        ]
        if len(paired) < 2:
            return None
        return paired_lift_bootstrap_ci(paired, rng_seed=rng_seed)

    async def _maybe_cross_judge(
        self,
        run_doc: KBOptimizationRun,
        kb_uuid: str,
        best_trial: dict | None,
        test_queries: list[KBTestQuery],
        *,
        enabled_models: list[str],
        primary_judge: str,
        token_budget: int,
    ) -> None:
        """Re-judge the winning trial with an alternate model (best-effort).

        Surfaces "judge A says 84%, judge B says 79%" so users can see whether
        the headline score is robust to the choice of judge. Skipped when
        another judge isn't available or the token budget is too tight.
        """
        if not best_trial or not best_trial.get("per_query_results"):
            return
        alt_judges = [m for m in enabled_models if m and m != primary_judge]
        if not alt_judges:
            return
        remaining = token_budget - run_doc.tokens_used
        if remaining < CROSS_JUDGE_TOKEN_RESERVE:
            logger.info(
                "Skipping cross-judge: only %d tokens remain (need >=%d).",
                remaining, CROSS_JUDGE_TOKEN_RESERVE,
            )
            return
        alt_judge_model = alt_judges[0]

        try:
            await self._update(
                run_doc,
                progress_message=f"Cross-judge sanity check with {alt_judge_model}…",
            )
            # Re-run the with-KB judge on the winning trial's config. We
            # piggy-back on judge_test_queries' RAG path via the same monkey-
            # patch trick used in _run_trial: temporarily install a closure
            # that injects the winning RAGConfig into _generate_kb_answer.
            cfg = RAGConfig(**best_trial["config"])
            original_gen = kb_validation_service._generate_kb_answer

            async def cross_generate(kb_uuid_, query, model_name, k=kb_validation_service.DEFAULT_K, **kw):
                kw.pop("config", None)
                return await original_gen(kb_uuid_, query, model_name, k, config=cfg)

            kb_validation_service._generate_kb_answer = cross_generate
            try:
                # Keep the *generator* identical to the winning trial — only
                # the judge swaps. Otherwise we're comparing "trial X scored
                # by model A" vs "trial Y scored by model B" which conflates
                # generator and judge changes.
                generator_model = best_trial["config"].get("model") or primary_judge
                alt_result = await kb_validation_service.judge_test_queries(
                    kb_uuid, test_queries, generator_model, mode="judge",
                    judge_model=alt_judge_model,
                )
            finally:
                kb_validation_service._generate_kb_answer = original_gen

            alt_score = alt_result.get("avg_judge_score") or 0.0
            alt_tokens = int(alt_result.get("tokens_used", 0) or 0)
            # Compare judge-vs-judge: the trial's ``score`` field is the
            # blended quality, but cross-judge tests whether two judges agree,
            # which is a pure judge-score comparison.
            primary_score = float(
                best_trial.get("judge_score")
                if best_trial.get("judge_score") is not None
                else (best_trial.get("score") or 0.0)
            )

            # Per-query verdict agreement between primary and alt judges.
            # Goes beyond "headline score delta" — answers "does the alt
            # judge agree with the *winner* call, query by query?" which is
            # the actual question users ask when staring at the cross-judge
            # number. Falls back gracefully if either side lacks per-query
            # detail (some legacy mocks).
            agreement_pct, kappa_eq = self._cross_judge_agreement(
                best_trial.get("per_query_results") or [],
                alt_result.get("details") or [],
            )
            cross_judge_payload = {
                "model": alt_judge_model,
                "score": round(alt_score, 4),
                "delta": round(alt_score - primary_score, 4),
                "tokens_used": alt_tokens,
            }
            if agreement_pct is not None:
                cross_judge_payload["agreement_pct"] = round(agreement_pct, 4)
            if kappa_eq is not None:
                cross_judge_payload["kappa_equivalent"] = round(kappa_eq, 4)
            await self._update(
                run_doc,
                cross_judge=cross_judge_payload,
                tokens_used=run_doc.tokens_used + alt_tokens,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Cross-judge pass failed (non-fatal): %s", e)

    @staticmethod
    def _cross_judge_agreement(
        primary_per_query: list[dict],
        alt_per_query: list[dict],
    ) -> tuple[float | None, float | None]:
        """Compute (verdict-agreement %, Cohen's κ-equivalent) between judges.

        Pairs queries by ``query_uuid`` (falling back to ``query`` text when
        uuids are absent), classifies each side's score into PASS/WARN/FAIL
        using the same thresholds the rubric uses, then computes:

          * ``agreement_pct`` — fraction of queries where both judges gave
            the same verdict bucket.
          * ``kappa_equivalent`` — Cohen's κ over the three buckets, the same
            metric used by the calibration tests. Lets users compare the
            cross-judge agreement directly against the judge↔human κ from
            the calibration ledger.

        Returns ``(None, None)`` when fewer than 2 paired queries exist —
        κ over 1 observation is undefined.
        """
        def _key(r: dict) -> str:
            return str(r.get("query_uuid") or r.get("query") or "")

        def _bucket(r: dict) -> str | None:
            jr = r.get("judge") if isinstance(r.get("judge"), dict) else r
            score = jr.get("score") if isinstance(jr, dict) else None
            if score is None:
                return None
            try:
                s = float(score)
            except (TypeError, ValueError):
                return None
            if s >= 0.7:
                return "PASS"
            if s >= 0.4:
                return "WARN"
            return "FAIL"

        alt_by_key = {_key(r): r for r in alt_per_query if _key(r)}
        pairs: list[tuple[str, str]] = []
        for r in primary_per_query:
            k = _key(r)
            alt = alt_by_key.get(k)
            if not alt:
                continue
            pb = _bucket(r)
            ab = _bucket(alt)
            if pb is None or ab is None:
                continue
            pairs.append((pb, ab))

        if len(pairs) < 2:
            return (None, None)

        agreement_pct = sum(1 for p, a in pairs if p == a) / len(pairs)

        # Cohen's κ for 3 categories.
        n = len(pairs)
        cats = ("PASS", "WARN", "FAIL")
        p_a = {c: sum(1 for p, _ in pairs if p == c) / n for c in cats}
        p_b = {c: sum(1 for _, a in pairs if a == c) / n for c in cats}
        p_exp = sum(p_a[c] * p_b[c] for c in cats)
        if p_exp >= 1.0:
            return (agreement_pct, 1.0)
        kappa = (agreement_pct - p_exp) / (1.0 - p_exp)
        return (agreement_pct, kappa)

    def _analyse_suggestions(
        self,
        trials: list[dict],
        baselines: dict,
        test_queries: list[KBTestQuery],
        *,
        tie_cluster_size: int | None = None,
        winner_reason: str | None = None,
    ) -> list[dict]:
        """Heuristic post-mortem on the trials to surface KB-data improvements.

        Coarse for v1; we mainly want to highlight obvious gaps and
        config-sensitivity. The thresholds are intentionally conservative so
        we don't emit a wall of noise.

        ``tie_cluster_size`` / ``winner_reason`` come from the variance-aware
        winner selection and let us emit a ``within_noise_floor`` suggestion
        when multiple configs scored statistically the same.
        """
        suggestions: list[dict] = []
        if not trials:
            return suggestions

        # Compare judge-vs-judge here: ``default_kb`` is the blended quality
        # (includes invariants); to ask "did the KB content actually lift the
        # judge?" we want the raw judge baseline from ``default_kb_judge``.
        no_kb = baselines.get("no_kb") or 0.0
        default_kb_judge = baselines.get("default_kb_judge") or 0.0
        if default_kb_judge - no_kb < 0.10:
            suggestions.append({
                "kind": "low_lift_baseline",
                "severity": "warning",
                "message": (
                    "The KB barely outperforms a no-retrieval answer "
                    f"({default_kb_judge*100:.0f}% vs {no_kb*100:.0f}%). "
                    "Consider whether your test questions actually require the KB, "
                    "or whether retrieval is finding the wrong chunks."
                ),
            })

        # Find the top-trial score; if even that is low, KB likely lacks coverage.
        best_score = max(t.get("score", 0.0) for t in trials)
        if best_score < 0.5:
            suggestions.append({
                "kind": "coverage_gap",
                "severity": "critical",
                "message": (
                    f"The best optimized configuration only scored {best_score*100:.0f}%. "
                    "This usually means the KB lacks coverage of the topics the test "
                    "questions ask about. Add more relevant sources or revise the "
                    "test questions."
                ),
            })
        elif best_score - (baselines.get("default_kb") or 0.0) < 0.05:
            suggestions.append({
                "kind": "saturated",
                "severity": "info",
                "message": (
                    "Optimization found only marginal improvement over default settings "
                    "(<5pts). The current configuration is already near-optimal for this "
                    "test set."
                ),
            })

        # Config sensitivity: if median trial is far below best trial, retrieval is fragile.
        scores = sorted(t.get("score", 0.0) for t in trials if t.get("status") == "completed")
        if scores:
            median = scores[len(scores) // 2]
            if best_score - median > 0.30:
                suggestions.append({
                    "kind": "retrieval_bottleneck",
                    "severity": "warning",
                    "message": (
                        "Performance varies widely across configurations "
                        f"(best {best_score*100:.0f}%, median {median*100:.0f}%). "
                        "Retrieval quality is highly config-sensitive — consider adding "
                        "more focused sources, or revisiting chunking when the indexing "
                        "track ships."
                    ),
                })

        # Within-noise-floor cluster (T2.2): multiple configs scored
        # statistically the same as the top — flag it so users know the
        # headline "winner" is one of several tied configs.
        if tie_cluster_size and tie_cluster_size > 1:
            reason_blurb = ""
            if winner_reason == "tied_with_baseline":
                reason_blurb = (
                    " The top trial is statistically tied with your current "
                    "config — apply was suppressed."
                )
            elif winner_reason == "closest_to_default":
                reason_blurb = (
                    " We picked the config with the fewest tweaks vs. default "
                    "to minimize surprise."
                )
            suggestions.append({
                "kind": "within_noise_floor",
                "severity": "info",
                "message": (
                    f"{tie_cluster_size} configurations scored within the judge's "
                    "noise floor of the top — they're statistically tied." + reason_blurb
                ),
            })

        # Per-axis marginal analysis (T2.3): bucket completed trials by each
        # search axis, compare mean score per bucket. Lifts smaller than
        # noise floor are reported as "axis didn't matter"; lifts > 2σ as
        # "axis matters: prefer value X".
        suggestions.extend(self._per_axis_marginal_suggestions(
            trials, judge_variance=baselines.get("judge_variance"),
        ))

        return suggestions

    @staticmethod
    def _per_axis_marginal_suggestions(
        trials: list[dict],
        *,
        judge_variance: float | None,
    ) -> list[dict]:
        """For each search axis, emit one suggestion about whether it mattered.

        Buckets completed trials by axis value, computes the mean score per
        bucket, and reports either "value=X dominates" (when best minus worst
        exceeds 2σ) or "axis didn't matter" (when all buckets agree within σ).
        Stays silent when buckets are too small to be meaningful.

        No new judge calls — pure re-aggregation of the trials we already have.
        """
        out: list[dict] = []
        completed = [t for t in trials if t.get("status") == "completed"]
        if len(completed) < 4:
            # Too few trials to draw any axis-level conclusion.
            return out

        # Trial ``score`` is blended (judge*0.40 + invariants). Only the judge
        # component varies between trials within a run, so the per-axis spread
        # we're comparing is in blended units — scale σ to match.
        judge_sigma = (
            judge_variance if judge_variance is not None else DEFAULT_JUDGE_NOISE_FLOOR
        )
        sigma = BLEND_WEIGHT_JUDGE * judge_sigma
        # Buckets per axis name → {axis_value: [scores]}.
        axes = {
            "k": "retrieval depth (k)",
            "prompt_variant": "prompt variant",
            "query_rewriting": "query rewriting",
            "source_label_visibility": "source labels",
            "model": "answer-generation model",
            "rerank": "LLM reranking",
            "answer_temperature": "answer temperature",
        }
        for axis, label in axes.items():
            buckets: dict[Any, list[float]] = {}
            for t in completed:
                cfg = t.get("config") or {}
                if axis not in cfg:
                    continue
                buckets.setdefault(cfg[axis], []).append(float(t.get("score") or 0.0))
            # Need at least 2 distinct values, with at least 2 trials in each
            # bucket, for the comparison to be remotely meaningful.
            usable = {v: s for v, s in buckets.items() if len(s) >= 2}
            if len(usable) < 2:
                continue
            means = {v: sum(s) / len(s) for v, s in usable.items()}
            best_val, best_mean = max(means.items(), key=lambda kv: kv[1])
            worst_val, worst_mean = min(means.items(), key=lambda kv: kv[1])
            spread = best_mean - worst_mean
            if spread > WINNER_TIE_SIGMAS * sigma:
                out.append({
                    "kind": "axis_matters",
                    "severity": "info",
                    "axis": axis,
                    "message": (
                        f"{label} mattered: best value '{best_val}' "
                        f"scored {best_mean*100:.0f}%, worst '{worst_val}' "
                        f"scored {worst_mean*100:.0f}% ({spread*100:.0f}pts spread)."
                    ),
                })
            elif spread < sigma:
                out.append({
                    "kind": "axis_irrelevant",
                    "severity": "info",
                    "axis": axis,
                    "message": (
                        f"{label} didn't move the score (spread {spread*100:.0f}pts, "
                        "within judge noise) — safe to leave at default."
                    ),
                })
        return out

    async def _apply_to_kb(
        self,
        kb_uuid: str,
        config: dict,
        run_uuid: str,
        run_doc: KBOptimizationRun | None = None,
    ) -> None:
        """Persist the winning RAGConfig to the KB so it's used at runtime.

        Snapshots the prior ``rag_config_override`` onto ``run_doc`` so a
        later Revert can restore it (Phase 1 of the loop-closure plan).
        """
        kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
        if not kb:
            return
        prior = kb.rag_config_override
        kb.rag_config_override = dict(config)
        kb.rag_config_override_set_at = _now()
        kb.rag_config_override_run_uuid = run_uuid
        await kb.save()
        if run_doc is not None:
            run_doc.previous_override = dict(prior) if prior else None
            run_doc.applied_at = _now()
            run_doc.reverted_at = None
            await run_doc.save()

    async def _notify_terminal(self, run_doc: KBOptimizationRun, kb) -> None:
        """Emit a Notification to the run's owner when the run reaches a
        terminal state. Best-effort — never raises into the caller.

        Thorough-tier runs span 45-90 minutes; users won't sit and watch the
        panel. The notification carries them back to the KB to inspect results.
        """
        from app.services import notification_service

        kb_title = (kb.title if kb else None) or "Knowledge base"
        link = f"/?mode=knowledge&kb={run_doc.kb_uuid}"

        if run_doc.status == "completed":
            kind = "kb_optimization_completed"
            score_pct = (run_doc.optimized_score or 0.0) * 100
            baseline_pct = (run_doc.baseline_default_score or 0.0) * 100
            lift = score_pct - baseline_pct
            sign = "+" if lift >= 0 else ""
            title = f"Optimization complete: {kb_title}"
            body = (
                f"Optimized score {score_pct:.0f}% "
                f"({sign}{lift:.0f}pts vs default). "
                f"{len(run_doc.trials)} trial{'s' if len(run_doc.trials) != 1 else ''} run."
            )
        elif run_doc.status == "cancelled":
            kind = "kb_optimization_cancelled"
            title = f"Optimization cancelled: {kb_title}"
            body = (
                f"Cancelled after {len(run_doc.trials)} trial"
                f"{'s' if len(run_doc.trials) != 1 else ''}."
            )
        elif run_doc.status == "failed":
            kind = "kb_optimization_failed"
            title = f"Optimization failed: {kb_title}"
            body = run_doc.error_message or "The optimization run failed unexpectedly."
        else:
            return  # not a terminal status we care about

        try:
            await notification_service.create_notification(
                user_id=run_doc.user_id,
                kind=kind,
                title=title,
                body=body,
                link=link,
                item_kind="knowledge_base",
                item_id=run_doc.kb_uuid,
                item_name=kb_title,
            )
        except Exception as e:
            logger.warning(
                "Could not emit %s notification for run %s: %s",
                kind, run_doc.uuid, e,
            )

    @staticmethod
    def _describe_config(cfg: dict) -> str:
        """Short human-readable summary for the live progress message."""
        bits = [f"k={cfg.get('k')}"]
        if cfg.get("model"):
            bits.append(cfg["model"])
        if cfg.get("prompt_variant") and cfg["prompt_variant"] != "default":
            bits.append(cfg["prompt_variant"])
        if cfg.get("query_rewriting"):
            bits.append("query-rewrite")
        if cfg.get("source_label_visibility") is False:
            bits.append("no-source-labels")
        if cfg.get("rerank") and cfg["rerank"] != "off":
            bits.append(f"rerank={cfg['rerank']}")
        temp = float(cfg.get("answer_temperature", 0.0) or 0.0)
        if temp != 0.0:
            bits.append(f"t={temp}")
        return " · ".join(bits)

    async def _finalize_cancelled(
        self, run_doc: KBOptimizationRun, kb,
    ) -> KBOptimizationRun:
        """Transition a run to the cancelled terminal state and notify.

        Shared by every cancel checkpoint so a cancel that lands after the
        trial sweep (e.g. mid holdout re-scoring) still stops the run instead
        of completing and applying the winner's config.
        """
        await self._update(
            run_doc, status="cancelled", phase="cancelled",
            progress_message="Cancelled by user.",
            stopped_reason="cancelled",
            completed_at=_now(),
        )
        await self._notify_terminal(run_doc, kb)
        return run_doc

    @staticmethod
    async def _update(run_doc: KBOptimizationRun, **fields) -> None:
        """Mutate-and-save helper. Keeps the run doc in sync with progress.

        Saves route through ``_save`` so a concurrently-requested cancel is
        pulled forward rather than reverted by this full-document write.
        """
        for k, v in fields.items():
            setattr(run_doc, k, v)
        try:
            await _save(run_doc)
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("Could not persist KBOptimizationRun update: %s", e)


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


async def _fetch_cancel_flag(run_uuid: str) -> bool:
    """Read the persisted ``cancel_requested`` flag straight from the DB.

    The cancel endpoint flips the flag on a freshly-loaded copy of the run.
    The worker holds a long-lived in-memory ``run_doc`` that is never
    refreshed during a run, so the database is the only reliable source of
    truth for whether a cancel has been requested.
    """
    fresh = await KBOptimizationRun.find_one({"uuid": run_uuid})
    return bool(fresh and fresh.cancel_requested)


async def _save(run_doc: KBOptimizationRun) -> None:
    """Persist ``run_doc`` without clobbering a concurrently-requested cancel.

    Beanie's ``.save()`` does a full-document replace, so writing the worker's
    stale in-memory copy would revert the cancel endpoint's ``cancel_requested``
    write — which is exactly why Cancel never stopped a running KB tune. Pull
    the persisted flag forward first so saves preserve it (and so the next
    ``_is_cancelled`` check sees it).
    """
    if not run_doc.cancel_requested and await _fetch_cancel_flag(run_doc.uuid):
        run_doc.cancel_requested = True
    await run_doc.save()


async def _is_cancelled(run_doc: KBOptimizationRun) -> bool:
    """True when a cancel has been requested for this run.

    Reads the flag from the database rather than trusting the worker's
    long-lived in-memory ``run_doc``, which is never refreshed during a run.
    """
    if run_doc.cancel_requested:
        return True
    if await _fetch_cancel_flag(run_doc.uuid):
        run_doc.cancel_requested = True
        return True
    return False
