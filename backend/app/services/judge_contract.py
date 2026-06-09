"""Judge contract — the uniform interface every judge surface conforms to.

We have three production judges today (extraction, KB, workflow) and they
each historically grew their own rubric, calibration test, and bias-mitigation
plumbing. The contract codifies the five properties that make the extraction
judge trustworthy (per the [[project_validation_uplift]] audit) so any new
judge surface gets them by construction:

  1. **Anchored rubric** — explicit PASS/PARTIAL/FAIL anchors with examples.
  2. **Deterministic shortcut** — optional pre-judge that resolves unambiguous
     cases (typed fields, absence-equality) without an LLM call.
  3. **Human-anchored κ gate** — a calibration fixture + tier-3 test that
     asserts Cohen's κ vs human gold ≥ a published threshold.
  4. **Same-family judge/candidate exclusion** — the judge model and any
     candidate model being optimized must not share a family (self-preference
     guard).
  5. **Variance-aware winner selection** — judge nondeterminism is measured
     via ``judge_variance.sample_judge_variance`` (boundary-band sampling) and
     fed into a ``WINNER_TIE_SIGMAS × σ`` tie band so the optimizer doesn't
     declare a winner on noise.

This module does NOT execute the judge. It declares the shape, gives each
surface a way to register itself, and exposes a registry so cross-cutting
tooling (κ-drift ledger, dashboards, contract-conformance tests) can iterate
over all judges without hard-coding their names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class JudgeCalibrationGate:
    """A surface's published agreement floor against human-labeled cases.

    ``fixture_path`` is relative to ``backend/tests/fixtures/``.

    ``min_kappa`` is the Cohen's κ floor (3-class). ``min_accuracy`` is the
    in-band-or-3-class-agreement accuracy floor. ``bias_metric_name`` /
    ``max_bias_rate`` describe the surface-specific bias check (length-bias
    for extraction, hallucination-trap FAIL→PASS for KB; workflow currently
    has no second-tier bias check).
    """

    fixture_path: str
    min_kappa: float
    min_accuracy: float
    bias_metric_name: str | None = None
    max_bias_rate: float | None = None


class PreJudge(Protocol):
    """Optional deterministic pre-judge.

    Returns a verdict dict (with ``comparator="deterministic"``) when the
    comparison is unambiguous, or ``None`` when the LLM judge should decide.
    Extraction implements this via ``extraction_judge_router.prejudge``; KB
    and workflow have no current pre-judge (always return None).
    """

    def __call__(self, **kwargs: Any) -> dict | None: ...


class JudgeFn(Protocol):
    """Async judge entry point.

    Returns ``{score, verdict, reasoning, tokens_used, comparator, ...}``.
    Surfaces are free to extend the shape (KB adds missing_facts /
    hallucinated_facts; workflow returns status instead of verdict at the
    outer level).
    """

    async def __call__(self, **kwargs: Any) -> dict: ...


@dataclass(frozen=True)
class JudgeSurface:
    """One registered judge surface.

    Conformance checks (P4.x contract test, drift ledger, dashboards) iterate
    over the registry so the surface set is data-driven, not name-driven.
    """

    name: str
    rubric_module: str  # importable module path holding the rubric prompts
    rubric_entrypoint: str  # function name returning the system prompt for a category/type
    judge_fn_module: str
    judge_fn_name: str
    has_same_family_exclusion: bool
    has_variance_aware_selection: bool
    calibration: JudgeCalibrationGate | None = None
    prejudge_module: str | None = None
    prejudge_name: str | None = None
    notes: str = ""


_REGISTRY: dict[str, JudgeSurface] = {}


def register(surface: JudgeSurface) -> None:
    """Register a judge surface. Idempotent — re-registration replaces."""
    _REGISTRY[surface.name] = surface


def get(name: str) -> JudgeSurface | None:
    return _REGISTRY.get(name)


def all_surfaces() -> list[JudgeSurface]:
    return list(_REGISTRY.values())


# ---------------------------------------------------------------------------
# Built-in registrations — one entry per production surface. Adding a fourth
# surface (verification, agent quality, …) is a single ``register(…)`` call.
# ---------------------------------------------------------------------------

register(JudgeSurface(
    name="extraction",
    rubric_module="app.services.extraction_judge",
    rubric_entrypoint="EXTRACTION_JUDGE_SYSTEM_PROMPT",
    judge_fn_module="app.services.extraction_judge",
    judge_fn_name="judge_field_value",
    has_same_family_exclusion=True,
    has_variance_aware_selection=True,
    calibration=JudgeCalibrationGate(
        fixture_path="judge_calibration.json",
        min_kappa=0.65,
        min_accuracy=0.80,
        bias_metric_name="length_bias_fail_to_pass",
        max_bias_rate=0.20,
    ),
    prejudge_module="app.services.extraction_judge_router",
    prejudge_name="prejudge",
    notes="Reference implementation; all other surfaces aim to match its guarantees.",
))


register(JudgeSurface(
    name="kb",
    rubric_module="app.services.kb_validation_service",
    rubric_entrypoint="_kb_judge_prompt_for_category",
    judge_fn_module="app.services.kb_validation_service",
    judge_fn_name="_judge_answer",
    has_same_family_exclusion=True,
    has_variance_aware_selection=True,
    calibration=JudgeCalibrationGate(
        fixture_path="kb_judge_calibration.json",
        min_kappa=0.60,
        min_accuracy=0.75,
        bias_metric_name="hallucination_trap_fail_to_pass",
        max_bias_rate=0.20,
    ),
    notes="Cross-judge agreement also surfaced as kappa_equivalent on each run.",
))


register(JudgeSurface(
    name="workflow",
    rubric_module="app.services.workflow_service",
    rubric_entrypoint="_evaluate_checks_against_output",
    judge_fn_module="app.services.workflow_service",
    judge_fn_name="_evaluate_checks_against_output",
    # Workflow optimizer is gated behind validation-uplift; same-family
    # exclusion lands when the optimizer ships (the rubric and κ gate land
    # first per the staged plan).
    has_same_family_exclusion=False,
    has_variance_aware_selection=True,  # via _sample_workflow_judge_variance
    calibration=JudgeCalibrationGate(
        fixture_path="workflow_judge_calibration.json",
        min_kappa=0.55,
        min_accuracy=0.70,
    ),
    notes="Plan is cached by definition_hash so check set is stable across runs.",
))
