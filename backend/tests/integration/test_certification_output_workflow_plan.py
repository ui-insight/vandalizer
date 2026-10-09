"""Owned output planning plus actual renderer/export/bundle execution with stubs."""
from copy import deepcopy
import json
import os

import pytest

from tests.integration import test_certification_output_workflow_inputs as capture_fixtures
from tests.test_certification_output_artifacts import record
from app.models.workflow import WorkflowStep, WorkflowStepTask
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.output_artifacts import capture_generated_artifacts
from app.services.certification_versions.output_workflow_plan import output_workflow_plan

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = capture_fixtures.repo
RUNTIME = {'available_models': [{'name': 'report-model'}, {'name': 'summary-model'}]}


async def fixture(repo, *, first_formatter=False):
    f = await capture_fixtures.fixture(repo)
    f.step.data = {'input_sources': ['workflow_documents']}
    f.task.name = 'Formatter' if first_formatter else 'Prompt'
    f.task.data = {'format_template' if first_formatter else 'prompt': 'Prepare the complete progress report', 'model': 'report-model'}
    await f.task.save()
    await f.step.save()
    stages = [('Report file', 'DocumentRenderer', {'format': 'pdf', 'filename': 'progress-report'}, ['step_input'], True),
              ('Summary record', 'Formatter', {'format_template': 'Prepare the complete summary record', 'model': 'summary-model'}, ['workflow_documents'], False),
              ('Summary file', 'DataExport', {'format': 'csv', 'filename': 'progress-summary'}, ['step_input'], True)]
    f.tasks, f.steps = [f.task], [f.step]
    for name, kind, data, sources, selected in stages:
        task = await WorkflowStepTask(name=kind, data=data).insert()
        step = await WorkflowStep(name=name, tasks=[task.id], data={'input_sources': sources}, is_output=selected).insert()
        f.tasks.append(task)
        f.steps.append(step)
        f.workflow.steps.append(step.id)
    await f.workflow.save()
    f.saved = await capture_fixtures.capture(repo, f)
    return f


def plan(f):
    return output_workflow_plan(f.saved, f.case, deepcopy(RUNTIME), default_model='report-model')


@pytest.mark.parametrize('first_formatter', [False, True])
async def test_real_engine_uses_source_for_both_preparations_and_emits_actual_pdf_csv_bundle(repo, monkeypatch, first_formatter):
    from app.services import workflow_engine
    f = await fixture(repo, first_formatter=first_formatter)
    before = deepcopy(f.saved)
    planned = plan(f)
    assert f.saved == before
    assert planned['execution_authorized'] is planned['release_authorized'] is planned['credit_awarded'] is False
    received = []
    def prompt(**kwargs):
        received.append(kwargs['data'])
        return json.dumps(record())
    def formatter(model, instructions, context, **kwargs):
        received.append(context)
        return 'Synthetic formatting instruction', record()
    monkeypatch.setattr(workflow_engine, 'llm_chat_model', prompt)
    monkeypatch.setattr(workflow_engine, 'format_model', formatter)
    engine = workflow_engine.build_workflow_engine(deepcopy(planned['engine_steps']), planned['default_model'],
        user_id=f.learner.user_id, system_config_doc=deepcopy(RUNTIME), allow_code_execution=False)
    actual_nodes = engine.get_topological_order()[1:]
    for node, stage in zip(actual_nodes, planned['stage_plans']):
        assert encode(node.tasks[0].data)[1] == stage['effective_settings_sha256']
    steps = {}
    def update(values):
        steps.update({key.removeprefix('steps_output.'): value for key, value in values.items() if key.startswith('steps_output.')})
    final, _ = engine.execute(workflow_result_updater=update)
    assert received == [f.document.raw_text, f.document.raw_text]
    assert 'source_checks' not in received[0] and 'review_guidance' not in received[0]
    saved = capture_generated_artifacts({'status': 'completed', 'workflow_name': f.workflow.name,
        'final_output': final, 'steps_output': steps, 'output_step_names': planned['output_step_keys']})
    assert saved['all_required_files_parseable'] is True
    assert saved['download']['file_type'] == 'zip'
    assert len(saved['files']) == 2


async def test_prose_formatter_fallback_is_preserved_as_incomplete_csv_evidence(repo, monkeypatch):
    from app.services import workflow_engine
    f = await fixture(repo)
    planned = plan(f)
    monkeypatch.setattr(workflow_engine, 'llm_chat_model', lambda **kwargs: json.dumps(record()))
    monkeypatch.setattr(workflow_engine, 'format_model', lambda *args, **kwargs: ('Synthetic formatter', 'Unstructured prose instead of a record'))
    engine = workflow_engine.build_workflow_engine(deepcopy(planned['engine_steps']), planned['default_model'],
        user_id=f.learner.user_id, system_config_doc=RUNTIME, allow_code_execution=False)
    steps = {}
    def update(values):
        steps.update({key.removeprefix('steps_output.'): value for key, value in values.items() if key.startswith('steps_output.')})
    final, _ = engine.execute(workflow_result_updater=update)
    assert 'plain text rather than CSV' in steps[planned['output_step_keys'][1]]['warning']
    saved = capture_generated_artifacts({'status': 'completed', 'final_output': final,
        'steps_output': steps, 'output_step_names': planned['output_step_keys']})
    assert saved['all_required_files_parseable'] is False
    assert saved['files'][1]['file_type'] == 'txt'


@pytest.mark.parametrize('change', ['external_delivery', 'resource', 'attachment', 'optimizer', 'unknown_model',
    'code', 'package_builder', 'wrong_step_order', 'wrong_task_order', 'wrong_output', 'missing_output',
    'formatter_reads_pdf', 'renderer_claims_source_input', 'selected_document', 'missing_prompt',
    'unresolved_prompt', 'wrong_format', 'missing_filename', 'unsafe_filename', 'source_override', 'duplicate_reference'])
async def test_unsupported_generation_is_rejected_without_silent_rewiring(repo, change):
    f = await fixture(repo)
    workflow, stages = f.saved['artifact']['workflow'], f.saved['artifact']['steps']
    if change == 'external_delivery':
        workflow['output_config'] = {'email': 'someone@example.invalid'}
    elif change == 'resource':
        workflow['resource_config'] = {'knowledge_base': 'unresolved'}
    elif change == 'attachment':
        workflow['attachments'] = [{'uuid': 'unrelated'}]
    elif change == 'optimizer':
        workflow['config_override'] = {'steps': {}}
    elif change == 'unknown_model':
        stages[0]['tasks'][0]['data']['model'] = 'not-configured'
    elif change in ('code', 'package_builder'):
        stages[1]['tasks'][0]['name'] = 'CodeNode' if change == 'code' else 'PackageBuilder'
    elif change == 'wrong_step_order':
        workflow['steps'].reverse()
    elif change == 'wrong_task_order':
        stages[0]['step']['tasks'] = stages[1]['step']['tasks']
    elif change == 'wrong_output':
        stages[0]['step']['is_output'] = True
    elif change == 'missing_output':
        stages[3]['step']['is_output'] = False
    elif change == 'formatter_reads_pdf':
        stages[2]['step']['data']['input_sources'] = ['step_input']
    elif change == 'renderer_claims_source_input':
        stages[1]['step']['data']['input_sources'] = ['workflow_documents']
    elif change == 'selected_document':
        stages[0]['tasks'][0]['data'].update(override_step_input=True, input_sources=['select_document'], selected_document_uuid='foreign')
    elif change == 'missing_prompt':
        stages[0]['tasks'][0]['data']['prompt'] = ' '
    elif change == 'unresolved_prompt':
        stages[0]['tasks'][0]['data']['prompt_id'] = 'unresolved'
    elif change == 'wrong_format':
        stages[3]['tasks'][0]['data']['format'] = 'json'
    elif change == 'missing_filename':
        stages[1]['tasks'][0]['data'].pop('filename')
    elif change == 'unsafe_filename':
        stages[1]['tasks'][0]['data']['filename'] = '../../report'
    elif change == 'source_override':
        stages[2]['tasks'][0]['data'].update(override_step_input=True, input_sources=['step_input'])
    elif change == 'duplicate_reference':
        stages[1]['tasks'][0]['id'] = stages[0]['tasks'][0]['id']
        stages[1]['step']['tasks'] = stages[0]['step']['tasks']
    f.saved['artifact_sha256'] = encode(f.saved['artifact'])[1]
    with pytest.raises(EnrollmentConflict):
        plan(f)


async def test_step_input_precedence_is_the_actual_product_precedence(repo):
    f = await fixture(repo)
    f.saved['artifact']['steps'][2]['tasks'][0]['data']['input_sources'] = ['step_input']
    f.saved['artifact_sha256'] = encode(f.saved['artifact'])[1]
    planned = plan(f)
    assert planned['stage_plans'][2]['effective_input_sources'] == ['workflow_documents']
