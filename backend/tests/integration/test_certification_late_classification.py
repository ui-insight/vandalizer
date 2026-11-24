"""A delayed classifier must not restore stale course sample content or labels."""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.document import SmartDocument
from app.models.system_config import SystemConfig
from app.services import classification_service, document_service
from app.tasks import classification_tasks, upload_tasks
from tests.integration import test_certification_enrollments as base
from tests.integration.test_certification_extraction_retry import source

repo = base.repo
pytestmark = base.pytestmark


@asynccontextmanager
async def no_external_metering(*args, **kwargs):
    yield


@pytest.mark.parametrize('change', ['retry', 'same_text_new_revision', 'text', 'manual', 'deleted', 'owner', 'folder', 'unrelated'])
async def test_late_classifier_cannot_overwrite_newer_document(repo, monkeypatch, change):
    import app.database
    import app.services.metering

    document = await source()
    collection = SmartDocument.get_motor_collection()
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_model(doc):
        entered.set()
        await asyncio.wait_for(release.wait(), 5)
        return {'classification': 'internal', 'confidence': 0.9}

    config = Mock()
    config.get_classification_config.return_value = {'enabled': True, 'auto_classify_on_upload': True}
    monkeypatch.setattr(app.database, 'init_db', AsyncMock())
    monkeypatch.setattr(SystemConfig, 'get_config', AsyncMock(return_value=config))
    monkeypatch.setattr(app.services.metering, 'metered_async', no_external_metering)
    monkeypatch.setattr(classification_service, 'classify_document', delayed_model)
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', Mock(return_value='synthetic-task'))
    worker = asyncio.create_task(classification_tasks._classify(document.uuid))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        if change in {'retry', 'same_text_new_revision'}:
            old_text = document.raw_text
            await document_service.restart_extraction(document, document.user_id)
            if change == 'same_text_new_revision':
                await collection.update_one({'_id': document.id}, {'$set': {'raw_text': old_text}})
        else:
            changes = {
                'text': {'raw_text': 'New extraction from the current pages'},
                'manual': {'classification': 'ferpa', 'classified_by': 'course-learner'},
                'deleted': {'soft_deleted': True},
                'owner': {'user_id': 'different-owner'},
                'folder': {'folder': 'other-folder'},
                'unrelated': {'processing': True, 'task_status': 'readying', 'validation_feedback': 'New feedback'},
            }
            await collection.update_one({'_id': document.id}, {'$set': changes[change]})
        before = await collection.find_one({'_id': document.id})
    finally:
        release.set()
        await worker
    after = await collection.find_one({'_id': document.id})
    if change == 'unrelated':
        for key in ('classification', 'classification_confidence', 'classified_by', 'classified_at'):
            before.pop(key, None)
            after.pop(key, None)
        assert (await SmartDocument.get(document.id)).classification == 'internal'
    assert after == before


async def test_manual_classification_updates_only_its_fields(repo):
    document = await source()
    collection = SmartDocument.get_motor_collection()
    await collection.update_one({'_id': document.id}, {'$set': {'raw_text': 'New reading', 'task_status': 'complete'}})
    before = await collection.find_one({'_id': document.id})
    await classification_service.apply_classification(document, 'ferpa', 1.0, classified_by=document.user_id)
    after = await collection.find_one({'_id': document.id})
    assert after['classification'] == 'ferpa'
    for key in ('classification', 'classification_confidence', 'classified_by', 'classified_at'):
        before.pop(key, None)
        after.pop(key, None)
    assert before == after


async def test_classification_does_not_recreate_deleted_document(repo):
    document = await source()
    await document.delete()
    result = await classification_service.apply_classification(document, 'internal', 1.0, classified_by=document.user_id)
    assert result is None
    assert await SmartDocument.get(document.id) is None


@pytest.mark.parametrize('actor', ['auto', 'default'])
async def test_background_classification_preserves_an_existing_manual_decision(repo, actor):
    document = await source()
    await classification_service.apply_classification(document, 'ferpa', 1.0, classified_by=document.user_id)
    before = await SmartDocument.get_motor_collection().find_one({'_id': document.id})
    assert await classification_service.apply_classification(document, 'internal', 0.9, classified_by=actor) is None
    assert await SmartDocument.get_motor_collection().find_one({'_id': document.id}) == before


async def test_default_classification_cannot_replace_a_later_manual_decision(repo):
    document = await source()
    stale = await SmartDocument.get(document.id)
    await classification_service.apply_classification(document, 'ferpa', 1.0, classified_by=document.user_id)
    before = await SmartDocument.get_motor_collection().find_one({'_id': document.id})
    assert await classification_service.apply_classification(stale, 'internal', 1.0, classified_by='default') is None
    assert await SmartDocument.get_motor_collection().find_one({'_id': document.id}) == before


@pytest.mark.parametrize('queued_revision', [0, 1])
async def test_classifier_reads_only_its_dispatched_generation(repo, monkeypatch, queued_revision):
    import app.database
    import app.services.metering

    document = await source()
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', Mock(return_value='synthetic-task'))
    await document_service.restart_extraction(document, document.user_id)
    monkeypatch.setattr(app.database, 'init_db', AsyncMock())
    config = Mock()
    config.get_classification_config.return_value = {'enabled': True, 'auto_classify_on_upload': True}
    monkeypatch.setattr(SystemConfig, 'get_config', AsyncMock(return_value=config))
    monkeypatch.setattr(app.services.metering, 'metered_async', no_external_metering)
    model = AsyncMock(return_value={'classification': 'internal', 'confidence': 0.9})
    monkeypatch.setattr(classification_service, 'classify_document', model)
    await classification_tasks._classify(document.uuid, queued_revision)
    saved = await SmartDocument.get(document.id)
    if queued_revision == 0:
        model.assert_not_called()
        assert saved.classification is None
    else:
        model.assert_awaited_once()
        assert saved.classification == 'internal' and saved._extraction_restart_revision == 1
