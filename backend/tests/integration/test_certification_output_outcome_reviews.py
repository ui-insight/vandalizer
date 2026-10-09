"""Owned output interpretation, complete model evidence and automatic-only review."""
from copy import deepcopy
import os
from unittest.mock import AsyncMock
from uuid import uuid4

from pydantic import ValidationError
import pytest

from tests.integration import test_certification_output_private_handoff as handoff_fixtures
from tests.integration import test_certification_enrollments as enrollment_fixtures
from app.models.certification import CertificationLabExecution, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.output_outcome_reviews import OutputOutcomeReviewRepository
from app.services.certification_versions.review_attempts import ReviewAttemptRepository
from app.services.certification_versions.review_delivery import ReviewDelivery
from app.services.certification_versions.runtime import CourseOperation

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = handoff_fixtures.repo


async def fixture(repo, monkeypatch, *, failed_only=False):
    f = await handoff_fixtures.fixture(repo, monkeypatch)
    f.failed = await handoff_fixtures.handoff(repo, f)
    f.handoff = f.failed
    if not failed_only:
        f.handoff_body = handoff_fixtures.retry_body(f, f.failed)
        f.handoff = await handoff_fixtures.handoff(repo, f)
    f.outcome_body = {'request_id': uuid4().hex, 'file_review_id': f.review['uuid'], 'file_review_sha256': encode(f.review)[1],
        'handoff_id': f.handoff['uuid'], 'handoff_sha256': encode(f.handoff)[1], 'case_sha256': f.case.digest,
        'delivery_review': 'The first controlled training attempt failed before writing. I preserved generation and retried only the failed private handoff. The saved destination copy matches the reviewed files and is not sponsor delivery.',
        'consent': 'save_output_delivery_interpretation'}
    if failed_only:
        f.outcome_body['delivery_review'] = 'The controlled first attempt failed before any copy; generation succeeded but delivery did not. I will explicitly retry only this handoff with the same approved files.'
    return f


async def submit(repo, f, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='review_output_outcome') as progress:
        return await OutputOutcomeReviewRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.outcome_body, actor_user_id=actor or f.learner.user_id)


async def prepare(repo, f, submission_id, request_id=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='prepare_output_assessment') as progress:
        return await ReviewAttemptRepository().prepare_from_output_review(
            CourseOperation(f.learner.user_id, f.package, progress, True), submission_id, request_id or uuid4().hex,
            actor_user_id=f.learner.user_id, model_name='synthetic-reviewer', system_config=enrollment_fixtures.REVIEW_CONFIG)


async def evaluate(repo, f, attempt_id, judge):
    return await enrollment_fixtures.evaluate_review(repo, f.learner, f.package, attempt_id, judge)


async def test_original_interpretation_and_revision_survive_deletion_of_live_source_records(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    original = await submit(repo, f)
    await CertificationLabExecution.get_motor_collection().delete_many({})
    await CertificationLearnerDecision.get_motor_collection().delete_many({'uuid': {'$in': [f.review['uuid'], f.failed['uuid'], f.handoff['uuid']]}})
    await f.document.delete()
    await f.workflow.delete()
    assert await submit(repo, f) == original
    f.outcome_body.update(request_id=uuid4().hex, previous_submission_id=original['uuid'],
        delivery_review='The destination confirms only my private training copy. It does not prove any external recipient saw the report.')
    revised = await submit(repo, f)
    assert revised['file_review'] == original['file_review'] and revised['handoff'] == original['handoff']
    assert await OutputOutcomeReviewRepository().get(f.learner.user_id, original['uuid']) == original
    assert await OutputOutcomeReviewRepository().get('foreign', original['uuid']) is None
    assert len(f.calls) == 2


@pytest.mark.parametrize('change', ['actor', 'case_sha256', 'handoff_sha256', 'file_review_sha256', 'missing_handoff', 'foreign_previous', 'blank', 'client_evidence', 'reused_request'])
async def test_unbound_or_changed_interpretation_is_rejected(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch)
    if change.endswith('sha256'):
        f.outcome_body[change] = 'a' * 64
    elif change == 'missing_handoff':
        f.outcome_body['handoff_id'] = uuid4().hex
    elif change == 'foreign_previous':
        f.outcome_body['previous_submission_id'] = uuid4().hex
    elif change == 'blank':
        f.outcome_body['delivery_review'] = ' ' * 12
    elif change == 'client_evidence':
        f.outcome_body['destination_copy'] = {'status': 'delivered'}
    elif change == 'reused_request':
        await submit(repo, f)
        f.outcome_body['delivery_review'] = 'Changed content cannot overwrite the original answer.'
    with pytest.raises((EnrollmentConflict, ValidationError)):
        await submit(repo, f, actor='foreign' if change == 'actor' else None)


@pytest.mark.parametrize('failed_only', [False, True])
async def test_complete_evidence_uses_actual_source_files_and_receipts_without_answer_keys(repo, monkeypatch, failed_only):
    f = await fixture(repo, monkeypatch, failed_only=failed_only)
    saved = await submit(repo, f)
    prepared = await prepare(repo, f, saved['uuid'])
    record = prepared['record']
    assert record['submission_channel'] == 'trusted_saved_output_records'
    evidence = encode(record['evidence'])[0]
    assert 'source_checks' not in evidence and 'review_guidance' not in evidence and 'data_base64' not in evidence
    assert 'USD 135500' in evidence and 'USD 287500' in evidence and 'controlled_training_rejection_before_write' in evidence
    assert ('private_training_copy_saved' in evidence) is not failed_only
    assert len([item for item in record['evidence'] if item['kind'] == 'delivery_receipt']) == (1 if failed_only else 2)
    assert {item['kind'] for item in record['evidence']} == {'execution_receipt', 'artifact_file_snapshot', 'destination_snapshot', 'delivery_receipt', 'learner_decision'}
    await CertificationLearnerDecision.get_motor_collection().delete_many({})
    await CertificationLabExecution.get_motor_collection().delete_many({})
    assert await prepare(repo, f, saved['uuid'], prepared['attempt_id']) == prepared
    judge = AsyncMock(side_effect=enrollment_fixtures.supported_review)
    assessed = await evaluate(repo, f, prepared['attempt_id'], judge)
    assert assessed['result']['assessment']['status'] == 'requirements_supported'
    public = await ReviewDelivery(repo).get(f.learner.user_id, f.learner.uuid, assessed['attempt_id'])
    assert public['assessment_kind'] == 'output_workflow_review_draft' and public['output_review_submission_id'] == saved['uuid']
    assert public['staff_review_required'] is public['credit_awarded'] is public['module_completion_eligible'] is False
    listed = await ReviewDelivery(repo).list(f.learner.user_id, f.learner.uuid, 'output_delivery')
    assert listed['attempts'][0]['output_review_submission_id'] == saved['uuid']
    assert await evaluate(repo, f, prepared['attempt_id'], judge) == assessed
    assert judge.await_count == 1 and len(f.calls) == 2


async def test_technical_retry_uses_original_evidence_without_provider_or_handoff_repeat(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    saved = await submit(repo, f)
    prepared = await prepare(repo, f, saved['uuid'])
    unavailable = await evaluate(repo, f, prepared['attempt_id'], AsyncMock(side_effect=RuntimeError('offline')))
    assert unavailable['state'] == 'unavailable' and unavailable['result']['assessment']['passed'] is None
    await OutputOutcomeReviewRepository().records.delete_one({'uuid': saved['uuid']})
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='retry_output_assessment') as progress:
        retried = await ReviewAttemptRepository().prepare_retry(CourseOperation(f.learner.user_id, f.package, progress, True),
            prepared['attempt_id'], uuid4().hex, actor_user_id=f.learner.user_id, system_config=enrollment_fixtures.REVIEW_CONFIG)
    assert retried['record']['evidence'] == prepared['record']['evidence']
    assert retried['record']['provenance'] == prepared['record']['provenance']
    assessed = await evaluate(repo, f, retried['attempt_id'], AsyncMock(side_effect=enrollment_fixtures.supported_review))
    assert assessed['result']['assessment']['status'] == 'requirements_supported'
    assert len(f.calls) == 2


@pytest.mark.parametrize('change', ['copy_reference', 'handoff', 'review_hash', 'credit'])
async def test_rehashed_original_evidence_cannot_be_replaced(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch)
    saved = await submit(repo, f)
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': saved['uuid']})
    altered = deepcopy(saved)
    if change == 'copy_reference':
        altered['handoff']['destination_copy_sha256'] = 'a' * 64
    elif change == 'handoff':
        altered['handoff']['destination_written'] = False
    elif change == 'review_hash':
        altered['file_review']['record_sha256'] = 'a' * 64
    else:
        altered['credit_awarded'] = True
    raw['record_json'], raw['record_sha256'] = encode(altered)
    with pytest.raises(CourseCatalogError):
        OutputOutcomeReviewRepository.decode(raw)
