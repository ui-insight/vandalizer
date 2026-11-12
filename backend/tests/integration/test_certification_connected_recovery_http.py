"""Authenticated stopped-run practice, finite-choice feedback and saved history."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.integration import test_certification_enrollments as f
from app.dependencies import get_current_user
from app.models.certification import CertificationLabExecution, CertificationLabInput
from app.services.certification_versions import runtime

repo = f.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def test_http_rehearsal_recovery_revision_separate_run_and_read_only_history(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    data, client, app, judge, config, providers = await f.connected_http_fixture(repo, monkeypatch)
    source = data[0]
    params = {'enrollment_id': source.uuid}
    prefix = '/certification/'

    def scope(run):
        return {'request_id': uuid4().hex, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
                'case_sha256': run['case_sha256'], 'choice': 'approve',
                'reason': 'I inspected the exact plan, source and disclosed execution purpose. Keep all outputs internal.',
                'consent': 'save_connected_workflow_scope_decision'}

    async def post(path, body):
        response = await client.post(prefix + path, params=params, json=body)
        assert response.status_code == 200, response.text
        return response.json()

    async def get(path):
        response = await client.get(prefix + path, params=params)
        assert response.status_code == 200, response.text
        return response.json()

    async with client:
        capture = await post('modules/multi_step/connected-captures', data[-1])
        request = {'request_id': uuid4().hex, 'input_snapshot_id': capture['uuid'], 'input_snapshot_sha256': capture['input_snapshot_sha256'],
                   'case_sha256': capture['case']['case_sha256'], 'consent': 'prepare_controlled_failure_rehearsal'}
        plan = await post('modules/multi_step/connected-runs', request)
        assert plan['execution_purpose'] == 'controlled_failure_rehearsal'
        assert capture['case']['controlled_failure_practice']['notice'] in plan['approval_question']['prompt']
        approved = await post('connected-runs/scope', scope(plan))
        execute = f.connected_execution_body(approved)
        stopped = await post('connected-runs/execute', execute)
        assert stopped['state'] == 'failed' and stopped['can_finalize'] is stopped['can_execute'] is False
        assert [provider.call_count for provider in providers] == [1, 0, 0]
        assert await post('connected-runs/execute', execute) == stopped
        choices = {'request_id': uuid4().hex, 'run_id': stopped['run_id'], 'result_sha256': stopped['result_sha256'],
                   'stage_events_sha256': stopped['stage_events_sha256'], 'case_sha256': stopped['case_sha256'],
                   'failed_stage': 'format', 'preserve': 'partial_is_complete', 'next_action': 'restart_all_writes',
                   'explanation': 'I inspected the stopped run. These intentionally incorrect fixture choices exercise feedback and retained revision history, not real learner understanding.',
                   'consent': 'save_my_actual_stopped_run_recovery_choices'}
        first = await post('modules/multi_step/connected-recovery-decisions', choices)
        assert first['checks']['choices_supported'] is False
        revision = {**choices, 'request_id': uuid4().hex, 'failed_stage': 'reason', 'preserve': 'keep_original_run_and_completed_outputs',
                    'next_action': 'prepare_separate_bounded_run', 'previous_submission_id': first['uuid'],
                    'explanation': 'The actual extraction completed and is preserved. Reasoning was deliberately rejected before its provider; Formatter did not start. Keep all original records and separately approve only another internal computation. This never authorizes repeating external writes.'}
        second = await post('modules/multi_step/connected-recovery-decisions', revision)
        assert second['checks']['choices_supported'] is True
        assert second['checks']['explanation_quality_assessed'] is False
        assert await post('modules/multi_step/connected-recovery-decisions', revision) == second
        normal = await post('modules/multi_step/connected-runs', {**request, 'request_id': uuid4().hex, 'consent': 'prepare_connected_workflow_plan'})
        assert normal['execution_purpose'] == 'complete_internal_chain' and not normal['can_execute']
        assert not normal['stage_events']
        normal = await post('connected-runs/scope', scope(normal))
        completed = await post('connected-runs/execute', f.connected_execution_body(normal))
        assert completed['state'] == 'completed' and len(completed['stage_events']) == 6
        assert [provider.call_count for provider in providers] == [2, 1, 1]
        listing = await get('modules/multi_step/connected-workflows')
        assert len(listing['recovery_submissions']) == 2 and listing['submissions'] == []
        if os.environ.get('CERTIFICATION_RECOVERY_HTTP_FIXTURE'):
            Path(os.environ['CERTIFICATION_RECOVERY_HTTP_FIXTURE']).write_text(json.dumps({
                'listing': listing, 'capture': capture, 'plan': plan, 'stopped': stopped,
                'first': first, 'second': second, 'completed': completed}, separators=(',', ':')) + '\n')
        for model in (CertificationLabExecution, CertificationLabInput, f.Workflow, f.SmartDocument):
            await model.get_motor_collection().delete_many({})
        config.side_effect = AssertionError('History and request replay cannot depend on live model configuration')
        assert await get('connected-recovery-decisions/' + first['uuid']) == first
        assert await post('modules/multi_step/connected-recovery-decisions', choices) == first
        monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
        assert await get('connected-recovery-decisions/' + second['uuid']) == second
        assert (await client.post(prefix + 'modules/multi_step/connected-recovery-decisions', params=params, json=revision)).status_code == 404
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign')
        assert (await client.get(prefix + 'connected-recovery-decisions/' + second['uuid'], params=params)).status_code in (404, 409)
        judge.assert_not_awaited()
        assert [provider.call_count for provider in providers] == [2, 1, 1]
        assert (await repo.read_progress(source.user_id, source.uuid)).total_xp == 0
