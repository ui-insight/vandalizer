"""Authenticated complete-suite HTTP journey and immutable history downloads."""
import hashlib
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_validation_inputs as inputs
from tests.integration import test_certification_validation_suites as suites
from tests.integration import test_certification_validation_execution as execution
from app.dependencies import get_current_user
from app.models.certification import CertificationLabInput, CertificationLabExecution, CertificationLearnerDecision
from app.routers.certification import router
from app.services.certification_versions import validation_delivery, practical_preparation, automatic_review, review_delivery, course_history, runtime
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
    f.provider = Mock(side_effect=execution.provider(f, wrong=True))
    f.judge = AsyncMock(side_effect=base.supported_review)
    monkeypatch.setattr(ExtractionEngine, 'extract', f.provider)
    monkeypatch.setattr(validation_delivery, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(validation_delivery, 'get_storage', lambda: f.storage)
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


async def plan_and_run(f, client, params, captured, suite, original=None):
    body = {'request_id': uuid4().hex, 'input_snapshot_id': captured['uuid'],
        'input_snapshot_sha256': captured['input_snapshot_sha256'], 'suite_id': suite['uuid'],
        'suite_record_sha256': suite['suite_record_sha256'], 'case_sha256': f.case.digest,
        'consent': 'prepare_complete_validation_suite'}
    if original:
        body.update(original_run_id=original['run_id'], original_run_sha256=original['run_sha256'])
    run = await post(client, 'modules/validation_qa/validation-runs', params, body)
    assert run['can_save_scope'] and not run['can_execute']
    approved = await post(client, 'validation-runs/scope', params, {'request_id': uuid4().hex,
        'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'], 'case_sha256': f.case.digest,
        'choice': 'approve', 'reason': 'I checked both complete source documents, all saved expectations and this exact revision and model.',
        'consent': 'save_validation_suite_scope_decision'})
    execute_body = {key: approved[key] for key in ('run_id', 'plan_sha256', 'scope_decision_id', 'scope_decision_sha256')}
    execute_body['consent'] = 'execute_approved_complete_validation_suite'
    completed = await post(client, 'validation-runs/execute', params, execute_body)
    assert completed['state'] == 'completed' and len(completed['case_events']) == 4
    assert await post(client, 'validation-runs/execute', params, execute_body) == completed
    return completed


@pytest.mark.parametrize('technical_retry', [False, True])
async def test_complete_http_validation_journey_and_preserved_originals(versioned_runtime, monkeypatch, technical_retry):
    repo = versioned_runtime
    f = await fixture(repo, monkeypatch)
    params = {'enrollment_id': f.learner.uuid}
    prefix = 'modules/validation_qa/'
    async with f.client as client:
        listing = await client.get('/certification/' + prefix + 'validation-suites', params=params)
        assert listing.status_code == 200, listing.text
        assert listing.json()['extractions'] == [{'artifact_id': f.artifact.uuid, 'title': f.artifact.title}]
        captured = await post(client, prefix + 'validation-captures', params, f.body)
        saved_snapshot = await validation_delivery.ValidationInputRepository().get(f.learner.user_id, captured['uuid'])
        suite = await post(client, prefix + 'validation-suites', params, suites.request(f, saved_snapshot))
        assert not suite['source_correctness_verified'] and not suite['execution_authorized']
        original = await plan_and_run(f, client, params, captured, suite)
        assert original['result']['checks']['observed_semantic_failure']
        f.fields[1].searchphrase = 'Extract the full multi-year project budget, never an annual amount, as a plain USD number.'
        await f.fields[1].save()
        f.provider.side_effect = execution.provider(f)
        corrected = await post(client, prefix + 'validation-captures', params, {**f.body, 'request_id': uuid4().hex})
        retest = await plan_and_run(f, client, params, corrected, suite, original)
        assert retest['result']['checks']['source_supported']
        assert retest['original_run']['run_sha256'] == original['run_sha256']
        assert retest['original_run']['can_execute'] is False
        reviewed = await post(client, prefix + 'validation-reviews', params, {'request_id': uuid4().hex,
            'run_id': retest['run_id'], 'result_sha256': retest['result_sha256'], 'case_sha256': f.case.digest,
            'answers': {'repair_review': 'The original NSF budget was an annual value, USD 177000. I repaired the same field to request the full project budget, USD 485000, and retested both unchanged cases. The NIH budget and explicit absent Co-PI remain supported. Two proposals cannot cover every future grant.'},
            'consent': 'save_validation_repair_interpretation'})
        if technical_retry:
            f.judge.side_effect = RuntimeError('Synthetic judge unavailable')
        assessment_body = {'request_id': uuid4().hex, 'consent': 'assess_saved_work'}
        assessed = await post(client, 'validation-reviews/' + reviewed['uuid'] + '/automatic-reviews', params, assessment_body)
        if technical_retry:
            assert assessed['status'] == 'grading_unavailable'
            f.judge.side_effect = base.supported_review
            assessed = await post(client, 'validation-automatic-reviews/' + assessed['attempt_id'] + '/retry', params,
                {'request_id': uuid4().hex, 'consent': 'retry_saved_assessment'})
        assert assessed['status'] == 'requirements_supported'
        assert assessed['credit_awarded'] is assessed['staff_review_required'] is False
        for origin, reference in [('capture', captured['uuid']), ('suite', suite['uuid']), ('run', retest['run_id']), ('review', reviewed['uuid'])]:
            for source in f.case.sources:
                response = await client.get(f'/certification/validation-sources/{origin}/{reference}/{source.id}', params=params)
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
        replay = await post(client, 'validation-reviews/' + reviewed['uuid'] + '/automatic-reviews', params, assessment_body)
        assert replay['status'] == ('grading_unavailable' if technical_retry else 'requirements_supported')
        monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
        history = await client.get('/certification/validation-reviews/' + reviewed['uuid'], params=params)
        assert history.status_code == 200, history.text
        assert history.json() == reviewed
        source = f.case.sources[0]
        response = await client.get(f'/certification/validation-sources/review/{reviewed["uuid"]}/{source.id}', params=params)
        assert hashlib.sha256(response.content).hexdigest() == source.sha256
        assert (await client.post('/certification/' + prefix + 'validation-captures', params=params, json=f.body)).status_code == 404
        f.settings.assert_not_awaited()
        f.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign')
        foreign = await client.get('/certification/validation-reviews/' + reviewed['uuid'], params=params)
        assert foreign.status_code in (404, 409)
    assert f.provider.call_count == 4
    assert f.judge.await_count == (2 if technical_retry else 1)
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_public_discovery_keeps_recognition_and_practical_separate(versioned_runtime, monkeypatch):
    f = await fixture(versioned_runtime, monkeypatch)
    module = next(m for m in public_modules(f.package) if m['id'] == 'validation_qa')
    assert module['validationAssessment'] == f.case.public_definition()
    # This synthetic package may omit the optional recognition bank. When present,
    # discovery must preserve both definitions rather than replacing recognition.
    if 'assessments/validation_qa.json' in f.package.manifest.artifacts:
        assert module['scenarioAssessment']
    history = await course_history.CourseHistory(versioned_runtime).course(f.learner.user_id, f.learner.uuid)
    saved = next(m for m in history['modules'] if m['module_id'] == 'validation_qa')
    assert saved['validation_definition'] == f.case.public_definition()
