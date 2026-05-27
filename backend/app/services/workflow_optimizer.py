"""Workflow optimizer — closed-loop autovalidate for workflows.

Mirrors the structure of ``extraction_optimizer`` and ``kb_optimizer``:

1. Measure baselines so the user can answer "is this workflow earning its
   complexity?":
   * ``baseline_no_workflow`` — single-shot LLM call against the source input,
     scored on the same validation plan. The "is a workflow even necessary
     for this task?" floor.
   * ``baseline_default`` — workflow as configured (respecting any existing
     override).
2. Sweep candidate configurations: per-LLM-step model + prompt variant.
   Trials run the full workflow end-to-end against each test input and score
   the final output against the validation plan.
3. Pick a defensible winner using variance-aware tie-breaking (don't crown
   wins inside the judge's noise floor).
4. Optionally apply the best per-step config back to ``Workflow.config_override``.

v1 search space is intentionally narrow ({model × prompt_variant} per LLM step)
because the smallest viable optimizer should fit within the budget tiers users
expect. Step removal and retry-policy trials are deferred to a later phase.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
import random
from typing import Any

from beanie import PydanticObjectId

from app.models.system_config import SystemConfig
from app.models.workflow import Workflow, WorkflowResult
from app.models.workflow_optimization_run import WorkflowOptimizationRun
from app.services.budget_enforcer import BudgetEnforcer
from app.services.config_service import get_user_model_name
from app.services.optimization_common import build_apply_preview, pick_winner_variance_aware
from app.services.workflow_prompt_variants import PROMPT_VARIANTS

logger = logging.getLogger(__name__)


# Per-trial token estimate for budget bookkeeping. Workflow trials run the
# full pipeline N times (one per test input), so this is a deliberately wide
# ceiling — the optimizer is conservative about fitting trials in a tier.
WORKFLOW_PER_TRIAL_TOKEN_ESTIMATE = 200_000

# Hard cap on trials regardless of budget. The optimizer's UI is unhelpful
# past ~25 trials, and storage cost in the run doc grows linearly.
DEFAULT_MAX_WORKFLOW_CANDIDATES = 10

# Fallback noise floor on the 0..1 score scale when judge variance couldn't be
# measured. 0.04 ≈ "4 pts on a 0..100 score" — workflows judge a small number
# of checks per run (typically 4–8), so a single verdict flip moves the score
# more than in extraction. Passed to pick_winner_variance_aware as the
# domain-specific override of the shared 0.02 default.
DEFAULT_WORKFLOW_JUDGE_NOISE_FLOOR = 0.04

# Early-stop: if a trial's running mean is more than this fraction below
# baseline_default after >= 30% of test inputs, abandon the trial. Spares
# budget on configs that are clearly worse.
EARLY_STOP_DELTA = 0.10
EARLY_STOP_FRACTION = 0.30

# Concurrency for trial execution. Each trial is I/O-bound on LLM calls and
# already parallelizes within a step via the engine's MultiTaskNode. 3 is the
# plan's target — high enough to compress wall time, low enough to avoid
# hammering the LLM endpoint.
TRIAL_CONCURRENCY = 3

# Train/holdout split. Workflow test inputs are user-marked expected outputs
# (typically 3-8), so the split threshold is lower than KB/extraction. With
# fewer than this many inputs the holdout would be useless; we skip the split
# and flag ``overfitting_warning`` so the UI can caveat the headline score.
HOLDOUT_MIN_INPUTS = 4
# Fraction of inputs reserved for holdout. 0.4 keeps both slices non-trivial
# at small N: N=4 → 2/2, N=5 → 3/2, N=6 → 4/2, N=10 → 6/4.
HOLDOUT_FRACTION = 0.4

# Convergence stopping. Need at least this many completed trials before we
# can claim convergence — early trials don't explore enough to pick a
# defensible winner.
CONVERGENCE_MIN_TRIALS = 5
# Patience window: trials completed since the leader's score last improved
# before we consider stopping. Larger = more conservative.
CONVERGENCE_PATIENCE = 4


# Task names whose ``data.prompt`` / analogous field is variant-eligible. Must
# stay in sync with the engine's _PROMPT_VARIANT_TASKS.
_PROMPT_VARIANT_TASKS = {"Prompt", "Formatter", "ResearchNode", "FormFiller"}

# Task names that are LLM-driven (model swap is meaningful). Extraction is
# included because it picks a model but isn't prompt-variant eligible.
_LLM_TASKS = _PROMPT_VARIANT_TASKS | {"Extraction", "DescribeImage"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_optimization(
    workflow_id: str,
    user_id: str,
    run_uuid: str,
    budget_tokens: int = 0,
    apply_on_finish: bool = False,
    max_candidates: int = DEFAULT_MAX_WORKFLOW_CANDIDATES,
    include_judge: bool = True,
    rng_seed: int | None = None,
) -> WorkflowOptimizationRun:
    """Execute the full optimization loop. Caller pre-allocates the run doc.

    ``include_judge`` is on by default for workflows — the workflow validator
    is judge-based to begin with, so omitting it would leave nothing to score
    against. Setting False is mainly useful for tests / dry runs.
    """
    # Dict-style query so the optimizer is testable without Beanie's init_db
    # wiring (the field-access form raises AttributeError when models aren't
    # registered yet — same pattern the routers follow).
    run_doc = await WorkflowOptimizationRun.find_one({"uuid": run_uuid})
    if not run_doc:
        raise ValueError(f"WorkflowOptimizationRun not found: {run_uuid}")

    try:
        await _update(run_doc, status="running", phase="preparing",
                      progress_message="Loading workflow and test inputs…")

        try:
            wf = await Workflow.get(PydanticObjectId(workflow_id))
        except Exception:
            wf = None
        if not wf:
            raise ValueError(f"Workflow not found: {workflow_id}")
        if not wf.validation_plan:
            raise ValueError(
                "Workflow has no validation plan. Generate or add checks first "
                "(Validate tab → Generate plan)."
            )

        test_inputs = await _resolve_test_inputs(wf)
        if not test_inputs:
            raise ValueError(
                "No test inputs available. Mark at least one past workflow run "
                "as 'expected output' on the Validate tab before optimizing."
            )

        # Train/holdout split — winner selection happens on train, headline
        # ``optimized_score`` is re-measured on holdout. Without this, best-of-N
        # selection bias inflates the score by roughly 2σ × √(2 ln N), turning
        # judge noise into "lift" on a test set where N is already small.
        train_inputs, holdout_inputs = _split_train_holdout(test_inputs, workflow_id)
        run_doc.train_input_ids = [str(ti.get("id", "") or "") for ti in train_inputs]
        run_doc.holdout_input_ids = [str(ti.get("id", "") or "") for ti in holdout_inputs]
        run_doc.overfitting_warning = not holdout_inputs
        await run_doc.save()

        sys_config = await SystemConfig.get_config()
        available_models = list(sys_config.available_models) if sys_config else []
        baseline_model = await get_user_model_name(user_id)

        judge_model = baseline_model if include_judge else None
        if judge_model:
            run_doc.judge_model = judge_model
            await run_doc.save()

        # --- Phase 1: baselines ---
        await _update(run_doc, phase="baselines",
                      progress_message="Measuring baselines…")

        from app.services.workflow_service import _measure_no_workflow_baseline, get_workflow

        wf_data = await get_workflow(workflow_id)

        # No-workflow baseline (single-shot prompt against the source text).
        # Best-effort — `_measure_no_workflow_baseline` returns None when the
        # workflow input isn't a document text we can reuse.
        no_wf_scores: list[float] = []
        for ti in train_inputs:
            ref_result = await _load_result_for_test_input(ti)
            if not ref_result:
                continue
            res = await _measure_no_workflow_baseline(
                wf_data=wf_data,
                last_result=ref_result,
                user_id=user_id,
            )
            if res and res.get("weighted_pass_rate") is not None:
                no_wf_scores.append(float(res["weighted_pass_rate"]))
        if no_wf_scores:
            run_doc.baseline_no_workflow_score = round(
                sum(no_wf_scores) / len(no_wf_scores), 4,
            )
            await run_doc.save()

        # Default baseline: run the workflow with its currently-applied config
        # (override-or-authored) against each test input.
        await _update(run_doc, progress_message="Scoring current configuration…")
        default_trial = await _run_single_trial(
            wf=wf,
            wf_data=wf_data,
            user_id=user_id,
            step_overrides=_extract_current_step_overrides(wf),
            test_inputs=train_inputs,
            baseline_score=None,  # no early-stop on the default baseline itself
            label="baseline-default",
        )
        run_doc.baseline_default_score = default_trial.get("score")
        await run_doc.save()

        # Workflow judge variance: replay the default trial's per-check
        # verdicts. Measured here (before the sweep) so the convergence test
        # can gate on real σ instead of the conservative fallback floor.
        if judge_model and default_trial.get("variance_samples"):
            variance = _compute_workflow_variance(default_trial["variance_samples"])
            if variance is not None:
                run_doc.judge_variance = variance
                await run_doc.save()

        if _is_cancelled(run_doc):
            return await _finalize_cancelled(run_doc)

        # --- Phase 2: trial sweep ---
        await _update(run_doc, phase="sweep",
                      progress_message="Trying configurations…")

        # Pre-generate one rewritten prompt per prompt-eligible step. Cached
        # here so trials don't repeatedly call the LLM for the same rewrite.
        # Best-effort — missing rewrites just mean no rewrite candidates for
        # that step, not an aborted run.
        prompt_rewrites = await _generate_prompt_rewrites(wf_data, user_id=user_id)

        candidates = _build_candidates(
            wf_data=wf_data,
            available_models=available_models,
            baseline_model=baseline_model,
            max_candidates=max_candidates,
            rng_seed=rng_seed,
            prompt_rewrites=prompt_rewrites,
        )

        # Budget cap. The estimate is pessimistic; we may run fewer trials
        # than budget allows once a trial early-stops.
        if budget_tokens > 0:
            enforcer = BudgetEnforcer(
                total_budget=budget_tokens,
                per_trial_estimate=WORKFLOW_PER_TRIAL_TOKEN_ESTIMATE,
                max_trial_count=max_candidates,
            )
            candidates = enforcer.sample_trials(candidates)

        run_doc.total_trials_planned = len(candidates)
        await run_doc.save()

        trial_results: list[dict] = []
        baseline_score = run_doc.baseline_default_score

        # Sliding-window concurrency: run TRIAL_CONCURRENCY trials in parallel,
        # rolling onto the next as each completes. Cheaper than gather()ing
        # the whole batch because we update best-so-far between completions.
        semaphore = asyncio.Semaphore(TRIAL_CONCURRENCY)
        trial_idx = {"i": 0}

        async def _bounded_trial(candidate: dict) -> dict:
            async with semaphore:
                if _is_cancelled(run_doc):
                    return {"label": candidate["label"], "status": "cancelled"}
                trial_idx["i"] += 1
                await _update(
                    run_doc,
                    current_trial_index=trial_idx["i"],
                    progress_message=f"Trying {candidate['label']}…",
                )
                return await _run_single_trial(
                    wf=wf,
                    wf_data=wf_data,
                    user_id=user_id,
                    step_overrides=candidate["step_overrides"],
                    test_inputs=train_inputs,
                    baseline_score=baseline_score,
                    label=candidate["label"],
                )

        # asyncio.as_completed lets us update best-so-far the moment each
        # trial finishes — the UI shows a useful live ticker even when
        # later trials are still grinding.
        pending = [asyncio.create_task(_bounded_trial(c)) for c in candidates]
        # Convergence tracking: completed trials since the leader improved.
        # When the leader stays put for ``CONVERGENCE_PATIENCE`` rounds AND
        # is clearly ahead of the runner-up (gap > 2σ), cancel the remaining
        # tasks. Stopping earlier than the budget allows is the whole point
        # of a convergence rule.
        trials_since_best_changed = 0
        stopped_reason: str | None = None
        for fut in asyncio.as_completed(pending):
            result = await fut
            trial_summary = _to_trial_summary(result, baseline_default_score=baseline_score)
            trial_results.append(trial_summary)

            score = trial_summary.get("score")
            improved = (
                score is not None
                and (run_doc.best_score_so_far is None or score > run_doc.best_score_so_far)
            )
            if improved:
                run_doc.best_score_so_far = score
                run_doc.best_config_so_far = trial_summary.get("config")
                trials_since_best_changed = 0
            else:
                trials_since_best_changed += 1

            run_doc.trials = trial_results
            run_doc.tokens_used = sum(int(t.get("tokens_used", 0) or 0) for t in trial_results)
            await run_doc.save()

            if (
                len(trial_results) >= CONVERGENCE_MIN_TRIALS
                and trials_since_best_changed >= CONVERGENCE_PATIENCE
            ):
                sigma = (
                    run_doc.judge_variance
                    if run_doc.judge_variance is not None
                    else DEFAULT_WORKFLOW_JUDGE_NOISE_FLOOR
                )
                completed_scores = sorted(
                    (
                        float(t["score"]) for t in trial_results
                        if t.get("status") in ("completed", "early_stopped")
                        and t.get("score") is not None
                    ),
                    reverse=True,
                )
                if len(completed_scores) >= 2 and (completed_scores[0] - completed_scores[1]) > 2.0 * sigma:
                    logger.info(
                        "Workflow optimizer converged after %d trials: best %.3f, runner-up %.3f, σ %.3f",
                        len(trial_results), completed_scores[0], completed_scores[1], sigma,
                    )
                    stopped_reason = "converged"
                    for t in pending:
                        if not t.done():
                            t.cancel()
                    break
        else:
            # for-else: hit only when the loop exhausts without `break`.
            stopped_reason = "all_trials_complete"

        run_doc.stopped_reason = stopped_reason
        await run_doc.save()

        # --- Phase 3: winner selection + holdout ---
        await _update(run_doc, phase="finalizing",
                      progress_message="Finalizing results…")

        if trial_results:
            n_items = max(1, len(train_inputs))
            sigma = run_doc.judge_variance if run_doc.judge_variance is not None else DEFAULT_WORKFLOW_JUDGE_NOISE_FLOOR
            run_doc.judge_score_se = round(sigma / (n_items ** 0.5), 4)

            default_overrides = _extract_current_step_overrides(wf)
            winner, reason, tied, _cluster_size = pick_winner_variance_aware(
                trial_results,
                judge_variance=run_doc.judge_variance,
                baseline_default_score=run_doc.baseline_default_score,
                distance_from_default=lambda t: _override_distance(
                    (t.get("config") or {}).get("step_overrides"),
                    default_overrides,
                ),
                n_items_for_se=n_items,
                completed_statuses=("completed", "early_stopped"),
                fallback_noise_floor=DEFAULT_WORKFLOW_JUDGE_NOISE_FLOOR,
            )
            run_doc.winner_selection_reason = (
                "no_judge_variance" if run_doc.judge_variance is None else reason
            )
            run_doc.tied_with_baseline = tied

            if winner is not None:
                # Preserve the in-sample (train) score for diagnostics. The
                # headline ``optimized_score`` may be overwritten below by
                # the holdout re-score when we have a holdout slice.
                run_doc.optimized_score_train = winner.get("score")
                run_doc.optimized_score = winner.get("score")
                run_doc.best_config = winner.get("config")
                # Surface the winning trial's step_breakdown at the run level
                # so the UI doesn't have to re-find the winner in the trials
                # list.
                run_doc.step_breakdown = list(winner.get("step_breakdown") or [])
                run_doc.best_per_step_config = dict(
                    (winner.get("config") or {}).get("step_overrides") or {}
                )

                # Holdout re-evaluation: rerun the winning config AND the
                # default config on the held-out inputs. The headline score
                # becomes the holdout number (unbiased by best-of-N selection).
                if holdout_inputs:
                    await _update(
                        run_doc,
                        progress_message="Re-scoring winner on held-out inputs…",
                    )
                    winner_overrides = (winner.get("config") or {}).get("step_overrides") or {}
                    try:
                        holdout_winner = await _run_single_trial(
                            wf=wf,
                            wf_data=wf_data,
                            user_id=user_id,
                            step_overrides=winner_overrides,
                            test_inputs=holdout_inputs,
                            baseline_score=None,
                            label="holdout-winner",
                        )
                        if holdout_winner.get("score") is not None:
                            run_doc.optimized_score = holdout_winner.get("score")
                    except Exception as e:
                        logger.warning("Holdout re-score (winner) failed: %s", e)

                    try:
                        holdout_default = await _run_single_trial(
                            wf=wf,
                            wf_data=wf_data,
                            user_id=user_id,
                            step_overrides=default_overrides,
                            test_inputs=holdout_inputs,
                            baseline_score=None,
                            label="holdout-default",
                        )
                        if holdout_default.get("score") is not None:
                            run_doc.holdout_default_score = holdout_default.get("score")
                    except Exception as e:
                        logger.warning("Holdout re-score (default) failed: %s", e)

                run_doc.suggestions = _generate_suggestions(
                    step_breakdown=run_doc.step_breakdown,
                    baseline_no_workflow=run_doc.baseline_no_workflow_score,
                    baseline_default=run_doc.baseline_default_score,
                    optimized=run_doc.optimized_score,
                    best_per_step_config=run_doc.best_per_step_config,
                )

                # Apply-preview rollup (Phase 2): per-step baseline-vs-winner
                # score deltas so the Apply modal can disclose "K of N steps
                # will change, R regress" before the override flips. Items
                # match Phase 3's per-step apply granularity.
                run_doc.apply_preview = _build_step_apply_preview(
                    winner_breakdown=run_doc.step_breakdown,
                    default_breakdown=list(default_trial.get("step_breakdown") or []),
                    judge_variance=run_doc.judge_variance,
                )

        # Apply-on-finish only when the winner cleared the significance band.
        if (
            apply_on_finish
            and run_doc.best_config
            and not run_doc.tied_with_baseline
        ):
            await _apply_best(wf, run_doc)

        run_doc.status = "completed"
        run_doc.phase = "done"
        run_doc.progress_message = "Optimization complete"
        run_doc.completed_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await run_doc.save()
        return run_doc

    except Exception as e:
        logger.exception("Workflow optimization failed for %s", workflow_id)
        run_doc.status = "failed"
        run_doc.phase = "failed"
        run_doc.stopped_reason = "failed"
        run_doc.error_message = str(e)
        run_doc.completed_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await run_doc.save()
        return run_doc


# ---------------------------------------------------------------------------
# Test-input resolution
# ---------------------------------------------------------------------------


async def _resolve_test_inputs(wf: Workflow) -> list[dict]:
    """Return the list of test-input dicts the optimizer will run trials against.

    A test input is an ``expected_output`` entry on the workflow's
    ``validation_inputs``. Each entry references a past WorkflowResult by
    ``session_id``; we use that result's ``input_context.doc_uuids`` as the
    documents to feed the trial run.

    Returns a list of:
        {
          "id": str,                  # validation_input entry id
          "session_id": str,
          "doc_uuids": list[str],     # source docs for the trial
          "expected_output": str,     # captured expected output text
          "steps_output_snapshot": dict | None,
        }

    Entries missing doc_uuids are filtered out — the optimizer can't run a
    trial without input documents.
    """
    out: list[dict] = []
    for inp in (wf.validation_inputs or []):
        if inp.get("type") != "expected_output":
            continue
        session_id = inp.get("session_id")
        if not session_id:
            continue
        wr = await WorkflowResult.find_one({"session_id": session_id})
        if not wr:
            continue
        doc_uuids = (wr.input_context or {}).get("doc_uuids") or []
        if not doc_uuids:
            continue
        out.append({
            "id": inp.get("id", ""),
            "session_id": session_id,
            "doc_uuids": list(doc_uuids),
            "expected_output": inp.get("output_text", ""),
            "steps_output_snapshot": inp.get("steps_output_snapshot"),
        })
    return out


async def _load_result_for_test_input(test_input: dict):
    """Fetch the original WorkflowResult so baseline_no_workflow can re-use
    its ``steps_output`` to pull the source document text. Returns None when
    the result has been deleted since the expected_output was saved."""
    session_id = test_input.get("session_id")
    if not session_id:
        return None
    return await WorkflowResult.find_one({"session_id": session_id})


# ---------------------------------------------------------------------------
# Train / holdout split
# ---------------------------------------------------------------------------


def _split_train_holdout(
    test_inputs: list[dict],
    workflow_id: str,
) -> tuple[list[dict], list[dict]]:
    """Deterministically partition test inputs into (train, holdout).

    Hash on ``(workflow_id, test_input.id)`` so re-running the same workflow
    yields the same split — comparing two runs is apples-to-apples. Below
    ``HOLDOUT_MIN_INPUTS`` we return (all_inputs, []) and rely on the caller
    to flag ``overfitting_warning``; the holdout slice would be too thin to
    be informative at smaller N.
    """
    if len(test_inputs) < HOLDOUT_MIN_INPUTS:
        return list(test_inputs), []

    def _bucket(ti: dict) -> str:
        uid = str(ti.get("id", "") or ti.get("session_id", "") or "")
        return hashlib.sha256(f"{workflow_id}:{uid}".encode("utf-8")).hexdigest()

    ordered = sorted(test_inputs, key=_bucket)
    n_holdout = max(1, int(round(len(ordered) * HOLDOUT_FRACTION)))
    holdout = ordered[:n_holdout]
    train = ordered[n_holdout:]
    return train, holdout


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------


def _enumerate_llm_steps(wf_data: dict) -> list[dict]:
    """List eligible steps with their LLM-task names.

    Returns a list of:
        {"name": step_name, "tasks": [task_name, ...], "variant_eligible": bool}

    A step is variant-eligible when it contains at least one task in
    ``_PROMPT_VARIANT_TASKS``. Steps with only structured tasks (e.g.
    Extraction) appear but with ``variant_eligible=False`` — model swap only.
    """
    steps_out: list[dict] = []
    for step in (wf_data or {}).get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        sname = step.get("name", "")
        if not sname or sname == "Document":
            continue
        task_names = [t.get("name", "") for t in (step.get("tasks") or []) if isinstance(t, dict)]
        llm_tasks = [n for n in task_names if n in _LLM_TASKS]
        if not llm_tasks:
            continue
        steps_out.append({
            "name": sname,
            "tasks": llm_tasks,
            "variant_eligible": any(n in _PROMPT_VARIANT_TASKS for n in llm_tasks),
        })
    return steps_out


def _build_candidates(
    *,
    wf_data: dict,
    available_models: list[Any],
    baseline_model: str,
    max_candidates: int,
    rng_seed: int | None = None,
    prompt_rewrites: dict[str, str] | None = None,
) -> list[dict]:
    """Build a list of candidate per-step override dicts.

    Strategy:
    - Always include single-knob trials per (step, model) — swap one step's
      model, leave others at default. Clean attribution.
    - Plus a handful of "uniform" trials — every LLM step uses the same model
      (haiku / sonnet / opus). Reveals systemic model effects.
    - Plus per-step prompt-rewrite trials when ``prompt_rewrites`` is supplied.
      Each rewrites one step's prompt to a literal LLM-improved version,
      attribution stays clean since only that one knob changed.
    - Plus random per-step samples (model + variant) up to max_candidates.

    Each candidate dict shape:
        {"label": str, "step_overrides": {step_name: {"model": str, "prompt_variant": str | None, "prompt_rewrite"?: str}}}
    """
    rng = random.Random(rng_seed)
    prompt_rewrites = prompt_rewrites or {}

    model_names = _extract_model_names(available_models)
    if not model_names:
        model_names = [baseline_model] if baseline_model else []
    # Drop the baseline model from sweep candidates — its trial IS the default
    # baseline, so re-running it adds nothing.
    swap_models = [m for m in model_names if m != baseline_model]
    if not swap_models:
        swap_models = list(model_names)

    llm_steps = _enumerate_llm_steps(wf_data)
    if not llm_steps:
        return []

    candidates: list[dict] = []
    seen_keys: set[tuple] = set()

    def _add(label: str, overrides: dict[str, dict]) -> None:
        # Dedup on the (sorted) overrides shape — same overrides under
        # different labels are still the same trial.
        key = _overrides_key(overrides)
        if key in seen_keys:
            return
        seen_keys.add(key)
        candidates.append({"label": label, "step_overrides": overrides})

    # 1. Single-step model swaps (one per step × non-default model)
    for step in llm_steps:
        for m in swap_models[:2]:  # cap fan-out — 2 alt models per step
            _add(
                f"swap-{step['name']}-{_model_short(m)}",
                {step["name"]: {"model": m, "prompt_variant": "default"}},
            )

    # 2. Prompt-rewrite trials (one per step that got a rewrite). Single-knob:
    # only the rewritten step changes; all other steps stay at default. The
    # engine consumes ``prompt_rewrite`` ahead of ``prompt_variant`` so we
    # don't double-modify the prompt.
    for step in llm_steps:
        if not step["variant_eligible"]:
            continue
        rewrite = prompt_rewrites.get(step["name"])
        if not rewrite:
            continue
        _add(
            f"rewrite-{step['name']}",
            {step["name"]: {"prompt_variant": "default", "prompt_rewrite": rewrite}},
        )

    # 2b. Retry-on-empty with a fallback model trials. One per step × top
    # alternative model. Useful when the primary model occasionally drops
    # outputs (rate limits, partial outages). The engine retries this step
    # once with the fallback when the primary returns empty/error-shaped.
    for step in llm_steps:
        if not swap_models:
            continue
        fallback = swap_models[0]
        _add(
            f"retry-fallback-{step['name']}-{_model_short(fallback)}",
            {step["name"]: {
                "prompt_variant": "default",
                "retry_on_empty": True,
                "fallback_model": fallback,
            }},
        )

    # 3. Uniform-model trials — every LLM step uses model X
    for m in swap_models[:3]:
        overrides = {s["name"]: {"model": m, "prompt_variant": "default"} for s in llm_steps}
        _add(f"uniform-{_model_short(m)}", overrides)

    # 4. Random samples (per-step independent draws) to fill quota
    while len(candidates) < max_candidates:
        overrides: dict[str, dict] = {}
        for step in llm_steps:
            m = rng.choice(model_names) if model_names else baseline_model
            variants_pool = PROMPT_VARIANTS if step["variant_eligible"] else ["default"]
            v = rng.choice(variants_pool)
            overrides[step["name"]] = {"model": m, "prompt_variant": v}
        # Skip degenerate samples (all-default) that match the baseline.
        if _overrides_key(overrides) == _overrides_key({}):
            continue
        _add(f"random-{len(candidates) + 1}", overrides)
        # Safety brake — if the per-step search space is tiny, we may have
        # exhausted distinct candidates before hitting max_candidates.
        if len(seen_keys) > 5 * max_candidates:
            break

    return candidates[:max_candidates]


async def _generate_prompt_rewrites(
    wf_data: dict, *, user_id: str,
) -> dict[str, str]:
    """Generate one LLM-improved prompt per prompt-eligible step, parallel.

    Returns ``{step_name: rewritten_prompt}``. Steps without a rewrite (missing
    prompt, LLM error) are simply absent — the candidate builder will skip
    them rather than failing.
    """
    from app.services.prompt_improvement_service import improve_prompt

    # Build the list of (step_name, original_prompt, field, prev_step_name) tuples
    targets: list[tuple[str, str, str]] = []
    steps = (wf_data or {}).get("steps") or []
    prev_step_name = ""
    for step in steps:
        if not isinstance(step, dict):
            continue
        sname = step.get("name", "")
        if not sname or sname == "Document":
            prev_step_name = sname or prev_step_name
            continue
        for task in step.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            tname = task.get("name", "")
            if tname not in _PROMPT_VARIANT_TASKS:
                continue
            data = task.get("data") or {}
            # Same field mapping as the engine's _apply_step_override.
            field = {
                "Prompt": "prompt",
                "Formatter": "format_template",
                "ResearchNode": "question",
                "FormFiller": "template",
            }.get(tname)
            if not field:
                continue
            prompt_text = (data.get(field) or "").strip()
            if tname == "Formatter" and not prompt_text:
                prompt_text = (data.get("prompt") or "").strip()
            if not prompt_text:
                continue
            targets.append((sname, prompt_text, prev_step_name))
        prev_step_name = sname

    if not targets:
        return {}

    async def _one(sname: str, original: str, prev: str) -> tuple[str, str | None]:
        try:
            res = await improve_prompt(
                prompt=original,
                input_source="step_input" if prev else None,
                prev_step_name=prev or None,
            )
            improved = (res.get("improved_prompt") or "").strip()
            return (sname, improved or None)
        except Exception as e:
            logger.warning("Prompt rewrite failed for step %s: %s", sname, e)
            return (sname, None)

    results = await asyncio.gather(*(_one(s, p, prev) for s, p, prev in targets))
    return {sname: rewrite for sname, rewrite in results if rewrite}


def _extract_model_names(available_models: list[Any]) -> list[str]:
    out: list[str] = []
    for m in available_models or []:
        # SystemConfig.available_models entries can be dicts or pydantic models.
        if isinstance(m, dict):
            name = m.get("name")
        else:
            name = getattr(m, "name", None)
        if name:
            out.append(str(name))
    return out


def _model_short(model_name: str) -> str:
    """Compact label suffix for trial naming. Strips provider/path prefix."""
    s = (model_name or "").lower()
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    return s.replace(".", "-")[:24]


def _overrides_key(overrides: dict[str, dict]) -> tuple:
    """Stable hashable key for a step_overrides dict.

    Includes a coarse fingerprint of ``prompt_rewrite`` (first 80 chars) so two
    rewrite candidates that produced the same text dedupe, but different
    rewrites for the same step don't collapse. ``retry_on_empty`` /
    ``fallback_model`` are part of the key too so retry candidates don't
    collide with non-retry ones that happen to share the model.
    """
    items = []
    for step, ov in sorted(overrides.items()):
        rewrite = ov.get("prompt_rewrite")
        rewrite_fp = rewrite[:80] if isinstance(rewrite, str) and rewrite else None
        items.append((
            step,
            ov.get("model"),
            ov.get("prompt_variant"),
            rewrite_fp,
            bool(ov.get("retry_on_empty")),
            ov.get("fallback_model"),
        ))
    return tuple(items)


def _extract_current_step_overrides(wf: Workflow) -> dict[str, dict]:
    """Pull the currently-applied step_overrides off the workflow, if any."""
    override = wf.config_override or {}
    raw = override.get("step_overrides") or {}
    return {k: dict(v) for k, v in raw.items() if isinstance(v, dict)}


# ---------------------------------------------------------------------------
# Trial execution
# ---------------------------------------------------------------------------


async def _run_single_trial(
    *,
    wf: Workflow,
    wf_data: dict,
    user_id: str,
    step_overrides: dict[str, dict],
    test_inputs: list[dict],
    baseline_score: float | None,
    label: str,
) -> dict:
    """Run one trial across all test inputs and return aggregated metrics.

    Returns a dict shaped for ``_to_trial_summary``:
        {
          "label": str,
          "step_overrides": dict,
          "score": float (0..1),
          "weighted_pass_rate": float (0..1),
          "tokens_used": int,
          "duration_seconds": float,
          "step_breakdown": list[dict],     # averaged across test inputs
          "variance_samples": list[tuple[dict, dict]],  # for default trial only
          "status": "completed" | "early_stopped" | "failed",
          "error": str | None,
        }
    """
    started = datetime.datetime.now(tz=datetime.timezone.utc)

    per_input_scores: list[float] = []
    per_input_checks: list[list[dict]] = []
    tokens_used = 0
    error: str | None = None
    status = "completed"

    threshold = (
        baseline_score - EARLY_STOP_DELTA if baseline_score is not None else None
    )
    early_stop_at = max(1, int(len(test_inputs) * EARLY_STOP_FRACTION))

    for idx, ti in enumerate(test_inputs):
        try:
            final_output, judge_checks, t_in, t_out = await _execute_and_score(
                wf=wf,
                wf_data=wf_data,
                user_id=user_id,
                step_overrides=step_overrides,
                test_input=ti,
            )
        except Exception as e:
            logger.warning("Trial %s on input %s failed: %s", label, ti.get("id"), e)
            error = str(e)
            status = "failed"
            break

        tokens_used += t_in + t_out
        per_input_checks.append(judge_checks)
        per_input_scores.append(_weighted_pass_rate(wf_data.get("validation_plan") or [], judge_checks))

        # Early-stop: if we've seen enough inputs and the running mean is
        # well below the baseline, abandon this trial.
        if (
            threshold is not None
            and idx + 1 >= early_stop_at
            and (sum(per_input_scores) / len(per_input_scores)) < threshold
        ):
            status = "early_stopped"
            break

    score = (sum(per_input_scores) / len(per_input_scores)) if per_input_scores else 0.0

    # Aggregate per-step breakdown across test inputs (mean of per-input
    # step pass-rates). Uses the same scoring formula as workflow_service.
    step_breakdown = _aggregate_step_breakdown(
        plan=wf_data.get("validation_plan") or [],
        checks_per_input=per_input_checks,
    )

    elapsed = (datetime.datetime.now(tz=datetime.timezone.utc) - started).total_seconds()

    return {
        "label": label,
        "step_overrides": step_overrides,
        "score": round(score, 4),
        "weighted_pass_rate": round(score, 4),
        "tokens_used": tokens_used,
        "duration_seconds": round(elapsed, 2),
        "step_breakdown": step_breakdown,
        # variance_samples is populated only for the default baseline trial,
        # via the variance helper below; trials don't store it to save space.
        "variance_samples": _build_variance_samples(per_input_checks) if label == "baseline-default" else [],
        "status": status,
        "error": error,
        "num_inputs_run": len(per_input_scores),
        "num_inputs_total": len(test_inputs),
    }


async def _execute_and_score(
    *,
    wf: Workflow,
    wf_data: dict,
    user_id: str,
    step_overrides: dict[str, dict],
    test_input: dict,
) -> tuple[Any, list[dict], int, int]:
    """Run the workflow against one test input and score the final output.

    Returns ``(final_output, judge_checks, tokens_in, tokens_out)``. ``final_output``
    is whatever the engine produced; ``judge_checks`` is the per-check verdict
    list from ``_evaluate_checks_against_output``.
    """
    final_output, steps_output, t_in, t_out = await _execute_workflow_inproc(
        wf_id=str(wf.id),
        wf_data=wf_data,
        user_id=user_id,
        step_overrides=step_overrides,
        doc_uuids=test_input["doc_uuids"],
    )

    output_text = _serialize_for_judge(final_output)
    if output_text is None:
        # Binary output — judge would SKIP everything; treat as failure for
        # this test input but don't abort the whole trial.
        return final_output, [], t_in, t_out

    from app.services.workflow_service import _evaluate_checks_against_output

    plan = wf_data.get("validation_plan") or []
    checks = await _evaluate_checks_against_output(
        plan, output_text, steps_output or {}, wf_data,
    )
    return final_output, checks, t_in, t_out


async def _execute_workflow_inproc(
    *,
    wf_id: str,
    wf_data: dict,
    user_id: str,
    step_overrides: dict[str, dict],
    doc_uuids: list[str],
) -> tuple[Any, dict, int, int]:
    """Execute the workflow synchronously in-process with the given overrides.

    The engine is sync — we run it on a worker thread to avoid blocking the
    event loop. Returns ``(final_output, steps_output_dict, tokens_in, tokens_out)``.

    This bypasses the Celery ``execute_workflow_task`` because we want
    in-process control: the optimizer needs the engine output directly and
    can't afford the queue round-trip for every trial.
    """
    from app.models.system_config import SystemConfig
    from app.services.workflow_engine import build_workflow_engine, sanitize_step_name

    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}

    # Default model: same resolution path Celery uses.
    model = await get_user_model_name(user_id)

    # Build steps_data the same way execute_workflow_task does, but driven by
    # wf_data (already-expanded steps) instead of raw mongo lookups.
    steps_data = await _build_steps_data_for_optimization(
        wf_data=wf_data,
        doc_uuids=doc_uuids,
        user_id=user_id,
    )

    def _run() -> tuple[Any, list, int, int]:
        engine = build_workflow_engine(
            steps_data=steps_data,
            model=model,
            user_id=user_id,
            system_config_doc=sys_config_doc,
            allow_code_execution=False,
            config_override={"step_overrides": step_overrides} if step_overrides else None,
        )
        # No progress updater — the optimizer reports trial-level progress, not
        # step-level.
        try:
            final_output, data = engine.execute()
        except Exception:
            return None, [], engine.usage.tokens_in, engine.usage.tokens_out
        return final_output, data, engine.usage.tokens_in, engine.usage.tokens_out

    final_output, data, tokens_in, tokens_out = await asyncio.to_thread(_run)

    # Recover a steps_output dict in the shape `_evaluate_checks_against_output`
    # expects (keyed by sanitized step name).
    steps_output: dict[str, dict] = {}
    for entry in data or []:
        name = sanitize_step_name(entry.get("name", ""))
        if not name:
            continue
        steps_output[name] = {"output": entry.get("output"), "step_name": entry.get("name")}

    return final_output, steps_output, tokens_in, tokens_out


async def _build_steps_data_for_optimization(
    *,
    wf_data: dict,
    doc_uuids: list[str],
    user_id: str,
) -> list[dict]:
    """Build the steps_data list expected by ``build_workflow_engine``.

    Mirrors the trigger+steps shape that ``execute_workflow_task`` constructs
    from raw mongo, but driven by the already-expanded ``wf_data`` (which
    ``get_workflow`` has hydrated for us). Pre-loads doc_texts for extraction
    nodes the same way the production path does.
    """
    from app.models.document import SmartDocument

    # Trigger step
    steps_data: list[dict] = [
        {"name": "Document", "data": {"doc_uuids": list(doc_uuids)}, "tasks": []},
    ]

    # Pre-load doc texts once — every extraction-style step reuses the same
    # list, just as the production path does.
    doc_texts: list[str] = []
    for du in doc_uuids:
        doc = await SmartDocument.find_one({"uuid": du})
        if doc and getattr(doc, "raw_text", None):
            doc_texts.append(doc.raw_text)

    for step in (wf_data or {}).get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        sname = step.get("name", "")
        if not sname or sname == "Document":
            continue
        tasks_out: list[dict] = []
        for task in step.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            tname = task.get("name", "")
            tdata = dict(task.get("data") or {})
            tdata["user_id"] = user_id
            # Inject doc_texts for any step that may consume them
            if doc_texts:
                tdata.setdefault("doc_texts", doc_texts)
            # Extraction: hydrate keys from search_set if not already present
            if tname == "Extraction" and not tdata.get("keys"):
                ss_uuid = tdata.get("search_set_uuid")
                if ss_uuid:
                    from app.models.search_set import SearchSetItem
                    items = await SearchSetItem.find(
                        {"searchset": ss_uuid, "searchtype": "extraction"},
                    ).to_list()
                    tdata["keys"] = [it.searchphrase for it in items]
            tasks_out.append({"name": tname, "data": tdata})
        steps_data.append({
            "name": sname,
            "data": step.get("data") or {},
            "tasks": tasks_out,
        })
    return steps_data


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


_CATEGORY_WEIGHTS = {
    "completeness": 1.5,
    "accuracy": 1.3,
    "content": 1.0,
    "formatting": 0.7,
}

_STATUS_TO_SCORE = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}


def _weighted_pass_rate(plan: list[dict], checks: list[dict]) -> float:
    """Same weighted-pass formula as workflow_service._build_result.

    Mirroring (rather than importing) keeps the optimizer decoupled from
    workflow_service's internal scoring helper, which has been changing as
    Phase 2A landed. If the formula drifts, this is the single place to
    re-sync.
    """
    cat_lookup = {str(c.get("id", "")): c.get("category", "content") for c in plan}
    weighted_sum = 0.0
    weight_total = 0.0
    for c in checks or []:
        status = str(c.get("status", "")).upper()
        if status == "SKIP":
            continue
        cat = cat_lookup.get(str(c.get("check_id", "")), "content")
        w = _CATEGORY_WEIGHTS.get(cat, 1.0)
        weighted_sum += _STATUS_TO_SCORE.get(status, 0.0) * w
        weight_total += w
    if weight_total == 0:
        return 0.0
    return weighted_sum / weight_total


def _aggregate_step_breakdown(
    *,
    plan: list[dict],
    checks_per_input: list[list[dict]],
) -> list[dict]:
    """Mean of per-input step breakdowns. Empty when fewer than 2 distinct
    target_steps appear — same suppression rule as workflow_service.

    Returns a list of:
        {step, score, pass, warn, fail, skip, total, evaluated}
    """
    target_lookup: dict[str, str] = {}
    for p in plan or []:
        cid = str(p.get("id", ""))
        if not cid:
            continue
        step = (p.get("target_step") or "").strip() or "Unassigned"
        target_lookup[cid] = step

    cat_lookup = {str(p.get("id", "")): p.get("category", "content") for p in (plan or [])}

    by_step: dict[str, dict] = {}
    for checks in checks_per_input or []:
        for c in checks or []:
            cid = str(c.get("check_id", ""))
            step = target_lookup.get(cid, "Unassigned")
            status = str(c.get("status", "")).upper()
            bucket = by_step.setdefault(step, {
                "step": step,
                "pass": 0, "warn": 0, "fail": 0, "skip": 0,
                "weighted_sum": 0.0, "weight_total": 0.0,
            })
            if status == "PASS":
                bucket["pass"] += 1
            elif status == "WARN":
                bucket["warn"] += 1
            elif status == "FAIL":
                bucket["fail"] += 1
            else:
                bucket["skip"] += 1
            if status and status != "SKIP":
                w = _CATEGORY_WEIGHTS.get(cat_lookup.get(cid, "content"), 1.0)
                bucket["weighted_sum"] += _STATUS_TO_SCORE.get(status, 0.0) * w
                bucket["weight_total"] += w

    if len(by_step) <= 1:
        return []

    out: list[dict] = []
    for step_name in sorted(by_step.keys()):
        b = by_step[step_name]
        total = b["pass"] + b["warn"] + b["fail"] + b["skip"]
        evaluated = total - b["skip"]
        score = (b["weighted_sum"] / b["weight_total"]) * 100 if b["weight_total"] > 0 else 0.0
        out.append({
            "step": step_name,
            "score": round(score, 1),
            "pass": b["pass"],
            "warn": b["warn"],
            "fail": b["fail"],
            "skip": b["skip"],
            "total": total,
            "evaluated": evaluated,
        })
    return out


def _build_variance_samples(checks_per_input: list[list[dict]]) -> list[tuple[dict, dict]]:
    """Construct the (original, replay) pairs the workflow variance helper
    expects. For v1 we use ``checks_per_input[0]`` against ``checks_per_input[1]``
    when at least two test inputs were judged — neighbours sampling.

    Returns an empty list when fewer than 2 inputs are available.
    """
    if not checks_per_input or len(checks_per_input) < 2:
        return []
    orig = checks_per_input[0]
    rep = checks_per_input[1]
    rep_by_id = {str(c.get("check_id", "")): c for c in rep}
    pairs: list[tuple[dict, dict]] = []
    for o in orig:
        cid = str(o.get("check_id", ""))
        r = rep_by_id.get(cid)
        if not r:
            continue
        if o.get("status") == "SKIP" or r.get("status") == "SKIP":
            continue
        pairs.append((o, r))
    return pairs


def _compute_workflow_variance(samples: list[tuple[dict, dict]]) -> float | None:
    """Stddev of per-check status-score deltas between original and replay.

    Uses the same Bessel-corrected sample stddev as judge_variance.py.
    """
    if not samples or len(samples) < 2:
        return None
    deltas: list[float] = []
    for orig, rep in samples:
        do = _STATUS_TO_SCORE.get(str(orig.get("status", "")).upper(), 0.0)
        dr = _STATUS_TO_SCORE.get(str(rep.get("status", "")).upper(), 0.0)
        deltas.append(dr - do)
    if len(deltas) < 2:
        return None
    mean = sum(deltas) / len(deltas)
    variance = sum((d - mean) ** 2 for d in deltas) / (len(deltas) - 1)
    return round(variance ** 0.5, 4)


def _serialize_for_judge(final_output) -> str | None:
    """Same serialization as workflow_service._serialize_output, kept inline so
    the optimizer doesn't depend on a private helper."""
    import base64 as _b64
    import json as _json

    if final_output is None:
        return ""
    output_data = (
        final_output.get("output", final_output)
        if isinstance(final_output, dict) else final_output
    )
    if isinstance(output_data, dict) and output_data.get("type") == "file_download":
        ft = output_data.get("file_type", "")
        if ft in ("zip", "pdf", "xlsx"):
            return None
        try:
            raw = _b64.b64decode(output_data.get("data_b64", ""))
            return raw.decode("utf-8", errors="replace")[:50_000]
        except Exception:
            return None
    if isinstance(output_data, (dict, list)):
        return _json.dumps(output_data, indent=2, default=str)[:50_000]
    return str(output_data)[:50_000]


# ---------------------------------------------------------------------------
# Trial summary + winner selection
# ---------------------------------------------------------------------------


def _to_trial_summary(result: dict, baseline_default_score: float | None) -> dict:
    score = result.get("score")
    lift = None
    if score is not None and baseline_default_score is not None:
        lift = round(score - baseline_default_score, 4)
    return {
        "trial_id": result.get("label", ""),
        "config": {"step_overrides": dict(result.get("step_overrides") or {})},
        "score": score,
        "weighted_pass_rate": result.get("weighted_pass_rate"),
        "lift_vs_default": lift,
        "tokens_used": int(result.get("tokens_used", 0) or 0),
        "status": result.get("status", "completed"),
        "duration_seconds": result.get("duration_seconds"),
        "step_breakdown": result.get("step_breakdown") or [],
        "error": result.get("error"),
        "num_inputs_run": int(result.get("num_inputs_run", 0) or 0),
        "num_inputs_total": int(result.get("num_inputs_total", 0) or 0),
    }


def _build_step_apply_preview(
    winner_breakdown: list[dict],
    default_breakdown: list[dict],
    *,
    judge_variance: float | None,
) -> dict | None:
    """Join winner + default per-step scores into an apply-preview rollup.

    Workflow step_breakdown entries carry ``score`` on a 0..100 scale; the
    shared helper expects 0..1, so we normalize. Items are keyed by step
    name (the same key Phase 3's per-step apply UI uses) so the apply modal
    deep-links to the right step card.
    """
    if not winner_breakdown and not default_breakdown:
        return None
    def_by_step = {b.get("step"): b for b in default_breakdown if b.get("step")}
    items: list[dict] = []
    for w in winner_breakdown:
        step_name = w.get("step")
        if not step_name:
            continue
        d = def_by_step.get(step_name) or {}
        items.append({
            "item_id": step_name,
            "label": step_name,
            "baseline": float(d.get("score", 0.0) or 0.0) / 100.0,
            "winner": float(w.get("score", 0.0) or 0.0) / 100.0,
        })
    if not items:
        return None
    return build_apply_preview(items, judge_variance=judge_variance)


def _override_distance(
    overrides: dict[str, dict] | None,
    default_overrides: dict[str, dict],
) -> int:
    """Count of step entries that differ from default. Used as a tie-breaker:
    smaller override surface = less surprising apply-back."""
    if not overrides:
        return 0
    distance = 0
    for step_name, ov in overrides.items():
        d_ov = default_overrides.get(step_name) or {}
        if ov.get("model") != d_ov.get("model"):
            distance += 1
        if ov.get("prompt_variant") != d_ov.get("prompt_variant"):
            distance += 1
    return distance


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------


WEAK_STEP_SCORE_THRESHOLD = 60.0  # 0..100 scale (matches step_breakdown scoring)
REDUNDANT_WORKFLOW_LIFT_THRESHOLD = 0.05
REDUNDANT_WORKFLOW_MIN_SCORE = 0.7


def _generate_suggestions(
    *,
    step_breakdown: list[dict],
    baseline_no_workflow: float | None,
    baseline_default: float | None,
    optimized: float | None,
    best_per_step_config: dict[str, dict],
) -> list[dict]:
    """Per-step + run-level suggestions ordered by severity."""
    out: list[dict] = []

    for entry in step_breakdown or []:
        score = entry.get("score")
        step = entry.get("step")
        if score is None or not step:
            continue
        if score < WEAK_STEP_SCORE_THRESHOLD:
            severity = "critical" if score < 40 else "warning"
            recommended = best_per_step_config.get(step) or {}
            rec_model = recommended.get("model")
            rec_variant = recommended.get("prompt_variant")
            recs: list[str] = []
            if rec_model:
                recs.append(f"switch to {rec_model}")
            if rec_variant and rec_variant != "default":
                recs.append(f"use the {rec_variant} prompt style")
            tail = (
                " The optimizer's best config for this step: " + ", ".join(recs) + "."
                if recs else ""
            )
            out.append({
                "kind": "weak_step",
                "severity": severity,
                "step": step,
                "message": (
                    f'Step "{step}" only scored {int(score)}% in the best trial. '
                    "Consider rewriting the step's prompt, adding more guidance, "
                    "or splitting it into smaller steps." + tail
                ),
            })

    if (
        baseline_no_workflow is not None
        and optimized is not None
        and optimized >= REDUNDANT_WORKFLOW_MIN_SCORE
        and (optimized - baseline_no_workflow) < REDUNDANT_WORKFLOW_LIFT_THRESHOLD
    ):
        out.append({
            "kind": "redundant_workflow",
            "severity": "info",
            "message": (
                f"A single-shot LLM call scored {int(baseline_no_workflow * 100)}% — about the same "
                f"as your optimized workflow ({int(optimized * 100)}%). This workflow may be more "
                "complex than the task requires."
            ),
        })

    if (
        baseline_default is not None
        and optimized is not None
        and (optimized - baseline_default) < 0.02
        and baseline_default >= 0.7
    ):
        out.append({
            "kind": "already_good",
            "severity": "info",
            "message": (
                f"Your current configuration already scored {int(baseline_default * 100)}% — "
                "the optimizer barely found anything to improve."
            ),
        })

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    out.sort(key=lambda s: severity_rank.get(s.get("severity", "info"), 99))
    return out


# ---------------------------------------------------------------------------
# Apply-back + utilities
# ---------------------------------------------------------------------------


async def _apply_best(wf: Workflow, run_doc: WorkflowOptimizationRun) -> None:
    """Persist the winning config to ``Workflow.config_override``.

    Snapshots the previous override on the run doc so a one-click revert
    restores the exact prior state.
    """
    if not run_doc.best_config:
        return
    run_doc.previous_override = wf.config_override
    step_overrides = (run_doc.best_config or {}).get("step_overrides") or {}
    wf.config_override = {
        "step_overrides": dict(step_overrides),
        "from_run_uuid": run_doc.uuid,
    }
    wf.config_override_set_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()


async def _update(run_doc: WorkflowOptimizationRun, **fields: Any) -> None:
    for k, v in fields.items():
        setattr(run_doc, k, v)
    await run_doc.save()


def _is_cancelled(run_doc: WorkflowOptimizationRun) -> bool:
    return bool(run_doc.cancel_requested)


async def _finalize_cancelled(run_doc: WorkflowOptimizationRun) -> WorkflowOptimizationRun:
    run_doc.status = "cancelled"
    run_doc.phase = "cancelled"
    run_doc.progress_message = "Cancelled by user"
    run_doc.stopped_reason = "cancelled"
    run_doc.completed_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await run_doc.save()
    return run_doc


async def get_active_run(workflow_id: str) -> WorkflowOptimizationRun | None:
    """Return the most-recent non-terminal run for this workflow, if any."""
    return await WorkflowOptimizationRun.find_one(
        {
            "workflow_id": workflow_id,
            "status": {"$in": ["queued", "running"]},
        },
        sort=[("started_at", -1)],
    )
