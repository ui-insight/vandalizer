"""Durable budget dispatch, retained task history and once-only provider calls."""
import asyncio
from copy import deepcopy
import os
from threading import Event

import pytest

from tests.integration import test_certification_advanced_workflow_preparation as preparation_fixtures
from app.models.certification import CertificationLabInput, CertificationLabExecution
from app.services.certification_versions.advanced_workflow_execution import AdvancedWorkflowExecution
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = preparation_fixtures.repo


async def fixture(repo, monkeypatch):
    from app.services import workflow_engine
    f = await preparation_fixtures.fixture(repo)
    run = await preparation_fixtures.prepare(repo, f)
    decision = await preparation_fixtures.decide(repo, f, preparation_fixtures.scope_body(f, run))
    f.execution_body = {'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
        'scope_decision_id': decision['uuid'], 'scope_decision_sha256': encode(decision)[1],
        'consent': 'execute_approved_budget_workflow'}
    f.calls = []

    def provider(**kwargs):
        f.calls.append(kwargs['prompt'])
        return 'RESULT: ' + kwargs['prompt']

    monkeypatch.setattr(workflow_engine, 'llm_chat_model', provider)
    return f


async def execute(repo, f, service=None, config=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='execute_budget_workflow') as progress:
        return await (service or AdvancedWorkflowExecution()).execute(
            CourseOperation(f.learner.user_id, f.package, progress, True), f.execution_body,
            preparation_fixtures.planning_fixtures.RUNTIME if config is None else config, actor_user_id=f.learner.user_id)


async def test_actual_owned_execution_persists_every_task_and_replay_never_repeats_provider(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    saved = await execute(repo, f)
    assert saved['state'] == 'completed'
    assert len(saved['task_events']) == 6 and len(f.calls) == 3
    assert saved['result']['task_event_count'] == 6
    assert saved['plan']['arithmetic_supported'] is False
    await CertificationLabInput.get_motor_collection().delete_many({})
    await f.document.delete()
    await f.workflow.delete()
    assert await execute(repo, f, config={}) == saved
    assert len(f.calls) == 3
    assert await AdvancedWorkflowExecution().get('foreign', saved['run_id']) is None
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('failure', ['exception', 'empty', 'checkpoint_limit'])
async def test_failed_run_preserves_completed_prefix_without_repeating_it(repo, monkeypatch, failure):
    from app.services import workflow_engine
    from app.services.certification_versions import advanced_workflow_checkpoints
    f = await fixture(repo, monkeypatch)
    if failure == 'checkpoint_limit':
        monkeypatch.setattr(advanced_workflow_checkpoints, 'MAX_CHECKPOINT_BYTES', 100)

    def provider(**kwargs):
        f.calls.append(kwargs['prompt'])
        if kwargs['prompt'] == 'Review source conflicts':
            if failure == 'exception':
                raise RuntimeError('PRIVATE PROVIDER SECRET')
            if failure == 'empty':
                return ''
        return 'Preserved source review'

    monkeypatch.setattr(workflow_engine, 'llm_chat_model', provider)
    saved = await execute(repo, f)
    assert saved['state'] == 'failed'
    assert 'Write the internal memo' not in f.calls
    assert 'PRIVATE PROVIDER SECRET' not in encode(saved)[0]
    if failure == 'checkpoint_limit':
        assert f.calls == [] and saved['task_events'] == []
    else:
        assert any(e['receipt']['kind'] == 'task_completed' for e in saved['task_events'])
    original_calls = list(f.calls)
    assert await execute(repo, f, config={}) == saved
    assert f.calls == original_calls
    from app.services.certification_versions.advanced_workflow_delivery import AdvancedWorkflowDelivery
    public = await AdvancedWorkflowDelivery(repo).run_view(saved, writable=True)
    assert not public['can_execute'] and not public['can_finalize'] and not public['can_save_scope']
    assert public['result']['status'] == 'failed' and public['credit_awarded'] is False
    assert 'final_output' not in public['result']
    if os.environ.get('CERTIFICATION_BUDGET_RECOVERY_FIXTURES'):
        import json
        from pathlib import Path
        destination = Path(os.environ['CERTIFICATION_BUDGET_RECOVERY_FIXTURES'])
        destination.mkdir(parents=True, exist_ok=True)
        (destination / f'{failure}.json').write_text(json.dumps(public, indent=2) + '\n')


async def test_lost_terminal_save_preserves_all_tasks_but_never_automatically_reruns(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    service = AdvancedWorkflowExecution()

    async def interrupted(*args):
        raise OSError('Synthetic terminal write outage')

    monkeypatch.setattr(service, '_finish_budget', interrupted)
    with pytest.raises(OSError):
        await execute(repo, f, service)
    current = await AdvancedWorkflowExecution().get(f.learner.user_id, f.execution_body['run_id'])
    assert current['state'] == 'executing' and len(current['task_events']) == 6
    assert await execute(repo, f, config={}) == current
    assert len(f.calls) == 3
    if os.environ.get('CERTIFICATION_BUDGET_RECOVERY_FIXTURES'):
        import json
        from pathlib import Path
        from app.services.certification_versions.advanced_workflow_delivery import AdvancedWorkflowDelivery
        public = await AdvancedWorkflowDelivery(repo).run_view(current, writable=True)
        assert public['can_finalize'] and not public['can_execute']
        destination = Path(os.environ['CERTIFICATION_BUDGET_RECOVERY_FIXTURES'])
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'saved_results.json').write_text(json.dumps(public, indent=2) + '\n')


async def test_new_hold_prevents_dispatch_of_old_displayed_approval(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    run = await AdvancedWorkflowExecution().get(f.learner.user_id, f.execution_body['run_id'])
    await preparation_fixtures.decide(repo, f, preparation_fixtures.scope_body(f, run, 'hold'))
    with pytest.raises(EnrollmentConflict, match='scope choice changed'):
        await execute(repo, f)
    assert f.calls == []


@pytest.mark.parametrize('change', ['context', 'missing_branch', 'duplicate_task', 'terminal_output'])
async def test_rehashed_log_cannot_fabricate_task_consumption_or_completed_memo(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch)
    saved = await execute(repo, f)
    assert saved['state'] == 'completed'
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': saved['run_id']})
    events = deepcopy(saved['task_events'])
    if change == 'context':
        events[0]['receipt']['consumed_context'] = 'Invented consumed context'
    elif change == 'missing_branch':
        events = [e for e in events if not (e['receipt']['stage_index'] == 0 and e['receipt']['task_index'] == 1)]
    elif change == 'duplicate_task':
        events.insert(1, deepcopy(events[0]))
    for index, item in enumerate(events):
        item['receipt']['sequence'] = index
        item['receipt']['previous_event_sha256'] = events[index - 1]['receipt_sha256'] if index else None
        item['receipt_sha256'] = encode(item['receipt'])[1]
    raw['task_events_json'], raw['task_events_sha256'] = encode(events)
    raw['task_event_count'] = len(events)
    result = deepcopy(saved['result'])
    result['task_events_sha256'] = raw['task_events_sha256']
    result['task_event_count'] = len(events)
    if change == 'terminal_output':
        result['final_output'] = 'A fabricated final memo'
    raw['result_json'], raw['result_sha256'] = encode(result)
    with pytest.raises(CourseCatalogError):
        AdvancedWorkflowExecution.decode(raw)


async def test_cancelled_caller_preserves_uncertainty_and_stops_late_memo(repo, monkeypatch):
    from app.services import workflow_engine
    f = await fixture(repo, monkeypatch)
    entered, release = Event(), Event()

    def provider(**kwargs):
        f.calls.append(kwargs['prompt'])
        entered.set()
        release.wait(timeout=10)
        return 'Late source result'

    monkeypatch.setattr(workflow_engine, 'llm_chat_model', provider)
    work = asyncio.create_task(execute(repo, f))
    try:
        assert await asyncio.to_thread(entered.wait, 10)
        work.cancel()
        with pytest.raises(asyncio.CancelledError):
            await work
    finally:
        release.set()
    saved = await AdvancedWorkflowExecution().get(f.learner.user_id, f.execution_body['run_id'])
    assert saved['state'] == 'uncertain'
    assert saved['result']['reason'] == 'caller_cancelled'
    assert 'Write the internal memo' not in f.calls
    assert await execute(repo, f, config={}) == saved
