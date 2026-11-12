"""Rollback/resume cohort rehearsal; no course work or credentials are reset."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from bson import ObjectId
import pytest

from app.services.certification_versions.credentials import CredentialRepository
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.saved_course_selection import SavedCourseSelectionRepository
from app.services.certification_versions.writes import save_progress
from tests.integration import test_certification_upgrade_activation as activation

repo = activation.repo
pytestmark = activation.pytestmark


async def setup(repo, *, earned=False, legacy_unknown=False):
    source, request, activations, original_credential = await activation.setup(repo, certified=True, preserve_existing=legacy_unknown)
    selected = await activations.activate(source.user_id, request)
    target_id = selected['target_enrollment_id']
    async with repo.write_boundary(source.user_id, target_id) as progress:
        package = repo.catalog.load(progress.course_version)
        progress.learning_position = {'module_id': package.manifest.modules[0].id,
            'lesson_id': package.manifest.modules[0].lesson_ids[0]}
        progress.position_revision = 3
        if earned:
            # Synthetic complete-cohort evidence from the credential integrity
            # fixture. This tests preservation, not real full-course grading.
            from tests.test_certification_outcome_credentials import complete_fixture
            original_id = progress.id
            _, progress = complete_fixture(SimpleNamespace(package=package, progress=progress))
            progress.id = original_id
            progress.total_xp = sum(module.base_xp for module in package.manifest.modules)
            for module in package.manifest.modules:
                progress.modules[module.id]['xp_earned'] = module.base_xp
            await CredentialRepository().persist(CredentialRepository.prepare(progress, package, 'New earned name'))
        await save_progress(progress)
    service = SavedCourseSelectionRepository(repo)
    preview = await service.preview(source.user_id, request['request_id'], 'return_to_original_course')
    body = {'request_id': uuid4().hex, 'activation_id': request['request_id'], 'action': 'return_to_original_course',
            'preview_sha256': preview['preview_sha256'], 'consent': 'select_saved_course_preserving_both_histories_and_credit'}
    return source, target_id, request, body, service, original_credential


async def histories(repo, user_id):
    progress = await repo.progress.find({'user_id': user_id}).sort('_id', 1).to_list(None)
    return {'progress': [activation.earned(row) for row in progress],
            'enrollments': await repo.enrollments.find({'user_id': user_id}).sort('_id', 1).to_list(None),
            'credentials': [value.model_dump(mode='json') for value in await CredentialRepository().list(user_id)]}


@pytest.mark.parametrize('earned', [False, True])
async def test_return_and_resume_keep_both_original_histories_and_new_credentials(repo, earned):
    source, target_id, original, body, service, credential = await setup(repo, earned=earned)
    before = deepcopy(await histories(repo, source.user_id))
    assert len(before['credentials']) == (2 if earned else 1)
    result = await service.select(source.user_id, body)
    assert result['target_enrollment_id'] == source.uuid and result['both_histories_preserved'] is True
    assert result['credit_transferred'] is False and result['revision'] == 2
    assert (await repo.current(source.user_id)).uuid == source.uuid
    assert await histories(repo, source.user_id) == before
    assert await service.select(source.user_id, body) == result
    preview = await service.preview(source.user_id, original['request_id'], 'resume_upgraded_course')
    resumed = await service.select(source.user_id, {**body, 'request_id': uuid4().hex, 'action': 'resume_upgraded_course',
        'preview_sha256': preview['preview_sha256']})
    assert resumed['target_enrollment_id'] == target_id and resumed['revision'] == 3
    assert await histories(repo, source.user_id) == before
    assert await CredentialRepository().for_enrollment(source.user_id, source.uuid) == credential
    # Historical replay confirms its original result; it never selects again.
    assert await service.select(source.user_id, body) == result
    assert (await repo.current(source.user_id)).uuid == target_id
    assert await repo.enrollments.count_documents({'user_id': source.user_id}) == 2
    assert await service.records.count_documents({'user_id': source.user_id}) == 2


async def test_preview_is_read_only_and_excludes_original_answers(repo):
    import json
    source, _, original, _, service, _ = await setup(repo)
    collections = (repo.progress, repo.enrollments, repo.selections, service.records)
    before = [await collection.find({}).to_list(None) for collection in collections]
    result = await service.preview(source.user_id, original['request_id'], 'return_to_original_course')
    assert result['read_only'] and result['can_activate'] is False and result['credit_transferred'] is False
    assert result['target']['total_xp'] == 125
    assert 'retained reflection' not in json.dumps(result)
    assert before == [await collection.find({}).to_list(None) for collection in collections]


@pytest.mark.parametrize('phase', ['intent', 'before_selection', 'after_selection', 'journal', 'cleanup'])
async def test_interrupted_return_preserves_both_histories_and_resumes_original_choice(repo, monkeypatch, phase):
    source, _, _, body, service, _ = await setup(repo, earned=True)
    before = await histories(repo, source.user_id)
    if phase == 'intent':
        original = service.records.insert_one
        async def fail(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError('Synthetic interrupted return')
        owner, method = service.records, 'insert_one'
    elif phase in ('before_selection', 'after_selection'):
        original = repo.selections.find_one_and_update
        async def fail(query, update, **kwargs):
            if 'last_transition' in update.get('$set', {}):
                if phase == 'after_selection':
                    await original(query, update, **kwargs)
                raise RuntimeError('Synthetic interrupted return')
            return await original(query, update, **kwargs)
        owner, method = repo.selections, 'find_one_and_update'
    elif phase == 'journal':
        original = service.records.update_one
        async def fail(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError('Synthetic interrupted return')
        owner, method = service.records, 'update_one'
    else:
        async def fail(*args, **kwargs):
            raise RuntimeError('Synthetic interrupted return')
        owner, method = service, 'clear_pending'
    with monkeypatch.context() as patch:
        patch.setattr(owner, method, fail)
        with pytest.raises(RuntimeError, match='interrupted return'):
            await service.select(source.user_id, body)
    assert await histories(repo, source.user_id) == before
    selected = await repo.selections.find_one({'user_id': source.user_id})
    if selected.get('pending_transition_id'):
        with pytest.raises(EnrollmentConflict):
            async with repo.write_boundary(source.user_id, selected['active_enrollment_id']):
                pytest.fail('Unconfirmed return must not allow new course writes')
    result = await service.select(source.user_id, body)
    assert result['target_enrollment_id'] == source.uuid and result['revision'] == 2
    assert await service.select(source.user_id, body) == result
    assert await histories(repo, source.user_id) == before


@pytest.mark.parametrize('change', ['current_work', 'destination_work', 'destination_unsupported', 'pending_credential', 'pending_attempt'])
async def test_changed_or_unfinished_work_requires_reconciliation_without_reset(repo, change):
    source, target_id, _, body, service, _ = await setup(repo)
    if change in ('current_work', 'destination_work'):
        enrollment_id = target_id if change == 'current_work' else source.uuid
        await repo.progress.update_one({'user_id': source.user_id, 'enrollment_id': enrollment_id}, {'$inc': {'position_revision': 1}})
    elif change == 'destination_unsupported':
        import json
        path = repo.catalog.root / 'registry.json'
        registry = json.loads(path.read_text())
        registry['releases'][source.course_version].update(state='retired', supported_for_existing=False)
        registry.pop('legacy_continuation', None)
        path.write_text(json.dumps(registry))
    elif change == 'pending_credential':
        await repo.progress.update_one({'_id': ObjectId(source.progress_id)}, {'$set': {'pending_credential': {'original': 'unconfirmed'}}})
    else:
        from app.models.certification import CertificationAttempt
        target = await repo._enrollment(source.user_id, target_id)
        await CertificationAttempt.get_motor_collection().insert_one({'uuid': uuid4().hex, 'user_id': source.user_id,
            'enrollment_id': target_id, 'module_id': 'foundations', 'course_version': target.course_version,
            'manifest_sha256': target.manifest_sha256, 'state': 'evaluating'})
    before = await histories(repo, source.user_id)
    with pytest.raises((EnrollmentConflict, CourseCatalogError)):
        await service.select(source.user_id, body)
    assert (await repo.current(source.user_id)).uuid == target_id
    assert await histories(repo, source.user_id) == before


async def test_foreign_rebound_and_wrong_direction_requests_cannot_select_a_saved_course(repo):
    from pydantic import ValidationError
    source, target_id, original, body, service, _ = await setup(repo)
    with pytest.raises(EnrollmentConflict):
        await service.preview('foreign', original['request_id'], 'return_to_original_course')
    with pytest.raises(EnrollmentConflict):
        await service.preview(source.user_id, original['request_id'], 'resume_upgraded_course')
    with pytest.raises(ValidationError):
        await service.select(source.user_id, {**body, 'consent': 'erase_new_course_work'})
    assert (await repo.current(source.user_id)).uuid == target_id
    await service.select(source.user_id, body)
    with pytest.raises(EnrollmentConflict):
        await service.select('foreign', body)
    with pytest.raises(EnrollmentConflict):
        await service.select(source.user_id, {**body, 'action': 'resume_upgraded_course'})


async def test_concurrent_return_confirms_one_selection_and_retains_new_work(repo):
    source, _, _, body, service, _ = await setup(repo, earned=True)
    before = await histories(repo, source.user_id)
    results = await asyncio.gather(*(service.select(source.user_id, body) for _ in range(5)), return_exceptions=True)
    successes = [result for result in results if isinstance(result, dict)]
    assert successes and all(result == successes[0] for result in successes)
    assert all(isinstance(result, (dict, EnrollmentConflict)) for result in results)
    assert await histories(repo, source.user_id) == before
    assert await service.records.count_documents({}) == 1
    assert (await repo.selections.find_one({'user_id': source.user_id}))['revision'] == 2


async def test_destination_change_at_final_commit_keeps_current_course_and_original_history(repo, monkeypatch):
    source, target_id, _, body, service, _ = await setup(repo)
    original = service.commit
    async def changed(raw):
        await repo.progress.update_one({'_id': ObjectId(source.progress_id)}, {'$inc': {'total_xp': 10}})
        return await original(raw)
    monkeypatch.setattr(service, 'commit', changed)
    with pytest.raises(EnrollmentConflict, match='changed before selection'):
        await service.select(source.user_id, body)
    assert (await repo.current(source.user_id)).uuid == target_id
    assert (await repo.read_progress(source.user_id, source.uuid)).total_xp == 135


async def test_return_preserves_actual_saved_practical_graduation_without_regrading(repo, monkeypatch):
    from app.services.certification_versions.transition_records import TransitionRecordReconciliation
    f, choice_id, judge = await activation.completed_outcome_choice(repo, monkeypatch)
    request = {'request_id': uuid4().hex, 'decision_id': choice_id,
        'consent': 'activate_optional_upgrade_preserving_original_work_without_credit_transfer'}
    await activation.UpgradeActivationRepository(repo).activate(f.learner.user_id, request)
    records = TransitionRecordReconciliation(repo)
    original_work = await records.inventory(f.learner.user_id, f.learner.uuid)
    original_histories = await histories(repo, f.learner.user_id)
    service = SavedCourseSelectionRepository(repo)
    preview = await service.preview(f.learner.user_id, request['request_id'], 'return_to_original_course')
    result = await service.select(f.learner.user_id, {'request_id': uuid4().hex, 'activation_id': request['request_id'],
        'action': 'return_to_original_course', 'preview_sha256': preview['preview_sha256'],
        'consent': 'select_saved_course_preserving_both_histories_and_credit'})
    assert result['target_enrollment_id'] == f.learner.uuid
    assert await records.inventory(f.learner.user_id, f.learner.uuid) == original_work
    assert await histories(repo, f.learner.user_id) == original_histories
    judge.assert_awaited_once()


async def test_unknown_legacy_origin_and_date_survive_return_and_resume(repo):
    from app.models.certification import CertificationProgress
    # The migration primitive must preserve this unversioned row, not infer
    # that a later snapshot proves a historical 4.0 or 5.0 credential.
    await CertificationProgress(user_id='upgrade-choice-learner', total_xp=90,
        modules={'foundations': {'completed': True, 'stars': 1, 'xp_earned': 90}}, certified=True).insert()
    source, target_id, original, body, service, _ = await setup(repo, legacy_unknown=True)
    assert source.provenance == 'legacy_version_unknown'
    before = await histories(repo, source.user_id)
    await service.select(source.user_id, body)
    preview = await service.preview(source.user_id, original['request_id'], 'resume_upgraded_course')
    await service.select(source.user_id, {**body, 'request_id': uuid4().hex, 'action': 'resume_upgraded_course',
        'preview_sha256': preview['preview_sha256']})
    assert (await repo.current(source.user_id)).uuid == target_id
    assert await histories(repo, source.user_id) == before
    credential = await CredentialRepository().for_enrollment(source.user_id, source.uuid)
    assert credential.provenance == 'legacy_completion_unverified' and credential.course_version is None
    assert credential.certified_at is None
    assert (await repo.read_progress(source.user_id, source.uuid)).total_xp == 90
