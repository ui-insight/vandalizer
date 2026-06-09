"""Extraction auto-tuning service — find optimal settings for a search set."""

import asyncio
import logging
import time

import datetime

from app.models.extraction_test_case import ExtractionTestCase
from app.models.search_set import SearchSet
from app.models.system_config import SystemConfig
from app.services.extraction_engine import ExtractionEngine
from app.services.extraction_validation_service import (
    _is_not_found,
    _values_match,
)
from app.services.search_set_service import (
    get_extraction_field_metadata,
    get_extraction_keys,
)

logger = logging.getLogger(__name__)


def _build_candidate_configs(available_models: list[dict], num_fields: int) -> list[dict]:
    """Build a prioritized list of extraction configs to try.

    Strategy: don't try all combinations (exponential). Instead, build
    a smart set of ~6-12 candidates covering the most impactful axes:
    1. Each available model with the default strategy
    2. One-pass vs two-pass for the top models
    3. Thinking on/off for thinking-capable models
    4. Chunking for large field sets
    """
    candidates = []
    seen_labels = set()

    # Resolve model names
    models = []
    for m in available_models:
        name = m.get("model_id") or m.get("name", "")
        if not name:
            continue
        models.append({
            "name": name,
            "tag": m.get("tag", name),
            "thinking": m.get("thinking", False),
            "structured": m.get("supports_structured", True),
        })

    if not models:
        return []

    def _add(label: str, model_name: str, config_override: dict):
        if label not in seen_labels:
            seen_labels.add(label)
            candidates.append({
                "label": label,
                "model": model_name,
                "config_override": config_override,
            })

    for m in models:
        # Default two-pass with each model
        _add(
            f"{m['tag']} - two-pass",
            m["name"],
            {"mode": "two_pass"},
        )

        # One-pass with each model
        _add(
            f"{m['tag']} - one-pass",
            m["name"],
            {"mode": "one_pass", "one_pass": {"thinking": m["thinking"], "structured": m["structured"]}},
        )

        # If model supports thinking, try two-pass with thinking on both passes
        if m["thinking"]:
            _add(
                f"{m['tag']} - two-pass (full thinking)",
                m["name"],
                {"mode": "two_pass", "two_pass": {
                    "pass_1": {"thinking": True, "structured": False, "model": m["name"]},
                    "pass_2": {"thinking": True, "structured": True, "model": m["name"]},
                }},
            )

        # One-pass without thinking (fast mode)
        _add(
            f"{m['tag']} - one-pass (fast, no thinking)",
            m["name"],
            {"mode": "one_pass", "one_pass": {"thinking": False, "structured": m["structured"]}},
        )

    # Repetition / consensus mode — runs extraction 3x and majority-votes (3x cost, higher consistency)
    if models:
        m = models[0]
        _add(
            f"{m['tag']} - two-pass + consensus (3x runs)",
            m["name"],
            {"mode": "two_pass", "repetition": {"enabled": True}},
        )
        # Also try consensus with one-pass for a faster high-consistency option
        _add(
            f"{m['tag']} - one-pass + consensus (3x runs)",
            m["name"],
            {"mode": "one_pass", "one_pass": {"thinking": m["thinking"], "structured": m["structured"]},
             "repetition": {"enabled": True}},
        )

    # If many fields, add chunking variants for the first model
    if num_fields > 12 and models:
        m = models[0]
        _add(
            f"{m['tag']} - two-pass + chunking (8 fields/chunk)",
            m["name"],
            {"mode": "two_pass", "chunking": {"enabled": True, "max_keys_per_chunk": 8}},
        )
        _add(
            f"{m['tag']} - two-pass + chunking (5 fields/chunk)",
            m["name"],
            {"mode": "two_pass", "chunking": {"enabled": True, "max_keys_per_chunk": 5}},
        )

    # Prompt-variant sweep (Phase 1B). Tried on the first model only — adding
    # all variants × all models would blow up the candidate count. The hypothesis
    # is that prompt wording matters within a model, not across models, so one
    # model gives the optimizer enough signal to favor a variant.
    if models:
        m = models[0]
        for variant in ("strict", "instructive"):
            _add(
                f"{m['tag']} - two-pass ({variant} prompt)",
                m["name"],
                {"mode": "two_pass", "prompt_variant": variant},
            )

    return candidates


async def _run_single_config(
    candidate: dict,
    keys: list[str],
    test_cases: list[ExtractionTestCase],
    sys_config_doc: dict,
    field_metadata: list[dict],
    num_runs: int,
    *,
    judge_model: str | None = None,
    cross_field_rules: list[dict] | None = None,
) -> dict:
    """Run extraction with a specific config against all test cases, measure quality.

    When ``judge_model`` is set, accuracy uses semantic LLM judge scoring
    (Phase 1B). When None, accuracy uses strict-match (the Phase 1A default
    and the regression check). Consistency is always strict-match-based —
    it measures stability of *output*, not correctness.

    Returns a result dict with accuracy, consistency, score, timing, plus
    per-field details. When the judge runs, ``judge_breakdown`` carries
    per-field judge scores so callers can route them into the optimizer's
    field_breakdown summary.
    """
    model = candidate["model"]
    config_override = candidate["config_override"]
    label = candidate["label"]

    start = time.monotonic()

    # Collect all extraction results first, then score in a second pass.
    # This separation lets us batch judge calls concurrently when judge_model
    # is set, instead of awaiting per (field, run) inside the loop.
    tc_run_results: list[tuple[ExtractionTestCase, list[dict]]] = []

    for tc in test_cases:
        # Resolve source text
        source_text = tc.source_text
        if tc.source_type == "document" and tc.document_uuid:
            from app.models.document import SmartDocument
            doc = await SmartDocument.find_one(SmartDocument.uuid == tc.document_uuid)
            if doc and doc.raw_text:
                source_text = doc.raw_text

        if not source_text:
            continue

        async def _single_run():
            engine = ExtractionEngine(system_config_doc=sys_config_doc)
            result = await asyncio.to_thread(
                engine.extract,
                extract_keys=keys,
                model=model,
                doc_texts=[source_text],
                extraction_config_override=config_override,
                field_metadata=field_metadata,
            )
            flat = {}
            if result and isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        flat.update(item)
            return flat

        try:
            run_results = list(await asyncio.gather(*(_single_run() for _ in range(num_runs))))
        except Exception as e:
            logger.warning("Config %s failed on test case %s: %s", label, tc.label, e)
            continue

        tc_run_results.append((tc, run_results))

    # Phase 2: optionally pre-judge every (test_case, field, run_idx) pair.
    judge_scores: dict[tuple[str, str, int], float] = {}
    # Lightweight sample suitable for downstream variance sampling — bundles
    # enough info to re-judge one item. Caller may pull a few of these to
    # feed into ``judge_variance.sample_judge_variance``.
    judge_samples: list[dict] = []
    judge_tokens = 0
    if judge_model:
        from app.services.extraction_judge import judge_field_value
        field_metadata_by_key: dict[str, dict] = {
            fm.get("key", ""): fm for fm in (field_metadata or []) if fm.get("key")
        }
        judge_tasks: list[tuple[tuple[str, str, int], asyncio.Task]] = []
        for tc, run_results in tc_run_results:
            for run_idx, r in enumerate(run_results):
                for field_name in keys:
                    expected = tc.expected_values.get(field_name)
                    if expected is None or expected == "":
                        continue
                    actual = str(r.get(field_name, "") or "")
                    key = (tc.uuid, field_name, run_idx)
                    judge_tasks.append((
                        key,
                        asyncio.create_task(judge_field_value(
                            field_name=field_name,
                            expected=str(expected),
                            actual=actual,
                            model_name=judge_model,
                            field_metadata=field_metadata_by_key.get(field_name),
                        )),
                    ))
        # Await all judges concurrently
        # We also record the (tc, field, run) triples + their extraction context
        # so the optimizer can pick a handful for variance sampling.
        tc_lookup = {tc.uuid: tc for tc, _ in tc_run_results}
        run_lookup = {(tc.uuid, idx): r for tc, runs in tc_run_results for idx, r in enumerate(runs)}
        for key, task in judge_tasks:
            try:
                verdict = await task
                score = float(verdict.get("score", 0.0))
                judge_scores[key] = score
                judge_tokens += int(verdict.get("tokens_used", 0) or 0)
                tc_uuid, field_name, run_idx = key
                tc = tc_lookup.get(tc_uuid)
                run_result = run_lookup.get((tc_uuid, run_idx), {})
                if tc is not None:
                    judge_samples.append({
                        "field_name": field_name,
                        "expected": str(tc.expected_values.get(field_name, "") or ""),
                        "actual": str(run_result.get(field_name, "") or ""),
                        "score": score,
                        # ``deterministic`` items have σ=0 by construction;
                        # variance sampling should skip them.
                        "comparator": verdict.get("comparator", "llm"),
                        "field_metadata": field_metadata_by_key.get(field_name),
                    })
            except Exception as e:
                logger.warning("Judge failed for %s: %s", key, e)
                judge_scores[key] = 0.0

    # Phase 3: compute per-field accuracy/consistency
    # Aggregate per field-name across all test cases — drives field_breakdown
    # in the optimizer's result + the recommendations engine.
    field_aggregates: dict[str, dict] = {}

    all_field_accuracies = []
    all_field_consistencies = []
    total_correct = 0
    total_evaluated = 0

    for tc, run_results in tc_run_results:
        for field_name in keys:
            expected = tc.expected_values.get(field_name)
            if expected is None or expected == "":
                continue

            extracted_values = [
                str(r.get(field_name, "")) if r.get(field_name) is not None else ""
                for r in run_results
            ]

            # Accuracy: judge mode = avg of per-run judge scores; strict mode = match count / runs.
            if judge_model:
                per_run_scores = [
                    judge_scores.get((tc.uuid, field_name, i), 0.0)
                    for i in range(len(extracted_values))
                ]
                accuracy = sum(per_run_scores) / len(per_run_scores) if per_run_scores else 0.0
                # For the strict-match-style "match_count" we count >=0.7 as a pass
                match_count = sum(1 for s in per_run_scores if s >= 0.7)
            else:
                match_count = 0
                for val in extracted_values:
                    exp_is_nf = _is_not_found(expected)
                    if exp_is_nf and _is_not_found(val):
                        match_count += 1
                    elif val and not _is_not_found(val) and not exp_is_nf and _values_match(val, expected):
                        match_count += 1
                accuracy = match_count / len(extracted_values) if extracted_values else 0.0

            all_field_accuracies.append(accuracy)
            total_correct += match_count
            total_evaluated += len(extracted_values)

            # Consistency: most common value frequency (always strict-match-based)
            from collections import Counter
            normalized = [None if _is_not_found(v) else v for v in extracted_values]
            counter = Counter(normalized)
            _, most_common_count = counter.most_common(1)[0]
            consistency = most_common_count / len(normalized) if normalized else 0.0
            all_field_consistencies.append(consistency)

            # Track per-field aggregates: accumulate sums then average at end
            agg = field_aggregates.setdefault(field_name, {
                "accuracy_sum": 0.0, "consistency_sum": 0.0, "samples": 0,
            })
            agg["accuracy_sum"] += accuracy
            agg["consistency_sum"] += consistency
            agg["samples"] += 1

    # Materialize the per-field breakdown for downstream recommendations
    field_breakdown: list[dict] = []
    for field_name in keys:
        agg = field_aggregates.get(field_name)
        if not agg or agg["samples"] == 0:
            continue
        field_breakdown.append({
            "field": field_name,
            "accuracy": round(agg["accuracy_sum"] / agg["samples"], 4),
            "consistency": round(agg["consistency_sum"] / agg["samples"], 4),
            "samples": agg["samples"],
        })

    # Cross-field evaluation. Runs the configured rules against every
    # (test_case, run) extraction. We need every run, not just the
    # most-common-value, because optimizer trials are about output stability —
    # a config whose rules pass on the modal value but fail on 4 of 5 runs is
    # less safe than one where they pass on all 5.
    cf_summary = None
    cf_results_flat: list[dict] = []
    if cross_field_rules:
        from app.services.cross_field_validation import (
            CrossFieldValidator,
            summarize_results,
        )
        cf_validator = CrossFieldValidator()
        for tc, run_results in tc_run_results:
            for r in run_results:
                cf_results_flat.extend(cf_validator.validate(r, cross_field_rules))
        cf_summary = summarize_results(cf_results_flat)

    elapsed = time.monotonic() - start

    avg_accuracy = sum(all_field_accuracies) / len(all_field_accuracies) if all_field_accuracies else 0.0
    avg_consistency = sum(all_field_consistencies) / len(all_field_consistencies) if all_field_consistencies else 0.0

    # Score: with cross-field rules that actually produced a decisive verdict,
    # use a 50/30/20 split. Otherwise the original 60/40. Treating unparseable
    # rules as a violation would penalize the model for our parser's blind
    # spots — see cross_field_validation.summarize_results for the rationale.
    if cf_summary and cf_summary["pass_rate"] is not None:
        cf_component = cf_summary["pass_rate"]
        score = min(100.0, max(0.0, avg_accuracy * 50 + avg_consistency * 30 + cf_component * 20))
    else:
        score = min(100.0, max(0.0, avg_accuracy * 60 + avg_consistency * 40))

    return {
        "label": label,
        "model": model,
        "config_override": config_override,
        "accuracy": round(avg_accuracy, 4),
        "consistency": round(avg_consistency, 4),
        "cross_field_summary": cf_summary,
        "cross_field_results": cf_results_flat,
        "score": round(score, 1),
        "elapsed_seconds": round(elapsed, 1),
        "fields_evaluated": len(all_field_accuracies),
        "total_comparisons": total_evaluated,
        "judge_used": bool(judge_model),
        "judge_tokens": judge_tokens if judge_model else 0,
        "judge_samples": judge_samples,
        "field_breakdown": field_breakdown,
    }


async def find_best_settings_stream(
    search_set_uuid: str,
    user_id: str,
    num_runs: int = 2,
    max_candidates: int = 8,
):
    """Async generator that yields SSE events as each config is tested.

    Events:
        {kind: "start", total: N, candidates: [...labels]}
        {kind: "testing", index: i, label: "...", total: N}
        {kind: "result", index: i, result: {...}, total: N}
        {kind: "done", best: {...}, results: [...], recommendation: "..."}
        {kind: "error", detail: "..."}
    """
    keys = await get_extraction_keys(search_set_uuid)
    if not keys:
        raise ValueError("No extraction fields defined")

    test_cases = await ExtractionTestCase.find(
        ExtractionTestCase.search_set_uuid == search_set_uuid
    ).to_list()
    test_cases = [tc for tc in test_cases if tc.expected_values and any(v for v in tc.expected_values.values())]
    if not test_cases:
        raise ValueError(
            "No test cases with expected values found. "
            "Create test cases first (you can use 'Create from extraction' to bootstrap them)."
        )

    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}
    field_metadata = await get_extraction_field_metadata(search_set_uuid)

    ss_for_rules = await SearchSet.find_one(SearchSet.uuid == search_set_uuid)
    cross_field_rules = ss_for_rules.normalized_cross_field_rules() if ss_for_rules else []

    candidates = _build_candidate_configs(sys_config.available_models, len(keys))
    if not candidates:
        raise ValueError("No models available for tuning")
    candidates = candidates[:max_candidates]

    total = len(candidates)
    yield {
        "kind": "start",
        "total": total,
        "candidates": [c["label"] for c in candidates],
    }

    results = []
    for i, candidate in enumerate(candidates):
        yield {"kind": "testing", "index": i, "label": candidate["label"], "total": total}

        try:
            result = await _run_single_config(
                candidate, keys, test_cases, sys_config_doc, field_metadata, num_runs,
                cross_field_rules=cross_field_rules,
            )
            results.append(result)
        except Exception as e:
            logger.warning("Tuning candidate %s failed: %s", candidate["label"], e)
            result = {
                "label": candidate["label"],
                "model": candidate["model"],
                "config_override": candidate["config_override"],
                "accuracy": 0.0,
                "consistency": 0.0,
                "score": 0.0,
                "elapsed_seconds": 0.0,
                "error": str(e),
            }
            results.append(result)

        yield {"kind": "result", "index": i, "result": result, "total": total}

    results.sort(key=lambda r: (-r["score"], r["elapsed_seconds"]))
    best = results[0] if results else None

    if best and best["score"] >= 90:
        recommendation = (
            f"Recommended: **{best['label']}** with score {best['score']} "
            f"({best['accuracy']*100:.0f}% accuracy, {best['consistency']*100:.0f}% consistency). "
            f"This configuration achieved excellent results in {best['elapsed_seconds']:.0f}s."
        )
    elif best and best["score"] >= 70:
        recommendation = (
            f"Best available: **{best['label']}** with score {best['score']} "
            f"({best['accuracy']*100:.0f}% accuracy, {best['consistency']*100:.0f}% consistency). "
            f"Consider refining extraction field definitions to improve accuracy."
        )
    elif best:
        recommendation = (
            f"Best available: **{best['label']}** with score {best['score']}, but quality is below 'good' threshold. "
            f"Review field definitions, add domain hints, or try more specific extraction prompts."
        )
    else:
        recommendation = "No configurations could be evaluated. Check model availability."

    # Persist results on the SearchSet so they survive navigation/reload
    ss = await SearchSet.find_one(SearchSet.uuid == search_set_uuid)
    if ss:
        ss.tuning_result = {
            "best": best,
            "results": results,
            "recommendation": recommendation,
            "ran_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        await ss.save()

    yield {
        "kind": "done",
        "best": best,
        "results": results,
        "recommendation": recommendation,
    }
