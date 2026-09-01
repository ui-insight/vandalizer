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
Each line is one entry; the file is checked in and appended to in CI — which
required a commit-back step in ``integration-llm.yaml``, because the tier-3 job
runs on an ephemeral GitHub Actions disk. Without it every run wrote one line
and threw it away, ``trailing_median`` never reached its three-entry minimum,
and drift detection was structurally incapable of ever firing.

**A κ measured in CI belongs to the model CI measured it on.** The tier-3 job
runs against ``INTEGRATION_LLM_MODEL``; a deployment whose judge is a local 8B
has no claim on that number. :func:`calibration_for` returns a figure only for
the exact model it was measured on, and returns None otherwise, so the honest
answer — "κ unmeasured for this model" — is the one a caller gets by default
rather than one it has to remember to ask for.
"""

from __future__ import annotations

import datetime
import json
import os
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path


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
    judge_model: str | None = None,
) -> float | None:
    """Median κ over the most recent ``window`` entries for a surface.

    Returns None when fewer than 3 prior entries exist — drift detection
    needs a stable baseline, not a single anchor point.

    ``judge_model`` scopes the baseline to one model, and callers that gate on
    the result should always pass it. Pooling models means the first run after
    a model rotation is compared against the *previous* model's median — a
    spurious regression on the exact event ("the judge model is silently
    swapped") this ledger exists to detect, followed by a permanently mixed
    baseline. Rotating models is a step change, not drift.
    """
    history = load_history(surface=surface, path=path)
    if judge_model is not None:
        history = [e for e in history if e.judge_model == judge_model]
    if len(history) < 3:
        return None
    # By timestamp, not file order, for the reason `calibration_for` gives:
    # line order is only chronological while the file is strictly appended, and
    # the commit-back flow can reorder it on a conflict resolution. "The most
    # recent `window` entries" has to mean the most recent ones.
    recent = sorted(history, key=lambda e: e.timestamp)[-window:]
    return statistics.median(e.kappa for e in recent)


def assert_no_regression(
    surface: str,
    new_kappa: float,
    *,
    window: int = TRAILING_WINDOW,
    max_regression: float = MAX_KAPPA_REGRESSION,
    path: Path | None = None,
    judge_model: str | None = None,
    baseline: float | None = None,
) -> None:
    """Raise AssertionError if ``new_kappa`` regresses > max_regression
    vs the trailing-``window`` median.

    Intentionally a soft check: when the ledger has too little history to
    establish a baseline, we *don't* fail — a brand-new surface can't have
    drifted from a non-existent past. The κ gate in the calibration test
    catches absolute floor violations; this catches *relative* drift.

    ``baseline`` lets a caller that records its measurement *before* asserting
    — which the tier-3 job does, so a run that trips the absolute floor still
    reaches the ledger — pass the median it captured beforehand. Without it the
    new entry sits inside the baseline it is being judged against: with exactly
    two prior runs for the model, a κ of 0.60 against a prior [0.80, 0.60]
    medians to 0.60 and silently clears a check the ledger was still too thin
    to make.
    """
    if baseline is None:
        baseline = trailing_median(
            surface, window=window, path=path, judge_model=judge_model,
        )
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


def calibration_for(
    surface: str,
    judge_model: str,
    path: Path | None = None,
) -> dict | None:
    """The measured agreement for ``judge_model`` on ``surface``, or None.

    None means exactly one thing: nobody has ever measured this model on this
    surface. It must not be filled in with another model's figure — that is the
    substitution this function exists to prevent. A customer running a local 8B
    as their judge would otherwise inherit an agreement number established
    against a frontier model in someone else's CI, and the whole point of a
    published κ is that it was measured on the thing doing the judging.

    Returns ``{judge_model, kappa, accuracy, measured_at, n_runs}`` using the
    most recent entry for the model, with ``n_runs`` counting how many times it
    has been measured — one run is a data point, not a baseline.
    """
    entries = [e for e in load_history(surface=surface, path=path)
               if e.judge_model == judge_model]
    if not entries:
        return None
    # By timestamp, not file order. Line order is only chronological while the
    # file is strictly appended, and the commit-back flow can reorder it on a
    # conflict resolution — after which `entries[-1]` would publish a stale κ
    # under a `measured_at` that is not the maximum.
    latest = max(entries, key=lambda e: e.timestamp)
    return {
        "judge_model": judge_model,
        "kappa": latest.kappa,
        "accuracy": latest.accuracy,
        "measured_at": latest.timestamp,
        "n_runs": len(entries),
    }


def measured_models(surface: str, path: Path | None = None) -> list[str]:
    """Judge models this surface has ever been calibrated against, newest last."""
    seen: list[str] = []
    for entry in load_history(surface=surface, path=path):
        if entry.judge_model and entry.judge_model not in seen:
            seen.append(entry.judge_model)
    return seen


def calibration_status(
    surface: str,
    judge_models: list[str],
    *,
    published_floor: float | None = None,
    path: Path | None = None,
) -> dict:
    """What can honestly be said about this surface's judge agreement here.

    ``judge_models`` are the models this deployment could actually judge with.
    The result names, per model, whether κ was measured *for that model* — never
    borrowing another's — plus the ledger-wide context a reader needs to
    interpret it: the published floor, which models have ever been measured,
    and whether the ledger has enough history for drift detection to fire at all.
    """
    history = load_history(surface=surface, path=path)
    models = []
    for model in judge_models:
        measured = calibration_for(surface, model, path=path)
        # Per model, because that is the scope the check actually runs at.
        n_for_model = sum(1 for e in history if e.judge_model == model)
        models.append({
            "judge_model": model,
            "calibrated": measured is not None,
            "drift_detectable": n_for_model >= 3,
            **(measured or {"kappa": None, "accuracy": None,
                            "measured_at": None, "n_runs": 0}),
        })
    return {
        "surface": surface,
        "published_floor": published_floor,
        "models": models,
        "measured_models": measured_models(surface, path=path),
        "ledger_entries": len(history),
        # Counted per model, not pooled. `trailing_median` needs three entries
        # *for the model being checked*, so a ledger holding one run each for
        # three different models has no baseline for any of them — pooling the
        # count claimed drift was detectable while `assert_no_regression` could
        # never fire for any model, which is the model-substitution error this
        # file exists to prevent, in the field that reports whether it works.
        "drift_detectable": any(m["drift_detectable"] for m in models),
    }
