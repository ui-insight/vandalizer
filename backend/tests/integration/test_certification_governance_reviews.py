"""Automatic final capstone review retains the complete authenticated supervision chain."""
from copy import deepcopy
import os
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_governance_handoff as handoff
from tests.integration import test_certification_enrollments as enrollments
from app.models.certification import CertificationLabExecution, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.governance_reviews import GovernanceReviewRepository
from app.services.certification_versions.review_attempts import ReviewAttemptRepository
from app.services.certification_versions.review_delivery import ReviewDelivery
from app.services.certification_versions.runtime import CourseOperation

repo = handoff.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo):
    f = await handoff.fixture(repo)
    f.release = await handoff.release(repo, f)
    f.first = await handoff.send(repo, f, handoff.handoff_body(f, f.release))
    f.delivered = await handoff.send(repo, f, handoff.retry_body(f.first))
    f.review_body = {'request_id': uuid4().hex, 'run_id': f.final['run_id'], 'case_sha256': f.case.digest,
        'handoff_id': f.delivered['uuid'], 'handoff_sha256': encode(f.delivered)[1],
        'final_supervision': 'I rejected the proposed broad document scope, sharing, sponsor email and recurring send. My original run returned the $600,000 ceiling as obligations; the saved source finding cites the amendment revising cumulative obligations to $250,000. I repaired the same funding field and approved a complete rerun on both unchanged records and models. All six actual values matched their sources. I inspected and approved the exact memo bytes for my private inbox, observed the disclosed rejection before any write, and explicitly retried only those same bytes. The confirming private-copy receipt preserves the first failure. I own this limited training artifact; changed real sources or instructions would require new validation and appropriate research-office review, not a certification staff queue. This one fictional pair does not establish general reliability or actual external delivery.',
        'consent': 'save_my_capstone_supervision_interpretation'}
    return f


async def submit(repo, f, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='save_capstone_review') as progress:
        return await GovernanceReviewRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.review_body, actor_user_id=actor or f.learner.user_id)


async def prepare(repo, f, submission_id, request_id=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='prepare_capstone_review') as progress:
        return await ReviewAttemptRepository().prepare_from_governance_review(CourseOperation(f.learner.user_id, f.package, progress, True),
            submission_id, request_id or uuid4().hex, actor_user_id=f.learner.user_id,
            model_name='synthetic-reviewer', system_config=enrollments.REVIEW_CONFIG)


async def test_complete_automatic_review_and_answer_revision_survive_live_history_deletion(repo):
    f = await fixture(repo)
    saved = await submit(repo, f)
    await CertificationLabExecution.get_motor_collection().delete_many({})
    await CertificationLearnerDecision.get_motor_collection().delete_many({'uuid': {'$ne': saved['uuid']}})
    assert await submit(repo, f) == saved
    f.review_body.update(request_id=uuid4().hex, previous_submission_id=saved['uuid'])
    f.review_body['final_supervision'] += ' This revised explanation retains the original complete work.'
    revised = await submit(repo, f)
    assert revised['handoff'] == saved['handoff']
    assert await GovernanceReviewRepository().get('foreign', saved['uuid']) is None
    prepared = await prepare(repo, f, saved['uuid'])
    packet = encode(prepared['record']['evidence'])[0]
    assert 'source_pdf_base64' not in packet and 'authored_case' not in packet and 'content_base64' not in packet
    assert all(value in packet for value in ('250000', '600000', 'controlled_training_rejection_before_write', 'private_training_copy_saved'))
    assert {e['kind'] for e in prepared['record']['evidence']} == {'capstone_attempt', 'source_reference', 'artifact_revision',
        'execution_receipt', 'learner_decision', 'validation_receipt', 'handoff_snapshot', 'delivery_receipt'}
    await CertificationLearnerDecision.get_motor_collection().delete_many({})
    assert await prepare(repo, f, saved['uuid'], prepared['attempt_id']) == prepared
    judge = AsyncMock(side_effect=enrollments.supported_review)
    assessed = await enrollments.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], judge)
    assert assessed['result']['assessment']['status'] == 'requirements_supported'
    public = await ReviewDelivery(repo).get(f.learner.user_id, f.learner.uuid, prepared['attempt_id'])
    assert public['assessment_kind'] == 'governance_capstone_review_draft' and public['governance_review_submission_id'] == saved['uuid']
    assert {o['outcome_id'] for o in public['outcomes'] if o['verdict'] == 'supported'} == {'governance.accountable_handoff', 'governance.capstone_supervision'}
    assert next(o for o in public['outcomes'] if o['method'] == 'scenario_choice')['verdict'] == 'not_assessed'
    assert public['staff_review_required'] is public['credit_awarded'] is False
    listed = await ReviewDelivery(repo).list(f.learner.user_id, f.learner.uuid, 'governance')
    assert listed['attempts'][0]['governance_review_submission_id'] == saved['uuid']
    assert await enrollments.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], judge) == assessed
    assert judge.await_count == 1
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['actor', 'case', 'run', 'handoff_digest', 'missing', 'failed_handoff', 'unknown_parent', 'blank', 'extra_evidence', 'reuse'])
async def test_final_review_cannot_claim_unconfirmed_delivery_or_other_evidence(repo, change):
    f = await fixture(repo)
    if change == 'case':
        f.review_body['case_sha256'] = '0' * 64
    elif change == 'run':
        f.review_body['run_id'] = f.original['run_id']
    elif change == 'handoff_digest':
        f.review_body['handoff_sha256'] = '0' * 64
    elif change == 'missing':
        f.review_body['handoff_id'] = uuid4().hex
    elif change == 'failed_handoff':
        f.review_body.update(handoff_id=f.first['uuid'], handoff_sha256=encode(f.first)[1])
    elif change == 'unknown_parent':
        f.review_body['previous_submission_id'] = uuid4().hex
    elif change == 'blank':
        f.review_body['final_supervision'] = ' ' * 40
    elif change == 'extra_evidence':
        f.review_body['passed'] = True
    elif change == 'reuse':
        await submit(repo, f)
        f.review_body['final_supervision'] += ' Different answer needs a new request.'
    with pytest.raises(ValueError):
        await submit(repo, f, actor='foreign' if change == 'actor' else None)


async def test_technical_judge_retry_preserves_evidence_and_never_repeats_extraction_or_handoff(repo):
    f = await fixture(repo)
    saved = await submit(repo, f)
    prepared = await prepare(repo, f, saved['uuid'])
    failed = await enrollments.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], AsyncMock(side_effect=RuntimeError('synthetic')))
    assert failed['state'] == 'unavailable'
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='retry_capstone_judge') as progress:
        retry = await ReviewAttemptRepository().prepare_retry(CourseOperation(f.learner.user_id, f.package, progress, True),
            failed['attempt_id'], uuid4().hex, actor_user_id=f.learner.user_id, system_config=enrollments.REVIEW_CONFIG)
    assert retry['record']['evidence'] == prepared['record']['evidence']
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        result = await enrollments.evaluate_review(repo, f.learner, f.package, retry['attempt_id'], AsyncMock(side_effect=enrollments.supported_review))
        assert result['state'] == 'evaluated'
        engine.assert_not_called()
    assert await CertificationLearnerDecision.get_motor_collection().count_documents({'prompt_id': 'governance_private_training_handoff'}) == 2


@pytest.mark.parametrize('change', ['copy', 'source', 'answer_binding', 'channel'])
async def test_rehashed_final_review_preserves_original_chain(repo, change):
    f = await fixture(repo)
    saved = await submit(repo, f)
    altered = deepcopy(saved)
    if change == 'copy':
        altered['handoff']['destination_copy']['sha256'] = '0' * 64
    elif change == 'source':
        altered['case']['sources'][0]['sha256'] = '0' * 64
    elif change == 'answer_binding':
        altered['submission']['handoff_sha256'] = '0' * 64
    else:
        altered['submission_channel'] = 'agent_claim'
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': saved['uuid']})
    raw['record_json'], raw['record_sha256'] = encode(altered)
    with pytest.raises(CourseCatalogError):
        GovernanceReviewRepository.decode(raw)
