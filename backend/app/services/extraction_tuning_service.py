"""Extraction auto-tuning service — find optimal settings for a search set."""

import asyncio
import logging
import time
from typing import Optional

from app.models.extraction_test_case import ExtractionTestCase
from app.models.system_config import SystemConfig
from app.services.config_service import get_user_model_name
from app.services.extraction_engine import ExtractionEngine
from app.services.extraction_validation_service import (
    _is_not_found,
    _values_match,
)
from app.services.search_set_service import (
    get_extraction_field_metadata,
    get_extraction_keys,
    get_search_set,
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
            f"{m['tag']} — two-pass",
            m["name"],
            {"mode": "two_pass"},
        )

        # One-pass with each model
        _add(
            f"{m['tag']} — one-pass",
            m["name"],
            {"mode": "one_pass", "one_pass": {"thinking": m["thinking"], "structured": m["structured"]}},
        )

        # If model supports thinking, try two-pass with thinking on both passes
        if m["thinking"]:
            _add(
                f"{m['tag']} — two-pass (full thinking)",
                m["name"],
                {"mode": "two_pass", "two_pass": {
                    "pass_1": {"thinking": True, "structured": False, "model": m["name"]},
                    "pass_2": {"thinking": True, "structured": True, "model": m["name"]},
                }},
            )

        # One-pass without thinking (fast mode)
        _add(
            f"{m['tag']} — one-pass (fast, no thinking)",
            m["name"],
            {"mode": "one_pass", "one_pass": {"thinking": False, "structured": m["structured"]}},
        )

    # Repetition / consensus mode — runs extraction 3x and majority-votes (3x cost, higher consistency)
    if models:
        m = models[0]
        _add(
            f"{m['tag']} — two-pass + consensus (3x runs)",
            m["name"],
            {"mode": "two_pass", "repetition": {"enabled": True}},
        )
        # Also try consensus with one-pass for a faster high-consistency option
        _add(
            f"{m['tag']} — one-pass + consensus (3x runs)",
            m["name"],
            {"mode": "one_pass", "one_pass": {"thinking": m["thinking"], "structured": m["structured"]},
             "repetition": {"enabled": True}},
        )

    # If many fields, add chunking variants for the first model
    if num_fields > 12 and models:
        m = models[0]
        _add(
            f"{m['tag']} — two-pass + chunking (8 fields/chunk)",
            m["name"],
            {"mode": "two_pass", "chunking": {"enabled": True, "max_keys_per_chunk": 8}},
        )
        _add(
            f"{m['tag']} — two-pass + chunking (5 fields/chunk)",
            m["name"],
            {"mode": "two_pass", "chunking": {"enabled": True, "max_keys_per_chunk": 5}},
        )

    return candidates


async def _run_single_config(
    candidate: dict,
    keys: list[str],
    test_cases: list[ExtractionTestCase],
    sys_config_doc: dict,
    field_metadata: list[dict],
    num_runs: int,
) -> dict:
    """Run extraction with a specific config against all test cases, measure quality.

    Returns a result dict with accuracy, consistency, score, timing, and per-field details.
    """
    model = candidate["model"]
    config_override = candidate["config_override"]
    label = candidate["label"]

    start = time.monotonic()

    # Run extraction num_runs times for each test case
    all_field_accuracies = []
    all_field_consistencies = []
    total_correct = 0
    total_evaluated = 0

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

        # Run extraction num_runs times concurrently
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

        # Compute per-field accuracy and consistency for this test case
        for field_name in keys:
            expected = tc.expected_values.get(field_name)
            if expected is None or expected == "":
                continue  # Skip fields with no expected value

            extracted_values = [str(r.get(field_name, "")) if r.get(field_name) is not None else "" for r in run_results]

            # Accuracy: how many runs got the right answer
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

            # Consistency: most common value frequency
            from collections import Counter
            normalized = [None if _is_not_found(v) else v for v in extracted_values]
            counter = Counter(normalized)
            _, most_common_count = counter.most_common(1)[0]
            consistency = most_common_count / len(normalized) if normalized else 0.0
            all_field_consistencies.append(consistency)

    elapsed = time.monotonic() - start

    avg_accuracy = sum(all_field_accuracies) / len(all_field_accuracies) if all_field_accuracies else 0.0
    avg_consistency = sum(all_field_consistencies) / len(all_field_consistencies) if all_field_consistencies else 0.0
    score = min(100.0, max(0.0, avg_accuracy * 60 + avg_consistency * 40))

    return {
        "label": label,
        "model": model,
        "config_override": config_override,
        "accuracy": round(avg_accuracy, 4),
        "consistency": round(avg_consistency, 4),
        "score": round(score, 1),
        "elapsed_seconds": round(elapsed, 1),
        "fields_evaluated": len(all_field_accuracies),
        "total_comparisons": total_evaluated,
    }


async def find_best_settings(
    search_set_uuid: str,
    user_id: str,
    num_runs: int = 2,
    max_candidates: int = 8,
) -> dict:
    """Try multiple extraction configurations and return ranked results.

    Requires at least one test case with expected values.
    Uses 2 runs per config by default (balance between speed and consistency measurement).

    Returns:
        {
            "best": {...},           # Best configuration
            "results": [...],        # All configs ranked by score
            "recommendation": str,   # Human-readable recommendation
            "search_set_uuid": str,
        }
    """
    keys = await get_extraction_keys(search_set_uuid)
    if not keys:
        raise ValueError("No extraction fields defined")

    # Load test cases
    test_cases = await ExtractionTestCase.find(
        ExtractionTestCase.search_set_uuid == search_set_uuid
    ).to_list()

    # Filter to test cases with at least some expected values
    test_cases = [tc for tc in test_cases if tc.expected_values and any(v for v in tc.expected_values.values())]
    if not test_cases:
        raise ValueError(
            "No test cases with expected values found. "
            "Create test cases first (you can use 'Create from extraction' to bootstrap them)."
        )

    # Load system config
    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}

    # Load field metadata
    field_metadata = await get_extraction_field_metadata(search_set_uuid)

    # Build candidate configs
    candidates = _build_candidate_configs(sys_config.available_models, len(keys))
    if not candidates:
        raise ValueError("No models available for tuning")

    # Limit candidates
    candidates = candidates[:max_candidates]

    # Run all candidates (sequentially to avoid overwhelming the LLM API)
    results = []
    for candidate in candidates:
        try:
            result = await _run_single_config(
                candidate, keys, test_cases, sys_config_doc, field_metadata, num_runs,
            )
            results.append(result)
        except Exception as e:
            logger.warning("Tuning candidate %s failed: %s", candidate["label"], e)
            results.append({
                "label": candidate["label"],
                "model": candidate["model"],
                "config_override": candidate["config_override"],
                "accuracy": 0.0,
                "consistency": 0.0,
                "score": 0.0,
                "elapsed_seconds": 0.0,
                "fields_evaluated": 0,
                "total_comparisons": 0,
                "error": str(e),
            })

    # Sort by score descending, then by elapsed_seconds ascending (tiebreak: faster is better)
    results.sort(key=lambda r: (-r["score"], r["elapsed_seconds"]))

    best = results[0] if results else None

    # Build recommendation
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

    return {
        "search_set_uuid": search_set_uuid,
        "best": best,
        "results": results,
        "recommendation": recommendation,
        "num_candidates_tested": len(results),
        "num_test_cases": len(test_cases),
        "num_runs_per_config": num_runs,
    }
