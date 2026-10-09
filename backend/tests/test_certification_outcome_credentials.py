"""Credential evidence is frozen from complete original selected judgments."""
from dataclasses import replace
import datetime
import json

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.credentials import CredentialRepository
from app.services.certification_versions.outcome_credit import freeze_credit, repeats_earned_outcomes
from app.services.certification_versions.outcomes import package_outcomes
from tests import test_certification_outcome_rubric as grading

candidate = grading.candidate


def complete_fixture(candidate):
    candidate.package = replace(candidate.package, entry=candidate.package.entry.model_copy(update={'state': 'published', 'supported_for_existing': True}))
    package, progress = candidate.package, candidate.progress
    progress.id = 'synthetic-progress'
    progress.certified = True
    progress.certified_at = datetime.datetime(2026, 10, 7, tzinfo=datetime.timezone.utc)
    progress.level = 'architect'
    contract = package_outcomes(package)
    for index, module in enumerate(contract.modules):
        selected = {}
        if any(item.method != 'scenario_choice' for item in module.outcomes):
            selected['review_attempt_id'] = f'{index + 100:032x}'
        if any(item.method == 'scenario_choice' for item in module.outcomes):
            selected['scenario_attempt_id'] = f'{index + 200:032x}'
        snapshot = {'enrollment_id': progress.enrollment_id, 'course_version': progress.course_version,
            'manifest_sha256': package.manifest_sha256, 'module_id': module.module_id,
            'contract_sha256': encode(contract.model_dump(mode='json'))[1], 'rubric_id': contract.rubric_id,
            'assessment_kind': 'module_readiness_draft', 'status': 'requirements_supported', 'all_required_outcomes_supported': True,
            'read_only': True, 'credit_awarded': False, 'module_completion_eligible': False, 'staff_review_required': False,
            'outcomes': [{'outcome_id': item.id, 'statement': item.statement, 'method': item.method, 'state': 'supported',
                'attempt_id': selected['scenario_attempt_id' if item.method == 'scenario_choice' else 'review_attempt_id']} for item in module.outcomes],
            'selected_receipts': [{'kind': 'automatic_review' if key == 'review_attempt_id' else 'scenario_recognition', 'attempt_id': reference,
                'record_sha256': 'c' * 64, 'result_sha256': 'd' * 64} for key, reference in selected.items()]}
        validation = {'course_version': progress.course_version, 'manifest_sha256': package.manifest_sha256, 'rubric_id': contract.rubric_id,
            'passed': True, 'stars': 1, 'assessment_kind': 'selected_outcome_validation', 'assessment_selection': selected,
            'assessment_snapshot': snapshot, 'assessment_snapshot_sha256': encode(snapshot)[1], 'credit_awarded': False, 'staff_review_required': False,
            'checks': [{'id': item.id, 'name': item.statement, 'role': 'required', 'passed': True, 'detail': 'Synthetic original supported result.'} for item in module.outcomes]}
        payload, digest = encode(validation)
        selection_payload, selection_digest = encode(selected)
        attempt = {'uuid': f'{index + 300:032x}', 'validation_json': payload, 'validation_sha256': digest,
            'assessment_selection_json': selection_payload, 'assessment_selection_sha256': selection_digest}
        progress.modules[module.module_id] = {'completed': True, 'completed_at': progress.certified_at.isoformat(), 'stars': 1,
            'completion_attempt_id': attempt['uuid'], 'outcome_credit': freeze_credit(package, progress, module.module_id, attempt)}
    return package, progress


def test_new_credential_freezes_all_required_outcomes_and_original_selected_evidence(candidate):
    package, progress = complete_fixture(candidate)
    credential = CredentialRepository.prepare(progress, package, 'Synthetic learner')
    assert len(credential.outcomes) == 33 and len(credential.evidence) == 11
    assert credential.outcomes == package_outcomes(package).required_outcomes()
    assert all(item['basis'] == 'selected_required_outcomes' for item in credential.evidence)
    assert all(item['assessment_snapshot']['enrollment_id'] == progress.enrollment_id for item in credential.evidence)
    assert credential.certified_at == progress.certified_at.isoformat()
    assert 'supported by original selected assessment receipts' in credential.outcome_evidence_status
    frozen = credential.model_dump_json()
    progress.modules['foundations']['outcome_credit']['validation_json'] = '{}'
    progress.level = 'changed'
    assert credential.model_dump_json() == frozen


@pytest.mark.parametrize('change', ['legacy_credit_only', 'digest', 'completion_reference', 'missing_outcome', 'failed_outcome',
    'foreign_enrollment', 'foreign_course', 'changed_selection', 'missing_original_result', 'advisory_check'])
def test_credit_counts_or_rehashed_inconsistent_evidence_cannot_establish_new_competence(candidate, change):
    package, progress = complete_fixture(candidate)
    module = progress.modules['governance']
    credit = module['outcome_credit']
    if change == 'legacy_credit_only':
        del module['outcome_credit']
    elif change == 'digest':
        credit['validation_sha256'] = '0' * 64
    elif change == 'completion_reference':
        module['completion_attempt_id'] = 'f' * 32
    else:
        value = json.loads(credit['validation_json'])
        snapshot = value['assessment_snapshot']
        if change == 'missing_outcome':
            snapshot['outcomes'].pop()
        elif change == 'failed_outcome':
            snapshot['outcomes'][0]['state'] = 'revision_required'
        elif change == 'foreign_enrollment':
            snapshot['enrollment_id'] = 'another-learner'
        elif change == 'foreign_course':
            snapshot['manifest_sha256'] = '0' * 64
        elif change == 'changed_selection':
            value['assessment_selection']['review_attempt_id'] = 'f' * 32
        elif change == 'missing_original_result':
            snapshot['selected_receipts'][0]['result_sha256'] = None
        else:
            value['checks'][0]['role'] = 'advisory'
        value['assessment_snapshot_sha256'] = encode(snapshot)[1]
        credit['validation_json'], credit['validation_sha256'] = encode(value)
    with pytest.raises(CourseCatalogError):
        CredentialRepository.prepare(progress, package, 'Synthetic learner')


def test_even_complete_synthetic_evidence_cannot_issue_a_draft_credential(candidate):
    package, progress = complete_fixture(candidate)
    package = replace(package, entry=package.entry.model_copy(update={'state': 'draft', 'supported_for_existing': False}))
    with pytest.raises(CourseCatalogError, match='supported published'):
        CredentialRepository.prepare(progress, package, 'Synthetic learner')


@pytest.mark.parametrize('changed_hash', ['record_sha256', 'result_sha256'])
def test_same_receipt_identity_cannot_replace_its_original_evidence_hash(candidate, changed_hash):
    package, progress = complete_fixture(candidate)
    original = progress.modules['governance']['outcome_credit']
    current = {**original, 'attempt_id': 'f' * 32}
    validation = json.loads(current['validation_json'])
    validation['assessment_snapshot']['selected_receipts'][0][changed_hash] = 'e' * 64
    validation['assessment_snapshot_sha256'] = encode(validation['assessment_snapshot'])[1]
    current['validation_json'], current['validation_sha256'] = encode(validation)
    with pytest.raises(CourseCatalogError, match='evidence changed after its original completion'):
        repeats_earned_outcomes(package, progress, 'governance', current)
