"""Real contained copy receipts, explicit retry and recovery without repeated work."""
from copy import deepcopy
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.integration import test_certification_output_file_reviews as review_fixtures
from app.models.certification import CertificationLabExecution, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.output_private_handoff import OutputPrivateHandoffRepository, PROMPT_ID
from app.services.certification_versions.runtime import CourseOperation

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = review_fixtures.repo


async def fixture(repo, monkeypatch):
    f = await review_fixtures.fixture(repo, monkeypatch)
    f.review = await review_fixtures.review(repo, f)
    f.handoff_body = {'request_id': uuid4().hex, 'run_id': f.run['run_id'], 'result_sha256': encode(f.run['result'])[1],
        'review_id': f.review['uuid'], 'review_sha256': encode(f.review)[1],
        'artifacts_sha256': f.review['submission']['artifacts_sha256'], 'destination_id': 'private_training_inbox',
        'action': 'attempt', 'consent': 'attempt_approved_private_training_handoff'}
    return f


async def handoff(repo, f, *, service=None, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='private_training_handoff') as progress:
        return await (service or OutputPrivateHandoffRepository()).submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.handoff_body, actor_user_id=actor or f.learner.user_id)


def retry_body(f, failed):
    return {**f.handoff_body, 'request_id': uuid4().hex, 'action': 'retry_failed_handoff',
        'previous_failed_id': failed['uuid'], 'previous_failed_sha256': encode(failed)[1],
        'consent': 'retry_only_failed_private_training_handoff'}


async def test_controlled_failure_then_explicit_private_copy_preserves_exact_bytes_and_once_only_work(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    first_body = deepcopy(f.handoff_body)
    failed = await handoff(repo, f)
    assert failed['status'] == 'failed' and failed['destination_copy'] is None
    assert failed['destination_written'] is False
    assert failed['reason'] == 'controlled_training_rejection_before_write'
    assert await handoff(repo, f) == failed
    f.handoff_body = retry_body(f, failed)
    delivered = await handoff(repo, f)
    assert delivered['status'] == 'delivered' and delivered['destination_written'] is True
    assert delivered['destination_copy'] == f.run['result']['generated_artifacts']
    assert delivered['external_delivery'] is delivered['credit_awarded'] is False
    assert delivered['previous_failed_receipt'] == failed
    assert await handoff(repo, f) == delivered
    f.handoff_body = first_body
    assert await handoff(repo, f) == failed
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': f.run['run_id']})
    assert raw['output_handoff_claimed'] is True and raw['output_handoff_receipt_id'] == delivered['uuid']
    assert len(f.calls) == 2
    assert await CertificationLearnerDecision.get_motor_collection().count_documents({'prompt_id': PROMPT_ID}) == 2
    assert await OutputPrivateHandoffRepository().get('foreign', delivered['uuid']) is None
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0
    await CertificationLabExecution.get_motor_collection().delete_many({})
    await CertificationLearnerDecision.get_motor_collection().delete_one({'uuid': f.review['uuid']})
    assert await OutputPrivateHandoffRepository().get(f.learner.user_id, delivered['uuid']) == delivered


@pytest.mark.parametrize('change', ['actor', 'review_sha256', 'result_sha256', 'artifacts_sha256', 'hold', 'other_request', 'reuse_changed'])
async def test_handoff_rejects_stale_approval_wrong_files_and_repeat_requests(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch)
    expected = 0
    if change.endswith('sha256'):
        f.handoff_body[change] = 'a' * 64
    elif change == 'hold':
        f.review_body.update(request_id=uuid4().hex, choice='hold')
        await review_fixtures.review(repo, f)
    elif change in ('other_request', 'reuse_changed'):
        await handoff(repo, f)
        expected = 1
        if change == 'other_request':
            f.handoff_body['request_id'] = uuid4().hex
        else:
            f.handoff_body['artifacts_sha256'] = 'a' * 64
    with pytest.raises(EnrollmentConflict):
        await handoff(repo, f, actor='foreign' if change == 'actor' else None)
    assert await CertificationLearnerDecision.get_motor_collection().count_documents({'prompt_id': PROMPT_ID}) == expected
    assert len(f.calls) == 2


@pytest.mark.parametrize('change', ['failed_hash', 'failed_id', 'hold', 'duplicate_retry', 'wrong_run'])
async def test_retry_requires_exact_failed_action_and_latest_approval(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch)
    failed = await handoff(repo, f)
    f.handoff_body = retry_body(f, failed)
    expected = 1
    if change == 'failed_hash':
        f.handoff_body['previous_failed_sha256'] = 'a' * 64
    elif change == 'failed_id':
        f.handoff_body['previous_failed_id'] = uuid4().hex
    elif change == 'hold':
        f.review_body.update(request_id=uuid4().hex, choice='hold')
        await review_fixtures.review(repo, f)
    elif change == 'duplicate_retry':
        await handoff(repo, f)
        expected = 2
        f.handoff_body['request_id'] = uuid4().hex
    else:
        f.handoff_body['run_id'] = uuid4().hex
    with pytest.raises(EnrollmentConflict):
        await handoff(repo, f)
    assert await CertificationLearnerDecision.get_motor_collection().count_documents({'prompt_id': PROMPT_ID}) == expected
    assert len(f.calls) == 2


async def test_reapproval_after_failure_hold_allows_only_same_bytes_retry(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    failed = await handoff(repo, f)
    f.review_body.update(request_id=uuid4().hex, choice='hold')
    await review_fixtures.review(repo, f)
    f.review_body.update(request_id=uuid4().hex, choice='approve')
    approved = await review_fixtures.review(repo, f)
    f.handoff_body = retry_body(f, failed)
    f.handoff_body.update(review_id=approved['uuid'], review_sha256=encode(approved)[1])
    saved = await handoff(repo, f)
    assert saved['destination_copy'] == f.run['result']['generated_artifacts']


@pytest.mark.parametrize('phase', ['first_before_insert', 'first_after_insert', 'retry_before_insert', 'retry_after_insert', 'retry_link'])
async def test_ambiguous_write_recovers_original_request_without_duplicate_private_copy(repo, monkeypatch, phase):
    f = await fixture(repo, monkeypatch)
    if phase.startswith('retry'):
        failed = await handoff(repo, f)
        f.handoff_body = retry_body(f, failed)
    collection = CertificationLearnerDecision.get_motor_collection()
    class Interrupted(OutputPrivateHandoffRepository):
        @property
        def records(self):
            async def insert(document):
                if phase.endswith('after_insert'):
                    await collection.insert_one(document)
                raise OSError('Synthetic receipt-write ambiguity')
            return SimpleNamespace(find_one=collection.find_one, insert_one=insert)
    service = Interrupted()
    if phase == 'retry_link':
        service = OutputPrivateHandoffRepository()
        async def interrupt_link(*args):
            raise OSError('Synthetic reply interrupted after destination commit')
        monkeypatch.setattr(service, '_finish_claim', interrupt_link)
    with pytest.raises(OSError):
        await handoff(repo, f, service=service)
    recovered = await handoff(repo, f)
    assert recovered['uuid'] == f.handoff_body['request_id']
    assert recovered['status'] == ('delivered' if phase.startswith('retry') else 'failed')
    assert await handoff(repo, f) == recovered
    assert await collection.count_documents({'prompt_id': PROMPT_ID}) == (2 if phase.startswith('retry') else 1)
    assert len(f.calls) == 2


@pytest.mark.parametrize('change', ['copy', 'failure', 'destination', 'scope', 'credit'])
async def test_rehashed_handoff_cannot_change_copy_destination_or_success_claim(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch)
    failed = await handoff(repo, f)
    f.handoff_body = retry_body(f, failed)
    saved = await handoff(repo, f)
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': saved['uuid']})
    altered = deepcopy(saved)
    if change == 'copy':
        altered['destination_copy']['files'][0]['data_base64'] = 'ZmFrZQ=='
    elif change == 'failure':
        altered['previous_failed_receipt']['destination_written'] = True
    elif change == 'destination':
        altered['destination']['owner_user_id'] = 'foreign'
    elif change == 'scope':
        altered['release_authorization']['submission']['choice'] = 'hold'
    else:
        altered['credit_awarded'] = True
    raw['record_json'], raw['record_sha256'] = encode(altered)
    with pytest.raises(CourseCatalogError):
        OutputPrivateHandoffRepository.decode(raw)
