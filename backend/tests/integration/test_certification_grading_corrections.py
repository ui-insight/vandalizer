"""GRADE-11: a supported grading correction regrades as a linked attempt, never an edit."""
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.grading_corrections import GradingCorrections
from app.services.certification_versions.review_attempts import ReviewAttemptRepository
from app.services.certification_versions.review_delivery import ReviewDelivery
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
ADMIN = 'course-admin'


async def unclear_review(name, config, payload):
    data = json.loads(payload)
    return {'outcomes': [{'outcome_id': item['id'], 'verdict': 'unclear',
        'explanation': 'Synthetic defective grading: the reviewer could not match a quoted span.',
        'revision_instruction': 'Explain the method choice against each assigned situation.', 'citations': []}
        for item in data['requirements']]}


async def graded(repo):
    learner, package, _, body = await base.process_design_fixture(repo)
    saved = await base.save_process(repo, learner, package, body)
    prepared = await base.prepare_process_review(repo, learner, package, saved['uuid'])
    reviewed = await base.evaluate_review(repo, learner, package, prepared['attempt_id'], AsyncMock(side_effect=unclear_review))
    assert reviewed['state'] == 'evaluated' and reviewed['result']['assessment']['status'] == 'revision_required'
    return SimpleNamespace(learner=learner, package=package, parent=reviewed)


def request(f, **changes):
    return {'request_id': uuid4().hex, 'parent_attempt_id': f.parent['attempt_id'],
            'parent_result_sha256': encode(f.parent['result'])[1],
            'reason': 'The reviewer rejected verbatim quotes from JSON evidence; fixed in the quote matcher.',
            'reference': 'commit 15b7f9a2', **changes}


async def test_correction_regrades_as_a_linked_attempt_and_keeps_the_original(repo):
    f = await graded(repo)
    corrections = GradingCorrections(repo)
    judge = AsyncMock(side_effect=base.supported_review)
    body = request(f)
    view = await corrections.submit(ADMIN, f.learner.user_id, f.learner.uuid, body, base.REVIEW_CONFIG, call_model=judge)
    assert view['state'] == 'evaluated' and view['status'] == 'requirements_supported'
    assert (view['reason'], view['reference'], view['actor_user_id']) == (body['reason'], 'commit 15b7f9a2', ADMIN)
    attempts = ReviewAttemptRepository()
    child = await attempts.get(f.learner.user_id, view['attempt_id'])
    assert child['record']['parent_attempt_id'] == f.parent['attempt_id']
    assert child['record']['evidence'] == f.parent['record']['evidence']
    assert child['record']['grading_correction']['parent_result_sha256'] == encode(f.parent['result'])[1]
    # The original result is untouched and still selectable.
    assert await attempts.get(f.learner.user_id, f.parent['attempt_id']) == f.parent
    learner_view = await ReviewDelivery(repo).get(f.learner.user_id, f.learner.uuid, view['attempt_id'])
    assert learner_view['grading_correction'] == {'reason': body['reason'], 'reference': 'commit 15b7f9a2'}
    assert ADMIN not in json.dumps(learner_view)
    assert 'grading_correction' not in await ReviewDelivery(repo).get(f.learner.user_id, f.learner.uuid, f.parent['attempt_id'])
    review = await corrections.review(f.learner.user_id, f.learner.uuid, f.parent['attempt_id'])
    assert [item['attempt_id'] for item in review['corrections']] == [view['attempt_id']]
    # Replaying the same request returns the same regrade without another model call.
    assert await corrections.submit(ADMIN, f.learner.user_id, f.learner.uuid, body, base.REVIEW_CONFIG, call_model=judge) == view
    assert judge.await_count == 1
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['stale_result', 'foreign_enrollment', 'unknown_parent', 'short_reason'])
async def test_correction_requires_the_reviewed_result_and_a_reason(repo, change):
    f = await graded(repo)
    body, enrollment = request(f), f.learner.uuid
    if change == 'stale_result':
        body['parent_result_sha256'] = '0' * 64
    elif change == 'foreign_enrollment':
        enrollment = uuid4().hex
    elif change == 'unknown_parent':
        body['parent_attempt_id'] = uuid4().hex
    else:
        body['reason'] = 'Regrade please'
    judge = AsyncMock(side_effect=base.supported_review)
    reasons = {'stale_result': 'preserve the original evidence', 'foreign_enrollment': 'unavailable for that enrollment',
               'unknown_parent': 'unavailable for that enrollment', 'short_reason': 'at least 20 characters'}
    with pytest.raises(ValueError, match=reasons[change]):
        await GradingCorrections(repo).submit(ADMIN, f.learner.user_id, enrollment, body, base.REVIEW_CONFIG, call_model=judge)
    judge.assert_not_awaited()
    assert await ReviewAttemptRepository().records.count_documents({'parent_attempt_id': f.parent['attempt_id']}) == 0


async def test_a_technical_failure_takes_a_retry_not_a_correction(repo):
    learner, package, _, body = await base.process_design_fixture(repo)
    saved = await base.save_process(repo, learner, package, body)
    prepared = await base.prepare_process_review(repo, learner, package, saved['uuid'])
    failed = await base.evaluate_review(repo, learner, package, prepared['attempt_id'], AsyncMock(side_effect=RuntimeError('outage')))
    assert failed['state'] == 'unavailable'
    f = SimpleNamespace(learner=learner, package=package, parent=failed)
    with pytest.raises(EnrollmentConflict, match='saved graded assessment'):
        await GradingCorrections(repo).submit(ADMIN, learner.user_id, learner.uuid, request(f), base.REVIEW_CONFIG)


async def test_only_full_admins_apply_corrections():
    from app.routers import admin
    payload = admin.CertificationGradingCorrectionRequest(request_id=uuid4().hex, parent_attempt_id=uuid4().hex,
        parent_result_sha256='a' * 64, reason='A reviewed grading defect affected this result.', reference='issue 1')
    for user in (SimpleNamespace(user_id='ordinary', is_admin=False, is_staff=False),
                 SimpleNamespace(user_id='staff', is_admin=False, is_staff=True)):
        with pytest.raises(HTTPException) as denied:
            await admin.apply_certification_grading_correction('learner', 'enrollment', payload, user=user)
        assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as denied:
        await admin.review_certification_grading_correction('learner', 'enrollment', uuid4().hex,
            user=SimpleNamespace(user_id='ordinary', is_admin=False, is_staff=False))
    assert denied.value.status_code == 403


async def test_an_applied_correction_is_in_the_admin_audit_trail_without_learner_work(repo, monkeypatch):
    from beanie import init_beanie
    from app.database import ALL_MODELS
    from app.models.audit_log import AdminAuditLog
    from app.models.search_set import SearchSet
    from app.routers import admin
    from app.services.certification_versions import practical_preparation
    await init_beanie(database=SearchSet.get_motor_collection().database, document_models=ALL_MODELS)
    f = await graded(repo)
    monkeypatch.setattr('app.services.certification_versions.grading_corrections.EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(practical_preparation, 'configured_runtime', AsyncMock(return_value=base.REVIEW_CONFIG))
    monkeypatch.setattr('app.services.certification_versions.automatic_review._call_model', AsyncMock(side_effect=base.supported_review))
    body = request(f)
    result = await admin.apply_certification_grading_correction(f.learner.user_id, f.learner.uuid,
        admin.CertificationGradingCorrectionRequest(**body), user=SimpleNamespace(user_id='root-admin', is_admin=True, is_staff=False))
    assert result['status'] == 'requirements_supported'
    [entry] = await AdminAuditLog.find({'action': 'certification.grading_correction'}).to_list()
    assert entry.user_id == 'root-admin'
    assert entry.payload['parent_attempt_id'] == f.parent['attempt_id'] and entry.payload['correction_attempt_id'] == result['attempt_id']
    assert entry.payload['reason'] == body['reason'] and entry.payload['credit_effect'] == 'none'
    # References and the stated reason only; no evidence, answers or verdict text.
    assert set(entry.payload) == {'user_id', 'enrollment_id', 'parent_attempt_id', 'parent_result_sha256',
                                  'correction_attempt_id', 'reason', 'reference', 'credit_effect'}
