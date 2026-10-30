"""Competing retry views must not dispatch or erase a newer sample twice."""
import asyncio
from unittest.mock import Mock

import pytest

from app.models.document import SmartDocument
from app.services import document_service
from app.services.extraction_restarts import ExtractionRestartConflict
from app.tasks import upload_tasks
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark


async def source():
    saved = await SmartDocument(uuid='course-retry-source', user_id='course-learner',
        title='Course sample.pdf', folder='course-lab', path='synthetic/sample.pdf',
        downloadpath='synthetic/sample.pdf', task_status='error', processing=False,
        raw_text='Original retained evidence', certification_provisioning_key='c' * 64).insert()
    return await SmartDocument.get(saved.id)


async def test_two_saved_retry_views_dispatch_once(repo, monkeypatch):
    document = await source()
    views = [await SmartDocument.get(document.id) for _ in range(2)]
    dispatch = Mock(return_value='synthetic-task')
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', dispatch)
    results = await asyncio.gather(*[document_service.restart_extraction(view, 'course-learner') for view in views], return_exceptions=True)
    assert dispatch.call_count == 1
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, ExtractionRestartConflict) for result in results) == 1
    current = await SmartDocument.get(document.id)
    assert current.processing is True and current.task_status == 'extracting'
    assert current.raw_text == ''


async def test_retry_cannot_erase_text_that_finished_after_its_original_read(repo, monkeypatch):
    document = await source()
    stale = await SmartDocument.get(document.id)
    await SmartDocument.get_motor_collection().update_one({'_id': document.id}, {'$set': {
        'task_status': 'complete', 'processing': False, 'raw_text': 'New complete source text',
    }})
    before = await SmartDocument.get_motor_collection().find_one({'_id': document.id})
    dispatch = Mock(return_value='must-not-dispatch')
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', dispatch)
    with pytest.raises(ExtractionRestartConflict):
        await document_service.restart_extraction(stale, 'course-learner')
    dispatch.assert_not_called()
    assert await SmartDocument.get_motor_collection().find_one({'_id': document.id}) == before


async def test_worker_model_save_cannot_roll_back_restart_revision(repo, monkeypatch):
    document = await source()
    stale = await SmartDocument.get(document.id)
    dispatch = Mock(return_value='synthetic-task')
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', dispatch)
    await document_service.restart_extraction(document, 'course-learner')
    # Simulate an older worker restoring the original public fields. This does
    # not claim worker-result fencing; it proves that the private CAS counter
    # survives ordinary model saves and prevents an identical stale retry.
    await stale.save()
    current = await SmartDocument.get(document.id)
    assert current._extraction_restart_revision == 1
    assert '_extraction_restart_revision' not in current.model_dump()
    with pytest.raises(ExtractionRestartConflict):
        await document_service.restart_extraction(stale, 'course-learner')
    assert dispatch.call_count == 1


async def test_unknown_dispatch_response_cannot_be_repeated_by_retrying_either_view(repo, monkeypatch):
    document = await source()
    stale = await SmartDocument.get(document.id)
    dispatch = Mock(side_effect=RuntimeError('Synthetic unknown dispatch response'))
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', dispatch)
    with pytest.raises(RuntimeError, match='unknown dispatch'):
        await document_service.restart_extraction(document, 'course-learner')
    fresh = await SmartDocument.get(document.id)
    for view in (stale, fresh):
        with pytest.raises(ExtractionRestartConflict):
            await document_service.restart_extraction(view, 'course-learner')
    assert dispatch.call_count == 1
    assert fresh._extraction_restart_revision == 1 and fresh.processing is True


async def test_competing_http_retries_return_one_success_and_one_conflict(repo, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from unittest.mock import AsyncMock
    from app.dependencies import get_current_user
    from app.models.folder import SmartFolder
    from app.models.user import User
    from app.routers.documents import router
    from app.rate_limit import limiter
    from app.services import access_control, audit_service
    document = await source()
    await SmartFolder(uuid='course-lab', title='Course lab', parent_id='0', user_id=document.user_id).insert()
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router, prefix='/documents')
    app.dependency_overrides[get_current_user] = lambda: User(user_id=document.user_id)
    original_authorize = access_control.get_authorized_document
    both_read = asyncio.Event()
    arrivals = 0
    async def authorize_together(*args, **kwargs):
        nonlocal arrivals
        result = await original_authorize(*args, **kwargs)
        assert result is not None
        arrivals += 1
        if arrivals == 2:
            both_read.set()
        await asyncio.wait_for(both_read.wait(), 5)
        return result
    monkeypatch.setattr(access_control, 'get_authorized_document', authorize_together)
    dispatch = Mock(return_value='synthetic-task')
    audit = AsyncMock()
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', dispatch)
    monkeypatch.setattr(audit_service, 'log_event', audit)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        responses = await asyncio.gather(*[client.post(f'/documents/{document.uuid}/retry-extraction') for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [200, 409], [r.text for r in responses]
    assert 'Refresh its status' in next(r for r in responses if r.status_code == 409).json()['detail']
    dispatch.assert_called_once()
    audit.assert_awaited_once()


@pytest.mark.parametrize('changes', [
    {'user_id': 'new-owner'}, {'folder': 'other-folder'}, {'soft_deleted': True},
    {'path': 'replacement.pdf'}, {'text_layer_rejected': True},
])
async def test_retry_rejects_changed_identity_or_processing_evidence(repo, monkeypatch, changes):
    document = await source()
    await SmartDocument.get_motor_collection().update_one({'_id': document.id}, {'$set': changes})
    before = await SmartDocument.get_motor_collection().find_one({'_id': document.id})
    dispatch = Mock(return_value='must-not-dispatch')
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', dispatch)
    with pytest.raises(ExtractionRestartConflict):
        await document_service.restart_extraction(document, 'course-learner')
    dispatch.assert_not_called()
    assert await SmartDocument.get_motor_collection().find_one({'_id': document.id}) == before
