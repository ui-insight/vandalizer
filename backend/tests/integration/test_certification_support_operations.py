"""Saved operation support uses real persisted requests with stubbed providers."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.dependencies import get_current_user
from app.routers import admin
from app.services.certification_versions import enrollments, readers
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.review_attempts import ReviewAttemptRepository
from app.services.certification_versions.lab_execution import LabExecutionRepository
from tests.integration import test_certification_enrollments as base
from tests.integration.test_certification_support_snapshot import snapshot

repo = base.repo
pytestmark = base.pytestmark


async def setup(repo, monkeypatch):
    source, package, document, inputs, run, _ = await base.trusted_review_fixture(repo)
    prepared = await base.prepare_trusted_review(repo, source, package, run['run_id'])
    monkeypatch.setattr(readers, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(enrollments, 'EnrollmentRepository', lambda: repo)
    app = FastAPI()
    app.include_router(admin.router, prefix='/admin')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='operator', is_admin=False, is_staff=True)
    client = AsyncClient(transport=ASGITransport(app=app), base_url='http://test')
    return source, package, document, inputs, run, prepared, client


async def read(client, source):
    response = await client.get('/admin/certifications/' + source.user_id, params={'enrollment_id': source.uuid})
    assert response.status_code == 200, response.text
    return response.json()['support_summary']['operations']


@pytest.mark.parametrize('state', ['prepared', 'evaluating', 'requirements_supported', 'grading_unavailable', 'revision_required'])
async def test_saved_review_and_run_state_excludes_private_work_and_never_dispatches_again(repo, monkeypatch, state):
    source, package, document, inputs, run, prepared, client = await setup(repo, monkeypatch)
    async def revise(*args):
        result = await base.supported_review(*args)
        for outcome in result['outcomes']:
            outcome.update(verdict='contradicted', explanation='PRIVATE SOURCE FEEDBACK', revision_instruction='PRIVATE LEARNER TEXT')
        return result
    judge = AsyncMock(side_effect=RuntimeError('PRIVATE PROVIDER DIAGNOSTIC') if state == 'grading_unavailable' else revise if state == 'revision_required' else base.supported_review)
    if state in ('requirements_supported', 'grading_unavailable', 'revision_required'):
        await base.evaluate_review(repo, source, package, prepared['attempt_id'], judge)
    if state == 'evaluating':
        await ReviewAttemptRepository().records.update_one({'uuid': prepared['attempt_id']}, {'$set': {'state': 'evaluating'}})
        await repo.selections.update_one({'user_id': source.user_id}, {'$set': {'in_flight_writes': 1}})
    before, calls = await snapshot(repo), judge.await_count
    async with client:
        operations = await read(client, source)
        assert await read(client, source) == operations
    groups = {group['kind']: group for group in operations['groups']}
    review = groups['automatic_review']['records'][0]
    execution = groups['lab_run']['records'][0]
    assert review['request_id'] == prepared['attempt_id'] and review['state'] == state
    assert review['references'] == {'run_id': run['run_id']}
    assert execution['request_id'] == run['run_id'] and execution['state'] == 'completed'
    assert execution['references'] == {'input_snapshot_id': inputs['uuid']}
    assert 'Execution alone does not prove' in execution['next_step']
    if state == 'grading_unavailable':
        assert 'not a learner failure' in review['next_step']
    if state == 'revision_required':
        assert review['failed_required_outcomes']
    assert operations['worker_marked_in_flight'] is (state == 'evaluating')
    rendered = json.dumps(operations)
    assert 'PRIVATE' not in rendered
    assert 'private-review-key' not in rendered and 'Synthetic value' not in rendered
    assert document.uuid not in rendered and 'plan_json' not in rendered and 'record_json' not in rendered
    assert await snapshot(repo) == before and judge.await_count == calls


@pytest.mark.parametrize('corruption', ['digest', 'course', 'semantic_result', 'private_reference'])
async def test_corrupt_review_returns_only_fixed_reconciliation_guidance(repo, monkeypatch, corruption):
    source, package, _, _, _, prepared, client = await setup(repo, monkeypatch)
    records = ReviewAttemptRepository().records
    changes = {}
    if corruption == 'digest':
        changes['record_sha256'] = 'bad'
    elif corruption == 'course':
        changes['manifest_sha256'] = 'bad'
    elif corruption == 'semantic_result':
        await base.evaluate_review(repo, source, package, prepared['attempt_id'], base.supported_review)
        raw = await records.find_one({'uuid': prepared['attempt_id']})
        result = json.loads(raw['result_json'])
        result['assessment']['outcomes'].pop()
        changes['result_json'], changes['result_sha256'] = encode(result)
    else:
        raw = await records.find_one({'uuid': prepared['attempt_id']})
        record = json.loads(raw['record_json'])
        record['provenance']['run_id'] = 'PRIVATE FAKE REFERENCE'
        changes['record_json'], changes['record_sha256'] = encode(record)
    await records.update_one({'uuid': prepared['attempt_id']}, {'$set': changes})
    before = await snapshot(repo)
    async with client:
        operations = await read(client, source)
    review = operations['groups'][0]['records'][0]
    assert review['state'] == 'unavailable' and set(review) == {'state', 'next_step'}
    assert 'PRIVATE' not in json.dumps(operations)
    assert await snapshot(repo) == before


async def test_older_pending_request_survives_bounded_newer_history_and_other_owner_is_excluded(repo, monkeypatch):
    source, _, _, _, _, prepared, client = await setup(repo, monkeypatch)
    records = ReviewAttemptRepository().records
    # Invalid synthetic newer rows establish ordering/cap behavior, never grades.
    for _ in range(7):
        await records.insert_one({'uuid': uuid4().hex, 'user_id': source.user_id, 'enrollment_id': source.uuid, 'state': 'evaluated'})
    await records.insert_one({'uuid': 'f' * 32, 'user_id': 'other-owner', 'enrollment_id': source.uuid, 'state': 'prepared'})
    async with client:
        operations = await read(client, source)
    group = operations['groups'][0]
    assert group['more_recent'] is True and group['more_pending'] is False
    assert len(group['records']) == 6
    assert group['records'][0]['request_id'] == prepared['attempt_id']
    assert 'f' * 32 not in json.dumps(operations)


async def test_corrupt_run_does_not_hide_valid_review_or_expose_plan(repo, monkeypatch):
    source, _, _, _, run, _, client = await setup(repo, monkeypatch)
    await LabExecutionRepository().records.update_one({'uuid': run['run_id']}, {'$set': {'plan_sha256': 'PRIVATE CORRUPT'}})
    async with client:
        operations = await read(client, source)
    assert operations['groups'][0]['records'][0]['state'] == 'prepared'
    assert operations['groups'][1]['records'][0]['state'] == 'unavailable'
    assert 'PRIVATE' not in json.dumps(operations)


@pytest.mark.parametrize('family', ['advanced_workflow', 'output_workflow', 'validation', 'batch', 'governance'])
async def test_each_specialized_run_is_decoded_by_its_original_integrity_reader(repo, family):
    import importlib
    from app.services.certification_versions.support_operations import support_operations
    fixtures = importlib.import_module('tests.integration.test_certification_' + family + '_preparation')
    f = await fixtures.fixture(repo)
    run = await fixtures.prepare(repo, f)
    before = await snapshot(repo)
    operations = await support_operations(f.learner, f.package)
    rows = operations['groups'][1]['records']
    row = next(item for item in rows if item.get('request_id') == run['run_id'])
    assert row['state'] == 'prepared' and row['references']['input_snapshot_id'] == run['plan']['input_snapshot_id']
    assert await snapshot(repo) == before
    # Rehashing a changed request must still fail the workflow-specific checks.
    raw = await LabExecutionRepository().records.find_one({'uuid': run['run_id']})
    plan = json.loads(raw['plan_json'])
    plan['request_sha256'] = 'b' * 64
    serialized, digest = encode(plan)
    await LabExecutionRepository().records.update_one({'uuid': run['run_id']}, {'$set': {'plan_json': serialized, 'plan_sha256': digest}})
    operations = await support_operations(f.learner, f.package)
    assert operations['groups'][1]['records'][0]['state'] == 'unavailable'


async def test_connected_run_reads_its_original_stage_receipts_without_dispatch(repo):
    from app.services.certification_versions.support_operations import support_operations
    fixture, prepared = await base.checkpoint_fixture(repo)
    source, package = fixture[:2]
    before = await snapshot(repo)
    operations = await support_operations(source, package)
    row = next(item for item in operations['groups'][1]['records'] if item.get('request_id') == prepared['run_id'])
    assert row['module_id'] == 'multi_step' and row['state'] == 'prepared'
    assert await snapshot(repo) == before
