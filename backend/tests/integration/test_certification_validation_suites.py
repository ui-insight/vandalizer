"""Saved learner expectations cannot mutate into execution or a passing grade."""
from copy import deepcopy
import os
from uuid import uuid4

import pytest

from tests.integration.test_certification_validation_inputs import fixture, capture
from tests.integration import test_certification_validation_inputs as input_fixtures
from app.models.certification import CertificationLabInput, CertificationLearnerDecision, CertificationLabExecution
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation
from app.services.certification_versions.validation_suites import ValidationSuiteRepository

repo = input_fixtures.repo

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


def request(f, snapshot):
    return {'request_id': uuid4().hex, 'input_snapshot_id': snapshot['uuid'], 'input_snapshot_sha256': encode(snapshot)[1],
        'case_sha256': f.case.digest, 'expectations': [{'source_id': e.source_id, 'field': e.field,
            'expected_kind': 'explicit_absence' if e.expected_value is None else 'value', 'expected_value': e.expected_value,
            'source_references': [a.model_dump() for a in e.anchors], 'source_reason': e.meaning} for e in f.case.expectations],
        'suite_design': 'Both complete sources cover different project-wide and annual amounts. The NIH source tests an unnamed Co-PI; no Co-Investigator is promoted to that role. These two proposals do not cover all possible grants.',
        'consent': 'save_checked_representative_expectations_before_execution'}


async def submit(repo, f, body, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='save_validation_suite') as progress:
        return await ValidationSuiteRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True), body,
            actor_user_id=actor or f.learner.user_id)


async def test_complete_suite_survives_capture_and_workspace_deletion_without_authority(repo):
    f = await fixture(repo)
    snapshot = await capture(repo, f)
    body = request(f, snapshot)
    saved = await submit(repo, f, body)
    assert len(saved['test_cases']) == 2
    assert all(len(case['expectations']) == 3 for case in saved['test_cases'])
    assert saved['suite_sha256'] == encode(saved['test_cases'])[1]
    assert saved['execution_authorized'] is saved['source_correctness_verified'] is saved['credit_awarded'] is False
    await CertificationLabInput.get_motor_collection().delete_many({})
    for document in f.documents:
        await document.delete()
    await f.artifact.delete()
    assert await submit(repo, f, body) == saved
    assert await ValidationSuiteRepository().get(f.learner.user_id, saved['uuid']) == saved
    assert await ValidationSuiteRepository().get('foreign', saved['uuid']) is None
    assert await CertificationLabExecution.get_motor_collection().count_documents({}) == 0
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['actor', 'foreign_capture', 'missing_capture', 'capture_digest', 'case', 'missing_pair',
    'duplicate_pair', 'empty_expected', 'null_as_value', 'text_as_absence', 'wrong_page', 'fabricated_quote', 'blank_reason',
    'blank_design', 'consent', 'client_grade'])
async def test_rejects_unowned_incomplete_or_untraceable_expectations(repo, change):
    f = await fixture(repo)
    snapshot = await capture(repo, f)
    body = request(f, snapshot)
    if change == 'foreign_capture':
        await CertificationLabInput.get_motor_collection().update_one({'uuid': snapshot['uuid']}, {'$set': {'user_id': 'foreign'}})
    elif change == 'missing_capture':
        body['input_snapshot_id'] = uuid4().hex
    elif change == 'capture_digest':
        body['input_snapshot_sha256'] = '0' * 64
    elif change == 'case':
        body['case_sha256'] = '0' * 64
    elif change == 'missing_pair':
        body['expectations'].pop()
    elif change == 'duplicate_pair':
        body['expectations'][1] = deepcopy(body['expectations'][0])
    elif change == 'empty_expected':
        body['expectations'][0]['expected_value'] = '   '
    elif change == 'null_as_value':
        body['expectations'][0]['expected_value'] = None
    elif change == 'text_as_absence':
        body['expectations'][-1]['expected_value'] = 'not found'
    elif change == 'wrong_page':
        body['expectations'][0]['source_references'][0]['page'] = 2
    elif change == 'fabricated_quote':
        body['expectations'][0]['source_references'][0]['quote'] = 'An invented source statement'
    elif change == 'blank_reason':
        body['expectations'][0]['source_reason'] = ' ' * 25
    elif change == 'blank_design':
        body['suite_design'] = ' ' * 50
    elif change == 'consent':
        body['consent'] = 'execute_validation'
    elif change == 'client_grade':
        body['passed'] = True
    with pytest.raises(ValueError):
        await submit(repo, f, body, actor='foreign' if change == 'actor' else None)
    assert await CertificationLearnerDecision.get_motor_collection().count_documents({}) == 0


async def test_quote_traceability_does_not_claim_correct_interpretation(repo):
    f = await fixture(repo)
    snapshot = await capture(repo, f)
    body = request(f, snapshot)
    body['expectations'][1]['expected_value'] = '177000'
    body['expectations'][1]['source_reason'] = 'I incorrectly interpreted the Year 1 column as the full project budget.'
    saved = await submit(repo, f, body)
    assert saved['test_cases'][0]['expectations'][1]['expected_value'] == '177000'
    assert saved['source_correctness_verified'] is False
    # Incorrect source interpretation stays actual learner evidence for grading.
    # Saving it never turns it into the private authored expected answer.
    original = await ValidationSuiteRepository().get(f.learner.user_id, saved['uuid'])
    assert original == saved and original['credit_awarded'] is False


@pytest.mark.parametrize('change', ['expected', 'source', 'cases', 'suite_hash', 'capture', 'authority'])
async def test_nested_changes_fail_after_outer_record_is_rehashed(repo, change):
    f = await fixture(repo)
    saved = deepcopy(await submit(repo, f, request(f, await capture(repo, f))))
    if change == 'expected':
        saved['submission']['expectations'][0]['expected_value'] = 'Changed answer'
    elif change == 'source':
        saved['test_cases'][0]['source_sha256'] = '0' * 64
    elif change == 'cases':
        saved['test_cases'].pop()
    elif change == 'suite_hash':
        saved['suite_sha256'] = '0' * 64
    elif change == 'capture':
        saved['input_snapshot']['record_sha256'] = '0' * 64
    else:
        saved['execution_authorized'] = True
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': saved['uuid']})
    serialized, digest = encode(saved)
    raw.update(record_json=serialized, record_sha256=digest)
    with pytest.raises(CourseCatalogError):
        ValidationSuiteRepository.decode(raw)


async def test_an_original_request_cannot_overwrite_checked_expectations(repo):
    f = await fixture(repo)
    body = request(f, await capture(repo, f))
    saved = await submit(repo, f, body)
    body['expectations'][0]['expected_value'] = 'Different PI'
    with pytest.raises(EnrollmentConflict):
        await submit(repo, f, body)
    assert await ValidationSuiteRepository().get(f.learner.user_id, saved['uuid']) == saved
