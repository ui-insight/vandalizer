"""The unversioned fallback must not overwrite concurrently saved learner work."""
import asyncio
from contextvars import copy_context
from types import SimpleNamespace
from uuid import uuid4

import pytest

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.certification import CertificationProgress
from app.routers.certification import router
from app.services import certification_service as service
from app.services.certification_versions import runtime
from app.services.certification_versions.enrollments import EnrollmentConflict
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark


async def test_delayed_legacy_completion_cannot_erase_another_modules_earned_credit(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    learner = 'legacy-concurrent'
    modules = {module_id: {'self_assessment': {key: 'Original learner answer' for key in service.ASSESSMENT_KEYS[module_id]}}
               for module_id in ('ai_literacy', 'process_mapping')}
    progress = CertificationProgress(user_id=learner, modules=modules)
    await progress.insert()
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=learner)
    entered, release = asyncio.Event(), asyncio.Event()
    save = service.save_progress
    calls = 0

    async def delayed_save(value):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await asyncio.wait_for(release.wait(), 30)
        return await save(value)

    monkeypatch.setattr(service, 'save_progress', delayed_save)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as first, AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as second:
        params = {'request_id': uuid4().hex}
        task = asyncio.create_task(first.post('/certification/modules/ai_literacy/complete', params=params))
        try:
            await asyncio.wait_for(entered.wait(), 30)
            other = await second.post('/certification/modules/process_mapping/complete', params={'request_id': uuid4().hex})
            assert other.status_code == 200, other.text
        finally:
            release.set()
        delayed = await task
        assert delayed.status_code == 409, delayed.text
        saved = await CertificationProgress.get(progress.id)
        assert saved.modules['process_mapping']['completed'] is True
        assert not saved.modules['ai_literacy'].get('completed')
        retry = await first.post('/certification/modules/ai_literacy/complete', params=params)
        assert retry.status_code == 200, retry.text
        saved = await CertificationProgress.get(progress.id)
        assert all(saved.modules[module_id]['completed'] for module_id in modules)
        assert saved.total_xp == sum(service.MODULE_XP[module_id] + 75 for module_id in modules)


async def test_parallel_first_reads_create_one_legacy_record_without_an_enrollment(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    results = await asyncio.gather(*(service.get_progress('parallel-first-reader') for _ in range(12)))
    assert len({str(item.id) for item in results}) == 1
    assert await repo.progress.count_documents({'user_id': 'parallel-first-reader'}) == 1
    assert await repo.enrollments.count_documents({}) == 0


async def test_answers_changed_after_validation_cannot_receive_the_older_grade(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    learner = 'answers-race'
    answers = {'experience': 'Original', 'comfort': 'Original', 'concern': 'Original'}
    await CertificationProgress(user_id=learner, modules={'ai_literacy': {'self_assessment': answers}}).insert()
    entered, release = asyncio.Event(), asyncio.Event()
    validate = service.validate_module

    async def delayed_validation(*args, **kwargs):
        result = await validate(*args, **kwargs)
        entered.set()
        await asyncio.wait_for(release.wait(), 30)
        return result

    monkeypatch.setattr(service, 'validate_module', delayed_validation)
    task = asyncio.create_task(service.complete_module(learner, 'ai_literacy'))
    try:
        await asyncio.wait_for(entered.wait(), 30)
        await service.store_assessment(learner, 'ai_literacy', {'experience': 'New incomplete answer'})
    finally:
        release.set()
    with pytest.raises(EnrollmentConflict, match='Progress changed'):
        await task
    saved = await service.get_progress(learner)
    assert saved.modules['ai_literacy']['self_assessment']['experience'] == 'New incomplete answer'
    assert not saved.modules['ai_literacy'].get('completed') and saved.total_xp == 0


@pytest.mark.parametrize('change', [{'_certification_write_fence': 'new-versioned-worker'}, {'enrollment_id': 'a' * 32}, {'unlocked': True}])
async def test_legacy_save_refuses_a_changed_course_or_administrator_state(repo, monkeypatch, change):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    original = CertificationProgress(user_id='changed-binding')
    await original.insert()

    @runtime.course_operation(write=True)
    async def delayed(user_id):
        progress = await service.get_progress(user_id)
        await repo.progress.update_one({'_id': original.id}, {'$set': change})
        progress.total_xp = 999
        await service.save_progress(progress)

    with pytest.raises(EnrollmentConflict, match='Progress changed'):
        await delayed(original.user_id)
    saved = await repo.progress.find_one({'_id': original.id})
    assert saved['total_xp'] == 0 and all(saved[key] == value for key, value in change.items())


async def test_repeated_saves_in_one_operation_preserve_private_history_and_update_the_revision(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    original = CertificationProgress(user_id='two-saves')
    await original.insert()
    await repo.progress.update_one({'_id': original.id}, {'$set': {'_certification_access_changes': [{'reason': 'Preserve original support event'}], 'historical_unknown': 'retain'}})

    @runtime.course_operation(write=True)
    async def save_twice(user_id):
        progress = await service.get_progress(user_id)
        progress.modules['ai_literacy'] = {'self_assessment': {'experience': 'First answer'}}
        await service.save_progress(progress)
        assert await service.get_progress(user_id) is progress
        progress.modules['ai_literacy']['self_assessment']['comfort'] = 'Second answer'
        await service.save_progress(progress)

    await save_twice(original.user_id)
    saved = await repo.progress.find_one({'_id': original.id})
    assert saved['_legacy_progress_revision'] == 2 and saved['historical_unknown'] == 'retain'
    assert saved['_certification_access_changes'] == [{'reason': 'Preserve original support event'}]
    assert saved['modules']['ai_literacy']['self_assessment'] == {'experience': 'First answer', 'comfort': 'Second answer'}
    assert '_legacy_progress_revision' not in await service.get_progress_dict(original.user_id)


async def test_ambiguous_legacy_records_and_nested_user_or_write_switches_are_refused(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    await CertificationProgress(user_id='ambiguous').insert()
    await CertificationProgress(user_id='ambiguous').insert()
    with pytest.raises(EnrollmentConflict, match='ambiguous'):
        await service.store_assessment('ambiguous', 'ai_literacy', {'experience': 'Do not guess a record'})

    @runtime.course_operation()
    async def read_then_write(user_id):
        return await service.store_assessment(user_id, 'ai_literacy', {})

    @runtime.course_operation(write=True)
    async def change_user(user_id):
        return await service.get_progress('different-learner')

    with pytest.raises(EnrollmentConflict, match='read-only'):
        await read_then_write('learner')
    with pytest.raises(EnrollmentConflict, match='different learner'):
        await change_user('learner')
    assert await repo.progress.count_documents({'user_id': 'different-learner'}) == 0


async def test_an_inherited_legacy_context_cannot_start_a_write_after_its_request_ends(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)

    @runtime.course_operation(write=True)
    async def capture_context(user_id):
        await service.get_progress(user_id)
        return copy_context()

    retained = await capture_context('ended-request')
    late = retained.run(asyncio.create_task, service.store_assessment('ended-request', 'ai_literacy', {'experience': 'Too late'}))
    with pytest.raises(EnrollmentConflict, match='operation has ended'):
        await late
    assert (await service.get_progress('ended-request')).modules == {}
