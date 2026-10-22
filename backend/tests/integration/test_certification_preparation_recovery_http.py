"""Owned learner recovery of uncommitted preparation, including another device."""
import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.dependencies import get_current_user
from app.routers.certification import router
from app.services.certification_versions import runtime, selection_delivery, selection_preparation_recovery
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.selection_delivery import SelectionDelivery
from tests.integration import test_certification_selection_preparation_recovery as core
from tests.integration.test_certification_saved_course_selection import histories

repo = core.repo
pytestmark = core.pytestmark


def body(preparation):
    return {key: preparation[key] for key in ('request_id', 'preview_sha256')} | {
        'consent': 'stop_uncommitted_course_preparation_preserving_all_work'}


@pytest.mark.parametrize('phase', ['before_acquisition', 'intent', 'before_cas'])
async def test_owned_read_and_explicit_stop_work_with_versioned_delivery_disabled(repo, monkeypatch, phase):
    async with core.worker(repo, monkeypatch, phase=phase) as (user, current, original, journal, action, task, release):
        monkeypatch.setattr(selection_delivery, 'EnrollmentRepository', lambda: repo)
        monkeypatch.setattr(selection_preparation_recovery, 'EnrollmentRepository', lambda: repo)
        monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
        app = FastAPI()
        app.include_router(router, prefix='/certification')
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=user)
        before = await histories(repo, user)
        selected = await repo.selections.find_one({'user_id': user})
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            first = await client.get('/certification/selection-status')
            assert first.status_code == 200
            preparation = first.json()['preparation']
            assert preparation['state'] == 'preparing' and preparation['read_only']
            assert (await client.get('/certification/selection-status')).json() == first.json()
            assert await repo.selections.find_one({'user_id': user}) == selected
            assert await histories(repo, user) == before
            assert 'record_json' not in first.text and 'retained reflection' not in first.text
            request = body(preparation)
            path = '/certification/selection-preparation-recoveries'
            assert (await client.get(path)).status_code == 405
            for invalid in ({**request, 'consent': 'switch'}, {**request, 'source_enrollment_id': current.uuid}, {**request, 'request_id': 'invalid'}):
                assert (await client.post(path, json=invalid)).status_code == 422
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign')
            assert (await client.get('/certification/selection-status')).json().get('preparation') is None
            assert (await client.post(path, json=request)).status_code == 409
            app.dependency_overrides.clear()
            assert (await client.post(path, json=request)).status_code == 401
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=user)
            stopped = await client.post(path, json=request)
            assert stopped.status_code == 200, stopped.text
            assert stopped.json()['status'] == 'preparation_stopped'
            assert (await client.post(path, json=request)).json() == stopped.json()
            assert (await client.get('/certification/selection-status')).json().get('preparation') is None
        release.set()
        assert isinstance((await asyncio.gather(task, return_exceptions=True))[0], EnrollmentConflict)
        assert await histories(repo, user) == before


@pytest.mark.parametrize('phase', ['intent_insert', 'claimed', 'journal_written'])
async def test_another_device_discovers_and_finishes_original_interrupted_recovery(repo, monkeypatch, phase):
    async with core.worker(repo, monkeypatch) as (user, current, original, journal, action, task, release):
        delivery = SelectionDelivery(repo)
        service = core.SelectionPreparationRecovery(repo)
        initial = await delivery.status(user)
        request = body(initial['preparation'])
        if phase == 'intent_insert':
            owner, name = service.records, 'insert_one'
            original_method = owner.insert_one
            async def fail(*args, **kwargs):
                await original_method(*args, **kwargs)
                raise RuntimeError('Lost recovery reply')
        elif phase == 'claimed':
            owner, name = service, 'finish'
            async def fail(*args):
                raise RuntimeError('Lost recovery reply')
        else:
            owner, name = service, 'clear'
            async def fail(*args):
                raise RuntimeError('Lost recovery reply')
        with monkeypatch.context() as patch:
            patch.setattr(owner, name, fail)
            with pytest.raises(RuntimeError):
                await service.recover(user, request)
        status = await SelectionDelivery(repo).status(user)
        assert status['preparation']['state'] == ('preparing' if phase == 'intent_insert' else 'recovery_pending')
        assert body(status['preparation']) == request
        result = await core.SelectionPreparationRecovery(repo).recover(user, body(status['preparation']))
        assert result['recovery_id'] == request['request_id']
        assert await service.records.count_documents({'user_id': user}) == 1
        assert (await delivery.status(user)).get('preparation') is None
