"""Exact file inspection and release choices remain learner-owned and immutable."""
from copy import deepcopy
import os
from uuid import uuid4

from pydantic import ValidationError
import pytest

from tests.integration import test_certification_output_workflow_execution as execution_fixtures
from app.models.certification import CertificationLabExecution, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.output_file_reviews import OutputFileReviewRepository
from app.services.certification_versions.runtime import CourseOperation

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = execution_fixtures.repo


async def fixture(repo, monkeypatch, *, invalid=False):
    f = await execution_fixtures.fixture(repo, monkeypatch)
    if invalid:
        from app.services import workflow_engine
        monkeypatch.setattr(workflow_engine, 'format_model', lambda *args, **kwargs: ('Synthetic', 'Prose instead of CSV'))
    f.run = await execution_fixtures.execute(repo, f)
    assert f.run['state'] == 'completed'
    artifacts = f.run['result']['generated_artifacts']
    f.review_body = {'request_id': uuid4().hex, 'run_id': f.run['run_id'],
        'result_sha256': encode(f.run['result'])[1], 'case_sha256': f.case.digest, 'artifacts_sha256': encode(artifacts)[1],
        'file_inspections': [{'sha256': file['sha256'], 'opened': True, 'judgment': 'usable',
            'observations': 'Opened this exact generated file and compared its values with the assigned report.'} for file in artifacts['files']],
        'bundle_sha256': artifacts['download']['sha256'], 'bundle_opened': True,
        'answers': {'artifact_review': 'Both files distinguish USD 135500 Year 2 from USD 287500 cumulative expenditure.',
                    'release_decision': 'Approve only these exact files for my private training inbox; no broader sharing.'},
        'choice': 'approve', 'destination_id': 'private_training_inbox', 'audience': 'enrolled_learner_only',
        'data_scope': 'approved_generated_files_only', 'consent': 'save_exact_output_inspection_and_release_choice'}
    return f


async def review(repo, f, *, actor=None, service=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='inspect_generated_output') as progress:
        return await (service or OutputFileReviewRepository()).submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.review_body, actor_user_id=actor or f.learner.user_id)


async def test_exact_inspection_links_release_choice_without_delivery_or_credit_and_survives_deletion(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    saved = await review(repo, f)
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': f.run['run_id']})
    assert raw['release_decision_id'] == saved['uuid'] and raw['release_decision_sha256'] == encode(saved)[1]
    assert saved['credit_awarded'] is saved['module_completion_eligible'] is saved['delivery_confirmed'] is False
    assert await review(repo, f) == saved
    assert len(f.calls) == 2
    await CertificationLabExecution.get_motor_collection().delete_many({})
    await f.document.delete()
    await f.workflow.delete()
    assert await review(repo, f) == saved
    assert await OutputFileReviewRepository().get('foreign', saved['uuid']) is None
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_newer_hold_cannot_be_replaced_by_replayed_approval(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    original_body = deepcopy(f.review_body)
    first = await review(repo, f)
    f.review_body.update(request_id=uuid4().hex, choice='hold', bundle_opened=False)
    f.review_body['file_inspections'][0].update(opened=False, judgment='unresolved')
    held = await review(repo, f)
    assert held['previous_release_decision_id'] == first['uuid']
    f.review_body = original_body
    assert await review(repo, f) == first
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': f.run['run_id']})
    assert raw['release_decision_id'] == held['uuid']


async def test_invalid_csv_can_be_held_but_cannot_be_approved(repo, monkeypatch):
    f = await fixture(repo, monkeypatch, invalid=True)
    with pytest.raises(EnrollmentConflict, match='Repair'):
        await review(repo, f)
    f.review_body['choice'] = 'hold'
    f.review_body['file_inspections'][1]['judgment'] = 'needs_repair'
    saved = await review(repo, f)
    assert saved['submission']['choice'] == 'hold'


@pytest.mark.parametrize('change', ['result', 'case', 'artifacts', 'file', 'bundle', 'unopened', 'unusable',
    'audience', 'destination', 'missing_file', 'duplicate_file', 'actor', 'blank', 'claimed', 'reused_request'])
async def test_changed_files_or_unsupported_approval_cannot_create_a_new_review(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch)
    initial = await CertificationLearnerDecision.get_motor_collection().count_documents({})
    if change in ('result', 'case', 'artifacts', 'bundle'):
        f.review_body[change + '_sha256'] = 'a' * 64
    elif change == 'file':
        f.review_body['file_inspections'][0]['sha256'] = 'a' * 64
    elif change == 'unopened':
        f.review_body['file_inspections'][0]['opened'] = False
    elif change == 'unusable':
        f.review_body['file_inspections'][0]['judgment'] = 'needs_repair'
    elif change == 'audience':
        f.review_body['audience'] = 'all_staff'
    elif change == 'destination':
        f.review_body['destination_id'] = 'external_email'
    elif change == 'missing_file':
        f.review_body['file_inspections'].pop()
    elif change == 'duplicate_file':
        f.review_body['file_inspections'][1] = deepcopy(f.review_body['file_inspections'][0])
    elif change == 'blank':
        f.review_body['answers']['release_decision'] = ' ' * 12
    elif change == 'claimed':
        await CertificationLabExecution.get_motor_collection().update_one({'uuid': f.run['run_id']}, {'$set': {'output_handoff_claimed': True}})
    elif change == 'reused_request':
        await review(repo, f)
        initial += 1
        f.review_body['answers']['artifact_review'] = 'Changed answers cannot replace the original request.'
    with pytest.raises((EnrollmentConflict, ValidationError)):
        await review(repo, f, actor='foreign' if change == 'actor' else None)
    assert await CertificationLearnerDecision.get_motor_collection().count_documents({}) == initial
    assert len(f.calls) == 2


async def test_lost_link_is_finished_with_same_saved_review_and_no_duplicate_record(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    service = OutputFileReviewRepository()
    async def interrupted(*args, **kwargs):
        raise OSError('Synthetic link outage')
    monkeypatch.setattr(service, '_link', interrupted)
    with pytest.raises(OSError):
        await review(repo, f, service=service)
    saved = await review(repo, f)
    assert saved['uuid'] == f.review_body['request_id']
    assert await CertificationLearnerDecision.get_motor_collection().count_documents({'prompt_id': saved['prompt_id']}) == 1
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': f.run['run_id']})
    assert raw['release_decision_id'] == saved['uuid']


@pytest.mark.parametrize('change', ['file', 'authority', 'actor', 'embedded_result'])
async def test_rehashed_inspection_cannot_change_bound_files_or_authority(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch)
    saved = await review(repo, f)
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': saved['uuid']})
    altered = deepcopy(saved)
    if change == 'file':
        altered['submission']['file_inspections'][0]['sha256'] = 'a' * 64
        altered['request_sha256'] = raw['request_sha256'] = encode(altered['submission'])[1]
    elif change == 'authority':
        altered['delivery_confirmed'] = True
    elif change == 'actor':
        altered['user_id'] = raw['user_id'] = 'foreign'
    else:
        altered['execution']['result_sha256'] = 'a' * 64
    raw['record_json'], raw['record_sha256'] = encode(altered)
    with pytest.raises(CourseCatalogError):
        OutputFileReviewRepository.decode(raw)
