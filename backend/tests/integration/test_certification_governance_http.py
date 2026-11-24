"""Full explicit capstone HTTP journey and exact preserved PDF/JSON downloads."""
import hashlib
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_governance_inputs as inputs
from tests.integration import test_certification_governance_execution as execution
from app.dependencies import get_current_user
from app.models.certification import CertificationLabInput, CertificationLabExecution, CertificationLearnerDecision
from app.routers.certification import router
from app.services.certification_versions import governance_delivery, practical_preparation, automatic_review, review_delivery, course_history, runtime
from app.services.certification_versions.delivery import public_modules

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo, monkeypatch):
    from app.services.extraction_engine import ExtractionEngine
    f = await inputs.fixture(repo)
    f.config = {**base.LAB_RUNTIME, 'available_models': base.LAB_RUNTIME['available_models'] + base.REVIEW_CONFIG['available_models'],
        'validation_judge_model': 'synthetic-reviewer'}
    f.settings, f.judge = AsyncMock(return_value=f.config), AsyncMock(side_effect=base.supported_review)
    f.provider = Mock(side_effect=execution.provider(f, wrong=True))
    monkeypatch.setattr(ExtractionEngine, 'extract', f.provider)
    monkeypatch.setattr(governance_delivery, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(governance_delivery, 'get_storage', lambda: f.storage)
    monkeypatch.setattr(review_delivery, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(course_history, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(practical_preparation, 'configured_runtime', f.settings)
    monkeypatch.setattr(automatic_review, '_call_model', f.judge)
    f.app = FastAPI()
    f.app.include_router(router, prefix='/certification')
    f.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=f.learner.user_id)
    f.prepared_runs = []
    f.client = AsyncClient(transport=ASGITransport(app=f.app), base_url='http://test')
    return f


async def post(client, path, params, body):
    response = await client.post('/certification/' + path, params=params, json=body)
    assert response.status_code == 200, response.text
    for private in ('source_pdf_base64', 'authored_case', 'review_guidance', 'content_base64', 'synthetic-secret', 'plan_json'):
        assert private not in response.text
    return response.json()


async def plan_and_run(f, client, params, captured, correction, finding=None):
    body = {'request_id': uuid4().hex, 'input_snapshot_id': captured['uuid'], 'input_snapshot_sha256': captured['input_snapshot_sha256'],
        'case_sha256': f.case.digest, 'scope_correction_id': correction['uuid'], 'scope_correction_sha256': correction['record_sha256'],
        'consent': 'prepare_repaired_bounded_capstone_extraction' if finding else 'prepare_original_bounded_capstone_extraction'}
    if finding:
        body.update(source_finding_id=finding['uuid'], source_finding_sha256=finding['record_sha256'])
    run = await post(client, 'modules/governance/governance-runs', params, body)
    f.prepared_runs.append(run)
    assert run['can_save_scope'] and not run['can_execute']
    approved = await post(client, 'governance-runs/scope', params, {'request_id': uuid4().hex, 'run_id': run['run_id'],
        'plan_sha256': run['plan_sha256'], 'case_sha256': f.case.digest, 'choice': 'approve',
        'reason': 'I inspected both complete assigned sources, all six saved instructions and the resolved model. This approval covers only this exact internal extraction, not handoff or external actions.',
        'consent': 'save_bounded_governance_execution_decision'})
    request = {'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'], 'scope_decision_id': approved['uuid'],
        'scope_decision_sha256': approved['record_sha256'], 'consent': 'execute_approved_bounded_capstone_extraction'}
    completed = await post(client, 'governance-runs/execute', params, request)
    assert completed['state'] == 'completed' and len(completed['extraction_events']) == 2
    assert await post(client, 'governance-runs/execute', params, request) == completed
    return completed


async def journey(f, client, params):
    prefix = 'modules/governance/'
    listing = await client.get('/certification/' + prefix + 'governance-work', params=params)
    assert listing.status_code == 200, listing.text
    assert listing.json()['extractions'] == [{'artifact_id': f.artifact.uuid, 'title': f.artifact.title}]
    capture = await post(client, prefix + 'governance-captures', params, f.body)
    f.snapshot = await governance_delivery.GovernanceInputRepository().get(f.learner.user_id, capture['uuid'])
    correction = await post(client, 'governance/corrections', params, {'request_id': uuid4().hex,
        'input_snapshot_id': capture['uuid'], 'input_snapshot_sha256': capture['input_snapshot_sha256'], 'case_sha256': f.case.digest,
        'choice': 'reject_broad_proposal', 'source_document_ids': [s['document_id'] for s in capture['documents']],
        'destination_id': 'private_training_inbox', 'audience': 'enrolled_learner_only', 'ongoing_automation': 'keep_disabled',
        'reason': 'Only these two complete assigned records are in scope. I reject broad sharing, sponsor email and recurring sends. An agent claim does not provide my approval; I would stop and inspect any unintended ongoing action.',
        'consent': 'save_my_corrected_capstone_scope_without_execution'})
    original = await plan_and_run(f, client, params, capture, correction)
    assert original['result']['checks']['observed_semantic_failure']
    finding = await post(client, 'governance/findings', params, {'request_id': uuid4().hex, 'run_id': original['run_id'],
        'result_sha256': original['result_sha256'], 'case_sha256': f.case.digest, 'field': 'Funds Obligated to Date', 'observed_value': '600000',
        'source_references': [f.case.expectations[0].anchors[0].model_dump(mode='json'), f.case.expectations[3].anchors[0].model_dump(mode='json')],
        'explanation': 'The actual $600,000 result is the planned ceiling. The issued amendment raises the original $180,000 obligation by $70,000, making $250,000 cumulative. I will repair this same funding instruction and rerun both complete sources.',
        'consent': 'save_my_original_source_finding_before_repair'})
    f.fields[3].searchphrase = 'Return cumulative funds actually obligated under the latest issued amendment, never the approved ceiling or additional increment alone.'
    await f.fields[3].save()
    f.body['request_id'] = uuid4().hex
    corrected = await post(client, prefix + 'governance-captures', params, f.body)
    f.provider.side_effect = execution.provider(f)
    repaired = await plan_and_run(f, client, params, corrected, correction, finding)
    assert repaired['result']['repair_checks']['repair_requirements_supported']
    assert repaired['source_finding']['run']['run_sha256'] == original['run_sha256']
    assert repaired['source_finding']['run']['can_execute'] is False
    memo = await post(client, 'governance/memos', params, {'request_id': uuid4().hex, 'run_id': repaired['run_id'],
        'result_sha256': repaired['result_sha256'], 'case_sha256': f.case.digest, 'owner_user_id': f.learner.user_id,
        'intended_use': 'Private rehearsal of an internal amendment routing memo, never an external sponsor submission.',
        'supported_inputs': 'Only the complete assigned fictional notice and issued amendment as of the simulated January 5, 2027 date.',
        'limitations': 'This single fictional award pair does not prove wider reliability, real institutional suitability or external delivery.',
        'review_route': 'I own the training memo. Changed real source records, instructions or intended use require new validation and appropriate research-office review, which is not a staff certification queue.',
        'consent': 'save_checked_capstone_memo_without_release'})
    release = await post(client, 'governance/releases', params, {'request_id': uuid4().hex, 'run_id': repaired['run_id'], 'case_sha256': f.case.digest,
        'memo_id': memo['uuid'], 'memo_sha256': memo['record_sha256'], 'file_sha256': memo['file']['sha256'],
        'opened': True, 'choice': 'approve', 'reason': 'I inspected the exact JSON and complete repaired source checks. I own the limited training artifact and approve only my private inbox. No broader sharing, sponsor email or ongoing automation is authorized.',
        'destination_id': 'private_training_inbox', 'audience': 'enrolled_learner_only', 'consent': 'save_my_exact_capstone_memo_release_choice'})
    first_body = {'request_id': uuid4().hex, 'run_id': repaired['run_id'], 'case_sha256': f.case.digest,
        'memo_id': memo['uuid'], 'memo_sha256': memo['record_sha256'], 'file_sha256': memo['file']['sha256'],
        'release_id': release['uuid'], 'release_sha256': release['record_sha256'], 'destination_id': 'private_training_inbox',
        'action': 'attempt', 'consent': 'attempt_approved_private_capstone_handoff'}
    first = await post(client, 'governance/handoffs', params, first_body)
    assert first['status'] == 'failed' and first['destination_copy'] is None
    delivered = await post(client, 'governance/handoffs', params, {**first_body, 'request_id': uuid4().hex, 'action': 'retry_failed_handoff',
        'previous_failed_id': first['uuid'], 'previous_failed_sha256': first['record_sha256'], 'consent': 'retry_only_failed_private_capstone_handoff'})
    assert delivered['status'] == 'delivered' and delivered['destination_copy'] == memo['file']
    reviewed = await post(client, prefix + 'governance-reviews', params, {'request_id': uuid4().hex, 'run_id': repaired['run_id'],
        'case_sha256': f.case.digest, 'handoff_id': delivered['uuid'], 'handoff_sha256': delivered['record_sha256'],
        'final_supervision': 'I corrected the proposed scope, recorded the actual unsupported ceiling value and source quotes, repaired the same funding instruction and approved a complete same-model rerun. Every actual field now matches both original sources. I inspected and approved the exact memo for my private inbox, observed the disclosed no-write rejection and explicitly retried only the same approved bytes. The confirmed copy preserves the original failed receipt. Changed real artifacts need new validation and appropriate review; this rehearsal proves no actual external delivery or general reliability.',
        'consent': 'save_my_capstone_supervision_interpretation'})
    return SimpleNamespace(capture=capture, correction=correction, original=original, finding=finding, corrected=corrected, repaired=repaired, memo=memo, release=release, first=first, delivered=delivered, reviewed=reviewed)


@pytest.mark.parametrize('technical_retry', [False, True])
async def test_full_http_governance_journey_and_preserved_downloads(versioned_runtime, monkeypatch, technical_retry):
    repo = versioned_runtime
    f = await fixture(repo, monkeypatch)
    params = {'enrollment_id': f.learner.uuid}
    async with f.client as client:
        flow = await journey(f, client, params)
        if technical_retry:
            f.judge.side_effect = RuntimeError('Synthetic judge unavailable')
        assessment_body = {'request_id': uuid4().hex, 'consent': 'assess_saved_work'}
        assessed = await post(client, 'governance-reviews/' + flow.reviewed['uuid'] + '/automatic-reviews', params, assessment_body)
        if technical_retry:
            assert assessed['status'] == 'grading_unavailable'
            f.judge.side_effect = base.supported_review
            assessed = await post(client, 'governance-automatic-reviews/' + assessed['attempt_id'] + '/retry', params,
                {'request_id': uuid4().hex, 'consent': 'retry_saved_assessment'})
        assert assessed['status'] == 'requirements_supported' and assessed['credit_awarded'] is assessed['staff_review_required'] is False
        for origin, reference in [('capture', flow.capture['uuid']), ('correction', flow.correction['uuid']), ('run', flow.repaired['run_id']), ('finding', flow.finding['uuid']), ('memo', flow.memo['uuid']), ('release', flow.release['uuid']), ('handoff', flow.first['uuid']), ('review', flow.reviewed['uuid'])]:
            for source in f.case.sources:
                response = await client.get(f'/certification/governance-sources/{origin}/{reference}/{source.id}', params=params)
                assert response.status_code == 200, response.text
                assert hashlib.sha256(response.content).hexdigest() == source.sha256
                assert response.headers['cache-control'] == 'private, no-store' and response.headers['x-content-type-options'] == 'nosniff'
        for origin, reference in [('memo', flow.memo['uuid']), ('release', flow.release['uuid']), ('handoff', flow.first['uuid']), ('handoff', flow.delivered['uuid']), ('review', flow.reviewed['uuid'])]:
            response = await client.get(f'/certification/governance-memo-files/{origin}/{reference}', params=params)
            assert response.status_code == 200, response.text
            assert hashlib.sha256(response.content).hexdigest() == flow.memo['file']['sha256']
            assert json.loads(response.content) == flow.memo['file']['memo']
        listing = await client.get('/certification/modules/governance/governance-work', params=params)
        assert listing.status_code == 200, listing.text
        assert len(listing.json()['records']['handoff']['items']) == 2
        fixture_path = os.environ.get('CERTIFICATION_GOVERNANCE_HTTP_FIXTURE')
        if fixture_path and not technical_retry:
            from pathlib import Path
            target = Path(fixture_path).resolve()
            assert target.is_relative_to('/private/tmp')
            target.write_text(json.dumps({'listing': listing.json(), 'review': flow.reviewed, 'prepared_runs': f.prepared_runs}, indent=2) + '\n')
        await CertificationLabInput.get_motor_collection().delete_many({})
        await CertificationLabExecution.get_motor_collection().delete_many({})
        await CertificationLearnerDecision.get_motor_collection().delete_many({'uuid': {'$ne': flow.reviewed['uuid']}})
        for document in f.documents:
            await document.delete()
        await f.artifact.delete()
        f.settings.reset_mock()
        f.settings.side_effect = RuntimeError('Live settings unavailable')
        replay = await post(client, 'governance-reviews/' + flow.reviewed['uuid'] + '/automatic-reviews', params, assessment_body)
        assert replay['status'] == ('grading_unavailable' if technical_retry else 'requirements_supported')
        monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
        history = await client.get('/certification/governance/review/' + flow.reviewed['uuid'], params=params)
        assert history.status_code == 200, history.text
        assert history.json() == flow.reviewed
        response = await client.get(f'/certification/governance-memo-files/review/{flow.reviewed["uuid"]}', params=params)
        assert hashlib.sha256(response.content).hexdigest() == flow.memo['file']['sha256']
        assert (await client.post('/certification/modules/governance/governance-captures', params=params, json=f.body)).status_code == 404
        f.settings.assert_not_awaited()
        f.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign')
        foreign = await client.get('/certification/governance/review/' + flow.reviewed['uuid'], params=params)
        assert foreign.status_code in (404, 409)
    assert f.provider.call_count == 2 and f.judge.await_count == (2 if technical_retry else 1)
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_governance_discovery_keeps_separate_recognition(versioned_runtime, monkeypatch):
    f = await fixture(versioned_runtime, monkeypatch)
    module = next(m for m in public_modules(f.package) if m['id'] == 'governance')
    assert module['governanceAssessment'] == f.case.public_definition() and module['scenarioAssessment']
    history = await course_history.CourseHistory(versioned_runtime).course(f.learner.user_id, f.learner.uuid)
    saved = next(m for m in history['modules'] if m['module_id'] == 'governance')
    assert saved['governance_definition'] == f.case.public_definition() and saved['scenario_definition']
