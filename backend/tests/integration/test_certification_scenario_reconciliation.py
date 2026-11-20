"""Lost scenario responses are checked without regrading or linking progress."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.certification import CertificationScenarioAttempt
from app.routers.certification import router
from app.services.certification_versions import scenario_submissions
from tests.integration import test_certification_enrollments as base

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = base.pytestmark


@pytest.mark.parametrize('state', ['selected', 'unlinked', 'superseded', 'unavailable'])
async def test_http_check_reads_original_result_and_link_without_writing(versioned_runtime, monkeypatch, state):
    repository = versioned_runtime
    source, package, bank, answers = await base.scenario_fixture(repository)
    request_id = uuid4().hex
    if state == 'unlinked':
        with monkeypatch.context() as scoped:
            scoped.setattr(scenario_submissions, 'save_progress', AsyncMock(side_effect=RuntimeError('Lost link save')))
            with pytest.raises(RuntimeError, match='Lost link save'):
                await base.submit_scenario(repository, source, package, bank, answers, request_id)
    else:
        await base.submit_scenario(repository, source, package, bank, answers, request_id)
    if state == 'superseded':
        await base.submit_scenario(repository, source, package, bank, {}, uuid4().hex)
    elif state == 'unavailable':
        await repository.progress.delete_many({'user_id': source.user_id})
    before = await repository.progress.find_one({'user_id': source.user_id})
    records = await CertificationScenarioAttempt.get_motor_collection().find({}).to_list(None)
    # Original receipts remain inspectable even without the current catalog.
    (repository.catalog.root / 'registry.json').unlink()
    grade = AsyncMock(side_effect=AssertionError('Read-only check must not grade'))
    save = AsyncMock(side_effect=AssertionError('Read-only check must not save'))
    monkeypatch.setattr(scenario_submissions.ScenarioBank, 'grade', grade)
    monkeypatch.setattr(scenario_submissions, 'save_progress', save)
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        path = '/certification/scenario-attempts/' + request_id
        response = await client.get(path)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['read_only'] is True and body['progress_link'] == state
        assert body['answers'] == answers and body['uuid'] == request_id
        assert body['result']['passed'] is True and body['result']['credit_awarded'] is False
        assert (await client.get(path)).json() == body
        assert (await client.get('/certification/scenario-attempts/' + uuid4().hex)).status_code == 404
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='another-user')
        assert (await client.get(path)).status_code == 404
    assert await repository.progress.find_one({'user_id': source.user_id}) == before
    assert await CertificationScenarioAttempt.get_motor_collection().find({}).to_list(None) == records
    grade.assert_not_called()
    save.assert_not_awaited()


async def test_check_refuses_corrupt_receipt_without_overwriting_it(versioned_runtime):
    repository = versioned_runtime
    source, package, bank, answers = await base.scenario_fixture(repository)
    request_id = uuid4().hex
    await base.submit_scenario(repository, source, package, bank, answers, request_id)
    records = CertificationScenarioAttempt.get_motor_collection()
    await records.update_one({'uuid': request_id}, {'$set': {'record_json': '{}'}})
    before = await records.find_one({'uuid': request_id})
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/certification/scenario-attempts/' + request_id)
        assert response.status_code == 503
    assert await records.find_one({'uuid': request_id}) == before


@pytest.mark.parametrize('damage', ['cleared_previous', 'invalid_current', 'changed_manifest', 'changed_progress'])
async def test_receipt_remains_readable_without_claiming_an_unverified_progress_link(versioned_runtime, damage):
    repository = versioned_runtime
    source, package, bank, answers = await base.scenario_fixture(repository)
    await base.submit_scenario(repository, source, package, bank, {}, uuid4().hex)
    request_id = uuid4().hex
    await base.submit_scenario(repository, source, package, bank, answers, request_id)
    if damage == 'cleared_previous':
        await repository.progress.update_one({'user_id': source.user_id}, {'$unset': {'modules.ai_literacy.scenario_attempt_id': ''}})
    elif damage == 'invalid_current':
        await repository.progress.update_one({'user_id': source.user_id}, {'$set': {'modules.ai_literacy.scenario_attempt_id': 'invalid'}})
    elif damage == 'changed_manifest':
        await repository.enrollments.update_one({'uuid': source.uuid}, {'$set': {'manifest_sha256': '0' * 64}})
    else:
        await repository.progress.update_one({'user_id': source.user_id}, {'$set': {'course_version': 'another-course'}})
    before = await repository.progress.find_one({'user_id': source.user_id})
    result = await scenario_submissions.ScenarioSubmissionRepository().status(source.user_id, request_id)
    assert result['uuid'] == request_id and result['answers'] == answers
    assert result['progress_link'] == 'unavailable' and result['read_only'] is True
    assert await repository.progress.find_one({'user_id': source.user_id}) == before
