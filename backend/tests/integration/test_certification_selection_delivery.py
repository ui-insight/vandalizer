"""Learners confirm committed switches across devices without new selection."""
import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.dependencies import get_current_user
from app.routers.certification import router
from app.services.certification_versions import runtime, selection_delivery
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.selection_delivery import SelectionDelivery
from tests.integration import test_certification_saved_course_selection as saved
from tests.integration import test_certification_upgrade_activation as activation

repo = activation.repo
pytestmark = activation.pytestmark


async def pending(repo, monkeypatch, *, kind='upgrade', phase='after_selection'):
    if kind == 'upgrade':
        source, body, journal, _ = await activation.setup(repo, certified=True)
        action = journal.activate
    else:
        source, _, _, body, journal, _ = await saved.setup(repo, earned=True)
        action = journal.select
    async def interrupt(*args):
        raise RuntimeError('Synthetic confirmation interruption')
    with monkeypatch.context() as patch:
        patch.setattr(journal, 'finalize' if phase == 'after_selection' else 'clear_pending', interrupt)
        with pytest.raises(RuntimeError, match='confirmation interruption'):
            await action(source.user_id, body)
    delivery = SelectionDelivery(repo)
    return source, body, journal, delivery


def confirmation(status):
    item = status['pending']
    return {key: item[key] for key in ('request_id', 'kind', 'receipt_sha256')} | {
        'consent': 'confirm_original_committed_course_selection'}


@pytest.mark.parametrize('kind', ['upgrade', 'return'])
@pytest.mark.parametrize('phase', ['after_selection', 'after_journal'])
async def test_read_is_pure_and_another_device_confirms_only_original_receipt(repo, monkeypatch, kind, phase):
    source, body, journal, delivery = await pending(repo, monkeypatch, kind=kind, phase=phase)
    history = await saved.histories(repo, source.user_id)
    selection = await repo.selections.find_one({'user_id': source.user_id})
    original = await journal.records.find_one({'uuid': body['request_id']})
    status = await delivery.status(source.user_id)
    assert status['read_only'] and status['pending']['histories_preserved']
    assert status['pending']['credit_transferred'] is False
    assert 'retained reflection' not in json.dumps(status) and 'record_json' not in json.dumps(status)
    assert await repo.selections.find_one({'user_id': source.user_id}) == selection
    assert await journal.records.find_one({'uuid': body['request_id']}) == original
    request = confirmation(status)
    # Reconstruct service: recovery needs no original browser storage/consent body.
    response = await SelectionDelivery(repo).confirm(source.user_id, request)
    assert response['confirmed'] and response['selection_changed'] is False
    assert response['receipt'] == status['pending']
    assert (await delivery.status(source.user_id))['pending'] is None
    assert (await repo.selections.find_one({'user_id': source.user_id}))['revision'] == selection['revision']
    after = await saved.histories(repo, source.user_id)
    if kind == 'upgrade':
        # Initial confirmation promotes only the original blank prepared
        # enrollment; earned history/progress and source metadata stay fixed.
        for enrollment in history['enrollments']:
            if enrollment['uuid'] == status['current_enrollment_id']:
                enrollment['state'] = 'active'
    assert after == history
    async with repo.write_boundary(source.user_id, status['current_enrollment_id']):
        pass
    assert await delivery.confirm(source.user_id, request) == response


async def test_empty_status_never_initializes_and_prepared_intent_never_activates(repo, monkeypatch):
    delivery = SelectionDelivery(repo)
    assert await delivery.status('new-learner') == {'read_only': True, 'current_enrollment_id': None, 'pending': None}
    assert await repo.enrollments.count_documents({}) == 0
    source, body, journal, _ = await activation.setup(repo)
    async def interrupt(*args):
        raise RuntimeError('Before selection')
    monkeypatch.setattr(journal, 'commit', interrupt)
    with pytest.raises(RuntimeError, match='Before selection'):
        await journal.activate(source.user_id, body)
    assert (await delivery.status(source.user_id))['pending'] is None
    with pytest.raises((CourseCatalogError, EnrollmentConflict)):
        await delivery.confirm(source.user_id, {'request_id': body['request_id'], 'kind': 'optional_upgrade_selection.1',
            'receipt_sha256': 'a' * 64, 'consent': 'confirm_original_committed_course_selection'})
    assert (await repo.current(source.user_id)).uuid == source.uuid
    assert (await journal.records.find_one({'uuid': body['request_id']}))['state'] == 'prepared'


async def test_historical_confirmation_cannot_undo_later_selection_or_clear_its_marker(repo, monkeypatch):
    source, _, _, delivery = await pending(repo, monkeypatch)
    request = confirmation(await delivery.status(source.user_id))
    first = await delivery.confirm(source.user_id, request)
    service = saved.SavedCourseSelectionRepository(repo)
    preview = await service.preview(source.user_id, request['request_id'], 'return_to_original_course')
    async def interrupt(*args):
        raise RuntimeError('Return interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(service, 'finalize', interrupt)
        with pytest.raises(RuntimeError):
            await service.select(source.user_id, {'request_id': uuid4().hex, 'activation_id': request['request_id'],
                'preview_sha256': preview['preview_sha256'], 'action': 'return_to_original_course',
                'consent': 'select_saved_course_preserving_both_histories_and_credit'})
    before = await repo.selections.find_one({'user_id': source.user_id})
    assert await delivery.confirm(source.user_id, request) == first
    assert await repo.selections.find_one({'user_id': source.user_id}) == before
    assert before['active_enrollment_id'] == source.uuid and before['pending_transition_id'] != request['request_id']


@pytest.mark.parametrize('phase', ['after_selection', 'after_journal'])
@pytest.mark.parametrize('damage', ['missing_journal', 'journal_digest', 'receipt_semantics', 'receipt_date', 'revision', 'foreign', 'write'])
async def test_unverifiable_switch_never_unlocks_course_writes(repo, monkeypatch, damage, phase):
    source, body, journal, delivery = await pending(repo, monkeypatch, phase=phase)
    request = confirmation(await delivery.status(source.user_id))
    if damage == 'missing_journal':
        await journal.records.delete_one({'uuid': body['request_id']})
    elif damage in ('journal_digest', 'foreign'):
        await journal.records.update_one({'uuid': body['request_id']}, {'$set': {
            'record_sha256' if damage == 'journal_digest' else 'user_id': '0' * 64 if damage == 'journal_digest' else 'foreign'}})
    else:
        row = await repo.selections.find_one({'user_id': source.user_id})
        if damage in ('receipt_semantics', 'receipt_date'):
            if damage == 'receipt_semantics':
                row['last_transition']['credit_transferred'] = True
            else:
                row['last_transition']['selected_at'] = 'invalid-date'
            row['last_transition']['receipt_sha256'] = encode({k: v for k, v in row['last_transition'].items() if k != 'receipt_sha256'})[1]
        elif damage == 'revision':
            row['revision'] += 1
        else:
            row['in_flight_writes'] = 1
            row['active_write'] = {'id': 'another-worker'}
        await repo.selections.replace_one({'user_id': source.user_id}, row)
    before = await repo.selections.find_one({'user_id': source.user_id})
    for operation in (delivery.status(source.user_id), delivery.confirm(source.user_id, request)):
        with pytest.raises((CourseCatalogError, EnrollmentConflict)):
            await operation
    assert await repo.selections.find_one({'user_id': source.user_id}) == before
    assert before['pending_transition_id'] == request['request_id']


async def test_concurrent_confirmations_then_lost_response_retry_do_not_reselect(repo, monkeypatch):
    source, _, _, delivery = await pending(repo, monkeypatch)
    status = await delivery.status(source.user_id)
    request = confirmation(status)
    results = await asyncio.gather(*(SelectionDelivery(repo).confirm(source.user_id, request) for _ in range(4)), return_exceptions=True)
    assert any(isinstance(result, dict) for result in results)
    assert all(isinstance(result, (dict, EnrollmentConflict)) for result in results)
    assert (await delivery.confirm(source.user_id, request))['confirmed']
    assert (await delivery.status(source.user_id))['pending'] is None
    assert (await repo.selections.find_one({'user_id': source.user_id}))['revision'] == 1


async def test_http_owned_confirmation_works_with_delivery_disabled_and_requires_exact_consent(repo, monkeypatch):
    source, _, journal, delivery = await pending(repo, monkeypatch)
    monkeypatch.setattr(selection_delivery, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        status = await client.get('/certification/selection-status')
        assert status.status_code == 200
        request = confirmation(status.json())
        path = '/certification/selection-confirmations'
        for invalid in ({**request, 'consent': 'activate'}, {**request, 'target_enrollment_id': 'another'}, {**request, 'request_id': 'invalid'}):
            assert (await client.post(path, json=invalid)).status_code == 422
        assert (await client.post(path, json={**request, 'receipt_sha256': '0' * 64})).status_code == 409
        assert (await client.get(path)).status_code == 405
        assert (await client.post('/certification/selection-status')).status_code == 405
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign')
        assert (await client.get('/certification/selection-status')).json()['pending'] is None
        assert (await client.post(path, json=request)).status_code == 409
        app.dependency_overrides.clear()
        assert (await client.get('/certification/selection-status')).status_code == 401
        assert (await client.post(path, json=request)).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
        confirmed = await client.post(path, json=request)
        assert confirmed.status_code == 200 and confirmed.json()['confirmed'] is True
        assert (await client.post(path, json=request)).json() == confirmed.json()
    assert (await delivery.status(source.user_id))['pending'] is None
    assert await journal.records.count_documents({'user_id': source.user_id}) == 1
