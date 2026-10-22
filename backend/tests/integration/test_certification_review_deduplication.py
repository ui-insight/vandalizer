"""Different tab request IDs must not grade identical saved evidence twice."""
import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest

from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.review_attempts import ReviewAttemptRepository
from app.services.certification_versions.runtime import CourseOperation
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark


async def prepare(repo, source, package, evidence, request_id=None, provenance=None):
    async with repo.write_boundary(source.user_id, source.uuid, operation='prepare_trusted_review') as progress:
        return await ReviewAttemptRepository().prepare(
            CourseOperation(source.user_id, package, progress, True), 'foundations', evidence,
            request_id or uuid4().hex, actor_user_id=source.user_id,
            model_name='synthetic-reviewer', system_config=base.REVIEW_CONFIG,
            _provenance=provenance or {'record_kind': 'saved_practical_run', 'run_id': 'b' * 32})


@pytest.mark.parametrize('state', ['prepared', 'evaluating', 'evaluated', 'unavailable', 'legacy'])
async def test_other_tab_gets_original_reference_without_another_attempt(repo, state):
    source, package, evidence = await base.review_fixture(repo)
    first = await prepare(repo, source, package, evidence)
    reviews = ReviewAttemptRepository()
    if state in ('evaluated', 'unavailable'):
        async def model(*args):
            if state == 'unavailable':
                raise RuntimeError('Synthetic provider outage')
            return await base.supported_review(*args)
        await base.evaluate_review(repo, source, package, first['attempt_id'], model)
    elif state == 'evaluating':
        await reviews.records.update_one({'uuid': first['attempt_id']}, {'$set': {'state': 'evaluating'}})
    elif state == 'legacy':
        await reviews.records.update_one({'uuid': first['attempt_id']}, {'$unset': {'evidence_request_sha256': ''}})
    before = await reviews.records.find({}).to_list(None)
    with pytest.raises(EnrollmentConflict) as caught:
        await prepare(repo, source, package, evidence)
    assert caught.value.detail['code'] == 'CERTIFICATION_REVIEW_EXISTS'
    assert caught.value.detail['attempt_id'] == first['attempt_id']
    assert await reviews.records.find({}).to_list(None) == before
    assert (await repo.read_progress(source.user_id, source.uuid)).total_xp == 0


async def test_same_reference_replays_but_revised_evidence_gets_a_new_attempt(repo):
    source, package, evidence = await base.review_fixture(repo)
    first = await prepare(repo, source, package, evidence)
    assert await prepare(repo, source, package, evidence, first['attempt_id']) == first
    revised = deepcopy(evidence)
    revised[0]['text'] += '\nA newly saved decision.'
    second = await prepare(repo, source, package, revised)
    assert second['attempt_id'] != first['attempt_id']
    assert await ReviewAttemptRepository().records.count_documents({}) == 2


async def test_concurrent_different_references_claim_only_one_evidence_packet(repo):
    source, package, evidence = await base.review_fixture(repo)
    reviews = ReviewAttemptRepository()
    async with repo.write_boundary(source.user_id, source.uuid, operation='prepare_trusted_review') as progress:
        operation = CourseOperation(source.user_id, package, progress, True)
        async def request():
            return await reviews.prepare(operation, 'foundations', evidence, uuid4().hex,
                actor_user_id=source.user_id, model_name='synthetic-reviewer', system_config=base.REVIEW_CONFIG,
                _provenance={'record_kind': 'saved_practical_run', 'run_id': 'b' * 32})
        results = await asyncio.gather(*(request() for _ in range(8)), return_exceptions=True)
    saved = [item for item in results if isinstance(item, dict)]
    conflicts = [item for item in results if isinstance(item, EnrollmentConflict)]
    assert len(saved) == 1 and len(conflicts) == 7
    assert {item.detail['attempt_id'] for item in conflicts} == {saved[0]['attempt_id']}
    assert await reviews.records.count_documents({}) == 1

versioned_runtime = base.versioned_runtime


async def test_http_other_tab_recovers_original_result_without_another_model_call(versioned_runtime, monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.dependencies import get_current_user
    from app.routers.certification import router
    source, _, _, run, _, payload, _, model, service = await base.assessment_delivery_fixture(versioned_runtime, monkeypatch)
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
    params = {'enrollment_id': source.uuid}
    path = '/certification/practical-runs/' + run['run_id'] + '/automatic-reviews'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        first = await client.post(path, params=params, json=payload.model_dump())
        assert first.status_code == 200, first.text
        for _ in range(3):
            second = await client.post(path, params=params, json={**payload.model_dump(), 'request_id': uuid4().hex})
            assert second.status_code == 409, second.text
            assert second.json()['detail']['code'] == 'CERTIFICATION_REVIEW_EXISTS'
            original_id = second.json()['detail']['attempt_id']
            assert original_id == first.json()['attempt_id']
            recovered = await client.get('/certification/automatic-reviews/' + original_id, params=params)
            assert recovered.json() == first.json()
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='another-learner')
        foreign = await client.post(path, params=params, json={**payload.model_dump(), 'request_id': uuid4().hex})
        assert foreign.status_code == 409
        assert not isinstance(foreign.json()['detail'], dict)
    assert model.await_count == 1
    assert await service.reviews.records.count_documents({}) == 1
    assert (await versioned_runtime.read_progress(source.user_id, source.uuid)).total_xp == 0


async def test_trusted_technical_retry_stays_explicit_and_cannot_fork(repo):
    from unittest.mock import AsyncMock
    source, package, evidence = await base.review_fixture(repo)
    original = await prepare(repo, source, package, evidence)
    await base.evaluate_review(repo, source, package, original['attempt_id'], AsyncMock(side_effect=RuntimeError('Synthetic outage')))
    child = await base.retry_review(repo, source, package, original['attempt_id'])
    with pytest.raises(EnrollmentConflict) as caught:
        await base.retry_review(repo, source, package, original['attempt_id'])
    assert caught.value.detail['attempt_id'] == child['attempt_id']
    assert await ReviewAttemptRepository().records.count_documents({}) == 2


async def test_changed_provenance_allows_new_work_but_corrupt_duplicate_key_fails_closed(repo):
    from app.services.certification_versions.catalog import CourseCatalogError
    source, package, evidence = await base.review_fixture(repo)
    original = await prepare(repo, source, package, evidence)
    revised = await prepare(repo, source, package, evidence,
        provenance={'record_kind': 'saved_practical_run', 'run_id': 'c' * 32})
    assert revised['attempt_id'] != original['attempt_id']
    reviews = ReviewAttemptRepository()
    await reviews.records.update_one({'uuid': original['attempt_id']}, {'$set': {'evidence_request_sha256': 'f' * 64}})
    with pytest.raises(CourseCatalogError, match='integrity'):
        await reviews.get(source.user_id, original['attempt_id'])
