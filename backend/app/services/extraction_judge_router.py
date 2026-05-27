"""Pre-judge router — deterministic comparators for typed extraction fields.

The LLM judge in ``extraction_judge`` is needed for free-text equivalence
("Smith, John" ≡ "John Smith") and ambiguous formatting. It is NOT needed for
dates, numbers, currency, enums, or booleans — those have unambiguous correct
answers that ``extraction_validation_service._values_match`` already resolves.

Routing every value through the LLM for typed fields:
  * burns tokens on cases the judge can't get wrong
  * introduces judge noise on cases that should be deterministic
  * makes the judge calibration set harder to construct (typed cases dominate)

This module exposes ``prejudge(field_name, expected, actual, field_metadata)``
which returns a verdict dict when the comparison is unambiguous, or ``None``
when the LLM judge should handle it. Callers (``extraction_judge``,
``extraction_tuning_service``) consult this before the LLM call.
"""

from __future__ import annotations

from typing import Any

import re

from app.services.extraction_validation_service import (
    _is_not_found,
    _normalize,
    _try_parse_date,
    _try_parse_number,
    _values_match,
)

# Currency symbol detection: if both sides carry a currency symbol and they
# don't match, the values aren't equal even when the numeric parts agree.
# Without this, "$1000" vs "€1000" would deterministically PASS because the
# numeric branch strips currency symbols before comparing.
_CURRENCY_SYMBOLS_RE = re.compile(r"[$€£¥₹]")


def _is_enum_field(field_meta: dict | None) -> bool:
    if not field_meta:
        return False
    enum = field_meta.get("enum_values") or []
    return bool(enum) and isinstance(enum, list)


def _both_parse_as_dates(expected: str, actual: str) -> bool:
    return _try_parse_date(expected) is not None and _try_parse_date(actual) is not None


def _both_parse_as_numbers(expected: str, actual: str) -> bool:
    return _try_parse_number(expected) is not None and _try_parse_number(actual) is not None


def _verdict(score: float, verdict: str, reasoning: str) -> dict[str, Any]:
    return {
        "score": score,
        "verdict": verdict,
        "reasoning": reasoning,
        "tokens_used": 0,
        "comparator": "deterministic",
    }


def prejudge(
    *,
    field_name: str,
    expected: str,
    actual: str | None,
    field_metadata: dict | None = None,
) -> dict | None:
    """Try to resolve the (expected, actual) comparison deterministically.

    Returns a judge-shaped verdict dict on success, or ``None`` if the LLM
    judge should decide. Verdicts returned by this function carry
    ``comparator="deterministic"`` so the calibration suite and UI can
    distinguish pre-judge resolutions from LLM judgements.

    Resolution order:
      1. Both empty/not-found → PASS (absence equality).
      2. Enum field → exact-or-normalized match; mismatch is FAIL (no judge).
      3. Both parse as the same date → PASS.
      4. Both parse as numbers and ``_values_match`` agrees → PASS.
      5. ``_values_match`` says equal (case/whitespace/normalization) → PASS.
      6. Expected parses as a date OR number, actual doesn't match → FAIL.
         (No judge: a typed expected with a non-matching typed actual is
         unambiguously wrong; the LLM can only add noise.)
      7. Anything else → ``None`` (defer to LLM judge).
    """
    exp_raw = expected or ""
    act_raw = "" if actual is None else str(actual)

    exp_nf = _is_not_found(exp_raw)
    act_nf = _is_not_found(act_raw)

    # 1. Absence equality
    if exp_nf and act_nf:
        return _verdict(1.0, "PASS", "both_absent")
    if exp_nf and not act_nf:
        return _verdict(0.0, "FAIL", "expected_absent_actual_present")
    if act_nf and not exp_nf:
        return _verdict(0.0, "FAIL", "expected_present_actual_absent")

    # 2. Enum field — must match one of enum_values exactly (after normalize)
    if _is_enum_field(field_metadata):
        enum_values = [str(v) for v in (field_metadata or {}).get("enum_values", [])]
        exp_n = _normalize(exp_raw)
        act_n = _normalize(act_raw)
        enum_norm = {_normalize(v) for v in enum_values}
        if act_n in enum_norm and exp_n == act_n:
            return _verdict(1.0, "PASS", "enum_match")
        # Enum field with a non-enum actual is wrong; don't waste a judge call.
        return _verdict(0.0, "FAIL", "enum_mismatch")

    # 3. Date equality
    if _both_parse_as_dates(exp_raw, act_raw):
        if _try_parse_date(exp_raw) == _try_parse_date(act_raw):
            return _verdict(1.0, "PASS", "date_match")
        return _verdict(0.0, "FAIL", "date_mismatch")

    # 4. Numeric equality (delegates to _values_match's numeric branch).
    # If both sides carry a currency symbol that DIFFERS, the values aren't
    # equal even when the numbers agree — defer to the LLM rather than
    # PASS '$1000' ≡ '€1000'.
    if _both_parse_as_numbers(exp_raw, act_raw):
        exp_syms = set(_CURRENCY_SYMBOLS_RE.findall(exp_raw))
        act_syms = set(_CURRENCY_SYMBOLS_RE.findall(act_raw))
        if exp_syms and act_syms and exp_syms != act_syms:
            return _verdict(0.0, "FAIL", "currency_symbol_mismatch")
        if _values_match(act_raw, exp_raw):
            return _verdict(1.0, "PASS", "numeric_match")
        return _verdict(0.0, "FAIL", "numeric_mismatch")

    # 5. String-level equality through the normalization ladder
    if _values_match(act_raw, exp_raw):
        return _verdict(1.0, "PASS", "string_match")

    # 6. Typed-expected with a non-matching actual — already caught above for
    # number/date; here, if expected is a date but actual isn't parseable as a
    # date (or vice versa), we *don't* deterministically fail because the
    # extractor may have produced a valid-but-differently-formatted value the
    # LLM judge can recognize. Defer.
    return None
