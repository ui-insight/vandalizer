"""Real persisted retry generations fence paused and queued sample workers."""
import asyncio
import datetime
import os
import threading
from unittest.mock import Mock
from contextlib import nullcontext

from pymongo import MongoClient
import pytest
import pytest_asyncio

from app.models.document import SmartDocument
from app.services import document_service, document_readers
from app.services.document_readers import DocumentReadError
from app.tasks import document_tasks, upload_tasks, upload_validation_tasks
from tests.integration import test_certification_enrollments as base
from tests.integration.test_certification_extraction_retry import source

repo = base.repo
pytestmark = base.pytestmark


@pytest_asyncio.fixture
async def worker_db(repo, monkeypatch):
    client = MongoClient(os.environ['CERTIFICATION_TEST_MONGO_URL'], serverSelectionTimeoutMS=3000)
    db = client[SmartDocument.get_motor_collection().database.name]
    monkeypatch.setattr(document_tasks, 'get_sync_db', lambda: db)
    monkeypatch.setattr(upload_validation_tasks, '_get_db', lambda: db)
    monkeypatch.setattr(document_tasks, '_notify_document_processing_failed', Mock())
    monkeypatch.setattr(document_tasks, '_resume_pending_kb_sources', Mock())
    monkeypatch.setattr(document_tasks, '_check_folder_watch_automations', Mock())
    monkeypatch.setattr(upload_tasks, 'dispatch_upload_tasks', Mock(return_value='synthetic-retry'))
    try:
        yield db
    finally:
        client.close()


async def restart_stalled(document):
    await SmartDocument.get_motor_collection().update_one({'_id': document.id}, {'$set': {
        'updated_at': datetime.datetime.now() - datetime.timedelta(hours=4),
    }})
    current = await SmartDocument.get(document.id)
    await document_service.restart_extraction(current, current.user_id)
    return await SmartDocument.get_motor_collection().find_one({'_id': document.id})


@pytest.mark.parametrize('outcome', ['success', 'empty', 'missing', 'unreadable', 'unexpected'])
async def test_paused_extraction_cannot_finish_over_a_new_retry(worker_db, monkeypatch, outcome):
    document = await source()
    entered, release = threading.Event(), threading.Event()

    def delayed_reader(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        if outcome == 'missing':
            raise FileNotFoundError('synthetic missing file')
        if outcome == 'unreadable':
            raise DocumentReadError('synthetic unreadable file')
        if outcome == 'unexpected':
            raise RuntimeError('synthetic failed reader')
        return 'Late text from superseded extraction' if outcome == 'success' else ''

    monkeypatch.setattr(document_readers, 'extract_text_from_file', delayed_reader)
    worker = asyncio.create_task(asyncio.to_thread(document_tasks.perform_extraction_and_update.run,
        document_uuid=document.uuid, extension='txt'))
    assert await asyncio.to_thread(entered.wait, 5)
    try:
        before = await restart_stalled(document)
    finally:
        release.set()
        await worker
    assert await SmartDocument.get_motor_collection().find_one({'_id': document.id}) == before
    document_tasks._notify_document_processing_failed.assert_not_called()


@pytest.mark.parametrize('task', ['extraction', 'update', 'cleanup', 'ingestion', 'validation', 'summary'])
async def test_queued_old_task_cannot_change_retried_sample(worker_db, monkeypatch, task):
    document = await source()
    before = await restart_stalled(document)
    reader = Mock(return_value='Old queued text')
    monkeypatch.setattr(document_readers, 'extract_text_from_file', reader)
    from app.services import document_manager
    manager = Mock()
    monkeypatch.setattr(document_manager, 'DocumentManager', manager)
    monkeypatch.setattr(upload_validation_tasks, '_get_compliance_settings', lambda: {'enabled': False})
    summary_agent = Mock()
    monkeypatch.setattr(upload_validation_tasks, '_get_secure_agent', summary_agent)
    actions = {
        'extraction': lambda: document_tasks.perform_extraction_and_update.run(document.uuid, 'txt'),
        'update': lambda: document_tasks.update_document_fields.run(document.uuid),
        'cleanup': lambda: document_tasks.cleanup_document.run(document.uuid),
        'ingestion': lambda: document_tasks.perform_semantic_ingestion.run('Old queued text', document.uuid, document.user_id),
        'validation': lambda: upload_validation_tasks.perform_document_validation.run(document.uuid, document.path),
        'summary': lambda: upload_validation_tasks.summarize_results.run([{'skipped': True}], document.uuid),
    }
    await asyncio.to_thread(actions[task])
    assert await SmartDocument.get_motor_collection().find_one({'_id': document.id}) == before
    reader.assert_not_called()
    manager.assert_not_called()
    summary_agent.assert_not_called()
    document_tasks._resume_pending_kb_sources.assert_not_called()
    document_tasks._check_folder_watch_automations.assert_not_called()


async def test_current_retry_can_extract_complete_validate_and_index(worker_db, monkeypatch):
    document = await source()
    restarted = await restart_stalled(document)
    revision = restarted['_extraction_restart_revision']
    assert upload_tasks.dispatch_upload_tasks.call_args.kwargs['extraction_revision'] == revision
    monkeypatch.setattr(document_readers, 'extract_text_from_file', Mock(return_value='Current sample text'))
    text = await asyncio.to_thread(document_tasks.perform_extraction_and_update.run,
        document.uuid, 'txt', extraction_revision=revision)
    assert text == 'Current sample text'
    await asyncio.to_thread(document_tasks.update_document_fields.run, document.uuid, extraction_revision=revision)
    monkeypatch.setattr(upload_validation_tasks, '_get_compliance_settings', lambda: {'enabled': False})
    await asyncio.to_thread(upload_validation_tasks.perform_document_validation.run,
        document.uuid, document.path, extraction_revision=revision)
    from app.services import document_manager
    manager = Mock()
    manager.return_value.add_document.return_value = 2
    monkeypatch.setattr(document_manager, 'DocumentManager', manager)
    monkeypatch.setattr(document_tasks, '_ingest_into_project_kb', Mock())
    await asyncio.to_thread(document_tasks.perform_semantic_ingestion.run,
        '', document.uuid, document.user_id, extraction_revision=revision)
    saved = await SmartDocument.get(document.id)
    assert saved.raw_text == text and saved.task_status == 'complete'
    assert saved.processing is False and saved.chromadb_ready is True and saved.chunk_count == 2
    assert saved.validation_feedback == 'Compliance checks disabled.'
    document_tasks._resume_pending_kb_sources.assert_called_once()
    document_tasks._check_folder_watch_automations.assert_called_once()
    document_tasks._ingest_into_project_kb.assert_called_once()


async def test_reaper_invalidates_dead_generation_before_late_result(worker_db, monkeypatch):
    document = await source()
    entered, release = threading.Event(), threading.Event()
    def delayed_reader(*args):
        entered.set()
        assert release.wait(10)
        return 'Late text from dead worker'
    monkeypatch.setattr(document_readers, 'extract_text_from_file', delayed_reader)
    worker = asyncio.create_task(asyncio.to_thread(document_tasks.perform_extraction_and_update.run, document.uuid, 'txt'))
    assert await asyncio.to_thread(entered.wait, 5)
    try:
        await SmartDocument.get_motor_collection().update_one({'_id': document.id}, {'$set': {
            'updated_at': datetime.datetime.now() - datetime.timedelta(hours=4),
        }})
        assert await asyncio.to_thread(document_tasks._reap_abandoned_extractions, worker_db) == 1
        before = await SmartDocument.get_motor_collection().find_one({'_id': document.id})
        assert before['_extraction_restart_revision'] == 1
        assert before['task_status'] == 'error' and before['processing'] is False
    finally:
        release.set()
        await worker
    assert await SmartDocument.get_motor_collection().find_one({'_id': document.id}) == before
    # Reaping twice is a no-op; the explicit retry gets a fresh generation.
    assert await asyncio.to_thread(document_tasks._reap_abandoned_extractions, worker_db) == 0
    await document_service.restart_extraction(await SmartDocument.get(document.id), document.user_id)
    assert upload_tasks.dispatch_upload_tasks.call_args.kwargs['extraction_revision'] == 2


@pytest.mark.parametrize('task', ['summary', 'ingestion_success', 'ingestion_error'])
async def test_already_running_followup_cannot_write_new_generation(worker_db, monkeypatch, task):
    document = await source()
    entered, release = threading.Event(), threading.Event()
    def delayed_provider(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        if task == 'ingestion_error':
            raise RuntimeError('Synthetic interrupted index write')
        if task == 'summary':
            result = Mock()
            result.output.model_dump.return_value = {'valid': True, 'feedback': 'Old validation'}
            return result
        return 3
    from app.services import document_manager, metering
    manager = Mock()
    manager.return_value.add_document.side_effect = delayed_provider
    monkeypatch.setattr(document_manager, 'DocumentManager', manager)
    mirror = Mock()
    monkeypatch.setattr(document_tasks, '_ingest_into_project_kb', mirror)
    agent = Mock()
    agent.run_sync.side_effect = delayed_provider
    monkeypatch.setattr(upload_validation_tasks, '_get_secure_agent', lambda: agent)
    monkeypatch.setattr(metering, 'metered', lambda *args, **kwargs: nullcontext())
    if task == 'summary':
        call = lambda: upload_validation_tasks.summarize_results.run([{'valid': True}], document.uuid)
    else:
        call = lambda: document_tasks.perform_semantic_ingestion.run(document.raw_text, document.uuid, document.user_id)
    worker = asyncio.create_task(asyncio.to_thread(call))
    assert await asyncio.to_thread(entered.wait, 5)
    try:
        before = await restart_stalled(document)
    finally:
        release.set()
        await worker
    assert await SmartDocument.get_motor_collection().find_one({'_id': document.id}) == before
    mirror.assert_not_called()


async def test_reaper_dispatches_current_generation_for_finished_orphan(worker_db, monkeypatch):
    document = await source()
    await restart_stalled(document)
    await SmartDocument.get_motor_collection().update_one({'_id': document.id}, {'$set': {
        'processing': False, 'raw_text': 'Finished current read',
    }})
    dispatch = Mock()
    monkeypatch.setattr(document_tasks.update_document_fields, 'delay', dispatch)
    await asyncio.to_thread(document_tasks.reap_stuck_documents.run)
    dispatch.assert_called_once_with(document.uuid, extraction_revision=1)


async def test_validation_chord_retains_dispatched_generation(worker_db, monkeypatch):
    document = await source()
    await restart_stalled(document)
    monkeypatch.setattr(upload_validation_tasks, '_get_compliance_settings', lambda: {
        'enabled': True, 'rules': 'Synthetic rule', 'chunk_size': 8000, 'chunk_overlap': 200,
    })
    chord = Mock()
    monkeypatch.setattr(upload_validation_tasks, 'chord', chord)
    await asyncio.to_thread(upload_validation_tasks.perform_document_validation.run,
        document.uuid, document.path, document_text='Current source to validate', extraction_revision=1)
    chord.assert_called_once()
    callback = chord.return_value.call_args.args[0]
    assert callback.task == 'tasks.upload.validation.summary'
    assert callback.kwargs['extraction_revision'] == 1


async def test_stalled_validation_becomes_retryable_and_rejects_late_summary(worker_db, monkeypatch):
    from app.services.certification_versions.lab_status import document_state
    document = await source()
    collection = SmartDocument.get_motor_collection()
    await collection.update_one({'_id': document.id}, {'$set': {
        'task_status': 'complete', 'processing': False, 'raw_text': 'Retained completed source',
        'validating': True, '_validation_heartbeat_at': datetime.datetime.now() - datetime.timedelta(hours=4),
    }})
    assert document_state(await SmartDocument.get(document.id)) == 'processing'
    await asyncio.to_thread(document_tasks.reap_stuck_documents.run)
    saved = await SmartDocument.get(document.id)
    assert document_state(saved) == 'failed'
    assert saved.raw_text == 'Retained completed source'
    assert saved.validating is False and saved.valid is False
    assert 'stopped' in saved.validation_feedback
    before = await collection.find_one({'_id': document.id})
    agent = Mock()
    monkeypatch.setattr(upload_validation_tasks, '_get_secure_agent', agent)
    await asyncio.to_thread(upload_validation_tasks.summarize_results.run, [{'skipped': True}], document.uuid)
    assert await collection.find_one({'_id': document.id}) == before
    agent.assert_not_called()
    await document_service.restart_extraction(saved, saved.user_id)
    assert document_state(await SmartDocument.get(document.id)) == 'processing'


@pytest.mark.parametrize('changes', [
    {'valid': False, 'processing': True, 'task_status': 'extracting'},
    {'text_layer_rejected': True, 'processing': True, 'task_status': 'ocr'},
    {'valid': False, 'validating': True, 'task_status': 'security'},
    {'processing': False, 'task_status': 'readying'},
])
async def test_active_sample_work_is_processing_even_with_previous_failure(worker_db, changes):
    from app.services.certification_versions.lab_status import document_state
    document = await source()
    await SmartDocument.get_motor_collection().update_one({'_id': document.id}, {'$set': changes})
    assert document_state(await SmartDocument.get(document.id)) == 'processing'


@pytest.mark.parametrize('renew_at_cas', [False, True])
async def test_live_validation_heartbeat_cannot_be_reaped(worker_db, renew_at_cas):
    from types import SimpleNamespace
    document = await source()
    collection = SmartDocument.get_motor_collection()
    old = datetime.datetime.now() - datetime.timedelta(hours=4)
    await collection.update_one({'_id': document.id}, {'$set': {
        'processing': False, 'task_status': 'complete', 'validating': True,
        '_validation_heartbeat_at': old, 'updated_at': old,
    }})
    if renew_at_cas:
        # A heartbeat wins between the reaper's cursor read and its CAS.
        def find_then_renew(*args, **kwargs):
            candidates = list(worker_db.smart_document.find(*args, **kwargs))
            assert upload_validation_tasks._touch_validation(document.uuid, 0)
            return candidates
        proxy = SimpleNamespace(smart_document=SimpleNamespace(
            find=find_then_renew, update_one=worker_db.smart_document.update_one))
    else:
        assert await asyncio.to_thread(upload_validation_tasks._touch_validation, document.uuid, 0)
        proxy = worker_db
    assert await asyncio.to_thread(document_tasks._reap_abandoned_validations, proxy) == 0
    saved = await SmartDocument.get(document.id)
    assert saved.validating is True and saved.valid is True
    assert saved._extraction_restart_revision == 0


async def test_reaped_validation_chunks_skip_model_work(worker_db, monkeypatch):
    document = await source()
    await SmartDocument.get_motor_collection().update_one({'_id': document.id}, {'$set': {
        'processing': False, 'task_status': 'complete', 'validating': True,
        '_validation_heartbeat_at': datetime.datetime.now() - datetime.timedelta(hours=4),
    }})
    assert await asyncio.to_thread(document_tasks._reap_abandoned_validations, worker_db) == 1
    model = Mock()
    monkeypatch.setattr(upload_validation_tasks, '_get_secure_agent', model)
    result = await asyncio.to_thread(upload_validation_tasks.validate_chunk.run,
        document.path, 'synthetic rule', 'superseded text', 1, 1,
        document_uuid=document.uuid, extraction_revision=0)
    assert result['skipped'] is True and result['reason'] == 'obsolete_extraction'
    model.assert_not_called()


async def test_legacy_validation_without_heartbeat_can_recover(worker_db):
    document = await source()
    await SmartDocument.get_motor_collection().update_one({'_id': document.id}, {'$set': {
        'processing': False, 'task_status': 'complete', 'validating': True,
        'updated_at': datetime.datetime.now() - datetime.timedelta(hours=4),
    }})
    assert await asyncio.to_thread(document_tasks._reap_abandoned_validations, worker_db) == 1
    assert await asyncio.to_thread(document_tasks._reap_abandoned_validations, worker_db) == 0
    saved = await SmartDocument.get(document.id)
    assert saved.validating is False and saved.valid is False
