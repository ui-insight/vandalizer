"""Authenticated bounded Batch HTTP journey and preserved complete-source history."""
import hashlib
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_batch_inputs as inputs
from tests.integration import test_certification_batch_execution as execution
from app.dependencies import get_current_user
from app.models.certification import CertificationLabInput, CertificationLabExecution, CertificationLearnerDecision
from app.routers.certification import router
from app.services.certification_versions import batch_delivery, practical_preparation, automatic_review, review_delivery, course_history, runtime
from app.services.certification_versions.delivery import public_modules

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo, monkeypatch):
    from app.services.extraction_engine import ExtractionEngine
    f = await inputs.fixture(repo)
    f.config = {**base.LAB_RUNTIME, 'available_models': base.LAB_RUNTIME['available_models'] + base.REVIEW_CONFIG['available_models'],
                'validation_judge_model': 'synthetic-reviewer'}
    f.settings = AsyncMock(return_value=f.config)
    f.provider = Mock(side_effect=execution.provider(f))
    f.judge = AsyncMock(side_effect=base.supported_review)
    monkeypatch.setattr(ExtractionEngine, 'extract', f.provider)
    monkeypatch.setattr(batch_delivery, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(batch_delivery, 'get_storage', lambda: f.storage)
    monkeypatch.setattr(review_delivery, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(course_history, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(practical_preparation, 'configured_runtime', f.settings)
    monkeypatch.setattr(automatic_review, '_call_model', f.judge)
    f.app = FastAPI()
    f.app.include_router(router, prefix='/certification')
    f.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=f.learner.user_id)
    f.client = AsyncClient(transport=ASGITransport(app=f.app), base_url='http://test')
    return f


async def post(client, path, params, body):
    response = await client.post('/certification/' + path, params=params, json=body)
    assert response.status_code == 200, response.text
    for private in ('source_pdf_base64', 'authored_case', 'review_guidance', 'synthetic-secret'):
        assert private not in response.text
    return response.json()


async def plan_and_run(f, client, params, captured, phase, parent=None):
    body = {'request_id': uuid4().hex, 'input_snapshot_id': captured['uuid'],
        'input_snapshot_sha256': captured['input_snapshot_sha256'], 'case_sha256': f.case.digest,
        'phase': phase, 'consent': 'prepare_bounded_batch_action'}
    if parent:
        body.update(parent_run_id=parent['run_id'], parent_run_sha256=parent['run_sha256'])
    if phase == 'retry':
        body['failed_source_id'] = 'proposal_2'
    run = await post(client, 'modules/batch_processing/batch-runs', params, body)
    assert run['can_save_scope'] and not run['can_execute']
    approved = await post(client, 'batch-runs/scope', params, {'request_id': uuid4().hex,
        'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'], 'case_sha256': f.case.digest,
        'choice': 'approve', 'reason': 'I checked this exact phase, the assigned source values, actual pilot results and bounded model scope; costs and wider reliability remain unknown.',
        'consent': 'save_bounded_batch_scope_decision'})
    execute_body = {key: approved[key] for key in ('run_id', 'plan_sha256', 'scope_decision_id', 'scope_decision_sha256')}
    execute_body['consent'] = 'execute_approved_bounded_batch_action'
    completed = await post(client, 'batch-runs/execute', params, execute_body)
    assert completed['state'] == 'completed' and len(completed['item_events']) == {'pilot': 4, 'batch': 6, 'retry': 2}[phase]
    assert await post(client, 'batch-runs/execute', params, execute_body) == completed
    return completed


@pytest.mark.parametrize('technical_retry', [False, True])
async def test_complete_http_batch_journey_and_preserved_originals(versioned_runtime, monkeypatch, technical_retry):
    repo = versioned_runtime
    f = await fixture(repo, monkeypatch)
    params = {'enrollment_id': f.learner.uuid}
    prefix = 'modules/batch_processing/'
    async with f.client as client:
        listing = await client.get('/certification/' + prefix + 'batch-work', params=params)
        assert listing.status_code == 200, listing.text
        assert listing.json()['extractions'] == [{'artifact_id': f.artifact.uuid, 'title': f.artifact.title}]
        captured = await post(client, prefix + 'batch-captures', params, f.body)
        f.snapshot = await batch_delivery.BatchInputRepository().get(f.learner.user_id, captured['uuid'])
        pilot = await plan_and_run(f, client, params, captured, 'pilot')
        original = await plan_and_run(f, client, params, captured, 'batch', pilot)
        assert not original['result']['checks']['all_items_completed']
        retry = await plan_and_run(f, client, params, captured, 'retry', original)
        assert retry['result']['checks']['all_values_source_supported']
        assert retry['parent_run']['run_sha256'] == original['run_sha256']
        assert retry['parent_run']['can_execute'] is False
        reviewed = await post(client, prefix + 'batch-reviews', params, {'request_id': uuid4().hex,
            'run_id': original['run_id'], 'result_sha256': original['result_sha256'], 'case_sha256': f.case.digest,
            'retries': [{'run_id': retry['run_id'], 'result_sha256': retry['result_sha256']}],
            'answers': {'batch_review': 'All three original input IDs have terminal receipts. Proposal 2 was the disclosed training rejection before model dispatch, and only that item was retried. Proposals 1 and 3 remain unchanged. The recovered five values support the source and preserve the original failure. This shared-template pilot does not establish reliability on other layouts; elapsed time is measured but usage and cost remain unknown.'},
            'consent': 'save_batch_recovery_interpretation'})
        assert reviewed['reconciliation']['targeted_recovery_supported']
        if technical_retry:
            f.judge.side_effect = RuntimeError('Synthetic judge unavailable')
        assessment_body = {'request_id': uuid4().hex, 'consent': 'assess_saved_work'}
        assessed = await post(client, 'batch-reviews/' + reviewed['uuid'] + '/automatic-reviews', params, assessment_body)
        if technical_retry:
            assert assessed['status'] == 'grading_unavailable'
            f.judge.side_effect = base.supported_review
            assessed = await post(client, 'batch-automatic-reviews/' + assessed['attempt_id'] + '/retry', params,
                {'request_id': uuid4().hex, 'consent': 'retry_saved_assessment'})
        assert assessed['status'] == 'requirements_supported'
        assert assessed['credit_awarded'] is assessed['staff_review_required'] is False
        for origin, reference in [('capture', captured['uuid']), ('run', retry['run_id']), ('review', reviewed['uuid'])]:
            for source in f.case.sources:
                response = await client.get(f'/certification/batch-sources/{origin}/{reference}/{source.id}', params=params)
                assert response.status_code == 200, response.text
                assert hashlib.sha256(response.content).hexdigest() == source.sha256
                assert response.headers['cache-control'] == 'private, no-store'
                assert response.headers['x-content-type-options'] == 'nosniff'
        await CertificationLabInput.get_motor_collection().delete_many({})
        await CertificationLabExecution.get_motor_collection().delete_many({})
        await CertificationLearnerDecision.get_motor_collection().delete_many({'uuid': {'$ne': reviewed['uuid']}})
        for document in f.documents:
            await document.delete()
        await f.artifact.delete()
        f.settings.reset_mock()
        f.settings.side_effect = RuntimeError('Live settings unavailable')
        replay = await post(client, 'batch-reviews/' + reviewed['uuid'] + '/automatic-reviews', params, assessment_body)
        assert replay['status'] == ('grading_unavailable' if technical_retry else 'requirements_supported')
        monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
        history = await client.get('/certification/batch-reviews/' + reviewed['uuid'], params=params)
        assert history.status_code == 200, history.text
        assert history.json() == reviewed
        response = await client.get(f'/certification/batch-sources/review/{reviewed["uuid"]}/proposal_1', params=params)
        assert hashlib.sha256(response.content).hexdigest() == f.case.sources[0].sha256
        assert (await client.post('/certification/' + prefix + 'batch-captures', params=params, json=f.body)).status_code == 404
        f.settings.assert_not_awaited()
        f.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign')
        foreign = await client.get('/certification/batch-reviews/' + reviewed['uuid'], params=params)
        assert foreign.status_code in (404, 409)
    assert f.provider.call_count == 5
    assert f.judge.await_count == (2 if technical_retry else 1)
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_public_discovery_preserves_bounded_batch_assignment(versioned_runtime, monkeypatch):
    f = await fixture(versioned_runtime, monkeypatch)
    module = next(m for m in public_modules(f.package) if m['id'] == 'batch_processing')
    assert module['batchAssessment'] == f.case.public_definition()
    history = await course_history.CourseHistory(versioned_runtime).course(f.learner.user_id, f.learner.uuid)
    saved = next(m for m in history['modules'] if m['module_id'] == 'batch_processing')
    assert saved['batch_definition'] == f.case.public_definition()
