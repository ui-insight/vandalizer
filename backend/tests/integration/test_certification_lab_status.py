"""Actual assigned source state, read without dispatch or earned-work changes."""
from unittest.mock import AsyncMock

import pytest

from app.models.folder import SmartFolder
from app.models.project import Project
from app.models.user import User
from app.services import file_service
from app.services.certification_versions import runtime
from app.services.certification_versions.lab_status import read_lab_status
from tests.integration import test_certification_enrollments as base

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = base.pytestmark


@pytest.mark.parametrize('versioned', [False, True])
async def test_status_tracks_assigned_source_and_never_retries_or_changes_credit(versioned_runtime, monkeypatch, versioned):
    repository = versioned_runtime
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: versioned)
    learner, _, source, _, _, _ = await base.make_lab_input_fixture(repository)
    user = User(user_id=learner.user_id)
    if not versioned:
        await repository.progress.update_one({'user_id': user.user_id}, {'$unset': {'enrollment_id': '', 'course_version': ''}})
    folder = await SmartFolder(uuid=source.folder, title='Certification Lab', user_id=user.user_id, parent_id='0').insert()
    upload = AsyncMock()
    monkeypatch.setattr(file_service, 'upload_document', upload)
    before = await repository.progress.find_one({'user_id': user.user_id})

    async def read():
        result = await read_lab_status(user, 'foundations', enrollment_id=learner.uuid if versioned else None)
        assert result['credit_changed'] is False
        assert await repository.progress.find_one({'user_id': user.user_id}) == before
        upload.assert_not_awaited()
        return result

    for changes, expected in [
        ({'task_status': 'extracting', 'processing': True}, 'processing'),
        ({'task_status': 'complete', 'processing': False}, 'ready'),
        ({'task_status': 'error', 'error_message': 'Private backend diagnostic'}, 'failed'),
        ({'task_status': 'complete', 'valid': False}, 'failed'),
        ({'valid': True, 'text_layer_rejected': True}, 'failed'),
        ({'text_layer_rejected': False, 'raw_text': ''}, 'failed'),
        ({'raw_text': 'Readable sample', 'task_status': None}, 'unavailable'),
    ]:
        for name, value in changes.items():
            setattr(source, name, value)
        await source.save()
        result = await read()
        assert result['state'] == expected
        assert result['documents'] == [{'name': source.title, 'document_id': source.uuid, 'state': expected}]
        assert 'Private backend diagnostic' not in str(result)
    source.task_status = 'complete'
    await source.save()
    project = await Project(uuid='restricted-lab', title='Secret project', owner_user_id='someone-else', root_folder_uuid=folder.uuid).insert()
    hidden = await read()
    assert hidden['state'] == 'unavailable'
    assert hidden['folder_id'] is hidden['folder_name'] is None
    assert hidden['documents'][0]['document_id'] is None
    await project.delete()
    for changes in [{'folder': 'another-folder'}, {'folder': folder.uuid, 'soft_deleted': True},
                    {'soft_deleted': False, 'user_id': 'someone-else'}]:
        for name, value in changes.items():
            setattr(source, name, value)
        await source.save()
        result = await read()
        assert result['state'] == 'unavailable'
        assert result['documents'][0]['document_id'] is None


async def test_http_status_uses_authenticated_pinned_course_and_distinguishes_setup(versioned_runtime):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.dependencies import get_current_user
    from app.routers.certification import router
    repository = versioned_runtime
    learner = await repository.ensure_initial('status-learner')
    other = await repository.ensure_initial('someone-else')
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: User(user_id=learner.user_id)
    params = {'enrollment_id': learner.uuid}
    before = await repository.progress.find_one({'user_id': learner.user_id})
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for module, state in [('foundations', 'not_setup'), ('ai_literacy', 'not_required')]:
            response = await client.get(f'/certification/modules/{module}/lab-status', params=params)
            assert response.status_code == 200
            result = response.json()
            assert result['state'] == state
            assert result['enrollment_id'] == learner.uuid
            assert result['course_version'] == learner.course_version
            assert result['documents'] == []
        denied = await client.get('/certification/modules/foundations/lab-status', params={'enrollment_id': other.uuid})
        assert denied.status_code == 409
        missing = await client.get('/certification/modules/not-a-module/lab-status', params=params)
        assert missing.status_code == 409
    assert await repository.progress.find_one({'user_id': learner.user_id}) == before


@pytest.mark.parametrize('versioned', [False, True])
async def test_http_setup_persists_assignment_then_reads_worker_states_without_reupload(versioned_runtime, monkeypatch, versioned):
    from uuid import uuid4
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.dependencies import get_current_user, get_settings
    from app.models.document import SmartDocument
    from app.routers.certification import router
    repository = versioned_runtime
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: versioned)
    learner = await repository.ensure_initial('http-lab-learner')
    if not versioned:
        await repository.progress.update_one({'user_id': learner.user_id}, {'$unset': {'enrollment_id': '', 'course_version': ''}})
    user = User(user_id=learner.user_id)
    # External storage/Celery is deliberately replaced; folder creation,
    # assignment, route identity, access checks and status reads are real.
    async def upload(**kwargs):
        assert kwargs['user'].user_id == user.user_id
        document = await SmartDocument(uuid=uuid4().hex, title=kwargs['filename'], user_id=user.user_id,
            folder=kwargs['folder'], path='synthetic/sample.pdf', downloadpath='synthetic/sample.pdf',
            processing=True, task_status='extracting').insert()
        return {'uuid': document.uuid}
    dispatch = AsyncMock(side_effect=upload)
    monkeypatch.setattr(file_service, 'upload_document', dispatch)
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: {}
    params = {'enrollment_id': learner.uuid} if versioned else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        setup = await client.post('/certification/modules/foundations/provision', params=params)
        assert setup.status_code == 200, setup.text
        assigned = setup.json()['provisioned_docs']
        assert len(assigned) == 1
        document = await SmartDocument.find_one(SmartDocument.uuid == assigned[0])
        before = await repository.progress.find_one({'user_id': user.user_id})
        assert before['total_xp'] == 0
        for task_status, processing, text, expected in [
            ('extracting', True, '', 'processing'), ('error', False, '', 'failed'),
            ('complete', False, 'Synthetic worker text', 'ready'),
        ]:
            document.task_status, document.processing, document.raw_text = task_status, processing, text
            await document.save()
            response = await client.get('/certification/modules/foundations/lab-status', params=params)
            assert response.status_code == 200
            status = response.json()
            assert status['state'] == expected
            assert status['folder_id'] == document.folder
            assert status['documents'][0]['document_id'] == assigned[0]
            assert await repository.progress.find_one({'user_id': user.user_id}) == before
        repeated = await client.post('/certification/modules/foundations/provision', params=params)
        assert repeated.status_code == 200
        assert repeated.json()['provisioned_docs'] == assigned
    dispatch.assert_awaited_once()
    assert await SmartDocument.count() == 1
    assert await SmartFolder.count() == 1
