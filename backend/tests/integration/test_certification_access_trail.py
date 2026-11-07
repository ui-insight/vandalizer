"""An access override has a durable reason and actor, never earned credit."""
from copy import deepcopy
from uuid import uuid4

import pytest

from app.models.certification import CertificationProgress
from app.services.certification_versions import readers, runtime
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.support_access import JOURNAL, access_history
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark


async def fixture(repo, monkeypatch, versioned):
    monkeypatch.setattr(readers, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: versioned)
    if versioned:
        learner = await repo.ensure_initial('access-history-learner')
        progress = await repo.read_progress(learner.user_id, learner.uuid)
    else:
        progress = await CertificationProgress(user_id='access-history-learner').insert()
    await repo.progress.update_one({'_id': progress.id}, {'$set': {
        'total_xp': 75, 'modules.ai_literacy': {'completed': True, 'stars': 1, 'completed_at': '2026-09-01'}}})
    return progress


async def change(progress, *, unlocked=True, request_id=None, reason='Restore requested course access', actor='authorized-admin'):
    return await readers.set_support_unlock(progress.user_id, unlocked, progress.enrollment_id,
        actor_user_id=actor, reason=reason, request_id=request_id or uuid4().hex)


@pytest.mark.parametrize('versioned', [False, True])
async def test_access_reason_and_actor_are_saved_with_effect_without_credit(repo, monkeypatch, versioned):
    progress = await fixture(repo, monkeypatch, versioned)
    saved = await change(progress)
    raw = await repo.progress.find_one({'_id': progress.id})
    assert saved.unlocked is True and saved.total_xp == 75
    assert saved.modules == {'ai_literacy': {'completed': True, 'stars': 1, 'completed_at': '2026-09-01'}}
    assert len(raw[JOURNAL]) == 1
    event = raw[JOURNAL][0]
    assert event['reason'] == 'Restore requested course access'
    assert event['actor_user_id'] == 'authorized-admin'
    assert event['previous_unlocked'] is False and event['unlocked'] is True
    assert event['credit_effect'] == 'none'
    assert JOURNAL not in saved.model_dump()
    history = await access_history(repo, saved)
    assert history['state'] == 'recorded' and history['changes'][0]['reason'] == event['reason']
    # Ordinary learner saves must neither expose nor erase the private trail.
    from app.services.certification_versions.writes import save_progress
    if versioned:
        async with repo.write_boundary(progress.user_id, progress.enrollment_id) as current:
            current.learning_position = {'module_id': 'foundations'}
            await save_progress(current)
    else:
        from app.services.certification_service import get_progress
        @runtime.course_operation(write=True)
        async def learner_save(user_id):
            current = await get_progress(user_id)
            current.learning_position = {'module_id': 'foundations'}
            await save_progress(current)
        await learner_save(saved.user_id)
    assert (await repo.progress.find_one({'_id': progress.id}))[JOURNAL] == raw[JOURNAL]


@pytest.mark.parametrize('versioned', [False, True])
async def test_lost_access_response_replays_once_and_cannot_undo_later_change(repo, monkeypatch, versioned):
    progress = await fixture(repo, monkeypatch, versioned)
    request_id = uuid4().hex
    original = repo.progress.find_one_and_update
    lost = False

    async def lose_response(query, update, *args, **kwargs):
        nonlocal lost
        result = await original(query, update, *args, **kwargs)
        if JOURNAL in update.get('$push', {}) and not lost:
            lost = True
            raise RuntimeError('Synthetic lost response after atomic access write')
        return result

    monkeypatch.setattr(repo.progress, 'find_one_and_update', lose_response)
    with pytest.raises(RuntimeError, match='lost response'):
        await change(progress, request_id=request_id)
    replay = await change(progress, request_id=request_id)
    assert replay.unlocked is True
    assert len((await repo.progress.find_one({'_id': progress.id}))[JOURNAL]) == 1
    await change(progress, unlocked=False, reason='Re-lock access after the requested review')
    old_replay = await change(progress, request_id=request_id)
    assert old_replay.unlocked is False
    assert len((await repo.progress.find_one({'_id': progress.id}))[JOURNAL]) == 2
    assert old_replay.total_xp == 75


@pytest.mark.parametrize('versioned', [False, True])
@pytest.mark.parametrize('field,value', [('reason', 'A different administrator reason'), ('actor', 'different-admin'), ('unlocked', False)])
async def test_request_identity_cannot_replace_a_recorded_reason_or_actor(repo, monkeypatch, versioned, field, value):
    progress = await fixture(repo, monkeypatch, versioned)
    request_id = uuid4().hex
    await change(progress, request_id=request_id)
    before = deepcopy((await repo.progress.find_one({'_id': progress.id}))[JOURNAL])
    with pytest.raises(EnrollmentConflict, match='different change'):
        await change(progress, request_id=request_id, **{field: value})
    assert (await repo.progress.find_one({'_id': progress.id}))[JOURNAL] == before


@pytest.mark.parametrize('versioned', [False, True])
async def test_failed_atomic_journal_write_cannot_apply_an_unrecorded_override(repo, monkeypatch, versioned):
    progress = await fixture(repo, monkeypatch, versioned)
    original = repo.progress.find_one_and_update

    async def refuse(query, update, *args, **kwargs):
        if JOURNAL in update.get('$push', {}):
            raise RuntimeError('Synthetic access journal storage failure')
        return await original(query, update, *args, **kwargs)

    monkeypatch.setattr(repo.progress, 'find_one_and_update', refuse)
    with pytest.raises(RuntimeError, match='journal storage failure'):
        await change(progress)
    raw = await repo.progress.find_one({'_id': progress.id})
    assert not raw['unlocked'] and JOURNAL not in raw
    assert raw['total_xp'] == 75


async def test_old_unlock_flag_does_not_invent_a_reason_or_actor(repo, monkeypatch):
    progress = await fixture(repo, monkeypatch, False)
    progress.unlocked = True
    await progress.save()
    history = await access_history(repo, progress)
    assert history == {'state': 'not_recorded', 'changes': [], 'older_available': False, 'historical_unlocked': True}


async def test_support_history_is_bounded_read_only_and_does_not_hide_corruption(repo, monkeypatch):
    progress = await fixture(repo, monkeypatch, False)
    await change(progress)
    raw = await repo.progress.find_one({'_id': progress.id})
    events = [{**raw[JOURNAL][0], 'request_id': f'{i:032x}', 'reason': f'Recorded access reason {i}'} for i in range(12)]
    await repo.progress.update_one({'_id': progress.id}, {'$set': {JOURNAL: events}})
    history = await access_history(repo, progress)
    assert history['older_available'] is True and len(history['changes']) == 10
    assert history['changes'][0]['reason'] == 'Recorded access reason 11'
    assert history['changes'][-1]['reason'] == 'Recorded access reason 2'
    assert (await repo.progress.find_one({'_id': progress.id}))[JOURNAL] == events
    events[-1]['reason'] = ''
    await repo.progress.update_one({'_id': progress.id}, {'$set': {JOURNAL: events}})
    unavailable = await access_history(repo, progress)
    assert unavailable['state'] == 'unavailable' and unavailable['changes'] == []


@pytest.mark.parametrize('case', ['authorized', 'non_admin', 'missing_reason', 'blank_reason', 'spoofed_actor', 'missing_request'])
async def test_http_access_change_requires_an_admin_and_records_the_authenticated_actor(repo, monkeypatch, case):
    from unittest.mock import AsyncMock
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.models.user import User
    from app.dependencies import get_current_user
    from app.routers import admin
    progress = await fixture(repo, monkeypatch, False)
    monkeypatch.setattr(admin, '_audit', AsyncMock())
    app = FastAPI()
    app.include_router(admin.router, prefix='/admin')
    app.dependency_overrides[get_current_user] = lambda: User(user_id='authenticated-operator', is_admin=case != 'non_admin')
    payload = {'request_id': uuid4().hex, 'unlocked': True, 'reason': '  Restore the requested module access  '}
    if case == 'missing_reason':
        payload.pop('reason')
    elif case == 'blank_reason':
        payload['reason'] = '     '
    elif case == 'spoofed_actor':
        payload['actor_user_id'] = 'another-admin'
    elif case == 'missing_request':
        payload.pop('request_id')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.put(f'/admin/certifications/{progress.user_id}/unlock', json=payload)
    raw = await repo.progress.find_one({'_id': progress.id})
    if case == 'authorized':
        assert response.status_code == 200
        assert raw[JOURNAL][0]['actor_user_id'] == 'authenticated-operator'
        assert raw[JOURNAL][0]['reason'] == 'Restore the requested module access'
        assert raw['unlocked'] is True and raw['total_xp'] == 75
    else:
        assert response.status_code == (403 if case == 'non_admin' else 422)
        assert JOURNAL not in raw and raw['unlocked'] is False
