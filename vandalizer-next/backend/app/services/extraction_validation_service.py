"""Extraction validation service  - test case CRUD and validation logic."""

import asyncio
import re
from collections import Counter
from typing import Optional

from app.models.document import SmartDocument
from app.models.extraction_test_case import ExtractionTestCase
from app.models.system_config import SystemConfig
from app.services.config_service import get_user_model_name
from app.services.extraction_engine import ExtractionEngine
from app.services.llm_service import create_chat_agent
from app.services.search_set_service import get_extraction_keys, get_search_set


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def create_test_case(
    search_set_uuid: str,
    label: str,
    source_type: str,
    user_id: str,
    source_text: Optional[str] = None,
    document_uuid: Optional[str] = None,
    expected_values: Optional[dict[str, str]] = None,
) -> ExtractionTestCase:
    tc = ExtractionTestCase(
        search_set_uuid=search_set_uuid,
        label=label,
        source_type=source_type,
        source_text=source_text,
        document_uuid=document_uuid,
        expected_values=expected_values or {},
        user_id=user_id,
    )
    await tc.insert()
    return tc


async def list_test_cases(search_set_uuid: str) -> list[ExtractionTestCase]:
    return await ExtractionTestCase.find(
        ExtractionTestCase.search_set_uuid == search_set_uuid
    ).to_list()


async def get_test_case(uuid: str) -> Optional[ExtractionTestCase]:
    return await ExtractionTestCase.find_one(ExtractionTestCase.uuid == uuid)


async def update_test_case(uuid: str, **fields) -> Optional[ExtractionTestCase]:
    tc = await get_test_case(uuid)
    if not tc:
        return None
    for key, val in fields.items():
        if val is not None:
            setattr(tc, key, val)
    await tc.save()
    return tc


async def delete_test_case(uuid: str) -> bool:
    tc = await get_test_case(uuid)
    if not tc:
        return False
    await tc.delete()
    return True


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

async def run_validation(
    search_set_uuid: str,
    user_id: str,
    test_case_uuids: Optional[list[str]] = None,
    num_runs: int = 3,
    model: Optional[str] = None,
) -> dict:
    """Run extraction validation against test cases.

    Returns a dict matching ValidationResponse schema.
    """
    # Load extraction keys
    keys = await get_extraction_keys(search_set_uuid)
    if not keys:
        raise ValueError("No extraction fields defined")

    # Load test cases
    if test_case_uuids:
        test_cases = []
        for tc_uuid in test_case_uuids:
            tc = await get_test_case(tc_uuid)
            if tc:
                test_cases.append(tc)
    else:
        test_cases = await list_test_cases(search_set_uuid)

    if not test_cases:
        raise ValueError("No test cases found")

    # Resolve model
    if not model:
        model = await get_user_model_name(user_id)

    # Load per-searchset config
    ss = await get_search_set(search_set_uuid)
    extraction_config_override = (ss.extraction_config if ss and ss.extraction_config else None)

    # Pre-fetch system config
    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}

    # Process each test case
    tc_results = []
    for tc in test_cases:
        tc_result = await _validate_test_case(
            tc, keys, model, sys_config_doc, extraction_config_override, num_runs,
        )
        tc_results.append(tc_result)

    # Aggregate
    all_accuracies = []
    all_consistencies = []
    for tcr in tc_results:
        all_consistencies.append(tcr["overall_consistency"])
        if tcr["overall_accuracy"] is not None:
            all_accuracies.append(tcr["overall_accuracy"])

    return {
        "search_set_uuid": search_set_uuid,
        "num_runs": num_runs,
        "test_cases": tc_results,
        "aggregate_accuracy": (
            sum(all_accuracies) / len(all_accuracies) if all_accuracies else None
        ),
        "aggregate_consistency": (
            sum(all_consistencies) / len(all_consistencies) if all_consistencies else 0.0
        ),
    }


async def _validate_test_case(
    tc: ExtractionTestCase,
    keys: list[str],
    model: str,
    sys_config_doc: dict,
    extraction_config_override: Optional[dict],
    num_runs: int,
) -> dict:
    """Run extraction N times against a test case and compute metrics."""
    # Resolve source text
    source_text = tc.source_text
    if tc.source_type == "document" and tc.document_uuid:
        doc = await SmartDocument.find_one(SmartDocument.uuid == tc.document_uuid)
        if doc and doc.raw_text:
            source_text = doc.raw_text

    if not source_text:
        return {
            "test_case_uuid": tc.uuid,
            "label": tc.label,
            "fields": [],
            "overall_accuracy": None,
            "overall_consistency": 0.0,
        }

    # Run extraction N times (each in its own thread with a fresh engine)
    run_results = []
    for _ in range(num_runs):
        engine = ExtractionEngine(system_config_doc=sys_config_doc)
        result = await asyncio.to_thread(
            engine.extract,
            extract_keys=keys,
            model=model,
            doc_texts=[source_text],
            extraction_config_override=extraction_config_override,
        )
        # Flatten to single dict
        flat = {}
        if result and isinstance(result, list) and len(result) > 0:
            for item in result:
                if isinstance(item, dict):
                    flat.update(item)
        run_results.append(flat)

    # Per-field metrics
    field_results = []
    for field_name in keys:
        extracted_values = [r.get(field_name) for r in run_results]
        field_result = await _compute_field_metrics(
            field_name, extracted_values, tc.expected_values.get(field_name),
            sys_config_doc, model,
        )
        field_results.append(field_result)

    # Aggregate per test case
    consistencies = [f["consistency"] for f in field_results]
    accuracies = [f["accuracy"] for f in field_results if f["accuracy"] is not None]

    return {
        "test_case_uuid": tc.uuid,
        "label": tc.label,
        "fields": field_results,
        "overall_accuracy": (
            sum(accuracies) / len(accuracies) if accuracies else None
        ),
        "overall_consistency": (
            sum(consistencies) / len(consistencies) if consistencies else 0.0
        ),
    }


async def _compute_field_metrics(
    field_name: str,
    extracted_values: list,
    expected: Optional[str],
    sys_config_doc: dict,
    model: str,
) -> dict:
    """Compute consistency and accuracy for a single field across runs."""
    # Consistency: how often the most common value appears
    str_values = [str(v) if v is not None else None for v in extracted_values]
    counter = Counter(str_values)
    most_common_value, most_common_count = counter.most_common(1)[0]
    consistency = most_common_count / len(str_values) if str_values else 0.0

    # Accuracy
    accuracy = None
    accuracy_method = None
    if expected is not None and expected != "":
        # Check each extraction against expected
        match_count = 0
        for val in str_values:
            if val is None:
                continue
            if _normalize(val) == _normalize(expected):
                match_count += 1
                continue
            # LLM judge for semantic equivalence
            is_match = await asyncio.to_thread(
                _sync_llm_judge, val, expected, sys_config_doc, model,
            )
            if is_match:
                match_count += 1
        accuracy = match_count / len(str_values) if str_values else 0.0
        accuracy_method = "exact+llm_judge"

    return {
        "field_name": field_name,
        "expected": expected,
        "extracted_values": str_values,
        "most_common_value": most_common_value,
        "consistency": consistency,
        "accuracy": accuracy,
        "accuracy_method": accuracy_method,
    }


def _normalize(value: str) -> str:
    """Normalize a string for comparison: lowercase, strip whitespace/punctuation."""
    s = value.lower().strip()
    s = re.sub(r'[,\s$%]+', '', s)
    return s


def _sync_llm_judge(
    extracted: str, expected: str, sys_config_doc: dict, model: str,
) -> bool:
    """Ask the LLM whether two values are semantically equivalent."""
    system_prompt = (
        "You are a strict value comparison judge. Given two values, determine if they "
        "represent the same information, accounting for format differences like date "
        "formats, currency symbols, abbreviations, or minor wording changes. "
        "Reply with ONLY 'yes' or 'no'."
    )
    prompt = (
        f"Are these two values semantically equivalent?\n"
        f"Value A: {extracted}\n"
        f"Value B: {expected}\n\n"
        f"Reply with only 'yes' or 'no'."
    )
    try:
        agent = create_chat_agent(model, system_prompt=system_prompt, system_config_doc=sys_config_doc)
        result = agent.run_sync(prompt)
        return result.output.strip().lower().startswith("yes")
    except Exception:
        return False
