"""Resolve bounded report/CSV generation from owned frozen source/configuration.

Four sequential stages implement the supported rendering path: source review,
PDF renderer, source-to-record formatter and CSV export. This is a supported
executor shape, never a node-count grading criterion or release authority.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

from .attempts import encode
from .catalog import CourseCatalogError
from .connected_workflow_plan import INPUT_KEYS, TASK_INPUT_KEYS, TASK_KEYS, checked_sources
from .enrollments import EnrollmentConflict
from .lab_execution import runtime_digest
from .output_artifacts import _filename
from .output_workflow_inputs import OutputWorkflowInputRepository

OUTPUT_KEYS = {'DocumentRenderer': TASK_INPUT_KEYS | {'format', 'filename', 'title'},
               'DataExport': TASK_INPUT_KEYS | {'format', 'filename'}}


def implementation_digest():
    folder = Path(__file__).parent
    paths = [Path(__file__), folder / 'output_workflow_inputs.py', folder / 'output_case.py',
             folder / 'output_artifacts.py', folder / 'connected_workflow_plan.py',
             folder / 'output_workflow_preparation.py', folder / 'output_workflow_approval.py',
             folder / 'connected_workflow_approval.py', folder / 'output_workflow_runtime.py',
             folder / 'output_workflow_checkpoints.py', folder / 'output_workflow_execution.py',
             folder / 'output_workflow_recovery.py',
             folder.parent / 'workflow_engine.py', folder.parent / 'workflow_prompt_variants.py',
             folder.parent / 'pdf_service.py', folder.parents[1] / 'routers/workflows.py']
    return encode({str(path.relative_to(folder.parents[1])): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})[1]


def output_workflow_plan(snapshot, case, system_config, *, default_model):
    from app.services.workflow_engine import apply_step_input_config, _resolve_input_sources, build_step_output_keys
    try:
        serialized, digest = encode(snapshot)
        OutputWorkflowInputRepository.decode({**snapshot, 'record_json': serialized, 'record_sha256': digest})
        if snapshot['case'] != case.public_definition():
            raise EnrollmentConflict('The captured configuration belongs to another output assignment')
        artifact = snapshot['artifact']
        workflow, captured = artifact['workflow'], artifact['steps']
        if (workflow.get('attachments') or workflow.get('resource_config') or workflow.get('output_config')
                or workflow.get('config_override') or artifact.get('referenced_extraction_sets')
                or set(workflow.get('input_config') or {}) - {'default_model'}):
            raise EnrollmentConflict('Generation is internal only; remove unresolved resources, delivery and optimizer settings')
        if (len(captured) != 4 or any(len(item['tasks']) != 1 for item in captured)
                or captured[0]['tasks'][0]['name'] not in ('Prompt', 'Formatter')
                or [item['tasks'][0]['name'] for item in captured[1:]] != ['DocumentRenderer', 'Formatter', 'DataExport']):
            raise EnrollmentConflict('Use source review, PDF rendering, source-to-record formatting and CSV export for this executor')
        if ([item['step']['id'] for item in captured] != workflow['steps']
                or any([t['id'] for t in item['tasks']] != item['step']['tasks'] for item in captured)):
            raise EnrollmentConflict('Saved workflow, step and task order disagree')
        references = [item['step']['id'] for item in captured] + [item['tasks'][0]['id'] for item in captured]
        if len(set(references)) != len(references):
            raise EnrollmentConflict('Generation requires unambiguous saved step and task identities')
        if [i for i, item in enumerate(captured) if item['step'].get('is_output')] != [1, 3]:
            raise EnrollmentConflict('Mark the PDF and CSV steps as the exact downloadable deliverables')
        models = [item.get('name') for item in system_config.get('available_models', [])]
        if any(not isinstance(name, str) or not name for name in models) or len(models) != len(set(models)):
            raise EnrollmentConflict('Configured models need distinct explicit identities')
        saved_default = (workflow.get('input_config') or {}).get('default_model')
        if saved_default is not None and (not isinstance(saved_default, str) or not saved_default):
            raise EnrollmentConflict('The workflow default model must be an explicit configured identity')
        base_model = saved_default or default_model
        if not isinstance(base_model, str) or base_model not in models:
            raise EnrollmentConflict('Select an available model before preparing generation')
        source = snapshot['documents'][0]
        metadata = {'uuid': source['document_id'], 'title': source['title'], 'text_markers': source['text_markers']}
        engine_steps = [{'name': 'Document', 'data': {'doc_uuids': [source['document_id']]}, 'tasks': []}]
        stages, used_models, filenames = [], set(), set()
        for index, item in enumerate(captured):
            step, task = item['step'], item['tasks'][0]
            kind, data = task['name'], deepcopy(task['data'])
            if not step['name'].strip() or step['name'] == 'Document' or set(step['data']) - INPUT_KEYS:
                raise EnrollmentConflict('A saved step has unsupported generation settings')
            allowed = OUTPUT_KEYS.get(kind, TASK_KEYS.get(kind))
            if set(data) - allowed:
                raise EnrollmentConflict('A task contains unresolved instructions or unsupported settings')
            checked_sources(step['data'])
            checked_sources({key: value for key, value in data.items() if key in TASK_INPUT_KEYS})
            apply_step_input_config(deepcopy(step['data']), data)
            sources = _resolve_input_sources(data, 'Document' if index == 0 else captured[index - 1]['tasks'][0]['name'])
            if index in (0, 2):
                if sources != ['workflow_documents'] or data.get('selected_document_uuid'):
                    raise EnrollmentConflict('Each source preparation must explicitly use only the assigned workflow document')
                requested = data.get('model')
                if requested is not None and (not isinstance(requested, str) or not requested):
                    raise EnrollmentConflict('The task model requires an explicit configured identity')
                model = requested or base_model
                if model not in models:
                    raise EnrollmentConflict('The selected preparation model is unavailable')
                instructions = data.get('prompt') if kind == 'Prompt' else data.get('format_template') or data.get('prompt')
                if not isinstance(instructions, str) or not instructions.strip():
                    raise EnrollmentConflict('Source preparation needs nonempty saved instructions')
                data.update(model=model, doc_texts=[source['text']], doc_metas=[deepcopy(metadata)])
                used_models.add(model)
            else:
                if sources != ['step_input'] or data.get('selected_document_uuid'):
                    raise EnrollmentConflict('Render/export tasks consume only their preceding prepared result')
                expected = 'pdf' if index == 1 else 'csv'
                if data.get('format') != expected:
                    raise EnrollmentConflict('Choose the assigned PDF and CSV formats explicitly')
                name = data.get('filename')
                if not isinstance(name, str) or not name:
                    raise EnrollmentConflict('Each deliverable requires an explicit saved filename')
                name = _filename(name + '.' + expected)
                if name in filenames:
                    raise EnrollmentConflict('Deliverable names must be distinct')
                filenames.add(name)
                if 'title' in data and (not isinstance(data['title'], str) or len(data['title']) > 300):
                    raise EnrollmentConflict('The report title is unsupported')
                data['model'] = base_model  # The actual builder sets this; renderer/export make no provider call.
                model = None
            data['user_id'] = snapshot['user_id']
            stages.append({'step_id': step['id'], 'task_id': task['id'], 'step_name': step['name'],
                'task_type': kind, 'effective_input_sources': sources, 'requested_model': model,
                'receives_previous_stage': index in (1, 3), 'is_deliverable': index in (1, 3),
                'effective_settings_sha256': encode(data)[1]})
            engine_steps.append({'name': step['name'], 'data': deepcopy(step['data']), 'tasks': [{'name': kind, 'data': data}]})
        keys = build_step_output_keys([SimpleNamespace(name=step['name']) for step in engine_steps])
        for stage, key in zip(stages, keys[1:]):
            stage['output_key'] = key
        return {'executor_id': 'saved-output-workflow.1', 'implementation_sha256': implementation_digest(),
            'runtime_config_sha256': runtime_digest(system_config), 'input_snapshot_sha256': digest,
            'case_sha256': case.digest, 'source_document_id': source['document_id'], 'default_model': base_model,
            'model_names': sorted(used_models), 'stage_plans': stages, 'engine_steps': engine_steps,
            'output_step_keys': [keys[2], keys[4]], 'execution_authorized': False, 'release_authorized': False,
            'credit_awarded': False, 'scope': 'assigned_progress_report_internal_file_generation_only'}
    except EnrollmentConflict:
        raise
    except (CourseCatalogError, KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        raise EnrollmentConflict('Output generation cannot be planned without changing its saved evidence') from exc
