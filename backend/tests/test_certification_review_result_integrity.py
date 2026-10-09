"""Saved feedback must remain internally consistent; no live judge calibration."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services.certification_versions.automatic_review import (
    AutomaticReviewPolicy,
    evaluate_draft_structured_review,
    reviewer_identity,
)
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.outcomes import OutcomeContract
from app.services.certification_versions.review_attempts import ReviewAttemptRepository
from app.services.certification_versions.review_result_integrity import (
    validate_saved_review_result,
)

DRAFT = Path(__file__).resolve().parents[1] / "certification-data/drafts/v5.0"
CONTRACT = OutcomeContract.model_validate_json((DRAFT / "outcomes.json").read_bytes())
MODULES = [
    m.module_id
    for m in CONTRACT.modules
    if any(o.method == "structured_review" for o in m.outcomes)
]
CONFIG = {"available_models": [{"name": "synthetic-judge"}]}


async def saved_review(
    module_id="foundations", *, missing=False, unavailable=False, veto=False
):
    module = next(m for m in CONTRACT.modules if m.module_id == module_id)
    required = [o for o in module.outcomes if o.method == "structured_review"]
    evidence = [
        {"id": kind, "kind": kind, "text": f"Synthetic saved evidence for {kind}."}
        for kind in sorted({kind for o in required for kind in o.evidence})
    ]
    by_kind = {item["kind"]: item for item in evidence}
    response = {
        "outcomes": [
            {
                "outcome_id": outcome.id,
                "verdict": "supported",
                "explanation": "Synthetic supported outcome for integration boundary testing.",
                "revision_instruction": "",
                "citations": [
                    {"evidence_id": by_kind[kind]["id"], "quote": by_kind[kind]["text"]}
                    for kind in outcome.evidence
                ],
            }
            for outcome in required
        ]
    }
    model = AsyncMock(
        side_effect=RuntimeError("PRIVATE SOURCE") if unavailable else None,
        return_value=response,
    )
    if missing:
        evidence = []
    assessment = await evaluate_draft_structured_review(
        CONTRACT,
        module_id,
        evidence,
        model_name="synthetic-judge",
        system_config=CONFIG,
        call_model=model,
    )
    provenance = {
        "deterministic_outcomes": [
            {
                "outcome_id": o.id,
                "passed": True,
                "explanation": "Synthetic saved deterministic check.",
                "revision_instruction": "",
            }
            for o in module.outcomes
            if o.method == "deterministic"
        ]
    }
    if veto:
        item = evidence[0]
        provenance["supporting_checks"] = [
            {
                "outcome_id": required[0].id,
                "passed": False,
                "evidence_id": item["id"],
                "quote": item["text"],
                "explanation": "The saved deterministic evidence contradicts the model verdict.",
                "revision_instruction": "Inspect the original source and correct the required result before resubmitting.",
            }
        ]
    saved = {
        "attempt_id": "saved-review",
        "state": "unavailable" if unavailable else "evaluated",
        "record": {
            "module_id": module_id,
            "evidence": evidence,
            "provenance": provenance,
            "policy": AutomaticReviewPolicy().model_dump(mode="json"),
            "reviewer": reviewer_identity("synthetic-judge", CONFIG),
        },
    }
    saved["result"] = {
        "assessment": ReviewAttemptRepository.with_saved_checks(saved, assessment)
    }
    return saved


@pytest.mark.parametrize("module_id", MODULES)
@pytest.mark.parametrize("mode", ["supported", "missing", "unavailable", "veto"])
async def test_actual_result_producer_remains_readable_for_every_practical_module(
    module_id, mode
):
    saved = await saved_review(
        module_id,
        missing=mode == "missing",
        unavailable=mode == "unavailable",
        veto=mode == "veto",
    )
    before = deepcopy(saved)
    validate_saved_review_result(saved, CONTRACT)
    assert saved == before
    assert saved["result"]["assessment"]["credit_awarded"] is False
    assert saved["result"]["assessment"]["staff_review_required"] is False


@pytest.mark.parametrize(
    "change",
    [
        "status",
        "passed_string",
        "missing_outcome",
        "duplicate_outcome",
        "foreign_outcome",
        "fabricated_quote",
        "wrong_evidence_digest",
        "wrong_contract",
        "wrong_judge",
        "credit",
        "missing_deterministic",
        "duplicate_deterministic",
        "changed_deterministic",
        "string_deterministic",
        "integer_deterministic",
        "integer_policy_flag",
        "duplicate_coverage",
        "missing_coverage",
        "inconsistent_summary",
        "unperformed_model",
        "staff_queue",
    ],
)
async def test_inconsistent_saved_success_is_rejected_without_mutating_the_receipt(
    change,
):
    saved = await saved_review()
    assessment = saved["result"]["assessment"]
    if change == "status":
        assessment["status"] = "unknown_success"
    elif change == "passed_string":
        assessment["passed"] = "true"
    elif change == "missing_outcome":
        assessment["outcomes"].pop()
    elif change == "duplicate_outcome":
        assessment["outcomes"].append(deepcopy(assessment["outcomes"][0]))
    elif change == "foreign_outcome":
        assessment["outcomes"][0]["outcome_id"] = "governance.capstone_supervision"
    elif change == "fabricated_quote":
        assessment["outcomes"][0]["citations"][0]["quote"] = "PRIVATE INVENTED EVIDENCE"
    elif change == "wrong_evidence_digest":
        assessment["evidence_sha256"] = "0" * 64
    elif change == "wrong_contract":
        assessment["contract_sha256"] = "0" * 64
    elif change == "wrong_judge":
        assessment["reviewer"]["model_name"] = "another-judge"
    elif change == "credit":
        assessment["credit_awarded"] = True
    elif change == "missing_deterministic":
        assessment["deterministic_outcomes"] = []
    elif change == "duplicate_deterministic":
        assessment["deterministic_outcomes"] *= 2
    elif change == "changed_deterministic":
        assessment["deterministic_outcomes"][0]["passed"] = False
    elif change == "string_deterministic":
        saved["record"]["provenance"]["deterministic_outcomes"][0]["passed"] = "true"
        assessment["deterministic_outcomes"][0]["passed"] = "true"
    elif change == "integer_deterministic":
        assessment["deterministic_outcomes"] = deepcopy(assessment["deterministic_outcomes"])
        assessment["deterministic_outcomes"][0]["passed"] = 1
    elif change == "integer_policy_flag":
        saved["record"]["policy"]["staff_queue_enabled"] = 0
    elif change == "duplicate_coverage":
        assessment["assessed_outcome_ids"] *= 2
    elif change == "missing_coverage":
        assessment["assessed_outcome_ids"].pop()
    elif change == "inconsistent_summary":
        assessment.update(passed=False, status="revision_required")
    elif change == "unperformed_model":
        assessment["model_called"] = False
    elif change == "staff_queue":
        assessment["staff_review_required"] = True
    before = deepcopy(saved)
    with pytest.raises(CourseCatalogError, match="needs reconciliation") as error:
        validate_saved_review_result(saved, CONTRACT)
    assert "PRIVATE" not in str(error.value)
    assert saved == before


async def test_restoring_a_model_success_cannot_remove_a_saved_source_or_arithmetic_veto():
    saved = await saved_review("advanced_nodes", veto=True)
    result = saved["result"]["assessment"]
    result.update(
        outcomes=result["model_outcomes"], passed=True, status="requirements_supported"
    )
    with pytest.raises(CourseCatalogError):
        validate_saved_review_result(saved, CONTRACT)


async def test_technical_failure_cannot_smuggle_successful_outcomes():
    saved = await saved_review(unavailable=True)
    saved["result"]["assessment"]["outcomes"] = (await saved_review())["result"][
        "assessment"
    ]["outcomes"]
    with pytest.raises(CourseCatalogError):
        validate_saved_review_result(saved, CONTRACT)


async def test_missing_check_cannot_be_removed_from_both_result_and_provenance():
    saved = await saved_review()
    saved["record"]["provenance"]["deterministic_outcomes"] = []
    saved["result"]["assessment"]["deterministic_outcomes"] = []
    with pytest.raises(CourseCatalogError):
        validate_saved_review_result(saved, CONTRACT)
