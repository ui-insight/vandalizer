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
import logging
import random
from typing import Any
from uuid import uuid4

from app.models.kb_optimization_run import KBOptimizationRun
from app.models.kb_test_query import KBTestQuery
from app.models.knowledge import KnowledgeBase
from app.models.system_config import SystemConfig
from app.services import kb_validation_service
from app.services.kb_validation_service import RAGConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Search space — cheap track only (v1)
# ---------------------------------------------------------------------------

K_VALUES = [4, 6, 8, 10, 12, 16]
PROMPT_VARIANTS = ["default", "strict", "concise"]
QUERY_REWRITING = [False, True]
SOURCE_LABEL_VISIBILITY = [True, False]

# How many trials at most we plan, regardless of budget. Caps DB document size.
MAX_TRIAL_COUNT = 100

# Conservative per-trial token estimate used for budget pacing — overridden
# after each trial by the actual usage we record from pydantic-ai.
DEFAULT_TRIAL_TOKEN_ESTIMATE = 100_000

# Auto-generation fallback when the user has no test queries yet but the
# optimizer is invoked anyway (e.g. via direct API call).
DEFAULT_AUTOGEN_COVERAGE = "standard"


def _enabled_model_names(sys_cfg: SystemConfig | None) -> list[str]:
    if not sys_cfg:
        return []
    out: list[str] = []
    for entry in sys_cfg.available_models or []:
        if isinstance(entry, dict) and entry.get("name"):
            out.append(str(entry["name"]))
    return out


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
                        space.append({
                            "k": k,
                            "model": model,
                            "prompt_variant": prompt_variant,
                            "query_rewriting": query_rewriting,
                            "source_label_visibility": source_label_visibility,
                        })
    return space


def _sample_trial_configs(
    search_space: list[dict],
    token_budget: int,
    per_trial_estimate: int = DEFAULT_TRIAL_TOKEN_ESTIMATE,
    rng: random.Random | None = None,
) -> list[dict]:
    """Random sample without replacement, capped by budget and MAX_TRIAL_COUNT."""
    rng = rng or random.Random()
    target = min(MAX_TRIAL_COUNT, max(0, token_budget // max(1, per_trial_estimate)))
    if target <= 0:
        return []
    pool = list(search_space)
    rng.shuffle(pool)
    return pool[:target]


def _config_is_default(cfg: dict) -> bool:
    """A trial is the 'default config' when its knobs match RAGConfig defaults."""
    return (
        cfg.get("k") == kb_validation_service.DEFAULT_K
        and cfg.get("prompt_variant") == "default"
        and cfg.get("query_rewriting") is False
        and cfg.get("source_label_visibility") is True
        # NOTE: model is intentionally NOT compared — default-model varies by user.
    )


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

        rng = random.Random(rng_seed) if rng_seed is not None else random.Random()

        try:
            await self._update(run_doc, status="running", phase="preparing",
                               progress_message="Loading KB and test queries…")
            kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
            if not kb:
                raise ValueError("Knowledge base not found")

            test_queries = await self._ensure_test_queries(kb_uuid, user_id, run_doc)
            if not test_queries:
                raise ValueError("Could not establish a test query set for this KB")

            # ----- Resolve model -----
            from app.services.workflow_validator import _resolve_model_name as _resolve_sync
            user_default_model = await asyncio.to_thread(_resolve_sync, user_id)
            if not user_default_model:
                raise ValueError("No LLM model configured for this user")

            sys_cfg = await SystemConfig.get_config()
            enabled_models = _enabled_model_names(sys_cfg)
            # Optimizer treats the user's resolved model as the safe fallback.
            if user_default_model not in enabled_models:
                enabled_models = [user_default_model] + enabled_models

            # ----- Establish baselines (no-KB first, then default-KB) -----
            # Measure no-KB first and persist it before the heavier default-KB
            # pass, so the running tab can show users the target score to beat
            # while the rest of the optimization runs.
            await self._update(run_doc, phase="running",
                               judge_model=user_default_model,
                               progress_message="Measuring no-KB baseline (score to beat)…")
            baselines = await self._establish_baselines(
                run_doc, kb_uuid, user_id, test_queries, user_default_model,
            )

            # ----- Build & sample trials -----
            search_space = _build_search_space(enabled_models)
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
            for i, cfg_dict in enumerate(trial_configs, start=1):
                # Cancellation check (re-fetch so a UI cancel propagates).
                fresh = await KBOptimizationRun.find_one(KBOptimizationRun.uuid == run_uuid)
                if fresh and fresh.cancel_requested:
                    await self._update(run_doc, status="cancelled", phase="cancelled",
                                       progress_message="Cancelled by user.",
                                       completed_at=_now())
                    await self._notify_terminal(run_doc, kb)
                    return run_doc

                # Budget check.
                if run_doc.tokens_used >= token_budget:
                    logger.info("Token budget exhausted — stopping at trial %d", i - 1)
                    break

                msg = self._describe_config(cfg_dict)
                await self._update(
                    run_doc,
                    current_trial_index=i,
                    progress_message=f"Trial {i} of {len(trial_configs)}: {msg}",
                )

                trial_result = await self._run_trial(
                    cfg_dict, kb_uuid, user_id, test_queries, user_default_model,
                    baseline_default_score=baselines["default_kb"],
                )
                run_doc.trials.append(trial_result)
                run_doc.tokens_used += trial_result["tokens_used"]

                if best_trial is None or trial_result["score"] > best_trial["score"]:
                    best_trial = trial_result
                    await self._update(
                        run_doc,
                        best_score_so_far=trial_result["score"],
                        best_config_so_far=trial_result["config"],
                        trials=run_doc.trials,
                        tokens_used=run_doc.tokens_used,
                    )
                else:
                    await self._update(
                        run_doc, trials=run_doc.trials, tokens_used=run_doc.tokens_used,
                    )

            # ----- Finalize -----
            await self._update(run_doc, phase="finalizing",
                               progress_message="Generating data source suggestions…")
            optimized_score = best_trial["score"] if best_trial else baselines["default_kb"]
            best_config = best_trial["config"] if best_trial else None
            suggestions = self._analyse_suggestions(
                run_doc.trials, baselines, test_queries,
            )

            await self._update(
                run_doc,
                optimized_score=optimized_score,
                best_config=best_config,
                data_source_suggestions=suggestions,
            )

            # ----- Apply (if requested) -----
            if apply_on_finish and best_config:
                await self._apply_to_kb(kb_uuid, best_config, run_uuid)
                await self._update(
                    run_doc, progress_message="Applied optimized settings to KB.",
                )

            await self._update(
                run_doc, status="completed", phase="done",
                progress_message="Optimization complete.",
                completed_at=_now(),
            )
            await self._notify_terminal(run_doc, kb)
            return run_doc

        except Exception as e:
            logger.exception("KB optimization failed (run %s): %s", run_uuid, e)
            await self._update(
                run_doc, status="failed", phase="failed",
                error_message=f"{type(e).__name__}: {str(e)[:500]}",
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
        """Load existing queries with expected_answer; if none, auto-generate
        Standard coverage (UI's default flow already covers manual selection)."""
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
        coverage = (run_doc.options or {}).get("autogen_coverage") or DEFAULT_AUTOGEN_COVERAGE
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
        """Establish no-KB and default-KB baselines in two visible phases.

        Phase 1 measures the no-KB target score (the bar the KB must beat) and
        persists it on ``run_doc`` immediately so the running tab can display
        it. Phase 2 then measures the default-KB score and runs a small judge
        variance sample on those results.

        Token usage is read from real pydantic-ai usage on each agent run
        (no estimation). Variance sampling adds two extra judge calls whose
        tokens we also account for.
        """
        # --- Phase 1: no-KB baseline (the score to beat) ---
        baseline_result = await kb_validation_service.judge_baselines_only(
            test_queries, model_name,
        )
        no_kb = baseline_result.get("avg_baseline_score") or 0.0
        baseline_tokens = int(baseline_result.get("tokens_used", 0) or 0)
        no_kb_rounded = round(no_kb, 4)
        await self._update(
            run_doc,
            baseline_no_kb_score=no_kb_rounded,
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

        # Light variance sample: re-judge two queries' KB answers and compare.
        # ``_sample_judge_variance`` returns (variance, tokens_used).
        by_uuid = {q.uuid: q for q in test_queries}
        variance, variance_tokens = await kb_validation_service._sample_judge_variance(
            kb_uuid, result.get("details", []), by_uuid, model_name,
        )

        default_kb_rounded = round(default_kb, 4)
        await self._update(
            run_doc,
            baseline_default_score=default_kb_rounded,
            judge_variance=variance,
            tokens_used=run_doc.tokens_used + judge_tokens + variance_tokens,
        )

        return {
            "no_kb": no_kb_rounded,
            "default_kb": default_kb_rounded,
            "judge_variance": variance,
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
    ) -> dict:
        """Run judge_test_queries with a specific RAGConfig override per query.

        We monkey-patch ``_generate_kb_answer`` for the duration of this trial
        so the existing judge_test_queries helper (which doesn't know about
        RAGConfig) routes through the trial's config without further refactor.
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
        try:
            judge_result = await kb_validation_service.judge_test_queries(
                kb_uuid, test_queries, effective_model, mode="judge",
            )
        except Exception as e:
            logger.exception("Trial %s failed: %s", trial_id, e)
            kb_validation_service._generate_kb_answer = original_gen
            return {
                "trial_id": trial_id,
                "config": cfg_dict,
                "score": 0.0,
                "lift_vs_default": -baseline_default_score,
                "tokens_used": 0,
                "status": "failed",
                "error": str(e)[:200],
                "started_at": started.isoformat(),
                "duration_seconds": (_now() - started).total_seconds(),
            }
        finally:
            kb_validation_service._generate_kb_answer = original_gen

        score = judge_result.get("avg_judge_score") or 0.0
        n_judged = judge_result.get("num_queries_judged", 0) or 0
        # Real token usage comes from judge_test_queries; fall back to the
        # estimate only when the upstream didn't report any (e.g. mocked tests
        # or a provider that doesn't expose usage).
        real_tokens = int(judge_result.get("tokens_used", 0) or 0)
        tokens_used = real_tokens if real_tokens > 0 else (n_judged * 5_000 or DEFAULT_TRIAL_TOKEN_ESTIMATE)
        return {
            "trial_id": trial_id,
            "config": cfg_dict,
            "score": round(score, 4),
            "lift_vs_default": round(score - baseline_default_score, 4),
            "num_queries_judged": n_judged,
            "discrimination_summary": judge_result.get("discrimination_summary"),
            "tokens_used": tokens_used,
            "status": "completed",
            "started_at": started.isoformat(),
            "duration_seconds": round((_now() - started).total_seconds(), 2),
        }

    def _analyse_suggestions(
        self,
        trials: list[dict],
        baselines: dict,
        test_queries: list[KBTestQuery],
    ) -> list[dict]:
        """Heuristic post-mortem on the trials to surface KB-data improvements.

        Coarse for v1; we mainly want to highlight obvious gaps and
        config-sensitivity. The thresholds are intentionally conservative so
        we don't emit a wall of noise.
        """
        suggestions: list[dict] = []
        if not trials:
            return suggestions

        no_kb = baselines.get("no_kb") or 0.0
        if (baselines.get("default_kb") or 0.0) - no_kb < 0.10:
            suggestions.append({
                "kind": "low_lift_baseline",
                "severity": "warning",
                "message": (
                    "The KB barely outperforms a no-retrieval answer "
                    f"({(baselines.get('default_kb') or 0.0)*100:.0f}% vs {no_kb*100:.0f}%). "
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
        return suggestions

    async def _apply_to_kb(self, kb_uuid: str, config: dict, run_uuid: str) -> None:
        """Persist the winning RAGConfig to the KB so it's used at runtime."""
        kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
        if not kb:
            return
        kb.rag_config_override = dict(config)
        kb.rag_config_override_set_at = _now()
        kb.rag_config_override_run_uuid = run_uuid
        await kb.save()

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
        return " · ".join(bits)

    @staticmethod
    async def _update(run_doc: KBOptimizationRun, **fields) -> None:
        """Mutate-and-save helper. Keeps the run doc in sync with progress."""
        for k, v in fields.items():
            setattr(run_doc, k, v)
        try:
            await run_doc.save()
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("Could not persist KBOptimizationRun update: %s", e)


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)
