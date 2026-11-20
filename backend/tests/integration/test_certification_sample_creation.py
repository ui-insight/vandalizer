"""Real upload arbitration for concurrent course setup; no storage or queue service."""
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import Mock
from pymongo import MongoClient

import pytest

from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.user import User
from app.services import certification_service, storage
from app.services.certification_versions import runtime
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.tasks import upload_tasks
from tests.integration import test_certification_enrollments as base

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = base.pytestmark


class MemoryStorage:
    def __init__(self):
        self.objects = {}
        self.writes = 0
        self.arrived = asyncio.Event()
        self.race = True

    async def write(self, path, data):
        self.objects[path] = data
        self.writes += 1
        if self.race:
            if self.writes == 2:
                self.arrived.set()
            await asyncio.wait_for(self.arrived.wait(), 5)

    async def delete(self, path):
        self.objects.pop(path, None)

    def public_path(self, path):
        return '/private/tmp/synthetic-upload/' + path


@pytest.mark.parametrize('worker_state', ['complete', 'error', 'retry', 'deleted', 'removed', 'processing'])
async def test_dispatch_response_cannot_restore_pre_worker_sample(versioned_runtime, monkeypatch, worker_state):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    files = MemoryStorage()
    files.race = False
    monkeypatch.setattr(storage, 'get_storage', lambda settings: files)
    client = MongoClient(os.environ['CERTIFICATION_TEST_MONGO_URL'], serverSelectionTimeoutMS=3000)
    collection = client[SmartDocument.get_motor_collection().database.name].smart_document
    expected = None
    dispatched_uuid = None
    def fast_worker(**kwargs):
        nonlocal expected, dispatched_uuid
        dispatched_uuid = kwargs['document_uuid']
        query = {'uuid': dispatched_uuid}
        changes = {
            'complete': {'raw_text': 'Completed course sample text', 'processing': False, 'task_status': 'complete', 'token_count': 6},
            'error': {'processing': False, 'task_status': 'error', 'error_message': 'Synthetic worker failure'},
            'retry': {'_extraction_restart_revision': 1, 'processing': True, 'task_status': 'extracting', 'task_id': 'new-retry'},
            'deleted': {'soft_deleted': True},
            'processing': {'task_status': 'ocr', 'validation_feedback': 'Fresh validation feedback'},
        }
        if worker_state == 'removed':
            collection.delete_one(query)
        else:
            collection.update_one(query, {'$set': changes[worker_state]})
        expected = collection.find_one(query)
        if worker_state == 'processing':
            expected['task_id'] = 'synthetic-dispatch'
        return 'synthetic-dispatch'
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', fast_worker)
    try:
        if worker_state in {'deleted', 'removed'}:
            with pytest.raises(EnrollmentConflict, match='no longer accessible'):
                await certification_service.provision_module_documents(
                    User(user_id='fast-worker-course-sample'), 'foundations', SimpleNamespace(max_upload_size_mb=10))
        else:
            await certification_service.provision_module_documents(
                User(user_id='fast-worker-course-sample'), 'foundations', SimpleNamespace(max_upload_size_mb=10))
        assert dispatched_uuid is not None
        assert await SmartDocument.get_motor_collection().find_one({'uuid': dispatched_uuid}) == expected
        if worker_state == 'complete':
            from app.services.certification_versions.lab_status import read_lab_status
            from app.tasks import upload_validation_tasks
            learner = User(user_id='fast-worker-course-sample')
            before_progress = await versioned_runtime.progress.find_one({'user_id': learner.user_id})
            assert (await read_lab_status(learner, 'foundations'))['state'] == 'processing'
            monkeypatch.setattr(upload_validation_tasks, '_get_db', lambda: collection.database)
            monkeypatch.setattr(upload_validation_tasks, '_get_compliance_settings', lambda: {'enabled': False})
            await asyncio.to_thread(upload_validation_tasks.perform_document_validation.run,
                dispatched_uuid, expected['path'], background=True)
            assert (await read_lab_status(learner, 'foundations'))['state'] == 'ready'
            assert await versioned_runtime.progress.find_one({'user_id': learner.user_id}) == before_progress
    finally:
        client.close()


@pytest.mark.parametrize('unknown_dispatch', [False, True])
async def test_parallel_course_uploads_keep_one_sample_and_one_dispatch(versioned_runtime, monkeypatch, unknown_dispatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    files = MemoryStorage()
    dispatch = Mock(return_value='synthetic-dispatch')
    if unknown_dispatch:
        dispatch.side_effect = RuntimeError('Synthetic unknown dispatch response')
    monkeypatch.setattr(storage, 'get_storage', lambda settings: files)
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', dispatch)
    user = User(user_id='simultaneous-course-setup')
    settings = SimpleNamespace(max_upload_size_mb=10)
    results = await asyncio.gather(*[
        certification_service.provision_module_documents(user, 'foundations', settings) for _ in range(2)
    ], return_exceptions=True)
    assert all(isinstance(result, (dict, EnrollmentConflict)) or (unknown_dispatch and isinstance(result, RuntimeError) and str(result) == 'Synthetic unknown dispatch response') for result in results), results
    assert sum(isinstance(result, dict) for result in results) >= 1
    folders = await SmartFolder.find({'user_id': user.user_id}).to_list()
    documents = await SmartDocument.find({'user_id': user.user_id}).to_list()
    assert len(folders) == 1
    assert len(documents) == 1
    document = documents[0]
    assert len(files.objects) == 1 and document.path in files.objects
    assert document.folder == folders[0].uuid
    dispatch.assert_called_once()
    assert dispatch.call_args.kwargs['document_uuid'] == document.uuid
    assert document.task_id == (None if unknown_dispatch else 'synthetic-dispatch')
    files.race = False
    replay = await certification_service.provision_module_documents(user, 'foundations', settings)
    assert replay['provisioned_docs'] == [document.uuid]
    assert dispatch.call_count == 1 and files.writes == 2
    saved = await versioned_runtime.progress.find_one({'user_id': user.user_id})
    assert saved['modules']['foundations']['provisioned_docs'] == [document.uuid]
    assert saved['total_xp'] == 0 and saved['certified'] is False
    from app.services.certification_versions.lab_status import read_lab_status
    status = await read_lab_status(user, 'foundations')
    assert status['state'] == 'processing' and status['credit_changed'] is False
    assert status['documents'][0]['document_id'] == document.uuid


@pytest.mark.parametrize('change', ['deleted', 'renamed', 'moved'])
async def test_explicit_setup_can_replace_an_unassigned_sample_without_overwriting_it(versioned_runtime, monkeypatch, change):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    files = MemoryStorage()
    files.race = False
    dispatch = Mock(return_value='synthetic-dispatch')
    monkeypatch.setattr(storage, 'get_storage', lambda settings: files)
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', dispatch)
    user = User(user_id='replace-course-sample')
    settings = SimpleNamespace(max_upload_size_mb=10)
    original = await certification_service.provision_module_documents(user, 'foundations', settings)
    document = await SmartDocument.find_one(SmartDocument.uuid == original['provisioned_docs'][0])
    if change == 'deleted':
        document.soft_deleted = True
    elif change == 'renamed':
        document.title = 'My previous sample.pdf'
    else:
        document.folder = 'my-other-folder'
    await document.save()
    before = await SmartDocument.get_motor_collection().find_one({'_id': document.id})
    replacement = await certification_service.provision_module_documents(user, 'foundations', settings)
    assert replacement['provisioned_docs'] != original['provisioned_docs']
    assert await SmartDocument.get_motor_collection().find_one({'_id': document.id}) == before
    assert await SmartDocument.find({'user_id': user.user_id}).count() == 2
    assert document.path in files.objects and len(files.objects) == 2
    assert dispatch.call_count == 2


async def test_new_index_accepts_existing_ordinary_documents_with_matching_names(versioned_runtime):
    for index in range(2):
        await SmartDocument(uuid=f'ordinary-{index}', user_id='ordinary-owner', title='same-name.pdf',
                            folder='ordinary-folder', path=f'ordinary/{index}.pdf', downloadpath=f'ordinary/{index}.pdf').insert()
    assert await SmartDocument.find({'user_id': 'ordinary-owner'}).count() == 2


@pytest.mark.parametrize('edit', ['rename', 'move'])
async def test_editing_a_sample_releases_creation_binding_without_blocking_later_edits(versioned_runtime, monkeypatch, edit):
    from app.services import file_service
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    files = MemoryStorage()
    files.race = False
    monkeypatch.setattr(storage, 'get_storage', lambda settings: files)
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', Mock(return_value='synthetic-dispatch'))
    user = User(user_id='renamed-course-sample')
    settings = SimpleNamespace(max_upload_size_mb=10)
    original = await certification_service.provision_module_documents(user, 'foundations', settings)
    document = await SmartDocument.find_one(SmartDocument.uuid == original['provisioned_docs'][0])
    original_title = document.title
    original_folder = document.folder
    assert document.certification_provisioning_key
    if edit == 'rename':
        assert await file_service.rename_document(document.uuid, 'My earlier sample.pdf', user=user)
    else:
        from app.tasks.document_tasks import sync_project_kb_on_move
        monkeypatch.setattr(sync_project_kb_on_move, 'delay', Mock())
        assert await file_service.move_document(document.uuid, '0', user=user)
    assert (await SmartDocument.get(document.id)).certification_provisioning_key is None
    replacement = await certification_service.provision_module_documents(user, 'foundations', settings)
    assert replacement['provisioned_docs'] != original['provisioned_docs']
    if edit == 'rename':
        assert await file_service.rename_document(document.uuid, original_title, user=user)
    else:
        assert await file_service.move_document(document.uuid, original_folder, user=user)
    restored = await SmartDocument.get(document.id)
    assert restored.title == original_title and restored.folder == original_folder
