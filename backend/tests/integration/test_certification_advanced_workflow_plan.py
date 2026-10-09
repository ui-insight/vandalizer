"""Budget plans preserve owned settings and actual engine dependency behavior."""
from copy import deepcopy
import os
from threading import Barrier, Lock

import pytest

from tests.integration import test_certification_advanced_workflow_inputs as capture_fixtures
from app.models.workflow import WorkflowStep, WorkflowStepTask
from app.services.certification_versions.advanced_workflow_plan import advanced_workflow_plan
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.enrollments import EnrollmentConflict

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = capture_fixtures.repo
RUNTIME = {'available_models': [{'name': 'review-model'}, {'name': 'memo-model'}]}


async def fixture(repo, *, parallel=True):
    f = await capture_fixtures.fixture(repo)
    f.step.data = {'input_sources': ['workflow_documents']}
    f.task.data = {'prompt': 'Review source purposes', 'model': 'review-model'}
    await f.task.save()
    if parallel:
        sibling = await WorkflowStepTask(name='Prompt', data={'prompt': 'Review source conflicts'}).insert()
        f.step.tasks.append(sibling.id)
    await f.step.save()
    memo = await WorkflowStepTask(name='Prompt', data={'prompt': 'Write the internal memo', 'model': 'memo-model'}).insert()
    memo_step = await WorkflowStep(name='Internal memo', tasks=[memo.id],
        data={'input_sources': ['step_input', 'workflow_documents']}, is_output=True).insert()
    f.workflow.steps.append(memo_step.id)
    await f.workflow.save()
    f.saved = await capture_fixtures.capture(repo, f)
    return f


def plan(f):
    return advanced_workflow_plan(f.saved, f.case, deepcopy(RUNTIME), default_model='review-model')


def reseal(f):
    f.saved['artifact_sha256'] = encode(f.saved['artifact'])[1]


@pytest.mark.parametrize('parallel', [True, False])
async def test_actual_engine_uses_saved_calculation_and_all_completed_review_results(repo, monkeypatch, parallel):
    from app.services import workflow_engine
    f = await fixture(repo, parallel=parallel)
    original = deepcopy(f.saved)
    planned = plan(f)
    assert f.saved == original
    assert planned['execution_authorized'] is planned['credit_awarded'] is False
    assert planned['arithmetic_supported'] is False
    assert planned['model_names'] == ['memo-model', 'review-model']
    assert planned['input_snapshot_sha256'] == encode(f.saved)[1]
    consumed, completed, guard = {}, [], Lock()
    barrier = Barrier(2) if parallel else None

    def provider(**kwargs):
        prompt, data = kwargs['prompt'], kwargs['data']
        with guard:
            consumed[prompt] = deepcopy(data)
        assert '45001.00' in data and '45000.00' in data
        assert 'SAVED LEARNER CALCULATIONS' in data and 'ASSIGNED BUDGET' in data
        assert 'review_guidance' not in data and 'passing_conditions' not in data
        if prompt == 'Write the internal memo':
            assert len(completed) == (2 if parallel else 1)
            assert 'RESULT: Review source purposes' in data
            if parallel:
                assert 'RESULT: Review source conflicts' in data
            return 'Internal memo preserves the unresolved arithmetic and policy claims.'
        if barrier:
            barrier.wait(timeout=10)
        with guard:
            completed.append(prompt)
        return 'RESULT: ' + prompt

    monkeypatch.setattr(workflow_engine, 'llm_chat_model', provider)
    engine = workflow_engine.build_workflow_engine(deepcopy(planned['engine_steps']), planned['default_model'],
        user_id=f.learner.user_id, system_config_doc=RUNTIME, allow_code_execution=False)
    final, _ = engine.execute()
    assert 'Internal memo preserves' in str(final)
    assert len(consumed) == (3 if parallel else 2)
    if parallel:
        assert consumed['Review source purposes'] == consumed['Review source conflicts']
        assert 'RESULT:' not in consumed['Review source purposes']


@pytest.mark.parametrize('change', ['external_delivery', 'attachment', 'resource', 'optimizer', 'code', 'api', 'crawler', 'research', 'missing_branch',
    'missing_calculations', 'unknown_model', 'blank_prompt', 'unresolved_prompt_reference',
    'foreign_document', 'wrong_output', 'task_order', 'step_order', 'forged_calculation'])
async def test_unsupported_or_missing_evidence_is_rejected_before_provider_dispatch(repo, change):
    f = await fixture(repo)
    workflow, steps = f.saved['artifact']['workflow'], f.saved['artifact']['steps']
    if change in ('external_delivery', 'attachment', 'resource', 'optimizer'):
        key = {'external_delivery': 'output_config', 'attachment': 'attachments', 'resource': 'resource_config',
               'optimizer': 'config_override'}[change]
        workflow[key] = ['external'] if key == 'attachments' else {'external': True}
    elif change in ('code', 'api', 'crawler', 'research'):
        steps[0]['tasks'][0]['name'] = {'code': 'CodeNode', 'api': 'APINode', 'crawler': 'CrawlerNode', 'research': 'ResearchNode'}[change]
    elif change == 'missing_branch':
        steps[1]['step']['data']['input_sources'] = ['workflow_documents']
    elif change == 'missing_calculations':
        steps[1]['step']['data']['input_sources'] = ['step_input']
    elif change == 'unknown_model':
        steps[0]['tasks'][0]['data']['model'] = 'not-available'
    elif change == 'blank_prompt':
        steps[0]['tasks'][0]['data']['prompt'] = ' '
    elif change == 'unresolved_prompt_reference':
        steps[0]['tasks'][0]['data']['prompt_uuid'] = 'live-library-reference'
    elif change == 'foreign_document':
        steps[0]['step']['data']['selected_document_uuid'] = 'foreign'
    elif change == 'wrong_output':
        steps[0]['step']['is_output'] = True
    elif change == 'task_order':
        steps[0]['tasks'].reverse()
    elif change == 'step_order':
        workflow['steps'].reverse()
    else:
        f.saved['calculation_snapshot']['checks']['all_arithmetic_supported'] = True
        f.saved['request']['calculation_snapshot_sha256'] = encode(f.saved['calculation_snapshot'])[1]
        f.saved['request_sha256'] = encode(f.saved['request'])[1]
    reseal(f)
    with pytest.raises(EnrollmentConflict):
        plan(f)


async def test_first_step_legacy_previous_input_resolves_to_documents_not_sibling_results(repo):
    f = await fixture(repo)
    f.saved['artifact']['steps'][0]['tasks'][1]['data'].update(override_step_input=True, input_sources=['step_input'])
    reseal(f)
    planned = plan(f)
    assert planned['stage_plans'][0]['tasks'][1]['effective_input_sources'] == ['workflow_documents']
    assert planned['stage_plans'][0]['tasks_share_previous_stage_only'] is True


async def test_one_failed_branch_stops_memo_in_actual_engine(repo, monkeypatch):
    from app.services import workflow_engine
    f = await fixture(repo)
    planned = plan(f)
    calls = []

    def provider(**kwargs):
        calls.append(kwargs['prompt'])
        if kwargs['prompt'] == 'Review source conflicts':
            raise RuntimeError('Synthetic provider unavailable')
        return 'Source-purpose review result'

    monkeypatch.setattr(workflow_engine, 'llm_chat_model', provider)
    engine = workflow_engine.build_workflow_engine(deepcopy(planned['engine_steps']), planned['default_model'],
        user_id=f.learner.user_id, system_config_doc=RUNTIME, allow_code_execution=False)
    with pytest.raises(RuntimeError, match='Synthetic provider'):
        engine.execute()
    assert 'Write the internal memo' not in calls
