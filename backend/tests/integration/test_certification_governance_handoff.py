"""Separate current release authority and atomic exact-bytes private handoff recovery."""
from copy import deepcopy
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_governance_memos as memos
from app.models.certification import CertificationLabExecution, CertificationLabInput, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.governance_handoff import GovernanceHandoffRepository
from app.services.certification_versions.governance_release import GovernanceReleaseRepository
from app.services.certification_versions.runtime import CourseOperation

repo = memos.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo):
    f = await memos.fixture(repo)
    f.memo = await memos.submit(repo, f)
    f.release_body = {'request_id': uuid4().hex, 'run_id': f.final['run_id'], 'case_sha256': f.case.digest,
        'memo_id': f.memo['uuid'], 'memo_sha256': encode(f.memo)[1], 'file_sha256': f.memo['file']['sha256'],
        'opened': True, 'choice': 'approve', 'reason': 'I inspected the exact JSON memo, original finding and complete source-correct repair. I own this limited rehearsal and approve only my private inbox; changed inputs require new source checks and appropriate review. No sponsor email, broad sharing or recurring action is authorized.',
        'destination_id': 'private_training_inbox', 'audience': 'enrolled_learner_only',
        'consent': 'save_my_exact_capstone_memo_release_choice'}
    return f


async def release(repo, f, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='release_capstone_memo') as progress:
        return await GovernanceReleaseRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.release_body, actor_user_id=actor or f.learner.user_id)


def handoff_body(f, approval):
    return {'request_id': uuid4().hex, 'run_id': f.final['run_id'], 'case_sha256': f.case.digest,
        'memo_id': f.memo['uuid'], 'memo_sha256': encode(f.memo)[1], 'file_sha256': f.memo['file']['sha256'],
        'release_id': approval['uuid'], 'release_sha256': encode(approval)[1], 'destination_id': 'private_training_inbox',
        'action': 'attempt', 'consent': 'attempt_approved_private_capstone_handoff'}


def retry_body(first):
    return {**first['submission'], 'request_id': uuid4().hex, 'action': 'retry_failed_handoff',
        'previous_failed_id': first['uuid'], 'previous_failed_sha256': encode(first)[1],
        'consent': 'retry_only_failed_private_capstone_handoff'}


async def send(repo, f, body, actor=None, sender=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='private_capstone_handoff') as progress:
        return await (sender or GovernanceHandoffRepository()).submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            body, actor_user_id=actor or f.learner.user_id)


async def test_exact_same_bytes_retry_and_all_prior_evidence_survive_live_workspace_deletion(repo):
    f = await fixture(repo)
    approved = await release(repo, f)
    request = handoff_body(f, approved)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        first = await send(repo, f, request)
        assert first['status'] == 'failed' and first['destination_written'] is False and first['destination_copy'] is None
        second = await send(repo, f, retry_body(first))
        assert second['status'] == 'delivered' and second['destination_copy'] == f.memo['file']
        assert second['previous_failed_receipt'] == first and second['external_delivery'] is False
        await CertificationLabExecution.get_motor_collection().delete_many({})
        await CertificationLabInput.get_motor_collection().delete_many({})
        await CertificationLearnerDecision.get_motor_collection().delete_many({'uuid': {'$nin': [first['uuid'], second['uuid']]}})
        assert await send(repo, f, request) == first
        assert await send(repo, f, second['submission']) == second
        assert await GovernanceHandoffRepository().get('foreign', second['uuid']) is None
        engine.assert_not_called()
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_latest_hold_blocks_delivery_and_old_approval_replay_does_not_restore_authority(repo):
    f = await fixture(repo)
    approved = await release(repo, f)
    original = deepcopy(f.release_body)
    f.release_body.update(request_id=uuid4().hex, choice='hold', opened=False)
    held = await release(repo, f)
    f.release_body = original
    assert await release(repo, f) == approved
    with pytest.raises(EnrollmentConflict):
        await send(repo, f, handoff_body(f, approved))
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': f.memo['uuid']})
    assert raw['release_decision_id'] == held['uuid']


async def test_hold_after_failed_attempt_blocks_retry_until_new_exact_approval(repo):
    f = await fixture(repo)
    approved = await release(repo, f)
    first = await send(repo, f, handoff_body(f, approved))
    f.release_body.update(request_id=uuid4().hex, choice='hold')
    await release(repo, f)
    request = retry_body(first)
    with pytest.raises(EnrollmentConflict):
        await send(repo, f, request)
    f.release_body.update(request_id=uuid4().hex, choice='approve')
    reapproved = await release(repo, f)
    request.update(release_id=reapproved['uuid'], release_sha256=encode(reapproved)[1])
    delivered = await send(repo, f, request)
    assert delivered['destination_copy'] == f.memo['file']
    assert await send(repo, f, first['submission']) == first
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': f.memo['uuid']})
    assert raw['governance_handoff_claimed'] is True and raw['governance_handoff_receipt_id'] == delivered['uuid']
    f.release_body.update(request_id=uuid4().hex, choice='hold')
    with pytest.raises(EnrollmentConflict):
        await release(repo, f)


@pytest.mark.parametrize('change', ['actor', 'file', 'memo', 'release', 'destination', 'previous', 'repeated_action'])
async def test_handoff_rejects_other_bytes_authority_or_duplicate_action(repo, change):
    f = await fixture(repo)
    approved = await release(repo, f)
    request = handoff_body(f, approved)
    if change in ('file', 'memo', 'release'):
        request[change + '_sha256'] = '0' * 64
    elif change == 'destination':
        request['destination_id'] = 'sponsor_email'
    elif change == 'previous':
        request.update(action='retry_failed_handoff', previous_failed_id=uuid4().hex, previous_failed_sha256='0' * 64,
            consent='retry_only_failed_private_capstone_handoff')
    elif change == 'repeated_action':
        await send(repo, f, request)
        request['request_id'] = uuid4().hex
    with pytest.raises(ValueError):
        await send(repo, f, request, actor='foreign' if change == 'actor' else None)


@pytest.mark.parametrize('change', ['actor', 'not_opened', 'file', 'audience', 'blank'])
async def test_release_requires_owned_opened_exact_memo_and_learner_reason(repo, change):
    f = await fixture(repo)
    if change == 'not_opened':
        f.release_body['opened'] = False
    elif change == 'file':
        f.release_body['file_sha256'] = '0' * 64
    elif change == 'audience':
        f.release_body['audience'] = 'everyone'
    elif change == 'blank':
        f.release_body['reason'] = ' ' * 40
    with pytest.raises(ValueError):
        await release(repo, f, actor='foreign' if change == 'actor' else None)


@pytest.mark.parametrize('change', ['copy', 'destination', 'failure', 'authority'])
async def test_rehashed_handoff_cannot_invent_delivery_or_replace_the_failed_receipt(repo, change):
    f = await fixture(repo)
    approved = await release(repo, f)
    first = await send(repo, f, handoff_body(f, approved))
    delivered = await send(repo, f, retry_body(first))
    altered = deepcopy(delivered)
    if change == 'copy':
        altered['destination_copy']['content_base64'] = 'e30='
    elif change == 'destination':
        altered['destination']['owner_user_id'] = 'foreign'
    elif change == 'failure':
        altered['previous_failed_receipt']['destination_written'] = True
    else:
        altered['external_delivery'] = True
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': delivered['uuid']})
    raw['record_json'], raw['record_sha256'] = encode(altered)
    with pytest.raises(CourseCatalogError):
        GovernanceHandoffRepository.decode(raw)


async def test_lost_receipt_reply_recovers_same_saved_copy_without_repeat_dispatch(repo):
    f = await fixture(repo)
    approved = await release(repo, f)
    first = await send(repo, f, handoff_body(f, approved))
    request = retry_body(first)
    class LostReply(GovernanceHandoffRepository):
        async def after_save(self, operation, saved, *, replay):
            await super().after_save(operation, saved, replay=replay)
            raise OSError('Synthetic reply lost after destination copy committed')
    with pytest.raises(OSError):
        await send(repo, f, request, sender=LostReply())
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        delivered = await send(repo, f, request)
        assert delivered['status'] == 'delivered' and delivered['destination_copy'] == f.memo['file']
        engine.assert_not_called()
    assert await CertificationLearnerDecision.get_motor_collection().count_documents({'prompt_id': 'governance_private_training_handoff'}) == 2
