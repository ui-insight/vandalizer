"""Zero-credit target staging; every source and receipt is disposable."""
from copy import deepcopy
from uuid import uuid4

from bson import ObjectId
import pytest

from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.upgrade_targets import UpgradeTargetRepository, target_identity
from tests.integration import test_certification_upgrade_decisions as choices

repo = choices.repo
pytestmark = choices.pytestmark


async def setup(repo, *, earned=False):
    source, _, body, decisions = await choices.setup(repo)
    if earned:
        await repo.progress.update_one({'_id': ObjectId(source.progress_id)}, {'$set': {'total_xp': 125,
            'modules.foundations': {'completed': True, 'stars': 2, 'xp_earned': 125, 'completed_at': '2025-01-01'}}})
        preview = await choices.UpgradeComparison(repo).inspect(source.user_id, source.uuid, body['target_version'])
        body['preview_sha256'] = preview['preview_sha256']
    await decisions.accept(source.user_id, body)
    return source, body, UpgradeTargetRepository(repo)


async def test_repeated_preparation_has_one_target_and_never_selects_or_copies_credit(repo):
    source, body, targets = await setup(repo, earned=True)
    before = await repo.progress.find_one({'_id': ObjectId(source.progress_id)})
    first = await targets.prepare(source.user_id, body['request_id'])
    target_id, _ = target_identity(body['request_id'])
    assert first['target_enrollment_id'] == target_id
    assert first['target_xp'] == 0 and first['credit_transferred'] is first['activated'] is False
    assert await targets.prepare(source.user_id, body['request_id']) == first
    assert (await repo.current(source.user_id)).uuid == source.uuid
    after = await repo.progress.find_one({'_id': ObjectId(source.progress_id)})
    before.pop('_certification_write_fence', None)
    after.pop('_certification_write_fence', None)
    assert after == before
    assert after['total_xp'] == 125 and after['modules']['foundations']['stars'] == 2
    assert await repo.enrollments.count_documents({'user_id': source.user_id}) == 2
    assert await repo.progress.count_documents({'user_id': source.user_id}) == 2
    target = await repo.read_progress(source.user_id, target_id)
    assert (await repo._enrollment(source.user_id, target_id)).state == 'prepared'
    assert target.modules == {} and target.learning_position is None and target.pending_credential is None
    with pytest.raises(EnrollmentConflict, match='read-only'):
        async with repo.write_boundary(source.user_id, target_id):
            pytest.fail('The prepared course cannot accept writes while the source stays selected')


@pytest.mark.parametrize('phase', ['before_progress', 'after_progress', 'after_enrollment'])
async def test_interrupted_staging_resumes_original_target_without_resetting_source(repo, monkeypatch, phase):
    source, body, targets = await setup(repo)
    target_id, progress_id = target_identity(body['request_id'])
    collection = repo.enrollments if phase == 'after_enrollment' else repo.progress
    original = collection.update_one
    async def interrupted(query, update, **kwargs):
        is_target = query.get('uuid') == target_id if phase == 'after_enrollment' else query.get('_id') == ObjectId(progress_id)
        if is_target and phase == 'before_progress':
            raise RuntimeError('Synthetic interrupted target preparation')
        result = await original(query, update, **kwargs)
        if is_target:
            raise RuntimeError('Synthetic interrupted target preparation')
        return result
    monkeypatch.setattr(collection, 'update_one', interrupted)
    with pytest.raises(RuntimeError, match='interrupted target'):
        await targets.prepare(source.user_id, body['request_id'])
    assert (await repo.current(source.user_id)).uuid == source.uuid
    monkeypatch.setattr(collection, 'update_one', original)
    result = await targets.prepare(source.user_id, body['request_id'])
    assert result['target_enrollment_id'] == target_id and result['activated'] is False
    assert await repo.enrollments.count_documents({'user_id': source.user_id}) == 2
    assert await repo.progress.count_documents({'user_id': source.user_id}) == 2


@pytest.mark.parametrize('change', ['credit', 'reading_place', 'unlocked', 'lab_inputs'])
async def test_existing_target_work_is_rejected_and_never_overwritten(repo, change):
    source, body, targets = await setup(repo)
    result = await targets.prepare(source.user_id, body['request_id'])
    target_id, progress_id = target_identity(body['request_id'])
    changes = {'credit': {'total_xp': 125, 'modules.foundations.completed': True},
        'reading_place': {'position_revision': 3}, 'unlocked': {'unlocked': True},
        'lab_inputs': {'lab_folder_id': 'original-lab'}}[change]
    await repo.progress.update_one({'_id': ObjectId(progress_id)}, {'$set': changes})
    preserved = deepcopy(await repo.progress.find_one({'_id': ObjectId(progress_id)}))
    with pytest.raises(EnrollmentConflict, match='contains saved work'):
        await targets.prepare(source.user_id, body['request_id'])
    assert await repo.progress.find_one({'_id': ObjectId(progress_id)}) == preserved
    assert (await repo.current(source.user_id)).uuid == source.uuid
    assert result['target_enrollment_id'] == target_id


async def test_target_reference_collision_cannot_adopt_someone_elses_progress(repo):
    source, body, targets = await setup(repo)
    _, progress_id = target_identity(body['request_id'])
    foreign = {'_id': ObjectId(progress_id), 'user_id': 'foreign-owner', 'total_xp': 900}
    await repo.progress.insert_one(foreign)
    with pytest.raises(EnrollmentConflict, match='progress is unavailable'):
        await targets.prepare(source.user_id, body['request_id'])
    assert await repo.progress.find_one({'_id': ObjectId(progress_id)}) == foreign
    assert (await repo.current(source.user_id)).uuid == source.uuid


async def test_revoked_preparation_guard_cannot_create_a_target(repo, monkeypatch):
    source, body, targets = await setup(repo)
    original = targets.stage
    async def revoked(decision, progress, package):
        await repo.progress.update_one({'_id': ObjectId(source.progress_id)}, {'$set': {'_certification_write_fence': uuid4().hex}})
        return await original(decision, progress, package)
    monkeypatch.setattr(targets, 'stage', revoked)
    with pytest.raises(EnrollmentConflict, match='lost its original course boundary'):
        await targets.prepare(source.user_id, body['request_id'])
    assert await repo.enrollments.count_documents({'user_id': source.user_id}) == 1
