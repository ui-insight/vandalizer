"""Extraction validation service  - test case CRUD and validation logic."""

import asyncio
import math
import re
from collections import Counter
from datetime import datetime
from typing import Optional

from app.models.document import SmartDocument
from app.models.extraction_test_case import ExtractionTestCase
from app.models.system_config import SystemConfig
from app.services.config_service import get_user_model_name
from app.services.extraction_engine import ExtractionEngine
from app.services.search_set_service import get_extraction_field_metadata, get_extraction_keys, get_search_set


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


async def create_test_cases_from_extraction(
    search_set_uuid: str,
    document_uuids: list[str],
    user_id: str,
    model: Optional[str] = None,
) -> list[ExtractionTestCase]:
    """Run extraction on documents and create test cases from results.

    This is the 'extract once, approve, save as test case' flow that lets
    users bootstrap test cases from known-good documents instead of manually
    entering expected values.
    """
    keys = await get_extraction_keys(search_set_uuid)
    if not keys:
        raise ValueError("No extraction fields defined")

    if not model:
        model = await get_user_model_name(user_id)

    ss = await get_search_set(search_set_uuid)
    extraction_config_override = (ss.extraction_config if ss and ss.extraction_config else None)

    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}
    field_metadata = await get_extraction_field_metadata(search_set_uuid)

    created: list[ExtractionTestCase] = []
    for doc_uuid in document_uuids:
        doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
        if not doc or not doc.raw_text:
            continue

        # Run extraction once to get baseline values
        engine = ExtractionEngine(system_config_doc=sys_config_doc)
        result = await asyncio.to_thread(
            engine.extract,
            extract_keys=keys,
            model=model,
            doc_texts=[doc.raw_text],
            extraction_config_override=extraction_config_override,
            field_metadata=field_metadata,
        )
        flat: dict = {}
        if result and isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    flat.update(item)

        # Convert all values to strings for expected_values
        expected_values = {k: str(v) if v is not None else "" for k, v in flat.items() if k in keys}

        tc = await create_test_case(
            search_set_uuid=search_set_uuid,
            label=doc.title or doc_uuid,
            source_type="document",
            user_id=user_id,
            document_uuid=doc_uuid,
            expected_values=expected_values,
        )
        created.append(tc)

    return created


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

    # Fetch field metadata for optional/enum awareness
    field_metadata = await get_extraction_field_metadata(search_set_uuid)
    meta_map = {m["key"]: m for m in field_metadata}

    # Process each test case concurrently
    tc_results = list(await asyncio.gather(*(
        _validate_test_case(
            tc, keys, model, sys_config_doc, extraction_config_override, num_runs,
            field_metadata=field_metadata, meta_map=meta_map,
        )
        for tc in test_cases
    )))

    # Add V2-style per-field diagnostics to each test case result
    for tcr in tc_results:
        # Per-run correct counts
        # We need run_results for this - add them to the test case output
        per_run_correct = tcr.get("per_run_correct", [])
        for fr in tcr.get("fields", []):
            # Error type classification
            exp = fr.get("expected")
            str_vals = fr.get("extracted_values", [])
            error_types: dict[str, int] = {}
            exp_is_nf = _is_not_found(exp)
            if exp is not None and exp != "":
                for val in str_vals:
                    if exp_is_nf and _is_not_found(val):
                        continue
                    if val is not None and not _values_match(val, exp):
                        err = _classify_error(val, exp)
                        error_types[err] = error_types.get(err, 0) + 1
                    elif val is None:
                        error_types["missing"] = error_types.get("missing", 0) + 1
            fr["error_types"] = error_types
            fr["distinct_value_count"] = len(set(str_vals))

    # Aggregate
    all_accuracies = []
    all_consistencies = []
    for tcr in tc_results:
        all_consistencies.append(tcr["overall_consistency"])
        if tcr["overall_accuracy"] is not None:
            all_accuracies.append(tcr["overall_accuracy"])

    # Compute V2-compatible diagnostics
    executive_summary = _compute_executive_summary(
        [{"source_label": tcr["label"], "overall_accuracy": tcr["overall_accuracy"],
          "overall_consistency": tcr["overall_consistency"],
          "per_run_correct": tcr.get("per_run_correct", []),
          "fields": tcr["fields"]} for tcr in tc_results],
        keys,
    )

    # Challenging fields
    challenging_fields = []
    for tcr in tc_results:
        for f in tcr.get("fields", []):
            is_challenging = False
            if f.get("accuracy") is not None and f["accuracy"] < 1.0:
                is_challenging = True
            if f.get("consistency") < 1.0:
                is_challenging = True
            if is_challenging:
                error_types = f.get("error_types", {})
                most_common_error = max(error_types, key=error_types.get) if error_types else "none"
                challenging_fields.append({
                    "field_name": f["field_name"],
                    "source_label": tcr["label"],
                    "accuracy": f["accuracy"],
                    "consistency": f["consistency"],
                    "most_common_error": most_common_error,
                })

    # Error type summary
    error_type_summary: dict[str, int] = {}
    for tcr in tc_results:
        for f in tcr.get("fields", []):
            for err_type, count in f.get("error_types", {}).items():
                error_type_summary[err_type] = error_type_summary.get(err_type, 0) + count

    # Run cross-field validation on most-common values from each test case
    cross_field_score = None
    if ss and ss.cross_field_rules:
        from app.services.cross_field_validation import CrossFieldValidator
        cf_validator = CrossFieldValidator()
        cf_pass_total = 0
        cf_rule_total = 0
        for tcr in tc_results:
            # Build data dict from most_common_value per field
            cf_data = {}
            for fr in tcr.get("fields", []):
                if fr.get("most_common_value") is not None:
                    cf_data[fr["field_name"]] = fr["most_common_value"]
            if cf_data:
                cf_results = cf_validator.validate(cf_data, ss.cross_field_rules)
                cf_pass_total += sum(1 for r in cf_results if r["passed"])
                cf_rule_total += len(cf_results)
        if cf_rule_total > 0:
            cross_field_score = cf_pass_total / cf_rule_total

    result_dict = {
        "search_set_uuid": search_set_uuid,
        "num_runs": num_runs,
        "test_cases": tc_results,
        "aggregate_accuracy": (
            sum(all_accuracies) / len(all_accuracies) if all_accuracies else None
        ),
        "aggregate_consistency": (
            sum(all_consistencies) / len(all_consistencies) if all_consistencies else 0.0
        ),
        "executive_summary": executive_summary,
        "challenging_fields": challenging_fields,
        "error_type_summary": error_type_summary,
        "cross_field_score": cross_field_score,
    }

    # Persist validation run for quality tracking
    from app.services.quality_service import persist_validation_run
    await persist_validation_run(
        item_kind="search_set",
        item_id=search_set_uuid,
        item_name=ss.title if ss else "",
        run_type="extraction",
        result=result_dict,
        user_id=user_id,
        model=model,
        extraction_config=extraction_config_override or {},
    )

    return result_dict


async def _validate_test_case(
    tc: ExtractionTestCase,
    keys: list[str],
    model: str,
    sys_config_doc: dict,
    extraction_config_override: Optional[dict],
    num_runs: int,
    field_metadata: list[dict] | None = None,
    meta_map: dict[str, dict] | None = None,
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

    # Run extraction N times concurrently (each in its own thread with a fresh engine)
    async def _single_run():
        engine = ExtractionEngine(system_config_doc=sys_config_doc)
        result = await asyncio.to_thread(
            engine.extract,
            extract_keys=keys,
            model=model,
            doc_texts=[source_text],
            extraction_config_override=extraction_config_override,
            field_metadata=field_metadata,
        )
        flat = {}
        if result and isinstance(result, list) and len(result) > 0:
            for item in result:
                if isinstance(item, dict):
                    flat.update(item)
        return flat

    run_results = list(await asyncio.gather(*(_single_run() for _ in range(num_runs))))

    # Per-field metrics — run all fields concurrently
    field_results = list(await asyncio.gather(*(
        _compute_field_metrics(
            field_name,
            [r.get(field_name) for r in run_results],
            tc.expected_values.get(field_name),
            sys_config_doc, model,
            field_meta=(meta_map or {}).get(field_name),
        )
        for field_name in keys
    )))

    # Per-run correct counts (how many fields were correct in each run)
    per_run_correct: list[int] = []
    for run_idx, run_data in enumerate(run_results):
        correct = 0
        for field_name in keys:
            fm = (meta_map or {}).get(field_name, {})
            exp = tc.expected_values.get(field_name)
            if fm.get("is_optional") and (exp is None or exp == "" or _is_not_found(exp)):
                continue
            if exp is None or exp == "":
                continue
            val = run_data.get(field_name)
            exp_is_nf = _is_not_found(exp)
            if exp_is_nf and _is_not_found(val):
                correct += 1
            elif val is not None and not _is_not_found(val) and not exp_is_nf and _values_match(str(val), exp):
                correct += 1
        per_run_correct.append(correct)

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
        "per_run_correct": per_run_correct,
    }


async def _compute_field_metrics(
    field_name: str,
    extracted_values: list,
    expected: Optional[str],
    sys_config_doc: dict,
    model: str,
    field_meta: dict | None = None,
) -> dict:
    """Compute consistency and accuracy for a single field across runs."""
    str_values = [str(v) if v is not None else None for v in extracted_values]

    # For consistency, treat all "not found" sentinel values as equivalent
    normalized_for_consistency = [
        None if _is_not_found(v) else v for v in str_values
    ]
    counter = Counter(normalized_for_consistency)
    most_common_value, most_common_count = counter.most_common(1)[0]
    consistency = most_common_count / len(normalized_for_consistency) if normalized_for_consistency else 0.0

    is_optional = (field_meta or {}).get("is_optional", False)
    enum_vals = (field_meta or {}).get("enum_values", [])

    # Accuracy — pure normalization, no LLM calls
    accuracy = None
    accuracy_method = None
    expected_is_not_found = _is_not_found(expected)

    # Skip accuracy for optional fields with no expected value (no penalty)
    if is_optional and (expected is None or expected == "" or expected_is_not_found):
        accuracy = None
        accuracy_method = None
    elif expected is not None and expected != "":
        match_count = 0
        for val in str_values:
            if expected_is_not_found and _is_not_found(val):
                # Both are "not found" sentinels — that's a match
                match_count += 1
            elif val is not None and not _is_not_found(val) and not expected_is_not_found and _values_match(val, expected):
                match_count += 1
            # If one is sentinel and the other isn't, it's a mismatch (count stays 0)
        accuracy = match_count / len(str_values) if str_values else 0.0
        accuracy_method = "normalized"

    # Confidence interval for accuracy
    accuracy_ci = None
    if accuracy is not None and str_values:
        match_count_for_ci = int(round(accuracy * len(str_values)))
        accuracy_ci = _wilson_confidence(match_count_for_ci, len(str_values))

    # Enum compliance: fraction of non-null extracted values within allowed set
    enum_compliance = None
    if enum_vals:
        enum_set_lower = {v.lower().strip() for v in enum_vals}
        non_null = [v for v in str_values if v is not None and not _is_not_found(v)]
        if non_null:
            compliant = sum(1 for v in non_null if v.strip().lower() in enum_set_lower)
            enum_compliance = compliant / len(non_null)

    return {
        "field_name": field_name,
        "expected": expected,
        "extracted_values": str_values,
        "most_common_value": most_common_value,
        "consistency": consistency,
        "accuracy": accuracy,
        "accuracy_ci": accuracy_ci,
        "accuracy_method": accuracy_method,
        "enum_compliance": enum_compliance,
    }


# ---------------------------------------------------------------------------
# Value comparison — multi-level normalization (no LLM calls)
# ---------------------------------------------------------------------------

_CURRENCY_RE = re.compile(r'^[\s$€£¥₹]+|[\s$€£¥₹]+$')
_WHITESPACE_RE = re.compile(r'\s+')
_PAREN_NEG_RE = re.compile(r'^\((.+)\)$')

# Sentinel values that all mean "not found / not applicable"
_NOT_FOUND_VARIANTS = frozenset({
    "", "n/a", "na", "n.a.", "not found", "not available",
    "not applicable", "none", "null", "nil", "unknown", "-", "--", "---",
    "nan", "no data", "no value", "not provided", "not specified",
})


def _is_not_found(value) -> bool:
    """Return True if a value is a 'not found' sentinel."""
    if value is None:
        return True
    s = str(value).strip().lower()
    return s in _NOT_FOUND_VARIANTS


def _wilson_confidence(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for binomial proportion. Returns (lower, upper)."""
    if trials == 0:
        return (0.0, 0.0)
    p = successes / trials
    denom = 1 + z * z / trials
    centre = p + z * z / (2 * trials)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * trials)) / trials)
    lower = max(0.0, (centre - spread) / denom)
    upper = min(1.0, (centre + spread) / denom)
    return (round(lower, 4), round(upper, 4))


# Month name → number for date normalization
_MONTH_MAP: dict[str, int] = {}
for _i, _names in enumerate([
    ("january", "jan"), ("february", "feb"), ("march", "mar"),
    ("april", "apr"), ("may",), ("june", "jun"),
    ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"),
    ("october", "oct"), ("november", "nov"), ("december", "dec"),
], start=1):
    for _name in _names:
        _MONTH_MAP[_name] = _i


def _values_match(extracted: str, expected: str) -> bool:
    """Check if two values are equivalent using multi-level normalization.

    Levels tried in order:
    1. Exact string match (case-insensitive, whitespace-trimmed)
    2. Normalized text (strip formatting noise)
    3. Numeric comparison (parse as numbers, compare with tolerance)
    4. Date comparison (parse common date formats, compare)
    """
    a, b = extracted.strip(), expected.strip()

    # Level 0: sentinel equivalence — all "not found" values match each other
    if _is_not_found(a) and _is_not_found(b):
        return True

    # Level 1: case-insensitive exact
    if a.lower() == b.lower():
        return True

    # Level 2: normalized text
    na, nb = _normalize(a), _normalize(b)
    if na == nb and na != "":
        return True

    # Level 3: numeric comparison
    num_a, num_b = _try_parse_number(a), _try_parse_number(b)
    if num_a is not None and num_b is not None:
        # Exact match or very close (handles float precision differences)
        if num_a == num_b:
            return True
        if num_b != 0 and abs(num_a - num_b) / max(abs(num_b), 1e-12) < 1e-6:
            return True

    # Level 4: date comparison
    date_a, date_b = _try_parse_date(a), _try_parse_date(b)
    if date_a is not None and date_b is not None:
        return date_a == date_b

    return False


def _normalize(value: str) -> str:
    """Normalize a string for comparison: lowercase, collapse whitespace,
    strip currency symbols, commas, percent signs, and other formatting noise."""
    s = value.lower().strip()
    # Remove currency symbols
    s = _CURRENCY_RE.sub('', s)
    # Remove commas (thousand separators)
    s = s.replace(',', '')
    # Remove percent signs
    s = s.rstrip('%').strip()
    # Collapse whitespace
    s = _WHITESPACE_RE.sub(' ', s).strip()
    # Normalize dashes/hyphens
    s = s.replace('–', '-').replace('—', '-')
    return s


def _try_parse_number(value: str) -> Optional[float]:
    """Try to parse a value as a number, handling currency, percentages,
    parenthetical negatives, and thousand separators."""
    s = value.strip()
    # Strip currency symbols
    s = _CURRENCY_RE.sub('', s)
    # Handle parenthetical negatives: (100) → -100
    m = _PAREN_NEG_RE.match(s)
    if m:
        s = '-' + m.group(1)
    # Remove thousand separators and percent signs
    s = s.replace(',', '').rstrip('%').strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _try_parse_date(value: str) -> Optional[tuple[int, int, int]]:
    """Try to parse a value as a date, returning (year, month, day) or None.

    Handles: MM/DD/YYYY, M/D/YYYY, YYYY-MM-DD, "Month DD, YYYY",
    "DD Month YYYY", and other common variants.
    """
    s = value.strip().rstrip('.')

    # ISO format: YYYY-MM-DD
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # US format: MM/DD/YYYY or M/D/YYYY or M/D/YY
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$', s)
    if m:
        y = int(m.group(3))
        if y < 100:
            y += 2000
        return (y, int(m.group(1)), int(m.group(2)))

    # "Month DD, YYYY" or "Month DD YYYY"
    m = re.match(r'^([a-zA-Z]+)\.?\s+(\d{1,2}),?\s+(\d{4})$', s)
    if m:
        month_num = _MONTH_MAP.get(m.group(1).lower())
        if month_num:
            return (int(m.group(3)), month_num, int(m.group(2)))

    # "DD Month YYYY"
    m = re.match(r'^(\d{1,2})\s+([a-zA-Z]+)\.?\s+(\d{4})$', s)
    if m:
        month_num = _MONTH_MAP.get(m.group(2).lower())
        if month_num:
            return (int(m.group(3)), month_num, int(m.group(1)))

    # Fallback: try Python's dateutil-style parsing via strptime common formats
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return (dt.year, dt.month, dt.day)
        except ValueError:
            continue

    return None


# ---------------------------------------------------------------------------
# V2 Validation  — source-based (no test case documents needed)
# ---------------------------------------------------------------------------

def _classify_error(extracted: Optional[str], expected: str) -> str:
    """Classify the type of extraction error."""
    if _is_not_found(extracted):
        return "missing"
    # Check truncation: one is a substantial prefix of the other
    e_lower = extracted.lower().strip()
    x_lower = expected.lower().strip()
    # Check if one is a meaningful prefix of the other (at least 3 chars match)
    if len(e_lower) >= 3 and x_lower.startswith(e_lower):
        return "truncated"
    if len(x_lower) >= 3 and e_lower.startswith(x_lower):
        return "truncated"
    # Check formatting difference (normalized match but not exact)
    if _values_match(extracted, expected):
        return "format_difference"
    return "wrong_value"


async def _validate_source(
    source_label: str,
    source_type: str,
    source_text: str,
    expected_values: dict[str, str],
    keys: list[str],
    model: str,
    sys_config_doc: dict,
    extraction_config_override: Optional[dict],
    num_runs: int,
    field_metadata: list[dict] | None = None,
    meta_map: dict[str, dict] | None = None,
) -> dict:
    """Run extraction N times against a source and compute metrics."""

    async def _single_run() -> dict:
        engine = ExtractionEngine(system_config_doc=sys_config_doc)
        result = await asyncio.to_thread(
            engine.extract,
            extract_keys=keys,
            model=model,
            doc_texts=[source_text],
            extraction_config_override=extraction_config_override,
            field_metadata=field_metadata,
        )
        flat: dict = {}
        if result and isinstance(result, list) and len(result) > 0:
            for item in result:
                if isinstance(item, dict):
                    flat.update(item)
        return flat

    run_results: list[dict] = list(await asyncio.gather(*(_single_run() for _ in range(num_runs))))

    # Per-field metrics — run all fields concurrently
    field_results_raw = await asyncio.gather(*(
        _compute_field_metrics(
            field_name,
            [r.get(field_name) for r in run_results],
            expected_values.get(field_name),
            sys_config_doc, model,
            field_meta=(meta_map or {}).get(field_name),
        )
        for field_name in keys
    ))
    field_results = []
    for field_result in field_results_raw:
        # Add V2-specific fields
        str_vals = field_result["extracted_values"]
        field_result["distinct_value_count"] = len(set(str_vals))
        # Error types
        exp = field_result["expected"]
        error_types: dict[str, int] = {}
        exp_is_nf = _is_not_found(exp)
        if exp is not None and exp != "":
            for val in str_vals:
                # Both are "not found" sentinels — not an error
                if exp_is_nf and _is_not_found(val):
                    continue
                if val is not None and not _values_match(val, exp):
                    err = _classify_error(val, exp)
                    error_types[err] = error_types.get(err, 0) + 1
                elif val is None:
                    error_types["missing"] = error_types.get("missing", 0) + 1
        field_result["error_types"] = error_types
        field_results.append(field_result)

    # Per-run correct counts (how many fields were correct in each run)
    per_run_correct: list[int] = []
    for run_idx, run_data in enumerate(run_results):
        correct = 0
        for field_name in keys:
            fm = (meta_map or {}).get(field_name, {})
            exp = expected_values.get(field_name)
            # Skip optional fields with no expected value
            if fm.get("is_optional") and (exp is None or exp == "" or _is_not_found(exp)):
                continue
            if exp is None or exp == "":
                continue
            val = run_data.get(field_name)
            exp_is_nf = _is_not_found(exp)
            if exp_is_nf and _is_not_found(val):
                correct += 1
            elif val is not None and not _is_not_found(val) and not exp_is_nf and _values_match(str(val), exp):
                correct += 1
        per_run_correct.append(correct)

    # Aggregate per source
    consistencies = [f["consistency"] for f in field_results]
    accuracies = [f["accuracy"] for f in field_results if f["accuracy"] is not None]

    return {
        "source_label": source_label,
        "source_type": source_type,
        "fields": field_results,
        "overall_accuracy": (
            sum(accuracies) / len(accuracies) if accuracies else None
        ),
        "overall_consistency": (
            sum(consistencies) / len(consistencies) if consistencies else 0.0
        ),
        "per_run_correct": per_run_correct,
    }


def _compute_executive_summary(source_results: list[dict], keys: list[str]) -> dict:
    """Compute executive summary across all sources."""
    all_accuracies = []
    all_consistencies = []
    all_run_corrects: list[int] = []
    per_run_reproducibility = []

    for sr in source_results:
        all_consistencies.append(sr["overall_consistency"])
        if sr["overall_accuracy"] is not None:
            all_accuracies.append(sr["overall_accuracy"])
        all_run_corrects.extend(sr["per_run_correct"])
        per_run_reproducibility.append({
            "source_label": sr["source_label"],
            "runs": sr["per_run_correct"],
        })

    mean_accuracy = (
        sum(all_accuracies) / len(all_accuracies) if all_accuracies else None
    )
    mean_consistency = (
        sum(all_consistencies) / len(all_consistencies) if all_consistencies else 0.0
    )

    # Perfect fields: fields at 100% consistency AND accuracy across all sources
    perfect_count = 0
    for field_name in keys:
        perfect = True
        for sr in source_results:
            for f in sr["fields"]:
                if f["field_name"] == field_name:
                    if f["consistency"] < 1.0:
                        perfect = False
                    if f["accuracy"] is not None and f["accuracy"] < 1.0:
                        perfect = False
        if perfect:
            perfect_count += 1

    # Std dev of per-run correct counts
    if len(all_run_corrects) > 1:
        mean_correct = sum(all_run_corrects) / len(all_run_corrects)
        variance = sum((x - mean_correct) ** 2 for x in all_run_corrects) / len(all_run_corrects)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0.0

    # Best/worst run
    best_run = {"source_index": 0, "run_index": 0, "correct": 0}
    worst_run = {"source_index": 0, "run_index": 0, "correct": float('inf')}
    for si, sr in enumerate(source_results):
        for ri, correct in enumerate(sr["per_run_correct"]):
            if correct > best_run["correct"]:
                best_run = {"source_index": si, "run_index": ri, "correct": correct}
            if correct < worst_run["correct"]:
                worst_run = {"source_index": si, "run_index": ri, "correct": correct}
    if worst_run["correct"] == float('inf'):
        worst_run = {"source_index": 0, "run_index": 0, "correct": 0}

    # Aggregate confidence interval
    total_comparisons = sum(len(sr.get("per_run_correct", [])) for sr in source_results)
    total_correct_sum = sum(sum(sr.get("per_run_correct", [])) for sr in source_results)
    # Use total fields * total runs for the denominator
    total_fields = len(keys)
    total_trials = total_comparisons * total_fields if total_comparisons > 0 else 0
    aggregate_accuracy_ci = _wilson_confidence(total_correct_sum, total_trials) if total_trials > 0 else None

    return {
        "mean_accuracy": mean_accuracy,
        "mean_consistency": mean_consistency,
        "accuracy_ci": aggregate_accuracy_ci,
        "perfect_fields_count": perfect_count,
        "total_fields_count": len(keys),
        "run_to_run_std_dev": round(std_dev, 3),
        "best_run": best_run,
        "worst_run": worst_run,
        "per_run_reproducibility": per_run_reproducibility,
    }


async def run_validation_v2(
    search_set_uuid: str,
    user_id: str,
    sources: list[dict],
    num_runs: int = 3,
    model: Optional[str] = None,
) -> dict:
    """Run V2 extraction validation against inline sources."""
    keys = await get_extraction_keys(search_set_uuid)
    if not keys:
        raise ValueError("No extraction fields defined")

    if not sources:
        raise ValueError("No sources provided")

    if not model:
        model = await get_user_model_name(user_id)

    ss = await get_search_set(search_set_uuid)
    extraction_config_override = (
        ss.extraction_config if ss and ss.extraction_config else None
    )

    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}

    # Fetch field metadata for optional/enum awareness
    field_metadata = await get_extraction_field_metadata(search_set_uuid)
    meta_map = {m["key"]: m for m in field_metadata}

    # Resolve document texts
    resolved_sources: list[dict] = []
    for i, src in enumerate(sources):
        source_text = src.get("source_text")
        source_type = src.get("source_type", "text")
        label = src.get("label") or f"Source {i + 1}"

        if source_type == "document" and src.get("document_uuid"):
            doc = await SmartDocument.find_one(
                SmartDocument.uuid == src["document_uuid"]
            )
            if doc and doc.raw_text:
                source_text = doc.raw_text
                if not src.get("label"):
                    label = doc.title or label

        if not source_text:
            continue

        resolved_sources.append({
            "label": label,
            "source_type": source_type,
            "source_text": source_text,
            "expected_values": src.get("expected_values", {}),
        })

    if not resolved_sources:
        raise ValueError("No sources with available text")

    # Validate all sources concurrently
    source_results = list(await asyncio.gather(*(
        _validate_source(
            source_label=rs["label"],
            source_type=rs["source_type"],
            source_text=rs["source_text"],
            expected_values=rs["expected_values"],
            keys=keys,
            model=model,
            sys_config_doc=sys_config_doc,
            extraction_config_override=extraction_config_override,
            num_runs=num_runs,
            field_metadata=field_metadata,
            meta_map=meta_map,
        )
        for rs in resolved_sources
    )))

    # Executive summary
    executive_summary = _compute_executive_summary(source_results, keys)

    # Aggregate accuracy/consistency
    all_accuracies = [
        sr["overall_accuracy"] for sr in source_results
        if sr["overall_accuracy"] is not None
    ]
    all_consistencies = [sr["overall_consistency"] for sr in source_results]

    # Challenging fields
    challenging_fields = []
    for sr in source_results:
        for f in sr["fields"]:
            is_challenging = False
            if f["accuracy"] is not None and f["accuracy"] < 1.0:
                is_challenging = True
            if f["consistency"] < 1.0:
                is_challenging = True
            if is_challenging:
                # Most common error type
                error_types = f.get("error_types", {})
                most_common_error = max(error_types, key=error_types.get) if error_types else "none"
                challenging_fields.append({
                    "field_name": f["field_name"],
                    "source_label": sr["source_label"],
                    "accuracy": f["accuracy"],
                    "consistency": f["consistency"],
                    "most_common_error": most_common_error,
                })

    # Error type summary across all sources/fields
    error_type_summary: dict[str, int] = {}
    for sr in source_results:
        for f in sr["fields"]:
            for err_type, count in f.get("error_types", {}).items():
                error_type_summary[err_type] = error_type_summary.get(err_type, 0) + count

    # Run cross-field validation on most-common values from each source
    cross_field_score = None
    if ss and ss.cross_field_rules:
        from app.services.cross_field_validation import CrossFieldValidator
        cf_validator = CrossFieldValidator()
        cf_pass_total = 0
        cf_rule_total = 0
        for sr in source_results:
            # Build data dict from most_common_value per field
            cf_data = {}
            for fr in sr.get("fields", []):
                if fr.get("most_common_value") is not None:
                    cf_data[fr["field_name"]] = fr["most_common_value"]
            if cf_data:
                cf_results = cf_validator.validate(cf_data, ss.cross_field_rules)
                cf_pass_total += sum(1 for r in cf_results if r["passed"])
                cf_rule_total += len(cf_results)
        if cf_rule_total > 0:
            cross_field_score = cf_pass_total / cf_rule_total

    result_dict = {
        "search_set_uuid": search_set_uuid,
        "num_runs": num_runs,
        "num_sources": len(source_results),
        "executive_summary": executive_summary,
        "sources": source_results,
        "aggregate_accuracy": (
            sum(all_accuracies) / len(all_accuracies) if all_accuracies else None
        ),
        "aggregate_consistency": (
            sum(all_consistencies) / len(all_consistencies)
            if all_consistencies else 0.0
        ),
        "challenging_fields": challenging_fields,
        "error_type_summary": error_type_summary,
        "cross_field_score": cross_field_score,
    }

    # Persist validation run for quality tracking
    from app.services.quality_service import persist_validation_run
    await persist_validation_run(
        item_kind="search_set",
        item_id=search_set_uuid,
        item_name=ss.title if ss else "",
        run_type="extraction",
        result=result_dict,
        user_id=user_id,
        model=model,
        extraction_config=extraction_config_override or {},
    )

    return result_dict
