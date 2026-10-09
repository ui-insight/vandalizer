"""Actual budget engine with stub providers and acknowledged task receipts."""
from copy import deepcopy
import os
from threading import Barrier

import pytest

from tests.integration import test_certification_advanced_workflow_preparation as preparation_fixtures
from app.services.certification_versions.advanced_workflow_approval import AdvancedScopeRepository
from app.services.certification_versions.advanced_workflow_preparation import AdvancedWorkflowPreparation
from app.services.certification_versions.advanced_workflow_runtime import execute_approved_budget
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = preparation_fixtures.repo


async def fixture(repo):
    f = await preparation_fixtures.fixture(repo)
    run = await preparation_fixtures.prepare(repo, f)
    await preparation_fixtures.decide(repo, f, preparation_fixtures.scope_body(f, run))
    current = await AdvancedWorkflowPreparation().get(f.learner.user_id, run['run_id'])
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='test_budget_worker_authorization') as progress:
        authorization = await AdvancedScopeRepository().authorize(CourseOperation(f.learner.user_id, f.package, progress, True), current)
    # This fixture simulates the caller's claim envelope, not durable dispatch.
    f.run = {**current, 'state': 'executing', 'authorization': authorization}
    return f


def execute(f, sink, stop=lambda: False, config=None):
    return execute_approved_budget(f.run, f.case,
        preparation_fixtures.planning_fixtures.RUNTIME if config is None else config,
        checkpoint=sink, should_stop=stop)


async def test_preserves_each_actual_parallel_result_and_memo_consumed_context(repo, monkeypatch):
    from app.services import workflow_engine
    f = await fixture(repo)
    events, provider_contexts = [], {}
    barrier = Barrier(2)

    def provider(**kwargs):
        prompt = kwargs['prompt']
        provider_contexts[prompt] = deepcopy(kwargs['data'])
        if prompt != 'Write the internal memo':
            barrier.wait(timeout=10)
        else:
            assert len([e for e in events if e['kind'] == 'task_completed']) == 2
        return 'RESULT: ' + prompt

    def sink(payload, digest):
        assert digest == encode(payload)[1]
        assert payload['sequence'] == len(events)
        assert payload['previous_event_sha256'] == (encode(events[-1])[1] if events else None)
        events.append(deepcopy(payload))

    monkeypatch.setattr(workflow_engine, 'llm_chat_model', provider)
    result = execute(f, sink)
    assert result['status'] == 'completed' and result['credit_awarded'] is False
    assert len(events) == 6
    for event in events:
        if event['kind'] == 'task_started':
            task = f.run['plan']['engine_steps'][event['stage_index'] + 1]['tasks'][event['task_index']]
            assert event['consumed_context'] == provider_contexts[task['data']['prompt']]
            assert event['upstream_result_sha256'] == encode(event['upstream_result'])[1]
    memo = next(e for e in events if e['kind'] == 'task_started' and e['stage_index'] == 1)
    assert 'RESULT: Review source purposes' in memo['consumed_context']
    assert 'RESULT: Review source conflicts' in memo['consumed_context']
    assert '45001.00' in memo['consumed_context']


@pytest.mark.parametrize('failure', ['exception', 'empty', 'checkpoint'])
async def test_failed_sibling_preserves_successful_work_and_never_starts_memo(repo, monkeypatch, failure):
    from app.services import workflow_engine
    f = await fixture(repo)
    events, calls = [], []

    def provider(**kwargs):
        calls.append(kwargs['prompt'])
        if kwargs['prompt'] == 'Review source conflicts':
            if failure == 'exception':
                raise RuntimeError('SECRET provider detail')
            if failure == 'empty':
                return ''
        return 'Preserved branch result'

    def sink(payload, digest):
        if failure == 'checkpoint' and payload['kind'] == 'task_completed' and payload['task_index'] == 1:
            raise OSError('Synthetic receipt persistence failure')
        events.append(deepcopy(payload))

    monkeypatch.setattr(workflow_engine, 'llm_chat_model', provider)
    with pytest.raises((RuntimeError, EnrollmentConflict, OSError)):
        execute(f, sink)
    assert 'Write the internal memo' not in calls
    assert any(e['kind'] == 'task_completed' and e['task_index'] == 0 for e in events)
    assert 'SECRET' not in encode(events)[0]
    if failure != 'checkpoint':
        assert any(e['kind'] == 'task_failed' for e in events)


@pytest.mark.parametrize('change', ['state', 'plan_hash', 'hold', 'authorization_hash', 'runtime'])
async def test_worker_rejects_changed_authorization_before_any_model(repo, monkeypatch, change):
    from app.services import workflow_engine
    f = await fixture(repo)
    config = None
    if change == 'state':
        f.run['state'] = 'prepared'
    elif change == 'plan_hash':
        f.run['plan_sha256'] = 'a' * 64
    elif change == 'hold':
        f.run['authorization']['decision']['submission']['choice'] = 'hold'
    elif change == 'authorization_hash':
        f.run['scope_decision_sha256'] = 'a' * 64
    else:
        config = {'available_models': [{'name': 'different-model'}]}
    calls = []
    monkeypatch.setattr(workflow_engine, 'llm_chat_model', lambda **kwargs: calls.append(kwargs))
    with pytest.raises((EnrollmentConflict, ValueError)):
        execute(f, lambda *args: None, config=config)
    assert calls == []


async def test_cancellation_after_persisted_start_does_not_call_its_provider(repo, monkeypatch):
    from app.services import workflow_engine
    f = await fixture(repo)
    events, calls = [], []
    monkeypatch.setattr(workflow_engine, 'llm_chat_model', lambda **kwargs: calls.append(kwargs))
    with pytest.raises(workflow_engine.WorkflowCancelled):
        execute(f, lambda payload, digest: events.append(payload), stop=lambda: bool(events))
    assert len(events) == 1 and events[0]['kind'] == 'task_started'
    assert calls == []
