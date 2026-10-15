"""A stale second tab cannot start another completion after credit changed."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.certification import CertificationProgress
from app.routers.certification import router
from app.services.certification_versions import runtime
from app.services import certification_service as service
from app.services.certification_versions.attempts import AttemptRepository
from app.services.certification_versions import legacy_completions
from unittest.mock import AsyncMock
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark


@pytest.mark.parametrize('pinned', [False, True])
async def test_stale_second_tab_cannot_create_another_legacy_completion(repo, monkeypatch, pinned):
    learner = 'completion-precondition-learner'
    module = 'ai_literacy'
    await CertificationProgress(user_id=learner, modules={module: {'self_assessment': {
        'experience': 'Original response', 'comfort': 'Original response', 'concern': 'Original response'}}}).insert()
    source = await repo.ensure_initial(learner) if pinned else None
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: pinned)
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=learner)
    params = {'request_id': uuid4().hex, 'expected_attempts': 0}
    if source:
        params['enrollment_id'] = source.uuid
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        path = f'/certification/modules/{module}/complete'
        validate = service.validate_module
        spy = AsyncMock(wraps=validate)
        monkeypatch.setattr(service, 'validate_module', spy)
        missing = {k: v for k, v in params.items() if k != 'expected_attempts'}
        blocked = await client.post(path, params=missing)
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()['detail']['code'] == 'CERTIFICATION_COMPLETION_REVIEW_REQUIRED'
        spy.assert_not_awaited()
        records = AttemptRepository().records if pinned else legacy_completions.records()
        assert await records.count_documents({}) == 0
        first = await client.post(path, params=params)
        assert first.status_code == 200, first.text
        before = await repo.progress.find_one({'user_id': learner})
        repeated = await client.post(path, params={**params, 'request_id': uuid4().hex})
        assert repeated.status_code == 409, repeated.text
        assert repeated.json()['detail']['code'] == 'CERTIFICATION_COMPLETION_CHANGED'
        after = await repo.progress.find_one({'user_id': learner})
        # Acquiring a pinned write boundary advances its fence, even when no
        # learner state or attempt is changed.
        assert {k: v for k, v in after.items() if k != '_certification_write_fence'} == {k: v for k, v in before.items() if k != '_certification_write_fence'}
        assert before['modules'][module]['attempts'] == 1
        # The winner still replays its exact receipt despite its old precondition.
        replay = await client.post(path, params=params)
        assert replay.json() == first.json()
        without_counter = await client.post(path, params=missing)
        assert without_counter.status_code == 200 and without_counter.json() == first.json()
        blocked = await client.post(path, params={**missing, 'request_id': uuid4().hex})
        assert blocked.status_code == 409
        assert await records.count_documents({}) == 1
        spy.assert_awaited_once()
        # A separately reviewed request with the current counter is still allowed.
        fresh = await client.post(path, params={**params, 'request_id': uuid4().hex, 'expected_attempts': 1})
        assert fresh.status_code == 200, fresh.text
        assert fresh.json()['xp_earned'] == 0
        assert (await repo.progress.find_one({'user_id': learner}))['modules'][module]['attempts'] == 2


@pytest.mark.parametrize('pinned', [False, True])
async def test_chat_reads_counter_and_fences_new_requests_but_replays_old_receipts(repo, monkeypatch, pinned):
    from app.services import chat_tools
    learner, module = 'chat-precondition-learner', 'ai_literacy'
    await CertificationProgress(user_id=learner, modules={module: {'self_assessment': {
        'experience': 'Original', 'comfort': 'Original', 'concern': 'Original'}}}).insert()
    source = await repo.ensure_initial(learner) if pinned else None
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: pinned)
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    context = SimpleNamespace(deps=SimpleNamespace(user_id=learner))
    identity = {'enrollment_id': source.uuid} if source else {}
    initial = await chat_tools.get_certification_progress(context)
    row = next(row for row in initial['modules'] if row['module_id'] == module)
    assert row['attempts'] == 0
    details = await chat_tools.get_certification_module(context, module)
    assert details['attempts'] == 0
    request_id = uuid4().hex
    blocked = await chat_tools.complete_certification_module(context, module, request_id=request_id, **identity)
    assert "latest check result" in blocked['error']
    assert 'check_certification_module' in blocked['next_step']
    for malformed in (False, -1, '0'):
        rejected = await chat_tools.complete_certification_module(context, module, request_id=request_id, expected_attempts=malformed, **identity)
        assert 'nonnegative' in rejected['error']
    # The check hands over the counter the completion is fenced against.
    check = await chat_tools.check_certification_module(context, module, **identity)
    assert check['passed'] is True and check['expected_attempts'] == row['attempts'] == 0
    first = await chat_tools.complete_certification_module(context, module, request_id=request_id, expected_attempts=check['expected_attempts'], **identity)
    assert first['xp_earned'] == 125
    assert await chat_tools.complete_certification_module(context, module, request_id=request_id, **identity) == first
    stale = await chat_tools.complete_certification_module(context, module, request_id=uuid4().hex, expected_attempts=0, **identity)
    assert 'changed' in stale['error']
    details = await chat_tools.get_certification_module(context, module)
    assert details['attempts'] == 1
    fresh = await chat_tools.complete_certification_module(context, module, request_id=uuid4().hex, expected_attempts=details['attempts'], **identity)
    assert fresh['xp_earned'] == 0
