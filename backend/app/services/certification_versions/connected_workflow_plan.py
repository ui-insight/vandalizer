"""Plan a bounded internal chain from frozen inputs without executing it."""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

from .attempts import encode
from .enrollments import EnrollmentConflict
from .lab_execution import implementation_digest as extraction_implementation_digest, runtime_digest

INPUT_KEYS = {'input_sources', 'input_source', 'selected_document_uuid'}
TASK_INPUT_KEYS = INPUT_KEYS | {'override_step_input'}
SOURCES = {'step_input', 'workflow_documents', 'select_document'}
TASK_KEYS = {
    'Extraction': TASK_INPUT_KEYS | {'model', 'extractions', 'search_set_uuid'},
    'Prompt': TASK_INPUT_KEYS | {'model', 'prompt'},
    'Formatter': TASK_INPUT_KEYS | {'model', 'format_template', 'prompt'},
}


def implementation_digest():
    services = Path(__file__).resolve().parents[1]
    paths = [Path(__file__), services / 'workflow_engine.py', services / 'workflow_prompt_variants.py',
             Path(__file__).with_name('connected_workflow_inputs.py'), Path(__file__).with_name('multi_step_case.py'),
             Path(__file__).with_name('connected_workflow_preparation.py'), Path(__file__).with_name('connected_workflow_approval.py'),
             Path(__file__).with_name('connected_workflow_runtime.py'), Path(__file__).with_name('connected_workflow_checkpoints.py'),
             Path(__file__).with_name('connected_workflow_execution.py'), Path(__file__).with_name('connected_workflow_recovery.py')]
    paths.append(Path(__file__).with_name('connected_failure_practice.py'))
    return encode({'extraction': extraction_implementation_digest(),
                   'files': {str(path.relative_to(services.parent)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}})[1]


def checked_sources(data):
    if set(data) - (TASK_INPUT_KEYS | TASK_KEYS['Extraction'] | TASK_KEYS['Prompt'] | TASK_KEYS['Formatter']):
        raise EnrollmentConflict('This workflow has settings the bounded executor does not support yet')
    if 'input_sources' in data and (not isinstance(data['input_sources'], list)
            or not data['input_sources'] or any(source not in SOURCES for source in data['input_sources'])
            or len(data['input_sources']) != len(set(data['input_sources']))):
        raise EnrollmentConflict('Input choices must be explicit supported sources, without ambiguous fallback')
    if 'input_source' in data and data['input_source'] not in SOURCES:
        raise EnrollmentConflict('This saved legacy input choice is unsupported')
    if 'override_step_input' in data and type(data['override_step_input']) is not bool:
        raise EnrollmentConflict('Task input override must be an explicit boolean')


def connected_workflow_plan(snapshot, case, system_config, *, default_model):
    """Support the assigned three-role chain, using product input precedence.

    No live artifact/source lookup occurs. Unsupported integrations, linked
    prompts and optimizer/template settings stop preparation, never become a
    learner failure or get silently dropped. Original wrong-input configurations
    remain runnable inside this internal-only scope for the repair exercise.
    """
    from app.services.extraction_engine import ExtractionEngine
    from app.services.workflow_engine import apply_step_input_config, _resolve_input_sources, build_step_output_keys
    try:
        artifact, documents = snapshot['artifact'], snapshot['documents']
        if (snapshot['record_kind'] != 'connected_workflow_input' or snapshot['module_id'] != 'multi_step'
                or snapshot['case'] != case.public_definition() or len(documents) != 1
                or documents[0]['source_sha256'] != case.source_sha256
                or documents[0]['assigned_filename'] != case.source_filename
                or not documents[0]['text'].strip()
                or hashlib.sha256(documents[0]['text'].encode()).hexdigest() != documents[0]['text_sha256']
                or encode(artifact)[1] != snapshot['artifact_sha256']):
            raise EnrollmentConflict('The workflow plan requires the exact captured case, configuration and assigned source')
        workflow, captured_steps = artifact['workflow'], artifact['steps']
        if workflow['id'] != snapshot['artifact_id'] or workflow['user_id'] != snapshot['user_id']:
            raise EnrollmentConflict('The captured workflow identity belongs to different inputs')
        if (workflow.get('attachments') or workflow.get('resource_config') or workflow.get('output_config')
                or workflow.get('config_override') or set(workflow.get('input_config') or {}) - {'default_model'}):
            raise EnrollmentConflict('This bounded workflow cannot resolve external resources, delivery or advanced input/optimizer settings yet')
        if len(captured_steps) != 3 or any(len(item['tasks']) != 1 for item in captured_steps):
            raise EnrollmentConflict('This assessed executor supports one extraction, reasoning and formatting task in order')
        if [item['tasks'][0]['name'] for item in captured_steps] != ['Extraction', 'Prompt', 'Formatter']:
            raise EnrollmentConflict('The captured workflow must contain the assigned extraction, reasoning and formatting roles')
        outputs = [index for index, item in enumerate(captured_steps) if item['step'].get('is_output')]
        if outputs not in ([], [2]):
            raise EnrollmentConflict('The bounded deliverable must be the final internal formatting result')
        model_options = [item.get('name') for item in system_config.get('available_models', [])]
        if any(not isinstance(name, str) or not name for name in model_options) or len(model_options) != len(set(model_options)):
            raise EnrollmentConflict('Configured model identities must be unique and nonempty')
        configured = set(model_options)
        saved_default = (workflow.get('input_config') or {}).get('default_model')
        if saved_default is not None and not isinstance(saved_default, str):
            raise EnrollmentConflict('The saved default model is not a supported model identity')
        base_model = (workflow.get('input_config') or {}).get('default_model') or default_model
        if not isinstance(base_model, str) or not base_model or base_model not in configured:
            raise EnrollmentConflict('Select an explicit configured default model before preparing the workflow')
        source = documents[0]
        meta = {'uuid': source['document_id'], 'title': source['title'], 'text_markers': deepcopy(source['text_markers'])}
        engine_steps = [{'name': 'Document', 'data': {'doc_uuids': [source['document_id']]}, 'tasks': []}]
        stage_plans, model_names, references = [], set(), set()
        for index, item in enumerate(captured_steps):
            step, task = item['step'], item['tasks'][0]
            if not step['name'].strip() or step['name'] == 'Document' or set(step['data']) - INPUT_KEYS:
                raise EnrollmentConflict('A saved step name or setting cannot be represented unambiguously')
            data = deepcopy(task['data'])
            if set(data) - TASK_KEYS[task['name']]:
                raise EnrollmentConflict('A saved task has unsupported dependencies or execution settings')
            checked_sources(step['data'])
            checked_sources(data)
            apply_step_input_config(deepcopy(step['data']), data)
            sources = _resolve_input_sources(data, 'Document' if index == 0 else captured_steps[index - 1]['tasks'][0]['name'])
            selected = data.get('selected_document_uuid')
            if selected and selected != source['document_id']:
                raise EnrollmentConflict('A selected document is outside the captured assigned source')
            if 'select_document' in sources and selected != source['document_id']:
                raise EnrollmentConflict('Select the captured assigned source explicitly before using selected-document input')
            if data.get('model') is not None and not isinstance(data['model'], str):
                raise EnrollmentConflict('The saved task model is not a supported model identity')
            model = data.get('model') or base_model
            if not isinstance(model, str) or model not in configured:
                raise EnrollmentConflict('Every workflow task must resolve to an explicit configured model')
            data['model'] = model
            data['doc_texts'], data['doc_metas'] = [source['text']], [deepcopy(meta)]
            if 'select_document' in sources:
                data['selected_doc_text'], data['selected_doc_meta'] = source['text'], deepcopy(meta)
            stage = {'step_id': step['id'], 'task_id': task['id'], 'step_name': step['name'],
                     'task_type': task['name'], 'effective_input_sources': sources,
                     'selected_document_id': selected or None, 'requested_model': model,
                     'receives_previous_stage': index > 0 and 'step_input' in sources}
            if task['name'] == 'Extraction':
                data['require_complete_extraction'] = True
                reference = data.get('search_set_uuid')
                if reference:
                    references.add(reference)
                    template = artifact.get('referenced_extraction_sets', {}).get(reference)
                    if (not template or template.get('uuid') != reference or template.get('domain')
                            or template.get('extraction_config') or template.get('extraction_config_override')
                            or template.get('cross_field_rules')):
                        raise EnrollmentConflict('Referenced extraction settings cannot be silently omitted by this workflow executor')
                    fields = template['fields']
                    data['keys'] = [field['searchphrase'] for field in fields]
                    data['field_metadata'] = [{'key': field['searchphrase'], 'is_optional': field['is_optional'],
                                               'enum_values': field['enum_values']} for field in fields]
                    data.pop('extractions', None)
                else:
                    raw = data.get('extractions')
                    data['extractions'] = [part.strip() for part in raw.split(',') if part.strip()] if isinstance(raw, str) else raw
                keys = data.get('keys') or data.get('extractions')
                if (not isinstance(keys, list) or not keys or any(not isinstance(key, str) or not key.strip() for key in keys)
                        or len(keys) != len({key.strip().casefold() for key in keys})):
                    raise EnrollmentConflict('The extraction requires unique nonempty captured fields')
                engine = ExtractionEngine(system_config_doc=deepcopy(system_config))
                config = engine._resolve_config()
                info = engine.effective_model_info(fallback_model=model)
                if config.get('mode') not in ('one_pass', 'two_pass') or config.get('use_images'):
                    raise EnrollmentConflict('The bounded workflow requires supported text extraction settings')
                if config.get('mode') == 'one_pass':
                    actual_models = {config.get('one_pass', {}).get('model') or info['model']}
                else:
                    actual_models = set(info['pass_models'].values())
                stage.update(effective_extraction_config=config, effective_model_info=info)
            else:
                instructions = data.get('prompt') if task['name'] == 'Prompt' else data.get('format_template') or data.get('prompt')
                if not isinstance(instructions, str) or not instructions.strip():
                    raise EnrollmentConflict('Reasoning and formatting require saved nonempty instructions')
                actual_models = {model}
            if not actual_models or not actual_models <= configured or not all(actual_models):
                raise EnrollmentConflict('Every effective provider pass must use a configured model')
            model_names.update(actual_models)
            stage['model_names'] = sorted(actual_models)
            stage['effective_settings_sha256'] = encode(data)[1]
            stage_plans.append(stage)
            engine_steps.append({'name': step['name'], 'data': deepcopy(step['data']),
                                 'tasks': [{'name': task['name'], 'data': data}]})
        if set(artifact.get('referenced_extraction_sets', {})) != references:
            raise EnrollmentConflict('Captured extraction dependencies differ from the selected tasks')
        output_keys = build_step_output_keys([SimpleNamespace(name=step['name']) for step in engine_steps])
        for stage, key in zip(stage_plans, output_keys[1:]):
            stage['output_key'] = key
        return {'executor_id': 'saved-internal-workflow.1', 'implementation_sha256': implementation_digest(),
                'runtime_config_sha256': runtime_digest(system_config), 'input_snapshot_sha256': encode(snapshot)[1],
                'case_sha256': case.digest, 'source_document_id': source['document_id'],
                'default_model': base_model, 'model_names': sorted(model_names), 'stage_plans': stage_plans,
                'engine_steps': engine_steps, 'output_step_key': output_keys[-1],
                'required_connections_present': all(stage['receives_previous_stage'] for stage in stage_plans[1:]),
                'execution_authorized': False, 'credit_awarded': False}
    except EnrollmentConflict:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise EnrollmentConflict('The captured workflow cannot be resolved without changing its saved inputs') from exc
