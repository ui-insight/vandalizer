"""Calibration tests for the deterministic pre-judge router.

These don't need an LLM. They lock in the behavior of the typed-field
short-circuit: dates / numbers / currency / enums / exact-or-normalized
string matches must be resolved without an LLM call, with the correct
verdict. Regressions here would either burn tokens unnecessarily (false
``None``s) or score wrong values (deterministic miscalls).

The fixture at ``tests/fixtures/judge_calibration.json`` is the same set
used by the LLM calibration test in ``test_tier3_llm.py``; this one only
asserts on cases where the router is supposed to be unambiguous.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.extraction_judge_router import prejudge

FIXTURE = Path(__file__).parent / "fixtures" / "judge_calibration.json"


def _load_cases() -> list[dict]:
    return json.loads(FIXTURE.read_text())["cases"]


# Field types where the deterministic router is supposed to fully resolve.
# Free-text and length-trap cases are explicitly OUT of scope here — they
# need the LLM judge.
DETERMINISTIC_TYPES = {"date", "currency", "number", "enum", "absence", "id"}


def _verdict_band(gold_verdict: str) -> tuple[float, float]:
    return {
        "PASS": (0.7, 1.0),
        "PARTIAL": (0.4, 0.7),
        "FAIL": (0.0, 0.4),
    }[gold_verdict]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_prejudge_typed_fields(case: dict) -> None:
    """For typed fields (dates/numbers/currency/enum/absence/id), the
    deterministic comparator must return a verdict (not None) and the score
    must fall within the gold band.

    Free-text and length-trap cases are skipped — those defer to the LLM.
    """
    field_type = case["field_type"]
    if field_type not in DETERMINISTIC_TYPES:
        pytest.skip(f"Field type '{field_type}' defers to LLM judge")

    result = prejudge(
        field_name=case["field_name"],
        expected=case["expected"],
        actual=case["actual"],
        field_metadata=case.get("field_metadata"),
    )

    assert result is not None, (
        f"Deterministic router returned None for typed field '{field_type}' "
        f"({case['id']}) — would force an unnecessary LLM call."
    )

    lo, hi = _verdict_band(case["gold_verdict"])
    score = float(result["score"])
    assert lo <= score <= hi, (
        f"Score {score:.3f} outside gold band [{lo}, {hi}] for "
        f"{case['gold_verdict']} case '{case['id']}': "
        f"expected={case['expected']!r}, actual={case['actual']!r}, "
        f"reasoning={result.get('reasoning')!r}"
    )
    assert result["comparator"] == "deterministic"


def test_prejudge_defers_for_free_text() -> None:
    """Free-text equivalence (paraphrases, multi-valued sets, partial
    matches) must return ``None`` so the LLM judge handles them. If the
    router starts claiming it can resolve these, that's a regression that
    would scoring legitimately-PARTIAL cases as 0.0 or 1.0."""
    cases = [c for c in _load_cases() if c["field_type"] in ("free_text", "length_trap")]
    # We expect MOST free-text cases to defer, with a few exceptions where
    # _values_match's normalization happens to resolve them (e.g. trailing
    # whitespace, capitalization). Assert the ratio.
    deferred = 0
    for case in cases:
        result = prejudge(
            field_name=case["field_name"],
            expected=case["expected"],
            actual=case["actual"],
            field_metadata=case.get("field_metadata"),
        )
        if result is None:
            deferred += 1

    assert deferred >= max(1, int(0.5 * len(cases))), (
        f"Router resolved {len(cases) - deferred}/{len(cases)} free-text cases "
        f"deterministically. Expected at least 50% deferral. The router may be "
        "over-eager."
    )
