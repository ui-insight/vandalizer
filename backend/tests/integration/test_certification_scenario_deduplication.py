"""Different tab request IDs must not create repeated deterministic assessments."""
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.certification import CertificationScenarioAttempt
from app.services.certification_versions import scenario_submissions
from tests.integration import test_certification_enrollments as base

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = base.pytestmark


async def test_separate_request_ids_reuse_one_scenario_result_and_never_award_credit(repo):
    source, package, bank, answers = await base.scenario_fixture(repo)
    original_id = uuid4().hex
    first = await base.submit_scenario(repo, source, package, bank, answers, original_id)
    for _ in range(3):
        second = await base.submit_scenario(repo, source, package, bank, answers, uuid4().hex)
        assert second['attempt_id'] == original_id
        assert second['result'] == first['result']
        assert second['linked_to_progress'] is True
        assert second['reused_existing'] is True
    assert await CertificationScenarioAttempt.get_motor_collection().count_documents({}) == 1
    progress = await repo.read_progress(source.user_id, source.uuid)
    assert progress.total_xp == 0 and not progress.certified


async def test_repeated_choices_do_not_replace_newer_changed_choices(repo):
    source, package, bank, answers = await base.scenario_fixture(repo)
    first_id, changed_id = uuid4().hex, uuid4().hex
    await base.submit_scenario(repo, source, package, bank, answers, first_id)
    await base.submit_scenario(repo, source, package, bank, {}, changed_id)
    second = await base.submit_scenario(repo, source, package, bank, answers, uuid4().hex)
    assert second['attempt_id'] == first_id and second['linked_to_progress'] is False
    assert (await repo.read_progress(source.user_id, source.uuid)).modules[bank.module_id]['scenario_attempt_id'] == changed_id
    assert await CertificationScenarioAttempt.get_motor_collection().count_documents({}) == 2


async def test_new_tab_recovers_unlinked_receipt_without_another_grade(repo):
    source, package, bank, answers = await base.scenario_fixture(repo)
    original_id = uuid4().hex
    with patch.object(scenario_submissions, 'save_progress', AsyncMock(side_effect=RuntimeError('Lost pointer save'))):
        with pytest.raises(RuntimeError, match='Lost pointer'):
            await base.submit_scenario(repo, source, package, bank, answers, original_id)
    with patch.object(scenario_submissions.ScenarioBank, 'grade', side_effect=AssertionError('Do not regrade identical choices')):
        result = await base.submit_scenario(repo, source, package, bank, answers, uuid4().hex)
    assert result['attempt_id'] == original_id and result['linked_to_progress'] is True
    assert await CertificationScenarioAttempt.get_motor_collection().count_documents({}) == 1


async def test_legacy_receipt_is_reused_without_backfill(repo):
    source, package, bank, answers = await base.scenario_fixture(repo)
    original_id = uuid4().hex
    await base.submit_scenario(repo, source, package, bank, answers, original_id)
    records = CertificationScenarioAttempt.get_motor_collection()
    await records.update_one({'uuid': original_id}, {'$unset': {'answers_sha256': ''}})
    before = await records.find_one({'uuid': original_id})
    with patch.object(scenario_submissions.ScenarioBank, 'grade', side_effect=AssertionError('No historical regrade')):
        result = await base.submit_scenario(repo, source, package, bank, answers, uuid4().hex)
    assert result['attempt_id'] == original_id
    assert await records.find_one({'uuid': original_id}) == before
    assert await records.count_documents({}) == 1


async def test_corrupt_answer_index_does_not_replay_a_receipt(repo):
    from app.services.certification_versions.catalog import CourseCatalogError
    source, package, bank, answers = await base.scenario_fixture(repo)
    original_id = uuid4().hex
    await base.submit_scenario(repo, source, package, bank, answers, original_id)
    records = CertificationScenarioAttempt.get_motor_collection()
    await records.update_one({'uuid': original_id}, {'$set': {'answers_sha256': '0' * 64}})
    with pytest.raises(CourseCatalogError, match='integrity'):
        await base.submit_scenario(repo, source, package, bank, answers, original_id)
    assert await records.count_documents({}) == 1


async def test_unique_answer_identity_converges_concurrent_repository_calls(repo):
    import asyncio
    from app.services.certification_versions.runtime import CourseOperation
    source, package, bank, answers = await base.scenario_fixture(repo)
    repository = scenario_submissions.ScenarioSubmissionRepository()
    async with repo.write_boundary(source.user_id, source.uuid, operation='submit_scenario_assessment') as progress:
        operation = CourseOperation(source.user_id, package, progress, True)
        results = await asyncio.gather(*(repository.submit(operation, bank.module_id, uuid4().hex, bank.digest, answers,
            actor_user_id=source.user_id) for _ in range(8)))
    assert len({item['attempt_id'] for item in results}) == 1
    assert sum(item['reused_existing'] is False for item in results) == 1
    assert await repository.records.count_documents({}) == 1


async def test_http_separate_tabs_preserve_one_owned_result(versioned_runtime):
    import asyncio
    from types import SimpleNamespace
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.dependencies import get_current_user
    from app.routers.certification import router
    repository = versioned_runtime
    source, package, bank, answers = await base.scenario_fixture(repository)
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
    bodies = [{'request_id': uuid4().hex, 'bank_sha256': bank.digest, 'answers': answers} for _ in range(8)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        path = '/certification/modules/ai_literacy/scenarios'
        params = {'enrollment_id': source.uuid}
        responses = await asyncio.gather(*(client.post(path, params=params, json=body) for body in bodies))
        assert all(response.status_code in (200, 409) for response in responses)
        assert any(response.status_code == 200 for response in responses)
        canonical = {response.json()['attempt_id'] for response in responses if response.status_code == 200}
        for body in bodies:
            response = await client.post(path, params=params, json=body)
            assert response.status_code == 200, response.text
            canonical.add(response.json()['attempt_id'])
        assert len(canonical) == 1
        receipt = await client.get('/certification/scenario-attempts/' + next(iter(canonical)))
        assert receipt.status_code == 200 and receipt.json()['answers'] == answers
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign-learner')
        assert (await client.get('/certification/scenario-attempts/' + next(iter(canonical)))).status_code == 404
    assert await CertificationScenarioAttempt.get_motor_collection().count_documents({}) == 1
    assert (await repository.read_progress(source.user_id, source.uuid)).total_xp == 0


async def test_identical_choices_belonging_to_another_learner_remain_separate(repo):
    source, package, bank, answers = await base.scenario_fixture(repo)
    other = await repo.ensure_initial('another-scenario-learner')
    first = await base.submit_scenario(repo, source, package, bank, answers, uuid4().hex)
    second = await base.submit_scenario(repo, other, package, bank, answers, uuid4().hex)
    assert first['attempt_id'] != second['attempt_id']
    assert first['reused_existing'] is False and second['reused_existing'] is False
    assert await CertificationScenarioAttempt.get_motor_collection().count_documents({}) == 2
    repository = scenario_submissions.ScenarioSubmissionRepository()
    assert await repository.get(source.user_id, second['attempt_id']) is None
    assert await repository.get(other.user_id, first['attempt_id']) is None
