"""Source-bound automatic Batch review, deterministic coverage and saved history."""
from copy import deepcopy
import os
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_batch_execution as execution
from tests.integration import test_certification_enrollments as enrollments
from app.models.certification import CertificationLabExecution, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.batch_reviews import BatchReviewRepository
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.practical_evidence import EvidenceAssemblyUnavailable
from app.services.certification_versions.review_attempts import ReviewAttemptRepository
from app.services.certification_versions.review_delivery import ReviewDelivery
from app.services.certification_versions.runtime import CourseOperation

repo = execution.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo, *, wrong=False, incomplete=False, failed=False):
    f = await execution.fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=execution.provider(f)):
        f.original = await execution.original_batch(repo, f)
    await execution.next_plan(repo, f, 'retry', f.original)
    callback = RuntimeError('synthetic failed retry') if failed else (lambda **kwargs: []) if incomplete else execution.provider(f, wrong=wrong)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=callback):
        f.retry = await execution.execute(repo, f)
    f.review_body = {'request_id': uuid4().hex, 'run_id': f.original['run_id'], 'result_sha256': encode(f.original['result'])[1],
        'case_sha256': f.case.digest, 'retries': [{'run_id': f.retry['run_id'], 'result_sha256': encode(f.retry['result'])[1]}],
        'answers': {'batch_review': 'The original batch has three distinct terminal input receipts. Proposal 2 was rejected by the disclosed training gate before model dispatch; proposals 1 and 3 retain their original successful receipt hashes. Only proposal 2 was retried, and its five source-checked values reconcile the inventory. Terminal coverage alone did not mean usable success. The two-source pilot uses one template and sponsor, so elapsed time does not prove wider reliability, and unmeasured cost remains unknown.'},
        'consent': 'save_batch_recovery_interpretation'}
    return f


async def submit(repo, f, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='save_batch_review') as progress:
        return await BatchReviewRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.review_body, actor_user_id=actor or f.learner.user_id)


async def prepare(repo, f, submission_id, request_id=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='prepare_batch_review') as progress:
        return await ReviewAttemptRepository().prepare_from_batch_review(CourseOperation(f.learner.user_id, f.package, progress, True),
            submission_id, request_id or uuid4().hex, actor_user_id=f.learner.user_id,
            model_name='synthetic-reviewer', system_config=enrollments.REVIEW_CONFIG)


async def test_complete_review_and_linked_revision_survive_live_work_deletion(repo):
    f = await fixture(repo)
    saved = await submit(repo, f)
    await CertificationLabExecution.get_motor_collection().delete_many({})
    assert await submit(repo, f) == saved
    f.review_body.update(request_id=uuid4().hex, previous_submission_id=saved['uuid'])
    f.review_body['answers']['batch_review'] += ' This clarification retains all original work.'
    revised = await submit(repo, f)
    assert revised['execution'] == saved['execution'] and revised['retry_executions'] == saved['retry_executions']
    assert await BatchReviewRepository().get('foreign', saved['uuid']) is None
    prepared = await prepare(repo, f, saved['uuid'])
    packet = encode(prepared['record']['evidence'])[0]
    assert 'source_pdf_base64' not in packet and 'authored_case' not in packet and 'review_guidance' not in packet
    assert all(value in packet for value in ('320000', '275000', '410000', 'controlled_training_rejection_before_dispatch'))
    assert {e['kind'] for e in prepared['record']['evidence']} == {'execution_receipt', 'pilot_result_snapshot', 'batch_result_snapshot', 'retry_receipt', 'learner_decision'}
    await CertificationLearnerDecision.get_motor_collection().delete_many({})
    assert await prepare(repo, f, saved['uuid'], prepared['attempt_id']) == prepared
    judge = AsyncMock(side_effect=enrollments.supported_review)
    assessed = await enrollments.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], judge)
    assert assessed['result']['assessment']['status'] == 'requirements_supported'
    public = await ReviewDelivery(repo).get(f.learner.user_id, f.learner.uuid, prepared['attempt_id'])
    assert public['assessment_kind'] == 'bounded_batch_review_draft' and public['batch_review_submission_id'] == saved['uuid']
    assert len(public['outcomes']) == 3 and all(o['verdict'] == 'supported' for o in public['outcomes'])
    assert public['staff_review_required'] is public['credit_awarded'] is False
    listed = await ReviewDelivery(repo).list(f.learner.user_id, f.learner.uuid, 'batch_processing')
    assert listed['attempts'][0]['batch_review_submission_id'] == saved['uuid']
    assert await enrollments.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], judge) == assessed
    assert judge.await_count == 1
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['actor', 'case', 'result', 'missing', 'pilot', 'unknown_parent', 'blank', 'extra_evidence', 'reuse', 'retry_digest', 'duplicate_retry', 'retry_original'])
async def test_foreign_or_changed_review_cannot_claim_original_work(repo, change):
    f = await fixture(repo)
    if change in ('case', 'result'):
        f.review_body[change + '_sha256'] = '0' * 64
    elif change == 'missing':
        f.review_body['run_id'] = uuid4().hex
    elif change == 'pilot':
        f.review_body['run_id'] = f.original['plan']['parent_run_id']
    elif change == 'unknown_parent':
        f.review_body['previous_submission_id'] = uuid4().hex
    elif change == 'blank':
        f.review_body['answers']['batch_review'] = '   '
    elif change == 'extra_evidence':
        f.review_body['passed'] = True
    elif change == 'reuse':
        await submit(repo, f)
        f.review_body['answers']['batch_review'] = 'A changed answer cannot replace an earlier request.'
    elif change == 'retry_digest':
        f.review_body['retries'][0]['result_sha256'] = '0' * 64
    elif change == 'duplicate_retry':
        f.review_body['retries'].append(f.review_body['retries'][0])
    elif change == 'retry_original':
        f.review_body['retries'][0] = {'run_id': f.original['run_id'], 'result_sha256': encode(f.original['result'])[1]}
    with pytest.raises(ValueError):
        await submit(repo, f, actor='foreign' if change == 'actor' else None)


@pytest.mark.parametrize('failed', [False, True])
async def test_wrong_or_failed_retry_vetoes_favorable_model_but_preserves_terminal_coverage(repo, failed):
    f = await fixture(repo, wrong=not failed, failed=failed)
    saved = await submit(repo, f)
    prepared = await prepare(repo, f, saved['uuid'])
    assessed = await enrollments.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], AsyncMock(side_effect=enrollments.supported_review))
    assessment = assessed['result']['assessment']
    assert assessment['status'] == 'revision_required' and assessment['passed'] is False
    assert assessment['deterministic_outcomes'][0]['passed'] is True
    assert next(o for o in assessment['outcomes'] if o['outcome_id'] == 'batch_processing.targeted_recovery')['verdict'] == 'contradicted'
    assert all(o['verdict'] == 'supported' for o in assessment['model_outcomes'])


async def test_unavailable_output_is_not_a_learner_failure(repo):
    f = await fixture(repo, incomplete=True)
    saved = await submit(repo, f)
    with pytest.raises(EvidenceAssemblyUnavailable):
        await prepare(repo, f, saved['uuid'])


async def test_technical_judge_retry_does_not_repeat_extraction(repo):
    f = await fixture(repo)
    saved = await submit(repo, f)
    prepared = await prepare(repo, f, saved['uuid'])
    failed = await enrollments.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], AsyncMock(side_effect=RuntimeError('synthetic')))
    assert failed['state'] == 'unavailable'
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='retry_batch_judge') as progress:
        retry = await ReviewAttemptRepository().prepare_retry(CourseOperation(f.learner.user_id, f.package, progress, True),
            failed['attempt_id'], uuid4().hex, actor_user_id=f.learner.user_id, system_config=enrollments.REVIEW_CONFIG)
    assert retry['record']['evidence'] == prepared['record']['evidence']
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        result = await enrollments.evaluate_review(repo, f.learner, f.package, retry['attempt_id'], AsyncMock(side_effect=enrollments.supported_review))
        assert result['state'] == 'evaluated'
        engine.assert_not_called()


@pytest.mark.parametrize('change', ['inventory', 'source', 'answer_binding', 'retry'])
async def test_rehashed_nested_review_cannot_replace_original_evidence(repo, change):
    f = await fixture(repo)
    saved = await submit(repo, f)
    altered = deepcopy(saved)
    if change == 'inventory':
        altered['reconciliation']['targeted_recovery_supported'] = False
    elif change == 'source':
        altered['case']['sources'][0]['sha256'] = '0' * 64
    elif change == 'answer_binding':
        altered['submission']['result_sha256'] = '0' * 64
    else:
        altered['retry_executions'] = []
    serialized, digest = encode(altered)
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': saved['uuid']})
    raw.update(record_json=serialized, record_sha256=digest)
    with pytest.raises(CourseCatalogError):
        BatchReviewRepository.decode(raw)
