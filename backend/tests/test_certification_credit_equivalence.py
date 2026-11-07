"""A preview cannot convert legacy activity or changed requirements to credit."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json

import pytest
from pydantic import ValidationError

from app.services.certification_versions.catalog import (
    CATALOG_ROOT,
    CourseCatalog,
    CourseCatalogError,
)
from app.services.certification_versions.credit_equivalence import (
    assessment_basis,
    equivalence_plan,
)
from app.services.certification_versions.outcomes import package_outcomes
from tests import test_certification_outcome_credentials as credit_fixtures

candidate = credit_fixtures.candidate
complete_fixture = credit_fixtures.complete_fixture


def changed(package, *, version=None, assets=None):
    manifest = package.manifest.model_dump(mode="json")
    if version:
        manifest["release_id"] = version
    content = dict(package.artifact_bytes)
    for name, value in (assets or {}).items():
        content[name] = (
            value if isinstance(value, bytes) else json.dumps(value).encode()
        )
    manifest["artifacts"] = {
        name: hashlib.sha256(data).hexdigest() for name, data in content.items()
    }
    raw = json.dumps(manifest).encode()
    digest = hashlib.sha256(raw).hexdigest()
    return replace(
        package,
        manifest_bytes=raw,
        manifest_sha256=digest,
        entry=package.entry.model_copy(update={"manifest_sha256": digest}),
        artifact_bytes=tuple(content.items()),
    )


def mapping(source):
    return {
        "schema_version": 1,
        "policy_id": "unchanged-outcomes.1",
        "source_version": source.manifest.release_id,
        "source_manifest_sha256": source.manifest_sha256,
        "target_version": "qa-equivalent.1",
        "assessment_basis_sha256": assessment_basis(source),
        "rules": [
            {
                "rule_id": outcome,
                "outcome_id": outcome,
                "reason": "The original evidence meets unchanged assessment requirements.",
            }
            for outcome in package_outcomes(source).required_outcomes()
        ],
    }


def pair(candidate):
    source, progress = complete_fixture(candidate)
    target = changed(
        source,
        version="qa-equivalent.1",
        assets={"credit-equivalence.json": mapping(source)},
    )
    return source, target, progress


def test_verified_original_outcomes_are_eligible_without_applying_credit(candidate):
    source, target, progress = pair(candidate)
    before = deepcopy(vars(progress))
    plan = equivalence_plan(source, target, progress)
    assert plan["eligible_outcome_count"] == plan["required_outcome_count"] == 33
    assert plan == equivalence_plan(source, target, progress)
    assert all(
        row["source_completion_attempt_id"] and row["source_assessment_sha256"]
        for row in plan["outcomes"]
    )
    assert (
        plan["credit_transferred"]
        is plan["can_apply"]
        is plan["staff_review_required"]
        is False
    )
    assert plan["xp_awarded"] == 0 and vars(progress) == before
    assert "validation_json" not in json.dumps(plan)


def test_matching_course_without_explicit_rule_never_transfers(candidate):
    source, _, progress = pair(candidate)
    target = changed(source, version="qa-equivalent.1")
    assert equivalence_plan(source, target, progress)["eligible_outcome_count"] == 0


@pytest.mark.parametrize(
    "field,value",
    [("source_version", "different.1"), ("source_manifest_sha256", "a" * 64)],
)
def test_rule_for_another_source_does_not_apply(candidate, field, value):
    source, _, progress = pair(candidate)
    rule = mapping(source)
    rule[field] = value
    target = changed(
        source, version="qa-equivalent.1", assets={"credit-equivalence.json": rule}
    )
    assert equivalence_plan(source, target, progress)["eligible_outcome_count"] == 0


def test_legacy_credit_and_certificate_remain_original_without_inferred_equivalence(
    candidate,
):
    _, target, progress = pair(candidate)
    source = CourseCatalog(CATALOG_ROOT).load("legacy-2026-10-02.1", preview=True)
    progress.course_version = source.manifest.release_id
    progress.total_xp = 999999
    before = deepcopy(vars(progress))
    assert equivalence_plan(source, target, progress)["eligible_outcome_count"] == 0
    assert vars(progress) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_credit",
        "incomplete_module",
        "missing_attempt",
        "corrupt_receipt",
        "wrong_enrollment",
    ],
)
def test_incomplete_or_invalid_original_evidence_cannot_pass(candidate, mutation):
    source, target, progress = pair(candidate)
    saved = progress.modules["foundations"]
    if mutation == "missing_credit":
        saved.pop("outcome_credit")
    elif mutation == "incomplete_module":
        saved["completed"] = False
    elif mutation == "missing_attempt":
        saved.pop("completion_attempt_id")
    elif mutation == "corrupt_receipt":
        saved["outcome_credit"]["validation_json"] = "{}"
    else:
        progress.enrollment_id = "another-enrollment"
    if mutation in ("missing_credit", "incomplete_module"):
        rows = equivalence_plan(source, target, progress)["outcomes"]
        assert all(
            row["status"] == "requires_assessment"
            for row in rows
            if row["module_id"] == "foundations"
        )
    else:
        with pytest.raises(CourseCatalogError):
            equivalence_plan(source, target, progress)


@pytest.mark.parametrize(
    "asset",
    [
        "rubric.py",
        "exercises.json",
        "assessment-policy.json",
        "progression-policy.json",
        "documents/new-source.txt",
        "unknown-new-grading-config.json",
    ],
)
def test_changed_or_new_assessment_assets_invalidate_mapping(candidate, asset):
    source, target, progress = pair(candidate)
    target = changed(target, assets={asset: b"changed"})
    with pytest.raises(CourseCatalogError, match="unchanged assessment"):
        equivalence_plan(source, target, progress)


def test_changed_passing_condition_invalidates_mapping(candidate):
    source, target, progress = pair(candidate)
    contract = target.json("outcomes.json")
    contract["modules"][0]["outcomes"][0]["passing_conditions"].append(
        "An additional assessed condition is now required."
    )
    target = changed(target, assets={"outcomes.json": contract})
    with pytest.raises(CourseCatalogError, match="unchanged assessment"):
        equivalence_plan(source, target, progress)


def test_editorial_lesson_change_does_not_erase_unchanged_assessed_evidence(candidate):
    source, target, progress = pair(candidate)
    lessons = target.json("lessons.json")
    lessons["ai_literacy"]["lessons"][0]["title"] = "Clearer introductory title"
    target = changed(target, assets={"lessons.json": lessons})
    assert equivalence_plan(source, target, progress)["eligible_outcome_count"] == 33


@pytest.mark.parametrize(
    "mutation", ["duplicate", "unknown_outcome", "wrong_target", "wrong_basis"]
)
def test_invalid_authored_mapping_is_rejected(candidate, mutation):
    source, _, progress = pair(candidate)
    rule = mapping(source)
    if mutation == "duplicate":
        rule["rules"].append(rule["rules"][0])
    elif mutation == "unknown_outcome":
        rule["rules"][0]["outcome_id"] = "ai_literacy.invented"
    elif mutation == "wrong_target":
        rule["target_version"] = "another.1"
    else:
        rule["assessment_basis_sha256"] = "f" * 64
    target = changed(
        source, version="qa-equivalent.1", assets={"credit-equivalence.json": rule}
    )
    with pytest.raises((CourseCatalogError, ValidationError)):
        equivalence_plan(source, target, progress)
