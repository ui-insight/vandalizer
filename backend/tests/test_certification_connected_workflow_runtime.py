"""Checkpoint actual consumed context and stop before repeating provider work."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from app.services import workflow_engine
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.connected_workflow_runtime import execute_approved_chain
from app.services.certification_versions.enrollments import EnrollmentConflict
from tests.test_certification_connected_workflow_plan import fixture, plan, reseal, RUNTIME


def approved_run(*, original=False, snapshot_id='b' * 32, run_id='c' * 32, decision_id='d' * 32, mutate_snapshot=None, failure_practice=False):
    case, snapshot = fixture()
    if original:
        snapshot['artifact']['steps'][2]['step']['data']['input_sources'] = ['workflow_documents']
        reseal(snapshot)
    if mutate_snapshot is not None:
        mutate_snapshot(snapshot)
        reseal(snapshot)
    identity = {'user_id': snapshot['user_id'], 'enrollment_id': 'enrollment', 'module_id': 'multi_step',
                'course_version': 'synthetic-course', 'manifest_sha256': 'a' * 64}
    snapshot.update(identity, uuid=snapshot_id)
    question = next(item for item in snapshot['case']['questions'] if item['id'] == 'scope_approval')
    if failure_practice:
        from app.services.certification_versions.connected_failure_practice import approval_question, PRACTICE_CONSENT
        question = approval_question(snapshot['case'], PRACTICE_CONSENT)
    prepared = {**identity, **plan(snapshot, case), 'uuid': run_id, 'input_snapshot_id': snapshot['uuid'],
                'input_snapshot': snapshot, 'approval_requirement': {'kind': 'connected_workflow_scope', 'question': question,
                    'input_snapshot_sha256': encode(snapshot)[1], 'case_sha256': case.digest}}
    if failure_practice:
        prepared['request'] = {'consent': PRACTICE_CONSENT}
    plan_hash = encode(prepared)[1]
    request = {'request_id': decision_id, 'run_id': prepared['uuid'], 'plan_sha256': plan_hash,
               'case_sha256': case.digest, 'choice': 'approve', 'reason': 'I checked the captured source and saved internal chain.',
               'consent': 'save_connected_workflow_scope_decision'}
    prompt = {**question, 'execution_choice': 'approve'}
    decision = {**identity, 'uuid': request['request_id'], 'record_kind': 'connected_workflow_scope',
                'prompt_id': 'scope_approval', 'prompt': prompt, 'prompt_sha256': encode(prompt)[1],
                'run_id': prepared['uuid'], 'plan_sha256': plan_hash, 'case_sha256': case.digest,
                'input_snapshot_id': snapshot['uuid'], 'input_snapshot_sha256': prepared['input_snapshot_sha256'],
                'submission': request, 'request_sha256': encode(request)[1], 'run_state_at_submission': 'prepared',
                'submission_channel': 'authenticated_learner_request', 'credit_awarded': False}
    authorization = {'run_id': prepared['uuid'], 'plan_sha256': plan_hash, 'decision': decision, 'decision_sha256': encode(decision)[1]}
    return case, {'run_id': prepared['uuid'], 'state': 'executing', 'plan': prepared, 'plan_sha256': plan_hash,
                  'scope_decision_id': decision['uuid'], 'scope_decision_sha256': encode(decision)[1], 'authorization': authorization}


def providers(monkeypatch):
    extraction = Mock(return_value={'raw': [{'Amount': '$185,000'}], 'formatted': '$185,000'})
    reasoning = Mock(return_value='Reporting obligations differ; no institutional comparison standard is supplied.')
    formatting = Mock(return_value=('Provider prompt', 'Internal draft'))
    for name, provider in zip(('data_extraction_model', 'llm_chat_model', 'format_model'), (extraction, reasoning, formatting)):
        monkeypatch.setattr(workflow_engine, name, provider)
    return extraction, reasoning, formatting


@pytest.mark.parametrize('original', [False, True])
def test_worker_preserves_actual_consumed_context_and_linked_stage_results(monkeypatch, original):
    case, run = approved_run(original=original)
    before = deepcopy(run)
    extraction, reasoning, formatting = providers(monkeypatch)
    events = []
    result = execute_approved_chain(run, case, deepcopy(RUNTIME), checkpoint=lambda value, digest: events.append((value, digest)), should_stop=lambda: False)
    assert run == before
    assert result['final_output'] == 'Internal draft' and result['credit_awarded'] is False
    assert extraction.call_count == reasoning.call_count == formatting.call_count == 1
    assert [value['kind'] for value, _ in events] == ['stage_started', 'stage_completed'] * 3
    for value, digest in events:
        assert encode(value)[1] == digest
        assert value['run_id'] == run['run_id'] and value['authorization_sha256'] == encode(run['authorization'])[1]
    assert events[0][0]['consumed_context']['documents'][0]['text'] == run['plan']['input_snapshot']['documents'][0]['text']
    assert events[2][0]['consumed_context']['value'] == reasoning.call_args.kwargs['data'] == {'Amount': '$185,000'}
    assert events[4][0]['consumed_context']['value'] == formatting.call_args.args[2]
    assert events[4][0]['stage']['receives_previous_stage'] is (not original)
    assert events[2][0]['previous_stage_receipt_sha256'] == events[1][1]
    assert events[4][0]['previous_stage_receipt_sha256'] == events[3][1]
    assert all(events[index + 1][0]['started_receipt_sha256'] == events[index][1] for index in (0, 2, 4))
    assert [item['receipt_sha256'] for item in result['stage_receipts']] == [events[index][1] for index in (1, 3, 5)]


@pytest.mark.parametrize('stage', [0, 1, 2])
def test_provider_failure_preserves_completed_prefix_without_dispatching_successors(monkeypatch, stage):
    case, run = approved_run()
    mocks = providers(monkeypatch)
    mocks[stage].side_effect = RuntimeError('synthetic provider failure')
    events = []
    with pytest.raises(RuntimeError, match='synthetic provider'):
        execute_approved_chain(run, case, RUNTIME, checkpoint=lambda value, digest: events.append(value), should_stop=lambda: False)
    assert [mock.call_count for mock in mocks] == [int(index <= stage) for index in range(3)]
    assert len([event for event in events if event['kind'] == 'stage_completed']) == stage
    assert events[-1]['kind'] == 'stage_started' and events[-1]['stage_index'] == stage


@pytest.mark.parametrize('fail_event', range(6))
def test_checkpoint_failure_stops_before_next_provider_and_never_retries(monkeypatch, fail_event):
    case, run = approved_run()
    mocks = providers(monkeypatch)
    events = []

    def checkpoint(value, digest):
        if len(events) == fail_event:
            raise OSError('synthetic lost durable checkpoint')
        events.append(value)

    with pytest.raises(OSError, match='durable checkpoint'):
        execute_approved_chain(run, case, RUNTIME, checkpoint=checkpoint, should_stop=lambda: False)
    assert [mock.call_count for mock in mocks] == [int(index < (fail_event + 1) // 2) for index in range(3)]
    assert len(events) == fail_event


@pytest.mark.parametrize('change', ['unclaimed', 'missing_approval', 'hold', 'actor', 'approval_reference', 'plan', 'runtime', 'implementation'])
def test_worker_rejects_changed_authorization_or_runtime_before_any_provider(monkeypatch, change):
    case, run = approved_run()
    mocks = providers(monkeypatch)
    config = deepcopy(RUNTIME)
    if change == 'unclaimed':
        run['state'] = 'prepared'
    elif change == 'missing_approval':
        run['authorization'] = None
    elif change == 'hold':
        run['authorization']['decision']['submission']['choice'] = 'hold'
    elif change == 'actor':
        run['authorization']['decision']['user_id'] = 'foreign'
    elif change == 'approval_reference':
        run['scope_decision_id'] = 'f' * 32
    elif change == 'plan':
        run['plan']['engine_steps'][2]['tasks'][0]['data']['prompt'] = 'Another task'
    elif change == 'runtime':
        config['available_models'][0]['temperature'] = 0.2
    else:
        monkeypatch.setattr('app.services.certification_versions.connected_workflow_plan.implementation_digest', lambda: 'f' * 64)
    with pytest.raises(EnrollmentConflict):
        execute_approved_chain(run, case, config, checkpoint=lambda *_: None, should_stop=lambda: False)
    assert all(mock.call_count == 0 for mock in mocks)


def test_stop_after_durable_start_prevents_provider_dispatch(monkeypatch):
    case, run = approved_run()
    mocks = providers(monkeypatch)
    events = []
    with pytest.raises(workflow_engine.WorkflowCancelled):
        execute_approved_chain(run, case, RUNTIME, checkpoint=lambda value, digest: events.append(value), should_stop=lambda: bool(events))
    assert len(events) == 1 and events[0]['kind'] == 'stage_started'
    assert all(mock.call_count == 0 for mock in mocks)


def test_assessed_extraction_rejects_skipped_source_before_reasoning(monkeypatch):
    case, run = approved_run()
    engine = Mock()
    engine.tokens_in = engine.tokens_out = 0
    engine.extract.return_value = [{'Amount': '$185,000'}]
    engine.skipped_doc_indices = [0]
    monkeypatch.setattr(workflow_engine, 'ExtractionEngine', Mock(return_value=engine))
    reasoning, formatting = Mock(), Mock()
    monkeypatch.setattr(workflow_engine, 'llm_chat_model', reasoning)
    monkeypatch.setattr(workflow_engine, 'format_model', formatting)
    events = []
    with pytest.raises(ValueError, match='did not complete'):
        execute_approved_chain(run, case, RUNTIME, checkpoint=lambda value, digest: events.append(value), should_stop=lambda: False)
    assert engine.extract.call_count == 1
    assert reasoning.call_count == formatting.call_count == 0
    assert len(events) == 1 and events[0]['kind'] == 'stage_started'


def test_explicit_engine_error_keeps_failed_stage_receipt_and_completed_prefix(monkeypatch):
    case, run = approved_run()
    extraction, reasoning, formatting = providers(monkeypatch)
    monkeypatch.setattr(workflow_engine.PromptNode, 'process', lambda self, inputs: {
        'output': 'Synthetic unavailable stage', 'error': 'Synthetic unavailable stage', 'step_name': 'Prompt'})
    events = []
    with pytest.raises(workflow_engine.WorkflowStepError):
        execute_approved_chain(run, case, RUNTIME, checkpoint=lambda value, digest: events.append(value), should_stop=lambda: False)
    assert extraction.call_count == 1 and reasoning.call_count == formatting.call_count == 0
    assert len(events) == 4 and events[1]['status'] == 'completed' and events[3]['status'] == 'failed'


def test_extraction_source_sidecar_survives_in_stage_receipt(monkeypatch):
    case, run = approved_run()
    extraction, _, _ = providers(monkeypatch)
    source = {'Amount': {'quote': '$185,000', 'document_id': run['plan']['source_document_id'], 'page': 1}}
    extraction.return_value['raw'][0][workflow_engine.SOURCE_KEY] = source
    events = []
    execute_approved_chain(run, case, RUNTIME, checkpoint=lambda value, digest: events.append(value), should_stop=lambda: False)
    assert events[1]['result']['field_sources'] == [source]
    assert events[2]['consumed_context']['value'] == {'Amount': '$185,000'}


def test_oversized_checkpoint_stops_without_truncation_or_provider_call(monkeypatch):
    case, run = approved_run()
    mocks = providers(monkeypatch)
    monkeypatch.setattr('app.services.certification_versions.connected_workflow_runtime.MAX_STAGE_BYTES', 1)
    events = []
    with pytest.raises(EnrollmentConflict, match='size limit'):
        execute_approved_chain(run, case, RUNTIME, checkpoint=lambda value, digest: events.append(value), should_stop=lambda: False)
    assert events == [] and all(mock.call_count == 0 for mock in mocks)
