"""Bounded planning preserves actual settings and never dispatches a provider."""
from copy import deepcopy
import hashlib
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.connected_workflow_plan import connected_workflow_plan
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.multi_step_case import MultiStepCase

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'
RUNTIME = {'available_models': [{'name': 'base-model'}, {'name': 'extract-model'}, {'name': 'format-model'}],
           'extraction_config': {'mode': 'one_pass', 'model': 'extract-model'}}


def fixture():
    case = MultiStepCase.model_validate_json((DRAFT / 'multi-step-case.json').read_bytes())
    data = [{'extractions': ['Amount', 'Reporting terms']}, {'prompt': 'Preserve supported terms and unresolved issues.'},
            {'format_template': 'Keep source facts distinct from interpretation.'}]
    artifact = {'workflow': {'id': 'a' * 24, 'user_id': 'learner', 'input_config': {}, 'output_config': {},
                             'resource_config': {}, 'attachments': [], 'config_override': None},
                'steps': [{'step': {'id': str(index) * 24, 'name': name + ' stage', 'data': {'input_sources': sources},
                                    'is_output': index == 3},
                           'tasks': [{'id': str(index + 3) * 24, 'name': name, 'data': settings}]}
                          for index, name, sources, settings in zip([1, 2, 3], ['Extraction', 'Prompt', 'Formatter'],
                              [['workflow_documents'], ['step_input'], ['step_input']], data)],
                'referenced_extraction_sets': {}}
    text = 'Synthetic ingested source for the planning unit fixture.'
    snapshot = {'record_kind': 'connected_workflow_input', 'module_id': 'multi_step', 'artifact_id': 'a' * 24,
                'user_id': 'learner', 'case': case.public_definition(), 'artifact': artifact, 'artifact_sha256': encode(artifact)[1],
                'documents': [{'document_id': 'b' * 32, 'title': case.source_filename, 'assigned_filename': case.source_filename,
                               'source_sha256': case.source_sha256, 'text': text, 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                               'text_markers': []}]}
    return case, snapshot


def plan(snapshot, case, config=None):
    return connected_workflow_plan(snapshot, case, deepcopy(RUNTIME if config is None else config), default_model='base-model')


def reseal(snapshot):
    snapshot['artifact_sha256'] = encode(snapshot['artifact'])[1]


def test_plan_keeps_saved_inputs_and_effective_models_without_dispatch(monkeypatch):
    from app.services import workflow_engine
    provider = Mock(side_effect=AssertionError('Planning must not execute models'))
    monkeypatch.setattr(workflow_engine, 'data_extraction_model', provider)
    monkeypatch.setattr(workflow_engine, 'llm_chat_model', provider)
    monkeypatch.setattr(workflow_engine, 'format_model', provider)
    case, saved = fixture()
    before = deepcopy(saved)
    result = plan(saved, case)
    assert saved == before
    assert result['execution_authorized'] is result['credit_awarded'] is False
    assert result['required_connections_present'] is True
    assert result['model_names'] == ['base-model', 'extract-model']
    assert result['stage_plans'][0]['requested_model'] == 'base-model'
    assert result['stage_plans'][0]['effective_model_info']['model'] == 'extract-model'
    assert result['input_snapshot_sha256'] == encode(saved)[1]
    assert result['engine_steps'][1]['tasks'][0]['data']['doc_texts'] == [saved['documents'][0]['text']]
    assert result['engine_steps'][1]['tasks'][0]['data']['doc_metas'][0]['uuid'] == saved['documents'][0]['document_id']
    provider.assert_not_called()


@pytest.mark.parametrize('task_override,expected', [(False, False), (True, True)])
def test_original_fault_and_task_override_keep_product_precedence(task_override, expected):
    case, saved = fixture()
    formatter = saved['artifact']['steps'][2]
    formatter['step']['data']['input_sources'] = ['workflow_documents']
    formatter['tasks'][0]['data'].update(input_sources=['step_input'], override_step_input=task_override)
    reseal(saved)
    result = plan(saved, case)
    assert result['required_connections_present'] is expected
    assert result['stage_plans'][2]['effective_input_sources'] == (['step_input'] if expected else ['workflow_documents'])


def test_captured_assigned_document_can_be_selected_without_live_lookup():
    case, saved = fixture()
    saved['artifact']['steps'][0]['step']['data'] = {'input_sources': ['select_document'], 'selected_document_uuid': saved['documents'][0]['document_id']}
    reseal(saved)
    task = plan(saved, case)['engine_steps'][1]['tasks'][0]['data']
    assert task['selected_doc_text'] == saved['documents'][0]['text']
    assert task['selected_doc_meta']['uuid'] == saved['documents'][0]['document_id']


def test_saved_template_wins_over_stale_manual_fields_and_preserves_field_metadata():
    case, saved = fixture()
    task = saved['artifact']['steps'][0]['tasks'][0]['data']
    task['search_set_uuid'] = 'owned-template'
    saved['artifact']['referenced_extraction_sets']['owned-template'] = {'uuid': 'owned-template', 'fields': [
        {'searchphrase': 'Required report', 'is_optional': False, 'enum_values': ['Financial', 'Technical']},
        {'searchphrase': 'Unnamed coordinator', 'is_optional': True, 'enum_values': []}]}
    reseal(saved)
    result = plan(saved, case)['engine_steps'][1]['tasks'][0]['data']
    assert 'extractions' not in result
    assert result['keys'] == ['Required report', 'Unnamed coordinator']
    assert result['field_metadata'][1]['is_optional'] is True
    assert result['field_metadata'][0]['enum_values'] == ['Financial', 'Technical']


@pytest.mark.parametrize('change', ['attachment', 'delivery', 'resource', 'optimizer', 'fixed_documents', 'unknown_task',
    'extra_step', 'multiple_tasks', 'reserved_name', 'unknown_step_setting', 'unknown_task_setting', 'invalid_sources',
    'duplicate_sources', 'empty_sources', 'foreign_selected_source', 'missing_selected_source', 'wrong_override_type',
    'empty_prompt', 'empty_format', 'empty_fields', 'duplicate_fields', 'nonstring_field', 'unknown_model',
    'invalid_model_type', 'wrong_output', 'missing_template', 'unreferenced_template', 'template_settings',
    'wrong_source', 'changed_text', 'foreign_case', 'foreign_workflow'])
def test_unsupported_or_changed_inputs_fail_before_engine_construction(change):
    case, saved = fixture()
    workflow = saved['artifact']['workflow']
    steps = saved['artifact']['steps']
    if change in ('attachment', 'delivery', 'resource', 'optimizer', 'fixed_documents'):
        key = {'attachment': 'attachments', 'delivery': 'output_config', 'resource': 'resource_config',
               'optimizer': 'config_override', 'fixed_documents': 'input_config'}[change]
        workflow[key] = ['external'] if key == 'attachments' else {'unresolved': 'external'}
    elif change == 'unknown_task':
        steps[1]['tasks'][0]['name'] = 'APICall'
    elif change == 'extra_step':
        steps.append(deepcopy(steps[-1]))
    elif change == 'multiple_tasks':
        steps[1]['tasks'].append(deepcopy(steps[1]['tasks'][0]))
    elif change == 'reserved_name':
        steps[1]['step']['name'] = 'Document'
    elif change == 'unknown_step_setting':
        steps[1]['step']['data']['script'] = 'unresolved'
    elif change == 'unknown_task_setting':
        steps[1]['tasks'][0]['data']['prompt_uuid'] = 'live-prompt-reference'
    elif change in ('invalid_sources', 'duplicate_sources', 'empty_sources'):
        steps[1]['step']['data']['input_sources'] = {'invalid_sources': ['previous_step'], 'duplicate_sources': ['step_input', 'step_input'], 'empty_sources': []}[change]
    elif change in ('foreign_selected_source', 'missing_selected_source'):
        steps[1]['step']['data'] = {'input_sources': ['select_document']}
        if change == 'foreign_selected_source':
            steps[1]['step']['data']['selected_document_uuid'] = 'foreign'
    elif change == 'wrong_override_type':
        steps[1]['tasks'][0]['data']['override_step_input'] = 'false'
    elif change == 'empty_prompt':
        steps[1]['tasks'][0]['data']['prompt'] = ' '
    elif change == 'empty_format':
        steps[2]['tasks'][0]['data']['format_template'] = ''
    elif change in ('empty_fields', 'duplicate_fields', 'nonstring_field'):
        steps[0]['tasks'][0]['data']['extractions'] = {'empty_fields': [], 'duplicate_fields': ['Amount', ' amount '], 'nonstring_field': [42]}[change]
    elif change in ('unknown_model', 'invalid_model_type'):
        steps[1]['tasks'][0]['data']['model'] = 'unconfigured-model' if change == 'unknown_model' else False
    elif change == 'wrong_output':
        steps[0]['step']['is_output'] = True
    elif change in ('missing_template', 'template_settings'):
        steps[0]['tasks'][0]['data']['search_set_uuid'] = 'owned-template'
        if change == 'template_settings':
            saved['artifact']['referenced_extraction_sets']['owned-template'] = {'uuid': 'owned-template', 'extraction_config_override': {'temperature': 0.1}}
    elif change == 'unreferenced_template':
        saved['artifact']['referenced_extraction_sets']['unused'] = {'uuid': 'unused'}
    elif change == 'wrong_source':
        saved['documents'][0]['source_sha256'] = 'f' * 64
    elif change == 'changed_text':
        saved['documents'][0]['text'] = 'New source ingestion'
    elif change == 'foreign_case':
        saved['case']['revision'] += 1
    else:
        workflow['user_id'] = 'foreign'
    reseal(saved)
    with pytest.raises(EnrollmentConflict):
        plan(saved, case)


@pytest.mark.parametrize('change', ['images', 'mode', 'pass_model', 'duplicate_models'])
def test_effective_provider_configuration_is_checked_before_execution(change):
    case, saved = fixture()
    config = deepcopy(RUNTIME)
    if change == 'images':
        config['extraction_config']['use_images'] = True
    elif change == 'mode':
        config['extraction_config']['mode'] = 'unknown'
    elif change == 'pass_model':
        config['extraction_config']['one_pass'] = {'model': 'unconfigured-pass'}
    else:
        config['available_models'].append({'name': 'base-model'})
    with pytest.raises(EnrollmentConflict):
        plan(saved, case, config)


@pytest.mark.parametrize('variant', ['corrected', 'original', 'stale_task', 'task_override', 'selected', 'template', 'duplicate_names'])
def test_planned_stages_execute_with_product_context_and_model_rules(monkeypatch, variant):
    from app.services import workflow_engine
    case, saved = fixture()
    steps = saved['artifact']['steps']
    steps[2]['tasks'][0]['data']['model'] = 'format-model'
    if variant in ('original', 'stale_task', 'task_override'):
        steps[2]['step']['data']['input_sources'] = ['workflow_documents']
    if variant in ('stale_task', 'task_override'):
        steps[2]['tasks'][0]['data'].update(input_sources=['step_input'], override_step_input=variant == 'task_override')
    if variant == 'selected':
        steps[0]['step']['data'] = {'input_sources': ['select_document'], 'selected_document_uuid': saved['documents'][0]['document_id']}
    if variant == 'template':
        steps[0]['tasks'][0]['data']['search_set_uuid'] = 'owned-template'
        saved['artifact']['referenced_extraction_sets']['owned-template'] = {'uuid': 'owned-template', 'fields': [
            {'searchphrase': 'Report', 'is_optional': True, 'enum_values': ['Financial', 'Technical']}]}
    if variant == 'duplicate_names':
        for item in steps:
            item['step']['name'] = 'Saved stage'
    reseal(saved)
    planned = plan(saved, case)
    before = deepcopy(planned)
    extraction = Mock(return_value={'raw': [{'Amount': '$185,000'}], 'formatted': 'Amount: $185,000'})
    reasoning = Mock(return_value='Separate reporting obligations; comparison standard is unavailable.')
    formatter = Mock(return_value=('Provider prompt', 'Final internal draft'))
    monkeypatch.setattr(workflow_engine, 'data_extraction_model', extraction)
    monkeypatch.setattr(workflow_engine, 'llm_chat_model', reasoning)
    monkeypatch.setattr(workflow_engine, 'format_model', formatter)
    engine = workflow_engine.build_workflow_engine(deepcopy(planned['engine_steps']), planned['default_model'],
        user_id=saved['user_id'], system_config_doc=deepcopy(RUNTIME), allow_code_execution=False)
    updates = []
    final, results = engine.execute(workflow_result_updater=updates.append)
    assert planned == before
    assert final == 'Final internal draft' and len(results) == 4
    assert extraction.call_count == reasoning.call_count == formatter.call_count == 1
    assert extraction.call_args.args[0] == 'base-model'
    assert extraction.call_args.kwargs['system_config_doc']['extraction_config']['model'] == 'extract-model'
    # MultiTaskNode unwraps the single extracted entity before the next stage.
    assert reasoning.call_args.kwargs['data'] == {'Amount': '$185,000'}
    assert reasoning.call_args.kwargs['model'] == 'base-model'
    assert formatter.call_args.args[0] == 'format-model'
    expected = saved['documents'][0]['text'] if variant in ('original', 'stale_task') else reasoning.return_value
    assert formatter.call_args.args[2] == expected
    source_arg = 'full_text' if variant == 'selected' else 'doc_texts'
    assert extraction.call_args.kwargs[source_arg] == (saved['documents'][0]['text'] if variant == 'selected' else [saved['documents'][0]['text']])
    assert extraction.call_args.kwargs['doc_metadata'][0]['uuid'] == saved['documents'][0]['document_id']
    if variant == 'template':
        assert extraction.call_args.args[1] == ['Report']
        assert extraction.call_args.kwargs['field_metadata'] == [{'key': 'Report', 'is_optional': True, 'enum_values': ['Financial', 'Technical']}]
    keys = [stage['output_key'] for stage in planned['stage_plans']]
    assert len(set(keys)) == 3
    assert all(any('steps_output.' + key in update for update in updates) for key in keys)


@pytest.mark.parametrize('change', ['actor', 'artifact', 'model', 'grade', 'consent', 'digest', 'request'])
def test_plan_request_accepts_only_explicit_captured_identity(change):
    from pydantic import ValidationError
    from app.services.certification_versions.connected_workflow_preparation import ConnectedPlanRequest
    body = {'request_id': 'a' * 32, 'input_snapshot_id': 'b' * 32, 'input_snapshot_sha256': 'c' * 64,
            'case_sha256': 'd' * 64, 'consent': 'prepare_connected_workflow_plan'}
    if change == 'consent':
        body['consent'] = 'execute_workflow'
    elif change == 'digest':
        del body['input_snapshot_sha256']
    elif change == 'request':
        body['request_id'] = 'invalid'
    else:
        body[change] = 'client supplied assertion'
    with pytest.raises(ValidationError):
        ConnectedPlanRequest.model_validate(body)


@pytest.mark.parametrize('change', ['actor', 'award', 'consent', 'plan', 'blank_reason', 'choice'])
def test_scope_request_cannot_invent_authority_or_omit_exact_plan(change):
    from pydantic import ValidationError
    from app.services.certification_versions.connected_workflow_approval import ConnectedScopeRequest
    body = {'request_id': 'a' * 32, 'run_id': 'b' * 32, 'plan_sha256': 'c' * 64,
            'case_sha256': 'd' * 64, 'choice': 'approve', 'reason': 'I checked the scope and saved source.',
            'consent': 'save_connected_workflow_scope_decision'}
    if change == 'consent':
        body['consent'] = 'agent_approval'
    elif change == 'plan':
        del body['plan_sha256']
    elif change == 'blank_reason':
        body['reason'] = ' ' * 30
    elif change == 'choice':
        body['choice'] = 'staff_review'
    else:
        body[change] = 'client assertion'
    with pytest.raises(ValidationError):
        ConnectedScopeRequest.model_validate(body)


@pytest.mark.parametrize('mode', ['one_pass', 'two_pass'])
def test_effective_pass_model_overrides_do_not_claim_an_unused_base_model(mode):
    case, saved = fixture()
    config = deepcopy(RUNTIME)
    config['extraction_config'].update(mode=mode, one_pass={'model': 'format-model'},
        two_pass={'pass_1': {'model': 'format-model'}, 'pass_2': {'model': 'base-model'}})
    stage = plan(saved, case, config)['stage_plans'][0]
    assert stage['effective_model_info']['model'] == 'extract-model'
    assert stage['model_names'] == (['format-model'] if mode == 'one_pass' else ['base-model', 'format-model'])


@pytest.mark.parametrize('change', ['actor', 'model', 'output', 'consent', 'approval', 'plan'])
def test_execution_request_requires_exact_reviewed_plan_and_scope_choice(change):
    from pydantic import ValidationError
    from app.services.certification_versions.connected_workflow_execution import ConnectedExecutionRequest
    body = {'run_id': 'a' * 32, 'plan_sha256': 'b' * 64, 'scope_decision_id': 'c' * 32,
            'scope_decision_sha256': 'd' * 64, 'consent': 'execute_approved_connected_workflow'}
    if change == 'consent':
        body['consent'] = 'prepare_connected_workflow_plan'
    elif change == 'approval':
        del body['scope_decision_sha256']
    elif change == 'plan':
        del body['plan_sha256']
    else:
        body[change] = 'client supplied assertion'
    with pytest.raises(ValidationError):
        ConnectedExecutionRequest.model_validate(body)


@pytest.mark.parametrize('change', ['actor', 'output', 'consent', 'approval', 'stages'])
def test_finalization_request_can_only_reference_saved_results(change):
    from pydantic import ValidationError
    from app.services.certification_versions.connected_workflow_recovery import ConnectedFinalizationRequest
    body = {'run_id': 'a' * 32, 'plan_sha256': 'b' * 64, 'authorization_sha256': 'c' * 64,
            'stage_events_sha256': 'd' * 64, 'consent': 'finalize_saved_connected_results_without_reexecution'}
    if change == 'consent':
        body['consent'] = 'retry_workflow'
    elif change == 'approval':
        del body['authorization_sha256']
    elif change == 'stages':
        del body['stage_events_sha256']
    else:
        body[change] = 'client supplied assertion'
    with pytest.raises(ValidationError):
        ConnectedFinalizationRequest.model_validate(body)
