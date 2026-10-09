"""Authenticated output journey, actual file downloads and preserved history."""
import hashlib
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from tests.integration import test_certification_enrollments as enrollment_fixtures
from tests.integration import test_certification_output_workflow_plan as planning_fixtures
from tests.test_certification_output_artifacts import record
from app.dependencies import get_current_user
from app.models.certification import CertificationLabInput, CertificationLabExecution
from app.routers.certification import router
from app.services.certification_versions import (output_workflow_delivery, practical_preparation, automatic_review,
    review_delivery, course_history, runtime)

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = enrollment_fixtures.repo
versioned_runtime = enrollment_fixtures.versioned_runtime


async def fixture(repo, monkeypatch):
    from app.services import workflow_engine
    f = await planning_fixtures.fixture(repo)
    f.config = {**planning_fixtures.RUNTIME,
        'available_models': planning_fixtures.RUNTIME['available_models'] + enrollment_fixtures.REVIEW_CONFIG['available_models'],
        'default_model': 'report-model', 'validation_judge_model': 'synthetic-reviewer'}
    f.settings = AsyncMock(return_value=f.config)
    f.judge = AsyncMock(side_effect=enrollment_fixtures.supported_review)
    f.calls = []
    def prompt(**kwargs):
        f.calls.append(('report', kwargs['data']))
        return json.dumps(record())
    def formatter(model, instructions, context, **kwargs):
        f.calls.append(('summary', context))
        return 'Synthetic formatting', record()
    monkeypatch.setattr(workflow_engine, 'llm_chat_model', prompt)
    monkeypatch.setattr(workflow_engine, 'format_model', formatter)
    monkeypatch.setattr(output_workflow_delivery, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(output_workflow_delivery, 'get_storage', lambda: f.storage)
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
    for private in ('source_pdf_base64', 'authored_case', 'review_guidance', 'source_checks', 'engine_steps', 'data_b64', 'data_base64'):
        assert private not in response.text
    return response.json()


@pytest.mark.parametrize('technical_retry', [False, True])
async def test_full_http_output_journey_with_real_downloads_private_retry_and_saved_history(versioned_runtime, monkeypatch, technical_retry):
    repo = versioned_runtime
    f = await fixture(repo, monkeypatch)
    params = {'enrollment_id': f.learner.uuid}
    prefix = 'modules/output_delivery/'
    async with f.client as client:
        listing = await client.get('/certification/' + prefix + 'output-workflows', params=params)
        assert listing.status_code == 200, listing.text
        assert len(listing.json()['captures']) == 1 and listing.json()['can_submit'] is True
        captured = await post(client, prefix + 'output-captures', params, {**f.body, 'request_id': uuid4().hex})
        prepared = await post(client, prefix + 'output-runs', params, {'request_id': uuid4().hex,
            'input_snapshot_id': captured['uuid'], 'input_snapshot_sha256': captured['input_snapshot_sha256'],
            'case_sha256': f.case.digest, 'consent': 'prepare_output_workflow_plan'})
        assert prepared['can_execute'] is False and prepared['can_save_scope'] is True
        scope_body = {'request_id': uuid4().hex, 'run_id': prepared['run_id'], 'plan_sha256': prepared['plan_sha256'],
            'case_sha256': f.case.digest, 'choice': 'approve', 'reason': 'Approve this original source and the exact internal generation only.',
            'consent': 'save_output_workflow_scope_decision'}
        approved = await post(client, 'output-runs/scope', params, scope_body)
        execute_body = {key: approved[key] for key in ('run_id', 'plan_sha256', 'scope_decision_id', 'scope_decision_sha256')}
        execute_body['consent'] = 'execute_approved_output_workflow'
        completed = await post(client, 'output-runs/execute', params, execute_body)
        assert completed['state'] == 'completed' and len(completed['stage_events']) == 8 and completed['can_inspect'] is True
        artifacts = completed['result']['generated_artifacts']
        expected = {}
        for kind, index in [('source', 0), ('file', 0), ('file', 1), ('bundle', 0)]:
            response = await client.get(f'/certification/output-files/run/{completed["run_id"]}/{kind}', params={**params, 'file_index': index})
            assert response.status_code == 200, response.text
            digest = hashlib.sha256(response.content).hexdigest()
            reference = f.case.source_sha256 if kind == 'source' else artifacts['download']['sha256'] if kind == 'bundle' else artifacts['files'][index]['sha256']
            assert digest == reference
            assert response.headers['cache-control'] == 'private, no-store'
            assert response.headers['x-content-type-options'] == 'nosniff'
            expected[(kind, index)] = response.content
        assert (await client.get(f'/certification/output-files/run/{completed["run_id"]}/file', params={**params, 'file_index': 7})).status_code == 404
        inspection_body = {'request_id': uuid4().hex, 'run_id': completed['run_id'], 'result_sha256': completed['result_sha256'],
            'case_sha256': f.case.digest, 'artifacts_sha256': artifacts['artifacts_sha256'],
            'file_inspections': [{'sha256': file['sha256'], 'opened': True, 'judgment': 'usable',
                'observations': 'Opened and checked this exact file against the assigned source and the other file.'} for file in artifacts['files']],
            'bundle_sha256': artifacts['download']['sha256'], 'bundle_opened': True,
            'answers': {'artifact_review': 'Year 2 expenditure is USD 135500, cumulative expenditure is USD 287500; both files preserve source references and publication statuses.',
                        'release_decision': 'Approve only these exact bytes to my learner-only private training inbox, never broader sharing.'},
            'choice': 'approve', 'destination_id': 'private_training_inbox', 'audience': 'enrolled_learner_only',
            'data_scope': 'approved_generated_files_only', 'consent': 'save_exact_output_inspection_and_release_choice'}
        inspection = await post(client, prefix + 'output-file-reviews', params, inspection_body)
        handoff_body = {'request_id': uuid4().hex, 'run_id': completed['run_id'], 'result_sha256': completed['result_sha256'],
            'review_id': inspection['uuid'], 'review_sha256': inspection['review_sha256'],
            'artifacts_sha256': artifacts['artifacts_sha256'], 'destination_id': 'private_training_inbox',
            'action': 'attempt', 'consent': 'attempt_approved_private_training_handoff'}
        failed = await post(client, prefix + 'output-handoffs', params, handoff_body)
        assert failed['status'] == 'failed' and failed['destination_copy'] is None
        assert (await client.get(f'/certification/output-files/handoff/{failed["uuid"]}/file', params=params)).status_code == 404
        retry_body = {**handoff_body, 'request_id': uuid4().hex, 'action': 'retry_failed_handoff',
            'previous_failed_id': failed['uuid'], 'previous_failed_sha256': failed['handoff_sha256'],
            'consent': 'retry_only_failed_private_training_handoff'}
        delivered = await post(client, prefix + 'output-handoffs', params, retry_body)
        assert delivered['status'] == 'delivered' and delivered['destination_written'] is True
        assert await post(client, prefix + 'output-handoffs', params, retry_body) == delivered
        private_copy = await client.get(f'/certification/output-files/handoff/{delivered["uuid"]}/bundle', params=params)
        assert private_copy.content == expected[('bundle', 0)]
        reviewed = await post(client, prefix + 'output-reviews', params, {'request_id': uuid4().hex,
            'file_review_id': inspection['uuid'], 'file_review_sha256': inspection['review_sha256'],
            'handoff_id': delivered['uuid'], 'handoff_sha256': delivered['handoff_sha256'], 'case_sha256': f.case.digest,
            'delivery_review': 'The first controlled rejection wrote nothing; I retried only the failed private handoff. These saved bytes confirm my private copy, not external delivery.',
            'consent': 'save_output_delivery_interpretation'})
        if technical_retry:
            f.judge.side_effect = RuntimeError('Synthetic judge offline')
        assessment_body = {'request_id': uuid4().hex, 'consent': 'assess_saved_work'}
        assessed = await post(client, 'output-reviews/' + reviewed['uuid'] + '/automatic-reviews', params, assessment_body)
        if technical_retry:
            assert assessed['status'] == 'grading_unavailable'
            f.judge.side_effect = enrollment_fixtures.supported_review
            assessed = await post(client, 'output-automatic-reviews/' + assessed['attempt_id'] + '/retry', params,
                {'request_id': uuid4().hex, 'consent': 'retry_saved_assessment'})
        assert assessed['status'] == 'requirements_supported' and assessed['credit_awarded'] is assessed['staff_review_required'] is False
        # History owns the full evidence and download bytes after the live run disappears.
        await CertificationLabInput.get_motor_collection().delete_many({})
        await CertificationLabExecution.get_motor_collection().delete_many({})
        await f.document.delete()
        await f.workflow.delete()
        f.settings.reset_mock()
        f.settings.side_effect = RuntimeError('Live settings unavailable')
        original = await post(client, 'output-reviews/' + reviewed['uuid'] + '/automatic-reviews', params, assessment_body)
        assert original['status'] == ('grading_unavailable' if technical_retry else 'requirements_supported')
        f.settings.assert_not_awaited()
        monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
        read_path = '/certification/output-reviews/' + reviewed['uuid']
        saved = (await client.get(read_path, params=params)).json()
        assert saved['submission'] == reviewed['submission']
        assert saved['file_review']['run']['can_execute'] is False and saved['file_review']['run']['can_inspect'] is False
        for kind, index in [('source', 0), ('file', 0), ('file', 1), ('bundle', 0)]:
            response = await client.get(f'/certification/output-files/review/{reviewed["uuid"]}/{kind}', params={**params, 'file_index': index})
            assert response.content == expected[(kind, index)]
        assert (await client.post('/certification/' + prefix + 'output-handoffs', params=params, json=retry_body)).status_code == 404
        f.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign')
        assert (await client.get(read_path, params=params)).status_code in (404, 409)
        response = await client.get(f'/certification/output-files/handoff/{delivered["uuid"]}/bundle', params=params)
        assert response.status_code in (404, 409) and response.content != expected[('bundle', 0)]
    assert len(f.calls) == 2 and f.judge.await_count == (2 if technical_retry else 1)
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_http_requires_explicit_enrollment_and_forbids_client_authority(versioned_runtime, monkeypatch):
    f = await fixture(versioned_runtime, monkeypatch)
    from app.services.certification_versions.delivery import public_modules
    module = next(item for item in public_modules(f.package) if item['id'] == 'output_delivery')
    assert module['outputWorkflowAssessment']['case_sha256'] == f.case.digest and module['assessment'] is None
    path = '/certification/modules/output_delivery/output-captures'
    async with f.client as client:
        assert (await client.post(path, json=f.body)).status_code == 422
        for field in ('user_id', 'credit_awarded', 'model', 'generated_artifacts'):
            response = await client.post(path, params={'enrollment_id': f.learner.uuid}, json={**f.body, field: 'client supplied'})
            assert response.status_code == 422
        response = await client.get('/certification/practical-history/' + f.learner.uuid)
        assert response.status_code == 200, response.text
        definition = next(m for m in response.json()['modules'] if m['module_id'] == 'output_delivery')['output_workflow_definition']
        assert definition['case_sha256'] == f.case.digest
    assert f.calls == [] and f.judge.await_count == 0
