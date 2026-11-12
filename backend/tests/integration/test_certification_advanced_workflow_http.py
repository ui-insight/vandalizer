"""Authenticated budget actions and private-data-free original history."""
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from tests.integration import test_certification_enrollments as enrollment_fixtures
from tests.integration import test_certification_advanced_workflow_plan as planning_fixtures
from app.dependencies import get_current_user
from app.models.certification import CertificationLabInput
from app.routers.certification import router
from app.services.certification_versions import (advanced_workflow_delivery, practical_preparation, automatic_review,
    review_delivery, course_history, runtime)

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = enrollment_fixtures.repo
versioned_runtime = enrollment_fixtures.versioned_runtime


async def fixture(repo, monkeypatch):
    from app.services import workflow_engine
    f = await planning_fixtures.fixture(repo)
    f.config = {**planning_fixtures.RUNTIME,
        'available_models': planning_fixtures.RUNTIME['available_models'] + enrollment_fixtures.REVIEW_CONFIG['available_models'],
        'default_model': 'review-model', 'validation_judge_model': 'synthetic-reviewer'}
    f.settings = AsyncMock(return_value=f.config)
    f.judge = AsyncMock(side_effect=enrollment_fixtures.supported_review)
    f.calls = []

    def provider(**kwargs):
        f.calls.append(kwargs['prompt'])
        return 'RESULT: ' + kwargs['prompt']

    monkeypatch.setattr(workflow_engine, 'llm_chat_model', provider)
    monkeypatch.setattr(advanced_workflow_delivery, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(advanced_workflow_delivery, 'get_storage', lambda: f.storage)
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
    for private in ('source_pdf_base64', 'authored_case', 'review_guidance', 'expected_value', 'engine_steps'):
        assert private not in response.text
    return response.json()


@pytest.mark.parametrize('technical_retry', [False, True])
async def test_full_http_budget_journey_preserves_calculations_and_graded_history(versioned_runtime, monkeypatch, technical_retry):
    repo = versioned_runtime
    f = await fixture(repo, monkeypatch)
    params = {'enrollment_id': f.learner.uuid}
    prefix = 'modules/advanced_nodes/'
    async with f.client as client:
        listed = await client.get('/certification/' + prefix + 'budget-workflows', params=params)
        assert listed.status_code == 200, listed.text
        assert len(listed.json()['calculations']) == len(listed.json()['captures']) == 1
        assert listed.json()['assigned_sources'][0]['document_id'] == f.document.uuid
        assert 'expected_value' not in listed.text
        calculation = await post(client, prefix + 'budget-calculations', params, {**f.body, 'request_id': uuid4().hex})
        assert calculation['checks']['all_arithmetic_supported'] is False
        assert (await client.get('/certification/budget-calculations/' + calculation['uuid'], params=params)).json() == calculation
        capture_body = {**f.capture_body, 'request_id': uuid4().hex, 'calculation_snapshot_id': calculation['uuid'],
                        'calculation_snapshot_sha256': calculation['calculation_snapshot_sha256']}
        captured = await post(client, prefix + 'budget-captures', params, capture_body)
        prepared = await post(client, prefix + 'budget-runs', params, {'request_id': uuid4().hex,
            'input_snapshot_id': captured['uuid'], 'input_snapshot_sha256': captured['input_snapshot_sha256'],
            'case_sha256': f.case.digest, 'consent': 'prepare_budget_workflow_plan'})
        assert prepared['can_execute'] is False and prepared['can_save_scope'] is True
        scope_body = {'request_id': uuid4().hex, 'run_id': prepared['run_id'], 'plan_sha256': prepared['plan_sha256'],
            'case_sha256': f.case.digest, 'choice': 'approve', 'reason': 'I approve only the saved internal memo on this source and these calculations.',
            'consent': 'save_budget_workflow_scope_decision'}
        approved = await post(client, 'budget-runs/scope', params, scope_body)
        execute_body = {key: approved[key] for key in ('run_id', 'plan_sha256', 'scope_decision_id', 'scope_decision_sha256')}
        execute_body['consent'] = 'execute_approved_budget_workflow'
        completed = await post(client, 'budget-runs/execute', params, execute_body)
        assert completed['state'] == 'completed' and len(completed['task_events']) == 6
        review = await post(client, prefix + 'budget-reviews', params, {'request_id': uuid4().hex,
            'run_id': completed['run_id'], 'result_sha256': completed['result_sha256'], 'case_sha256': f.case.digest,
            'answers': {'calculation_review': 'The stored equipment result is wrong. These additions do not establish policy or compatible periods.',
                        'dependency_review': 'Both source reviews finish before the memo consumes their outputs and the saved calculation record.'},
            'consent': 'save_budget_calculation_and_dependency_review'})
        if technical_retry:
            f.judge.side_effect = RuntimeError('Synthetic judge offline')
        assessment_body = {'request_id': uuid4().hex, 'consent': 'assess_saved_work'}
        assessment = await post(client, 'budget-reviews/' + review['uuid'] + '/automatic-reviews', params, assessment_body)
        if technical_retry:
            assert assessment['status'] == 'grading_unavailable'
            f.judge.side_effect = enrollment_fixtures.supported_review
            assessment = await post(client, 'budget-automatic-reviews/' + assessment['attempt_id'] + '/retry', params,
                                    {'request_id': uuid4().hex, 'consent': 'retry_saved_assessment'})
        assert assessment['status'] == 'revision_required'
        assert next(o for o in assessment['outcomes'] if o['outcome_id'] == 'advanced_nodes.checked_computation')['verdict'] == 'contradicted'
        assert assessment['credit_awarded'] is assessment['staff_review_required'] is False
        await CertificationLabInput.get_motor_collection().delete_many({})
        await f.workflow.delete()
        await f.document.delete()
        f.settings.reset_mock()
        f.settings.side_effect = RuntimeError('Live settings unavailable')
        assert await post(client, 'budget-runs/execute', params, execute_body) == completed
        original = await post(client, 'budget-reviews/' + review['uuid'] + '/automatic-reviews', params, assessment_body)
        assert original['status'] == ('grading_unavailable' if technical_retry else 'revision_required')
        f.settings.assert_not_awaited()
        monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
        read_path = '/certification/budget-reviews/' + review['uuid']
        saved = (await client.get(read_path, params=params)).json()
        assert saved['submission'] == review['submission']
        assert saved['run']['can_execute'] is False
        assert (await client.post('/certification/budget-runs/execute', params=params, json=execute_body)).status_code == 404
        f.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign')
        assert (await client.get(read_path, params=params)).status_code in (404, 409)
    assert len(f.calls) == 3 and f.judge.await_count == (2 if technical_retry else 1)
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_budget_http_requires_explicit_enrollment_and_rejects_client_authority(versioned_runtime, monkeypatch):
    f = await fixture(versioned_runtime, monkeypatch)
    path = '/certification/modules/advanced_nodes/budget-calculations'
    async with f.client as client:
        assert (await client.post(path, json=f.body)).status_code == 422
        for field in ('user_id', 'credit_awarded', 'model', 'checks'):
            response = await client.post(path, params={'enrollment_id': f.learner.uuid}, json={**f.body, field: 'client supplied'})
            assert response.status_code == 422
        module_response = await client.get('/certification/practical-history/' + f.learner.uuid)
        assert module_response.status_code == 200, module_response.text
        history = module_response.json()
        advanced = next(m for m in history['modules'] if m['module_id'] == 'advanced_nodes')
        assert advanced['budget_workflow_definition']['case_sha256'] == f.case.digest
    assert f.calls == [] and f.judge.await_count == 0
