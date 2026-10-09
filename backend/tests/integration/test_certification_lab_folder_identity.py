"""Course lab creation keeps one identity across races and interrupted saves."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.models.folder import SmartFolder
from app.models.user import User
from app.services import certification_service, file_service
from app.services.certification_versions import runtime
from tests.integration import test_certification_enrollments as base

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = base.pytestmark


async def test_parallel_legacy_setup_creates_one_folder(versioned_runtime, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    user = User(user_id='parallel-legacy-lab')
    # Make both workers observe the original missing folder before either creates.
    original_find = SmartFolder.find_one
    barrier = asyncio.Event()
    arrivals = 0
    async def find_missing_together(*args, **kwargs):
        nonlocal arrivals
        result = await original_find(*args, **kwargs)
        if result is None and arrivals < 2:
            arrivals += 1
            if arrivals == 2:
                barrier.set()
            await asyncio.wait_for(barrier.wait(), 5)
        return result
    monkeypatch.setattr(SmartFolder, 'find_one', find_missing_together)
    uploads = []
    async def interrupted_upload(**kwargs):
        uploads.append(kwargs['folder'])
        raise RuntimeError('Synthetic stop before document creation')
    monkeypatch.setattr(file_service, 'upload_document', interrupted_upload)
    results = await asyncio.gather(*[
        certification_service.provision_module_documents(user, 'foundations', {}) for _ in range(2)
    ], return_exceptions=True)
    assert all(isinstance(result, RuntimeError) and 'Synthetic stop' in str(result) for result in results), results
    folders = await SmartFolder.find({'user_id': user.user_id}).to_list()
    assert len(folders) == 1
    assert uploads == [folders[0].uuid, folders[0].uuid]


async def test_retry_after_failed_lab_reference_save_reuses_created_folder(versioned_runtime, monkeypatch):
    learner = await versioned_runtime.ensure_initial('interrupted-lab-reference')
    user = User(user_id=learner.user_id)
    original_save = certification_service.save_progress
    fail_once = True
    async def save_with_interruption(progress):
        nonlocal fail_once
        if fail_once and progress.lab_folder_id:
            fail_once = False
            raise RuntimeError('Synthetic stop before lab reference is saved')
        return await original_save(progress)
    monkeypatch.setattr(certification_service, 'save_progress', save_with_interruption)
    upload = AsyncMock(side_effect=RuntimeError('Synthetic stop before document creation'))
    monkeypatch.setattr(file_service, 'upload_document', upload)
    with pytest.raises(RuntimeError, match='lab reference'):
        await certification_service.provision_module_documents(user, 'foundations', {}, enrollment_id=learner.uuid)
    first = await SmartFolder.find({'user_id': user.user_id}).to_list()
    assert len(first) == 1
    assert (await versioned_runtime.read_progress(user.user_id, learner.uuid)).lab_folder_id is None
    with pytest.raises(RuntimeError, match='document creation'):
        await certification_service.provision_module_documents(user, 'foundations', {}, enrollment_id=learner.uuid)
    folders = await SmartFolder.find({'user_id': user.user_id}).to_list()
    assert len(folders) == 1
    assert folders[0].uuid == first[0].uuid
    assert (await versioned_runtime.read_progress(user.user_id, learner.uuid)).lab_folder_id == first[0].uuid
    upload.assert_awaited_once()


async def test_unknown_creation_response_reuses_folder_without_overwriting_user_changes(versioned_runtime, monkeypatch):
    from app.services.certification_versions.lab_folders import ensure_lab_folder
    learner = await versioned_runtime.ensure_initial('unknown-folder-response')
    user = User(user_id=learner.user_id)
    progress = await versioned_runtime.read_progress(user.user_id, learner.uuid)
    collection = SmartFolder.get_motor_collection()
    original = collection.find_one_and_update
    fail_once = True
    async def lose_response(*args, **kwargs):
        nonlocal fail_once
        result = await original(*args, **kwargs)
        if fail_once:
            fail_once = False
            raise RuntimeError('Synthetic lost creation response')
        return result
    monkeypatch.setattr(collection, 'find_one_and_update', lose_response)
    with pytest.raises(RuntimeError, match='lost creation response'):
        await ensure_lab_folder(user, progress, 'Original course title')
    saved = await collection.find_one({'user_id': user.user_id})
    await collection.update_one({'_id': saved['_id']}, {'$set': {'title': 'My renamed lab', 'parent_id': 'my-new-parent'}})
    restored = await ensure_lab_folder(user, progress, 'Original course title')
    assert restored.id == saved['_id'] and restored.uuid == saved['uuid']
    assert restored.title == 'My renamed lab' and restored.parent_id == 'my-new-parent'
    assert await collection.count_documents({'user_id': user.user_id}) == 1


@pytest.mark.parametrize('change', [
    {'user_id': 'different-owner'}, {'team_id': 'different-team'},
    {'uuid': 'different-lab'}, {'_certification_lab_identity': 'different-course'},
])
async def test_creation_identity_conflicts_fail_without_replacing_the_folder(versioned_runtime, change):
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.lab_folders import ensure_lab_folder
    learner = await versioned_runtime.ensure_initial('folder-conflict')
    user = User(user_id=learner.user_id)
    progress = await versioned_runtime.read_progress(user.user_id, learner.uuid)
    folder = await ensure_lab_folder(user, progress, 'Original course title')
    collection = SmartFolder.get_motor_collection()
    await collection.update_one({'_id': folder.id}, {'$set': change})
    before = await collection.find_one({'_id': folder.id})
    with pytest.raises(EnrollmentConflict, match='creation identity'):
        await ensure_lab_folder(user, progress, 'Original course title')
    assert await collection.find_one({'_id': folder.id}) == before
    assert await collection.count_documents({}) == 1


async def test_unrecorded_folder_moved_to_private_project_is_not_uploaded_into(versioned_runtime, monkeypatch):
    from app.models.project import Project
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.lab_folders import ensure_lab_folder
    learner = await versioned_runtime.ensure_initial('unrecorded-moved-lab')
    user = User(user_id=learner.user_id)
    progress = await versioned_runtime.read_progress(user.user_id, learner.uuid)
    # The folder exists, but an interrupted request has not saved its reference.
    folder = await ensure_lab_folder(user, progress, 'Certification Lab')
    await Project(uuid='other-owner-project', title='Private project', owner_user_id='other-owner', root_folder_uuid=folder.uuid).insert()
    upload = AsyncMock()
    monkeypatch.setattr(file_service, 'upload_document', upload)
    with pytest.raises(EnrollmentConflict, match='no longer accessible'):
        await certification_service.provision_module_documents(user, 'foundations', {}, enrollment_id=learner.uuid)
    upload.assert_not_awaited()
    assert (await versioned_runtime.read_progress(user.user_id, learner.uuid)).lab_folder_id is None
    assert await SmartFolder.find({'user_id': user.user_id}).count() == 1


async def test_course_creation_identity_cannot_be_reused_by_a_different_learner(versioned_runtime):
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.lab_folders import ensure_lab_folder
    learner = await versioned_runtime.ensure_initial('folder-original-owner')
    progress = await versioned_runtime.read_progress(learner.user_id, learner.uuid)
    with pytest.raises(EnrollmentConflict, match='original learner progress'):
        await ensure_lab_folder(User(user_id='different-learner'), progress, 'Do not create')
    assert await SmartFolder.find_all().count() == 0
