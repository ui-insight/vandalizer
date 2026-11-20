"""Owned output execution preserves original file bytes and never repeats providers."""
import asyncio
from copy import deepcopy
import json
import os
from threading import Event

import pytest

from tests.integration import test_certification_output_workflow_preparation as preparation_fixtures
from tests.test_certification_output_artifacts import record
from app.models.certification import CertificationLabInput, CertificationLabExecution
from app.services.certification_versions.output_workflow_execution import OutputWorkflowExecution
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
        'consent': 'execute_approved_output_workflow'}
    f.calls = []
    def prompt(**kwargs):
        f.calls.append(('report', kwargs['data']))
        return json.dumps(record())
    def formatter(model, instructions, context, **kwargs):
        f.calls.append(('summary', context))
        return 'Synthetic format', record()
    monkeypatch.setattr(workflow_engine, 'llm_chat_model', prompt)
    monkeypatch.setattr(workflow_engine, 'format_model', formatter)
    return f


async def execute(repo, f, service=None, config=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='execute_output_workflow') as progress:
        return await (service or OutputWorkflowExecution()).execute(
            CourseOperation(f.learner.user_id, f.package, progress, True), f.execution_body,
            preparation_fixtures.planning_fixtures.RUNTIME if config is None else config, actor_user_id=f.learner.user_id)


async def test_actual_generation_preserves_all_stages_files_and_original_zip_without_replay(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    saved = await execute(repo, f)
    assert saved['state'] == 'completed', saved['result']
    assert len(saved['stage_events']) == 8 and len(f.calls) == 2
    assert f.calls == [('report', f.document.raw_text), ('summary', f.document.raw_text)]
    result = saved['result']
    assert result['stage_event_count'] == 8
    assert result['generated_artifacts']['all_required_files_parseable'] is True
    assert result['release_authorized'] is result['delivery_confirmed'] is result['credit_awarded'] is False
    assert result['generated_artifacts']['download']['file_type'] == 'zip'
    await CertificationLabInput.get_motor_collection().delete_many({})
    await f.document.delete()
    await f.workflow.delete()
    assert await execute(repo, f, config={}) == saved
    assert len(f.calls) == 2
    assert await OutputWorkflowExecution().get('foreign', saved['run_id']) is None
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_invalid_csv_remains_inspectable_repair_evidence(repo, monkeypatch):
    from app.services import workflow_engine
    f = await fixture(repo, monkeypatch)
    monkeypatch.setattr(workflow_engine, 'format_model', lambda *args, **kwargs: ('Synthetic', 'Prose instead of a record'))
    saved = await execute(repo, f)
    assert saved['state'] == 'completed'
    artifacts = saved['result']['generated_artifacts']
    assert artifacts['all_required_files_parseable'] is False
    assert artifacts['files'][1]['file_type'] == 'txt'
    assert 'unexpected_file_format' in artifacts['files'][1]['inspection']['issues']


@pytest.mark.parametrize('failure', ['exception', 'checkpoint_limit'])
async def test_failure_preserves_prefix_and_cannot_repeat_providers(repo, monkeypatch, failure):
    from app.services import workflow_engine
    from app.services.certification_versions import output_workflow_checkpoints
    f = await fixture(repo, monkeypatch)
    if failure == 'checkpoint_limit':
        monkeypatch.setattr(output_workflow_checkpoints, 'MAX_CHECKPOINT_BYTES', 100)
    def formatter(*args, **kwargs):
        f.calls.append(('summary', 'failed'))
        raise RuntimeError('PRIVATE PROVIDER SECRET')
    monkeypatch.setattr(workflow_engine, 'format_model', formatter)
    saved = await execute(repo, f)
    assert saved['state'] == 'failed'
    assert 'PRIVATE PROVIDER SECRET' not in encode(saved)[0]
    if failure == 'checkpoint_limit':
        assert f.calls == [] and saved['stage_events'] == []
    else:
        assert len(saved['stage_events']) == 5  # Two results plus the failed provider's saved start.
    original_calls = deepcopy(f.calls)
    assert await execute(repo, f, config={}) == saved
    assert f.calls == original_calls


async def test_lost_terminal_write_cannot_dispatch_again(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    service = OutputWorkflowExecution()
    async def interrupted(*args):
        raise OSError('Synthetic terminal write outage')
    monkeypatch.setattr(service, '_finish_output', interrupted)
    with pytest.raises(OSError):
        await execute(repo, f, service)
    current = await OutputWorkflowExecution().get(f.learner.user_id, f.execution_body['run_id'])
    assert current['state'] == 'executing' and len(current['stage_events']) == 8
    assert await execute(repo, f, config={}) == current
    assert len(f.calls) == 2


async def test_new_hold_blocks_old_approval(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    run = await OutputWorkflowExecution().get(f.learner.user_id, f.execution_body['run_id'])
    await preparation_fixtures.decide(repo, f, preparation_fixtures.scope_body(f, run, 'hold'))
    with pytest.raises(EnrollmentConflict, match='scope choice changed'):
        await execute(repo, f)
    assert f.calls == []


@pytest.mark.parametrize('change', ['context', 'missing_stage', 'file_bytes', 'release_authority', 'event_link'])
async def test_rehashed_evidence_cannot_change_consumption_files_or_authority(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch)
    saved = await execute(repo, f)
    assert saved['state'] == 'completed'
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': saved['run_id']})
    events, result = deepcopy(saved['stage_events']), deepcopy(saved['result'])
    if change == 'context':
        events[0]['receipt']['consumed_context']['value'] = 'Fabricated source'
        events[0]['receipt_sha256'] = encode(events[0]['receipt'])[1]
    elif change == 'missing_stage':
        events = events[:-2]
    elif change == 'file_bytes':
        result['generated_artifacts']['files'][0]['data_base64'] = 'ZmFrZQ=='
    elif change == 'release_authority':
        result['release_authorized'] = True
    else:
        result['stage_receipt_sha256s'][0] = 'a' * 64
    raw['stage_events_json'], raw['stage_events_sha256'] = encode(events)
    raw['stage_event_count'] = len(events)
    result['stage_events_sha256'], result['stage_event_count'] = raw['stage_events_sha256'], len(events)
    raw['result_json'], raw['result_sha256'] = encode(result)
    with pytest.raises(CourseCatalogError):
        OutputWorkflowExecution.decode(raw)


async def test_cancelled_provider_cannot_append_or_start_successor_after_terminal_fence(repo, monkeypatch):
    from app.services import workflow_engine
    f = await fixture(repo, monkeypatch)
    entered, release = Event(), Event()
    def blocking(**kwargs):
        f.calls.append(('report', kwargs['data']))
        entered.set()
        release.wait(15)
        return json.dumps(record())
    monkeypatch.setattr(workflow_engine, 'llm_chat_model', blocking)
    task = asyncio.create_task(execute(repo, f))
    try:
        for _ in range(500):
            if entered.is_set():
                break
            await asyncio.sleep(.01)
        assert entered.is_set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        saved = await OutputWorkflowExecution().get(f.learner.user_id, f.execution_body['run_id'])
        assert saved['state'] == 'uncertain' and len(saved['stage_events']) == 1
    finally:
        release.set()
    await asyncio.sleep(.1)
    assert await execute(repo, f, config={}) == saved
    assert len(f.calls) == 1


@pytest.mark.parametrize('change', ['runtime', 'plan', 'actor'])
async def test_dispatch_rejects_changed_runtime_plan_or_actor_before_any_provider(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch)
    if change == 'plan':
        f.execution_body['plan_sha256'] = 'a' * 64
    if change == 'actor':
        async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='foreign_dispatch') as progress:
            with pytest.raises(EnrollmentConflict):
                await OutputWorkflowExecution().execute(CourseOperation(f.learner.user_id, f.package, progress, True),
                    f.execution_body, preparation_fixtures.planning_fixtures.RUNTIME, actor_user_id='foreign')
    else:
        with pytest.raises(EnrollmentConflict):
            await execute(repo, f, config={} if change == 'runtime' else None)
    assert f.calls == []
    run = await OutputWorkflowExecution().get(f.learner.user_id, f.execution_body['run_id'])
    assert run['state'] == 'prepared' and run['stage_events'] == []
