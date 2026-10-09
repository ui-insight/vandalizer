"""Internal optional selection commits on isolated synthetic course packages."""
import asyncio
from copy import deepcopy
import datetime
from uuid import uuid4

from bson import ObjectId
import pytest

from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.credentials import CredentialRepository
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.transition_preview import TransitionPreview
from app.services.certification_versions.upgrade_activation import UpgradeActivationRepository
from app.services.certification_versions.upgrade_comparison import UpgradeUnavailable
from app.services.certification_versions.upgrade_targets import target_identity
from app.services.certification_versions.writes import save_progress
from tests.integration import test_certification_upgrade_decisions as choices

repo = choices.repo
pytestmark = choices.pytestmark


async def setup(repo, *, certified=False, preserve_existing=False):
    source, target, choice, decisions = await choices.setup(repo)
    progress = await repo.read_progress(source.user_id, source.uuid)
    if not preserve_existing:
        progress.total_xp = 125
        progress.modules = {'foundations': {'completed': True, 'stars': 2, 'xp_earned': 125,
            'completed_at': '2026-09-01', 'self_assessment': {'original': 'retained reflection'},
            'provisioned_docs': ['original-lab-document']}}
        progress.lab_folder_id = 'original-course-folder'
        progress.learning_position = {'module_id': 'foundations', 'lesson_id': 'original-place'}
        if certified:
            progress.certified = True
            progress.certified_at = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
        await progress.save()
    credential = None
    if certified:
        credential = CredentialRepository.prepare(progress, repo.catalog.load(source.course_version), 'Original name', legacy=True)
        await CredentialRepository().persist(credential)
    preview = await TransitionPreview(repo).inspect(source.user_id, source.uuid, target)
    await decisions.accept(source.user_id, {**choice, 'preview_sha256': preview['preview_sha256']})
    request = {'request_id': uuid4().hex, 'decision_id': choice['request_id'],
        'consent': 'activate_optional_upgrade_preserving_original_work_without_credit_transfer'}
    return source, request, UpgradeActivationRepository(repo), credential


def earned(raw):
    raw = deepcopy(raw)
    raw.pop('_certification_write_fence', None)
    return raw


@pytest.mark.parametrize('certified', [False, True])
async def test_selection_changes_once_and_preserves_original_credit_credential_and_workspace(repo, certified):
    source, request, activations, credential = await setup(repo, certified=certified)
    before = await repo.progress.find_one({'_id': ObjectId(source.progress_id)})
    source_enrollment = await repo.enrollments.find_one({'uuid': source.uuid})
    # These owned workspace rows represent an independent in-flight worker.
    # The selection commit has no write path into them and no dispatch hook.
    documents = repo.progress.database['document']
    jobs = repo.progress.database['workflow_results']
    await documents.insert_one({'uuid': 'original-lab-document', 'user_id': source.user_id,
        'folder': 'original-course-folder', 'processing': True, 'task_id': 'original-worker'})
    await jobs.insert_one({'session_id': 'independent-workspace-job', 'status': 'running', 'source_document_id': 'original-lab-document'})
    workspace = [await documents.find({}).to_list(None), await jobs.find({}).to_list(None)]
    result = await activations.activate(source.user_id, request)
    assert result['status'] == 'applied' and result['credit_transferred'] is False
    assert result['source_history_preserved'] is True
    assert (await repo.current(source.user_id)).uuid == result['target_enrollment_id']
    assert (await repo.selections.find_one({'user_id': source.user_id}))['revision'] == 1
    assert earned(await repo.progress.find_one({'_id': ObjectId(source.progress_id)})) == earned(before)
    assert await repo.enrollments.find_one({'uuid': source.uuid}) == source_enrollment
    assert await CredentialRepository().for_enrollment(source.user_id, source.uuid) == credential
    assert workspace == [await documents.find({}).to_list(None), await jobs.find({}).to_list(None)]
    # The independent worker can finish against the same original identities.
    await documents.update_one({'task_id': 'original-worker'}, {'$set': {'processing': False}})
    await jobs.update_one({'session_id': 'independent-workspace-job'}, {'$set': {'status': 'completed'}})
    target = await repo.read_progress(source.user_id, result['target_enrollment_id'])
    assert target.total_xp == 0 and target.modules == {} and target.lab_folder_id is None
    with pytest.raises(EnrollmentConflict):
        async with repo.write_boundary(source.user_id, source.uuid):
            pytest.fail('Original source must be readable history until explicitly selected again')
    async with repo.write_boundary(source.user_id, target.enrollment_id) as writable:
        writable.position_revision = 1
        await save_progress(writable)
    assert await activations.activate(source.user_id, request) == result
    assert (await repo.read_progress(source.user_id, target.enrollment_id)).position_revision == 1
    assert await activations.records.count_documents({}) == 1


@pytest.mark.parametrize('phase', ['intent_insert', 'before_selection', 'after_selection', 'receipt_write', 'pending_clear'])
async def test_each_interruption_resumes_original_request_without_reset_or_duplicate_selection(repo, monkeypatch, phase):
    source, request, activations, _ = await setup(repo)
    if phase == 'intent_insert':
        original = activations.records.insert_one
        async def fail(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError('Synthetic interrupted switch')
        owner, method = activations.records, 'insert_one'
    elif phase in ('before_selection', 'after_selection'):
        original = repo.selections.find_one_and_update
        async def fail(query, update, **kwargs):
            if 'last_transition' in update.get('$set', {}):
                if phase == 'after_selection':
                    await original(query, update, **kwargs)
                raise RuntimeError('Synthetic interrupted switch')
            return await original(query, update, **kwargs)
        owner, method = repo.selections, 'find_one_and_update'
    elif phase == 'receipt_write':
        original = activations.records.update_one
        async def fail(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError('Synthetic interrupted switch')
        owner, method = activations.records, 'update_one'
    else:
        async def fail(*args, **kwargs):
            raise RuntimeError('Synthetic interrupted switch')
        owner, method = activations, 'clear_pending'
    with monkeypatch.context() as patch:
        patch.setattr(owner, method, fail)
        with pytest.raises(RuntimeError, match='interrupted switch'):
            await activations.activate(source.user_id, request)
    current = await repo.current(source.user_id)
    if current.uuid != source.uuid:
        with pytest.raises(EnrollmentConflict, match='switch'):
            async with repo.write_boundary(source.user_id, current.uuid):
                pytest.fail('The target must wait for the original durable receipt')
    result = await activations.activate(source.user_id, request)
    assert result['target_enrollment_id'] == target_identity(request['decision_id'])[0]
    assert await activations.activate(source.user_id, request) == result
    assert await repo.enrollments.count_documents({'user_id': source.user_id}) == 2
    assert await repo.progress.count_documents({'user_id': source.user_id}) == 2
    assert await activations.records.count_documents({}) == 1
    selected = await repo.selections.find_one({'user_id': source.user_id})
    assert selected['revision'] == 1 and not selected.get('pending_transition_id')
    assert selected['in_flight_writes'] == 0


async def test_competing_switch_requests_do_not_overwrite_the_winning_selection(repo):
    source, request, activations, _ = await setup(repo)
    results = await asyncio.gather(*(activations.activate(source.user_id, request) for _ in range(5)), return_exceptions=True)
    successes = [result for result in results if isinstance(result, dict)]
    assert successes and all(result == successes[0] for result in successes)
    assert all(isinstance(result, (dict, EnrollmentConflict)) for result in results)
    assert await activations.activate(source.user_id, request) == successes[0]
    assert (await repo.selections.find_one({'user_id': source.user_id}))['revision'] == 1


@pytest.mark.parametrize('change', ['target_work', 'withdrawn_offer', 'source_fence', 'selection_revision'])
async def test_changed_final_commit_conditions_never_select_or_reset_a_target(repo, monkeypatch, change):
    source, request, activations, _ = await setup(repo)
    original = activations.commit
    async def changed(raw, lease, package):
        if change == 'target_work':
            _, progress_id = target_identity(request['decision_id'])
            await repo.progress.update_one({'_id': ObjectId(progress_id)}, {'$set': {'total_xp': 75}})
        elif change == 'withdrawn_offer':
            choices.fixtures.set_upgrade_offer(repo, source.course_version, package.manifest.release_id, enabled=False)
        elif change == 'source_fence':
            await repo.progress.update_one({'_id': ObjectId(source.progress_id)}, {'$set': {'_certification_write_fence': 'revoked'}})
        else:
            await repo.selections.update_one({'user_id': source.user_id}, {'$inc': {'revision': 1}})
        return await original(raw, lease, package)
    monkeypatch.setattr(activations, 'commit', changed)
    with pytest.raises((EnrollmentConflict, CourseCatalogError, UpgradeUnavailable)):
        await activations.activate(source.user_id, request)
    assert (await repo.current(source.user_id)).uuid == source.uuid
    if change == 'target_work':
        assert (await repo.read_progress(source.user_id, target_identity(request['decision_id'])[0])).total_xp == 75


async def test_foreign_or_rebound_request_cannot_recover_or_reactivate_a_switch(repo):
    source, request, activations, _ = await setup(repo)
    result = await activations.activate(source.user_id, request)
    with pytest.raises(EnrollmentConflict):
        await activations.activate('foreign-owner', request)
    with pytest.raises(EnrollmentConflict):
        await activations.activate(source.user_id, {**request, 'decision_id': uuid4().hex})
    assert await activations.activate(source.user_id, request) == result


async def test_original_source_fence_is_revoked_before_target_becomes_visible(repo, monkeypatch):
    source, request, activations, _ = await setup(repo)
    original = repo.selections.find_one_and_update
    async def check(query, update, **kwargs):
        if 'last_transition' in update.get('$set', {}):
            progress = await repo.read_progress(source.user_id, source.uuid)
            progress.total_xp = 9999
            with pytest.raises(EnrollmentConflict, match='no longer owns'):
                await save_progress(progress)
        return await original(query, update, **kwargs)
    monkeypatch.setattr(repo.selections, 'find_one_and_update', check)
    await activations.activate(source.user_id, request)
    assert (await repo.read_progress(source.user_id, source.uuid)).total_xp == 125


async def completed_outcome_choice(repo, monkeypatch):
    import hashlib
    import json
    import shutil
    from tests.integration import test_certification_outcome_completion as completion
    from app.services.certification_versions.upgrade_decisions import UpgradeDecisionRepository
    f, client, _, body, _, judge = await completion.setup(repo, monkeypatch, single_module=True)
    async with client:
        response = await client.post('/certification/modules/validation_qa/complete',
            params={'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex}, json=body)
        assert response.status_code == 200, response.text
    target_version = 'synthetic-next-outcome-course'
    target = repo.catalog.root / target_version
    shutil.copytree(repo.catalog.root / f.package.manifest.release_id, target)
    manifest = json.loads((target / 'manifest.json').read_text())
    manifest['release_id'] = target_version
    (target / 'manifest.json').write_text(json.dumps(manifest))
    path = repo.catalog.root / 'registry.json'
    registry = json.loads(path.read_text())
    registry['releases'][target_version] = {'state': 'published', 'supported_for_existing': True,
        'manifest_sha256': hashlib.sha256((target / 'manifest.json').read_bytes()).hexdigest()}
    path.write_text(json.dumps(registry))
    choices.fixtures.set_upgrade_offer(repo, f.learner.course_version, target_version)
    preview = await TransitionPreview(repo).inspect(f.learner.user_id, f.learner.uuid, target_version)
    choice_id = uuid4().hex
    await UpgradeDecisionRepository(repo).accept(f.learner.user_id, {'request_id': choice_id,
        'source_enrollment_id': f.learner.uuid, 'target_version': target_version, 'preview_sha256': preview['preview_sha256'],
        'consent': 'preserve_original_work_and_require_all_new_outcomes'})
    return f, choice_id, judge


async def test_completed_outcome_course_preserves_every_saved_receipt_and_issuance_through_switch(repo, monkeypatch):
    from app.services.certification_versions.transition_records import TransitionRecordReconciliation
    f, choice_id, judge = await completed_outcome_choice(repo, monkeypatch)
    before = await TransitionRecordReconciliation(repo).inventory(f.learner.user_id, f.learner.uuid)
    credential = await CredentialRepository().for_enrollment(f.learner.user_id, f.learner.uuid)
    original = await repo.progress.find_one({'_id': ObjectId(f.learner.progress_id)})
    result = await UpgradeActivationRepository(repo).activate(f.learner.user_id, {'request_id': uuid4().hex,
        'decision_id': choice_id, 'consent': 'activate_optional_upgrade_preserving_original_work_without_credit_transfer'})
    assert await TransitionRecordReconciliation(repo).inventory(f.learner.user_id, f.learner.uuid) == before
    assert await CredentialRepository().for_enrollment(f.learner.user_id, f.learner.uuid) == credential
    assert earned(await repo.progress.find_one({'_id': ObjectId(f.learner.progress_id)})) == earned(original)
    selected = await repo.read_progress(f.learner.user_id, result['target_enrollment_id'])
    assert selected.total_xp == 0 and selected.modules == {} and not selected.certified
    assert len(await CredentialRepository().list(f.learner.user_id)) == 1
    judge.assert_awaited_once()


async def test_damaged_committed_receipt_cannot_unlock_new_course_writes(repo, monkeypatch):
    from app.services.certification_versions.attempts import encode
    source, request, activations, _ = await setup(repo)
    async def interrupted(*args):
        raise RuntimeError('Synthetic receipt not yet confirmed')
    with monkeypatch.context() as patch:
        patch.setattr(activations, 'finalize', interrupted)
        with pytest.raises(RuntimeError):
            await activations.activate(source.user_id, request)
    selection = await repo.selections.find_one({'user_id': source.user_id})
    result = selection['last_transition']
    result['credit_transferred'] = True
    result['receipt_sha256'] = encode({key: value for key, value in result.items() if key != 'receipt_sha256'})[1]
    await repo.selections.update_one({'user_id': source.user_id}, {'$set': {'last_transition': result}})
    with pytest.raises(CourseCatalogError):
        await activations.activate(source.user_id, request)
    with pytest.raises(EnrollmentConflict):
        async with repo.write_boundary(source.user_id, selection['active_enrollment_id']):
            pytest.fail('Corruption must not clear the unconfirmed switch marker')


async def test_explicit_activation_consent_cannot_be_replaced_by_a_preview_or_extra_credit_claim(repo):
    from pydantic import ValidationError
    source, request, activations, _ = await setup(repo)
    for invalid in ({**request, 'consent': 'preserve_original_work_and_require_all_new_outcomes'},
                    {**request, 'transfer_xp': 125}):
        with pytest.raises(ValidationError):
            await activations.activate(source.user_id, invalid)
    assert await activations.records.count_documents({}) == 0
    assert (await repo.current(source.user_id)).uuid == source.uuid
