"""κ-drift ledger — continuous tracking of judge↔human agreement over time.

A single 53-case κ check at one point in time tells us "the judge agrees with
humans on the day we wrote the test". It does not tell us what happens when:
  * the judge model is silently swapped (provider rotation)
  * the rubric is reworded for clarity but its meaning shifts
  * a calibration case is added/removed in a way that changes the score band
  * the underlying model is upgraded by the vendor

The ledger records (date, judge_model, surface, kappa, accuracy, bias_rate)
per tier-3 run. CI fails on regression of κ > ``MAX_KAPPA_REGRESSION`` versus
the trailing-30-run median for the same surface — catching silent drift
between an explicit gate violation and the previous baseline.

File format: JSON-Lines at ``backend/tests/fixtures/judge_drift_history.jsonl``.
Each line is one entry; the file is checked in and appended to in CI.
"""

from __future__ import annotations

import datetime
import json
import os
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


# Trailing window for the median we regress against. 30 runs is large enough
# for the median to be stable but small enough that a deliberate rubric
# improvement is reflected within ~a couple weeks of CI runs.
TRAILING_WINDOW = 30

# Maximum allowed drop in κ vs the trailing-window median. Tuned to 0.05 —
# κ moves of less than that on a 50-case fixture are well inside the
# 95% CI on κ itself, so smaller regressions are noise, not signal.
MAX_KAPPA_REGRESSION = 0.05


DEFAULT_LEDGER_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "judge_drift_history.jsonl"
)


@dataclass(frozen=True)
class DriftEntry:
    """One row in the ledger.

    ``surface`` is one of the names in ``judge_contract.all_surfaces()``.
    ``judge_model`` is the LLM model name. ``kappa``, ``accuracy``, and
    ``bias_rate`` are the floats reported by the calibration test. ``commit``
    is the short SHA from CI when available so a regression can be linked
    back to the change that caused it.
    """

    timestamp: str
    surface: str
    judge_model: str
    kappa: float
    accuracy: float
    bias_metric_name: str | None = None
    bias_rate: float | None = None
    n_cases: int | None = None
    commit: str | None = None


def _now_iso() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat(timespec="seconds")


def record(
    surface: str,
    judge_model: str,
    kappa: float,
    accuracy: float,
    *,
    bias_metric_name: str | None = None,
    bias_rate: float | None = None,
    n_cases: int | None = None,
    commit: str | None = None,
    path: Path | None = None,
) -> DriftEntry:
    """Append one drift entry to the ledger and return it.

    Idempotent on identical entries within the same minute (tier-3 tests
    re-run in flaky CI shouldn't double-write). Read-then-append rather
    than open(..., 'a') so the existence check stays simple — the ledger
    is small (one line per release per surface, hundreds of bytes each).
    """
    target = path or DEFAULT_LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    entry = DriftEntry(
        timestamp=_now_iso(),
        surface=surface,
        judge_model=judge_model,
        kappa=round(float(kappa), 4),
        accuracy=round(float(accuracy), 4),
        bias_metric_name=bias_metric_name,
        bias_rate=round(float(bias_rate), 4) if bias_rate is not None else None,
        n_cases=n_cases,
        commit=commit or os.environ.get("GITHUB_SHA") or os.environ.get("GIT_COMMIT"),
    )

    # Dedupe same (surface, model, kappa, accuracy, current-minute) — protects
    # against parallel-tier3 jobs that all want to log on the same release.
    minute_key = entry.timestamp[:16]
    if target.exists():
        for line in target.read_text().splitlines():
            if not line.strip():
                continue
            try:
                prior = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                prior.get("surface") == entry.surface
                and prior.get("judge_model") == entry.judge_model
                and abs(float(prior.get("kappa", 0)) - entry.kappa) < 1e-6
                and abs(float(prior.get("accuracy", 0)) - entry.accuracy) < 1e-6
                and (prior.get("timestamp") or "")[:16] == minute_key
            ):
                return entry  # already recorded this minute

    with target.open("a") as f:
        f.write(json.dumps(asdict(entry)) + "\n")
    return entry


def load_history(
    surface: str | None = None,
    path: Path | None = None,
) -> list[DriftEntry]:
    """Load all ledger entries, optionally filtered by surface."""
    target = path or DEFAULT_LEDGER_PATH
    if not target.exists():
        return []
    out: list[DriftEntry] = []
    for line in target.read_text().splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if surface and d.get("surface") != surface:
            continue
        out.append(DriftEntry(
            timestamp=d.get("timestamp", ""),
            surface=d.get("surface", ""),
            judge_model=d.get("judge_model", ""),
            kappa=float(d.get("kappa", 0.0)),
            accuracy=float(d.get("accuracy", 0.0)),
            bias_metric_name=d.get("bias_metric_name"),
            bias_rate=(float(d["bias_rate"]) if d.get("bias_rate") is not None else None),
            n_cases=d.get("n_cases"),
            commit=d.get("commit"),
        ))
    return out


def trailing_median(
    surface: str,
    window: int = TRAILING_WINDOW,
    path: Path | None = None,
) -> float | None:
    """Median κ over the most recent ``window`` entries for a surface.

    Returns None when fewer than 3 prior entries exist — drift detection
    needs a stable baseline, not a single anchor point.
    """
    history = load_history(surface=surface, path=path)
    if len(history) < 3:
        return None
    recent = history[-window:]
    return statistics.median(e.kappa for e in recent)


def assert_no_regression(
    surface: str,
    new_kappa: float,
    *,
    window: int = TRAILING_WINDOW,
    max_regression: float = MAX_KAPPA_REGRESSION,
    path: Path | None = None,
) -> None:
    """Raise AssertionError if ``new_kappa`` regresses > max_regression
    vs the trailing-``window`` median.

    Intentionally a soft check: when the ledger has too little history to
    establish a baseline, we *don't* fail — a brand-new surface can't have
    drifted from a non-existent past. The κ gate in the calibration test
    catches absolute floor violations; this catches *relative* drift.
    """
    baseline = trailing_median(surface, window=window, path=path)
    if baseline is None:
        return
    if baseline - new_kappa > max_regression:
        raise AssertionError(
            f"Judge κ regression for surface '{surface}': "
            f"new κ {new_kappa:.3f} is {baseline - new_kappa:.3f} below the "
            f"trailing-{window} median of {baseline:.3f} "
            f"(threshold: {max_regression:.3f}). "
            "Either revert the change, or — if intentional — update the "
            "ledger by appending the new entry and reviewing the trend."
        )
