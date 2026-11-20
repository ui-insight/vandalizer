"""The combined module preview is authenticated, explicit and read-only."""
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.certification import CertificationScenarioAttempt
from app.routers.certification import router
from app.services.certification_versions import module_readiness, runtime
from tests.integration import test_certification_enrollments as existing

repo = existing.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def test_owned_preview_survives_disabled_delivery_without_creating_or_changing_work(repo, monkeypatch):
    source, package, bank, answers = await existing.scenario_fixture(repo)
    attempt_id = uuid4().hex
    await existing.submit_scenario(repo, source, package, bank, answers, attempt_id)
    monkeypatch.setattr(module_readiness, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
    path = '/certification/modules/ai_literacy/readiness'
    params = {'enrollment_id': source.uuid, 'scenario_attempt_id': attempt_id}
    before = await repo.progress.find_one({'user_id': source.user_id})
    attempts = CertificationScenarioAttempt.get_motor_collection()
    original = await attempts.find_one({'uuid': attempt_id})
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        empty = await client.get(path, params={'enrollment_id': source.uuid})
        assert empty.status_code == 200 and empty.json()['status'] == 'selection_required'
        response = await client.get(path, params=params)
        assert response.status_code == 200, response.text
        assert response.json()['all_required_outcomes_supported'] is True
        assert response.json()['credit_awarded'] is response.json()['module_completion_eligible'] is False
        assert response.json()['read_only'] is True
        assert (await client.post(path, params=params, json={'passed': True})).status_code == 405
        assert (await client.get(path)).status_code == 422
        assert (await client.get(path, params={**params, 'scenario_attempt_id': uuid4().hex})).status_code == 404
        assert (await client.get(path, params={**params, 'review_attempt_id': uuid4().hex})).status_code == 409
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign')
        assert (await client.get(path, params=params)).status_code == 409
        app.dependency_overrides.clear()
        assert (await client.get(path, params=params)).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
        await attempts.update_one({'uuid': attempt_id}, {'$set': {'record_sha256': '0' * 64}})
        corrupt = await client.get(path, params=params)
        assert corrupt.status_code == 503
        assert 'answers' not in corrupt.text and 'correct_choice' not in corrupt.text
        await attempts.replace_one({'uuid': attempt_id}, original)
    assert await attempts.find_one({'uuid': attempt_id}) == original
    assert await attempts.count_documents({}) == 1
    assert await repo.progress.find_one({'user_id': source.user_id}) == before
