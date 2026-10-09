"""Owned budget review revisions, complete evidence and checked automatic grades."""
from copy import deepcopy
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tests.integration import test_certification_advanced_workflow_execution as execution_fixtures
from tests.integration import test_certification_advanced_calculation_records as calculation_fixtures
from tests.integration import test_certification_advanced_workflow_inputs as capture_fixtures
from tests.integration import test_certification_enrollments as enrollment_fixtures
from app.models.certification import CertificationLabInput, CertificationLabExecution
from app.services.certification_versions.advanced_workflow_reviews import AdvancedReviewRepository
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.review_attempts import ReviewAttemptRepository
from app.services.certification_versions.review_delivery import ReviewDelivery
from app.services.certification_versions.runtime import CourseOperation

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = execution_fixtures.repo


async def fixture(repo, monkeypatch, *, correct=False):
    f = await execution_fixtures.fixture(repo, monkeypatch)
    if correct:
        f.body.update(request_id=uuid4().hex, previous_snapshot_id=f.calculation['uuid'])
        f.body['records'][0]['result'] = '45000.00'
        revised = await calculation_fixtures.submit(repo, f)
        f.capture_body.update(request_id=uuid4().hex, calculation_snapshot_id=revised['uuid'],
                              calculation_snapshot_sha256=encode(revised)[1])
        f.saved = await capture_fixtures.capture(repo, f)
        f.plan_body.update(request_id=uuid4().hex, input_snapshot_id=f.saved['uuid'], input_snapshot_sha256=encode(f.saved)[1])
        prepared = await execution_fixtures.preparation_fixtures.prepare(repo, f)
        scope = await execution_fixtures.preparation_fixtures.decide(repo, f,
            execution_fixtures.preparation_fixtures.scope_body(f, prepared))
        f.execution_body.update(run_id=prepared['run_id'], plan_sha256=prepared['plan_sha256'],
            scope_decision_id=scope['uuid'], scope_decision_sha256=encode(scope)[1])
    f.completed = await execution_fixtures.execute(repo, f)
    assert f.completed['state'] == 'completed'
    f.review_body = {'request_id': uuid4().hex, 'run_id': f.completed['run_id'],
        'result_sha256': encode(f.completed['result'])[1], 'case_sha256': f.case.digest,
        'consent': 'save_budget_calculation_and_dependency_review',
        'answers': {'calculation_review': 'The stored additions check named source rows in USD, but do not resolve conflicting period and rate claims.',
                    'dependency_review': 'Both source reviews use the assigned budget and saved calculations. The memo receives both completed results; sibling tasks cannot consume one another.'}}
    return f


async def submit(repo, f, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='review_budget_results') as progress:
        return await AdvancedReviewRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.review_body, actor_user_id=actor or f.learner.user_id)


async def prepare(repo, f, submission_id, request_id=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='prepare_budget_assessment') as progress:
        return await ReviewAttemptRepository().prepare_from_budget_review(
            CourseOperation(f.learner.user_id, f.package, progress, True), submission_id, request_id or uuid4().hex,
            actor_user_id=f.learner.user_id, model_name='synthetic-reviewer', system_config=enrollment_fixtures.REVIEW_CONFIG)


async def evaluate(repo, f, attempt_id, judge):
    return await enrollment_fixtures.evaluate_review(repo, f.learner, f.package, attempt_id, judge)


async def test_saved_answers_and_linked_revision_survive_deletion_of_original_run(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    original = await submit(repo, f)
    await CertificationLabInput.get_motor_collection().delete_many({})
    await CertificationLabExecution.get_motor_collection().delete_many({})
    await f.document.delete()
    await f.workflow.delete()
    assert await submit(repo, f) == original
    f.review_body = {**f.review_body, 'request_id': uuid4().hex, 'previous_submission_id': original['uuid'],
                    'answers': {**f.review_body['answers'], 'calculation_review': 'The original equipment result is wrong; I must correct the source-bound record before relying on it.'}}
    revised = await submit(repo, f)
    assert revised['execution'] == original['execution']
    assert revised['submission']['answers'] != original['submission']['answers']
    assert await AdvancedReviewRepository().get(f.learner.user_id, original['uuid']) == original
    assert await AdvancedReviewRepository().get('foreign', original['uuid']) is None
    assert len(f.calls) == 3


@pytest.mark.parametrize('change', ['actor', 'case', 'result_hash', 'missing_run', 'missing_answer', 'client_evidence', 'foreign_previous'])
async def test_review_rejects_unbound_or_fabricated_work(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch)
    if change == 'case':
        f.review_body['case_sha256'] = 'a' * 64
    elif change == 'result_hash':
        f.review_body['result_sha256'] = 'a' * 64
    elif change == 'missing_run':
        f.review_body['run_id'] = uuid4().hex
    elif change == 'missing_answer':
        f.review_body['answers'].pop('dependency_review')
    elif change == 'client_evidence':
        f.review_body['execution'] = {'status': 'completed'}
    elif change == 'foreign_previous':
        f.review_body['previous_submission_id'] = uuid4().hex
    with pytest.raises((EnrollmentConflict, ValidationError)):
        await submit(repo, f, actor='foreign' if change == 'actor' else None)
    assert await AdvancedReviewRepository().records.count_documents({'prompt_id': 'budget_result_review'}) == 0


async def test_review_request_and_rehashed_execution_cannot_replace_original_work(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    original = await submit(repo, f)
    f.review_body['answers']['calculation_review'] += ' Changed answer.'
    with pytest.raises(EnrollmentConflict):
        await submit(repo, f)
    raw = await AdvancedReviewRepository().records.find_one({'uuid': original['uuid']})
    altered = deepcopy(original)
    altered['execution']['task_event_count'] -= 1
    raw['record_json'], raw['record_sha256'] = encode(altered)
    with pytest.raises(CourseCatalogError):
        AdvancedReviewRepository.decode(raw)


@pytest.mark.parametrize('correct', [False, True])
async def test_actual_calculation_check_controls_assessment_even_when_stub_judge_passes(repo, monkeypatch, correct):
    f = await fixture(repo, monkeypatch, correct=correct)
    review = await submit(repo, f)
    prepared = await prepare(repo, f, review['uuid'])
    record = prepared['record']
    assert record['submission_channel'] == 'trusted_saved_budget_records'
    assert record['provenance']['supporting_checks'][0]['passed'] is correct
    evidence = encode(record['evidence'])[0]
    assert 'review_guidance' not in evidence and 'authored_case' not in evidence
    await CertificationLabExecution.get_motor_collection().delete_many({})
    await CertificationLabInput.get_motor_collection().delete_many({})
    await AdvancedReviewRepository().records.delete_one({'uuid': review['uuid']})
    assert await prepare(repo, f, review['uuid'], prepared['attempt_id']) == prepared
    judge = AsyncMock(side_effect=enrollment_fixtures.supported_review)
    assessed = await evaluate(repo, f, prepared['attempt_id'], judge)
    assessment = assessed['result']['assessment']
    assert assessment['passed'] is correct
    assert assessment['status'] == ('requirements_supported' if correct else 'revision_required')
    assert all(item['verdict'] == 'supported' for item in assessment['model_outcomes'])
    computation = next(item for item in assessment['outcomes'] if item['outcome_id'] == 'advanced_nodes.checked_computation')
    assert computation['verdict'] == ('supported' if correct else 'contradicted')
    public = await ReviewDelivery(repo).get(f.learner.user_id, f.learner.uuid, assessed['attempt_id'])
    assert public['status'] == assessment['status'] and public['assessment_kind'] == 'budget_workflow_review_draft'
    public_computation = next(item for item in public['outcomes'] if item['outcome_id'] == computation['outcome_id'])
    assert public_computation['verdict'] == computation['verdict']
    assert public['staff_review_required'] is public['credit_awarded'] is False
    listing = await ReviewDelivery(repo).list(f.learner.user_id, f.learner.uuid, 'advanced_nodes')
    assert listing['attempts'][0]['budget_review_submission_id'] == review['uuid']
    assert await evaluate(repo, f, prepared['attempt_id'], judge) == assessed
    assert judge.await_count == 1 and len(f.calls) == 3


async def test_technical_retry_preserves_evidence_and_does_not_become_learner_failure(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    review = await submit(repo, f)
    prepared = await prepare(repo, f, review['uuid'])
    unavailable = await evaluate(repo, f, prepared['attempt_id'], AsyncMock(side_effect=RuntimeError('provider offline')))
    assert unavailable['state'] == 'unavailable' and unavailable['result']['assessment']['passed'] is None
    await AdvancedReviewRepository().records.delete_one({'uuid': review['uuid']})
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='retry_budget_assessment') as progress:
        retried = await ReviewAttemptRepository().prepare_retry(CourseOperation(f.learner.user_id, f.package, progress, True),
            prepared['attempt_id'], uuid4().hex, actor_user_id=f.learner.user_id, system_config=enrollment_fixtures.REVIEW_CONFIG)
    assert retried['record']['evidence'] == prepared['record']['evidence']
    assert retried['record']['provenance'] == prepared['record']['provenance']
    result = await evaluate(repo, f, retried['attempt_id'], AsyncMock(side_effect=enrollment_fixtures.supported_review))
    assert result['result']['assessment']['status'] == 'revision_required'
    assert len(f.calls) == 3
