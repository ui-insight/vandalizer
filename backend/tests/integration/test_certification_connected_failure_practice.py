"""Real disposable persistence for an explicit stopped-run training exercise."""
from copy import deepcopy
import os

import pytest

from tests.integration import test_certification_enrollments as f
from tests.test_certification_connected_workflow_runtime import providers
from app.models.certification import CertificationLabInput, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.connected_failure_practice import PRACTICE_CONSENT, STOP_MARKER
from app.services.certification_versions.connected_workflow_execution import ConnectedWorkflowExecution
from app.services.certification_versions.connected_workflow_preparation import ConnectedWorkflowPreparation
from app.services.certification_versions.connected_workflow_recovery import ConnectedWorkflowRecovery
from app.services.certification_versions.enrollments import EnrollmentConflict

repo = f.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo):
    data = await f.connected_workflow_fixture(repo)
    snapshot = await f.capture_connected(repo, data)
    body = {**f.connected_plan_body(snapshot), 'consent': PRACTICE_CONSENT}
    prepared = await f.prepare_connected(repo, data, body)
    await f.submit_connected_scope(repo, data, f.connected_scope_body(prepared))
    run = await ConnectedWorkflowPreparation().get(data[0].user_id, prepared['run_id'])
    return data, body, f.connected_execution_body(run)


async def test_controlled_stop_is_once_only_preserved_after_deletion_and_never_finalized(repo, monkeypatch):
    data, plan_body, execution = await fixture(repo)
    extract, reason, formatter = providers(monkeypatch)
    run = await f.dispatch_connected(repo, data, execution)
    assert run['state'] == 'failed' and run['result']['reason'] == STOP_MARKER
    assert len(run['stage_events']) == 4 and run['stage_events'][1]['receipt']['status'] == 'completed'
    assert run['stage_events'][-1]['receipt']['result']['provider_dispatched'] is False
    assert extract.call_count == 1 and reason.call_count == formatter.call_count == 0
    assert run['plan']['input_snapshot']['case']['controlled_failure_practice']['notice'] in run['authorization']['decision']['prompt']['prompt']
    for model in (CertificationLabInput, CertificationLearnerDecision, f.Workflow, f.SmartDocument):
        await model.get_motor_collection().delete_many({})
    assert await f.prepare_connected(repo, data, plan_body, config={}) == run
    assert await f.dispatch_connected(repo, data, execution, config={}) == run
    assert extract.call_count == 1 and reason.call_count == formatter.call_count == 0
    # Finalization never turns a preserved successful prefix into a complete run.
    body = {'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
            'authorization_sha256': encode(run['authorization'])[1], 'stage_events_sha256': encode(run['stage_events'])[1],
            'consent': 'finalize_saved_connected_results_without_reexecution'}
    with pytest.raises(EnrollmentConflict):
        await f.finalize_connected(repo, data, body, recovery=ConnectedWorkflowRecovery())
    assert (await repo.read_progress(data[0].user_id, data[0].uuid)).total_xp == 0


async def test_normal_new_plan_needs_fresh_approval_and_keeps_the_stopped_run(repo, monkeypatch):
    data, _, execution = await fixture(repo)
    extract, reason, formatter = providers(monkeypatch)
    original = await f.dispatch_connected(repo, data, execution)
    new = await f.prepare_connected(repo, data, f.connected_plan_body(original['plan']['input_snapshot']))
    with pytest.raises(EnrollmentConflict, match='scope choice changed'):
        await f.dispatch_connected(repo, data, {**execution, 'run_id': new['run_id'], 'plan_sha256': new['plan_sha256']})
    await f.submit_connected_scope(repo, data, f.connected_scope_body(new))
    new = await ConnectedWorkflowPreparation().get(data[0].user_id, new['run_id'])
    completed = await f.dispatch_connected(repo, data, f.connected_execution_body(new))
    assert completed['state'] == 'completed' and completed['run_id'] != original['run_id']
    assert extract.call_count == 2 and reason.call_count == formatter.call_count == 1
    assert await ConnectedWorkflowPreparation().get(data[0].user_id, original['run_id']) == original


@pytest.mark.parametrize('change', ['result_reason', 'stage_result', 'purpose'])
async def test_rehashed_saved_record_cannot_invent_a_different_training_stop(repo, monkeypatch, change):
    data, _, execution = await fixture(repo)
    providers(monkeypatch)
    run = await f.dispatch_connected(repo, data, execution)
    store = ConnectedWorkflowExecution()
    raw = await store.records.find_one({'uuid': run['run_id']})
    if change == 'result_reason':
        raw['state'] = 'completed'
    elif change == 'stage_result':
        events = deepcopy(run['stage_events'])
        events[-1]['receipt']['result']['provider_dispatched'] = True
        events[-1]['receipt_sha256'] = encode(events[-1]['receipt'])[1]
        raw['stage_events_json'], raw['stage_events_sha256'] = encode(events)
    else:
        plan = deepcopy(run['plan'])
        plan['request']['consent'] = 'prepare_connected_workflow_plan'
        plan['request_sha256'] = encode(plan['request'])[1]
        raw['plan_json'], raw['plan_sha256'] = encode(plan)
    with pytest.raises(CourseCatalogError):
        store.decode(raw)
