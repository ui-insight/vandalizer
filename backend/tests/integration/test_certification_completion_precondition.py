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
        # A separately reviewed request with the current counter is still allowed.
        fresh = await client.post(path, params={**params, 'request_id': uuid4().hex, 'expected_attempts': 1})
        assert fresh.status_code == 200, fresh.text
        assert fresh.json()['xp_earned'] == 0
        assert (await repo.progress.find_one({'user_id': learner}))['modules'][module]['attempts'] == 2
