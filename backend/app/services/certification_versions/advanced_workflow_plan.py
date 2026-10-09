"""Resolve internal budget interpretation and synthesis from frozen evidence.

Supports one source review, or two independent source reviews in a parallel
step, followed by one internal memo. This is an executor capability boundary,
not a node-count grading rule. No provider, database or arbitrary code runs.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

from .advanced_workflow_inputs import AdvancedWorkflowInputRepository
from .attempts import encode
from .catalog import CourseCatalogError
from .connected_workflow_plan import INPUT_KEYS, TASK_KEYS, checked_sources
from .enrollments import EnrollmentConflict
from .lab_execution import runtime_digest


def implementation_digest():
    folder = Path(__file__).parent
    paths = [Path(__file__), folder / 'advanced_workflow_inputs.py', folder / 'advanced_calculation_records.py',
             folder / 'advanced_calculations.py', folder / 'advanced_case.py', folder / 'connected_workflow_plan.py',
             folder / 'advanced_workflow_preparation.py', folder / 'advanced_workflow_approval.py',
             folder / 'connected_workflow_approval.py', folder / 'advanced_workflow_runtime.py',
             folder / 'advanced_workflow_checkpoints.py', folder / 'advanced_workflow_execution.py',
             folder / 'advanced_workflow_recovery.py',
             folder.parent / 'workflow_engine.py', folder.parent / 'workflow_prompt_variants.py']
    return encode({str(path.relative_to(folder.parent)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})[1]


def calculation_context(snapshot):
    """Only submitted arithmetic and checked facts, never the private answer key."""
    return {'kind': 'saved_learner_calculation_evidence', 'snapshot_id': snapshot['uuid'],
            'snapshot_sha256': encode(snapshot)[1], 'source_sha256': snapshot['document']['source_sha256'],
            'records': snapshot['request']['records'], 'checks': snapshot['checks']}


def advanced_workflow_plan(snapshot, case, system_config, *, default_model):
    from app.services.workflow_engine import apply_step_input_config, _resolve_input_sources, build_step_output_keys

    try:
        serialized, digest = encode(snapshot)
        AdvancedWorkflowInputRepository.decode({**snapshot, 'record_json': serialized, 'record_sha256': digest})
        if snapshot['case'] != case.public_definition():
            raise EnrollmentConflict('The captured workflow belongs to another budget case')
        artifact = snapshot['artifact']
        workflow, captured_steps = artifact['workflow'], artifact['steps']
        if (workflow.get('attachments') or workflow.get('resource_config') or workflow.get('output_config')
                or workflow.get('config_override') or artifact.get('referenced_extraction_sets')
                or set(workflow.get('input_config') or {}) - {'default_model'}):
            raise EnrollmentConflict('This internal budget executor cannot resolve external resources, delivery or optimizer settings')
        if (len(captured_steps) != 2 or len(captured_steps[0]['tasks']) not in (1, 2)
                or len(captured_steps[1]['tasks']) != 1
                or any(t['name'] != 'Prompt' for t in captured_steps[0]['tasks'])
                or captured_steps[1]['tasks'][0]['name'] not in ('Prompt', 'Formatter')):
            raise EnrollmentConflict('Use one or two source-review prompts followed by one internal memo step for this executor')
        if ([item['step']['id'] for item in captured_steps] != workflow['steps']
                or any([t['id'] for t in item['tasks']] != item['step']['tasks'] for item in captured_steps)):
            raise EnrollmentConflict('Captured step and task order differs from the owned workflow')
        all_ids = [item['step']['id'] for item in captured_steps] + [t['id'] for item in captured_steps for t in item['tasks']]
        if len(all_ids) != len(set(all_ids)):
            raise EnrollmentConflict('Captured step and task references must be unambiguous')
        outputs = [i for i, item in enumerate(captured_steps) if item['step'].get('is_output')]
        if outputs not in ([], [1]):
            raise EnrollmentConflict('Only the final internal memo can be the selected deliverable')
        models = [item.get('name') for item in system_config.get('available_models', [])]
        if any(not isinstance(name, str) or not name for name in models) or len(models) != len(set(models)):
            raise EnrollmentConflict('Configured model identities must be unique and nonempty')
        saved_default = (workflow.get('input_config') or {}).get('default_model')
        if saved_default is not None and (not isinstance(saved_default, str) or not saved_default):
            raise EnrollmentConflict('The saved default model must be an explicit configured identity')
        base_model = saved_default or default_model
        if not isinstance(base_model, str) or base_model not in models:
            raise EnrollmentConflict('Select an available default model before preparing this workflow')
        calculation = snapshot['calculation_snapshot']
        source = calculation['document']
        evidence = calculation_context(calculation)
        calculation_text = 'SAVED LEARNER CALCULATIONS — not source-document text or policy approval\n' + encode(evidence)[0]
        budget_text = 'ASSIGNED BUDGET — original captured ingestion text\n' + source['text']
        doc_texts = [budget_text, calculation_text]
        metadata = [{'uuid': source['document_id'], 'title': source['title'], 'text_markers': source['text_markers']},
                    {'uuid': None, 'title': 'Saved learner calculations', 'text_markers': []}]
        engine_steps = [{'name': 'Document', 'data': {'doc_uuids': [source['document_id']]}, 'tasks': []}]
        stage_plans, used_models = [], set()
        for index, item in enumerate(captured_steps):
            step = item['step']
            if not step['name'].strip() or step['name'] == 'Document' or set(step['data']) - INPUT_KEYS:
                raise EnrollmentConflict('The saved step name or settings cannot be represented by this executor')
            checked_sources(step['data'])
            tasks, task_plans = [], []
            for task in item['tasks']:
                data = deepcopy(task['data'])
                if set(data) - TASK_KEYS[task['name']]:
                    raise EnrollmentConflict('A saved task has unsupported instructions or runtime settings')
                checked_sources(data)
                apply_step_input_config(deepcopy(step['data']), data)
                sources = _resolve_input_sources(data, 'Document' if index == 0 else 'Prompt')
                selected = data.get('selected_document_uuid')
                if selected and selected != source['document_id']:
                    raise EnrollmentConflict('The selected document is outside the assigned source')
                if 'select_document' in sources and selected != source['document_id']:
                    raise EnrollmentConflict('Select the exact assigned budget explicitly')
                # Never silently wire in missing branch/calculation evidence.
                if index == 0 and 'step_input' in sources:
                    raise EnrollmentConflict('Independent source review must explicitly use the assigned workflow documents')
                if 'workflow_documents' not in sources or (index == 1 and 'step_input' not in sources):
                    raise EnrollmentConflict('Source review needs saved source/calculations; the memo also needs every preceding review result')
                requested = data.get('model')
                if requested is not None and (not isinstance(requested, str) or not requested):
                    raise EnrollmentConflict('The saved task model must be an explicit configured identity')
                model = requested or base_model
                if model not in models:
                    raise EnrollmentConflict('The chosen interpretation method is unavailable; select a supported model')
                instructions = data.get('prompt') if task['name'] == 'Prompt' else data.get('format_template') or data.get('prompt')
                if not isinstance(instructions, str) or not instructions.strip():
                    raise EnrollmentConflict('Every source review and memo needs saved nonempty instructions')
                data.update(model=model, user_id=snapshot['user_id'], doc_texts=deepcopy(doc_texts), doc_metas=deepcopy(metadata))
                if 'select_document' in sources:
                    data.update(selected_doc_text=source['text'], selected_doc_meta=deepcopy(metadata[0]))
                tasks.append({'name': task['name'], 'data': data})
                task_plans.append({'task_id': task['id'], 'task_type': task['name'], 'model': model,
                                   'effective_input_sources': sources, 'effective_settings_sha256': encode(data)[1]})
                used_models.add(model)
            stage_plans.append({'step_id': step['id'], 'step_name': step['name'], 'tasks': task_plans,
                                'waits_for_previous_stage': index == 1, 'tasks_share_previous_stage_only': True})
            engine_steps.append({'name': step['name'], 'data': deepcopy(step['data']), 'tasks': tasks})
        output_keys = build_step_output_keys([SimpleNamespace(name=step['name']) for step in engine_steps])
        for stage, key in zip(stage_plans, output_keys[1:]):
            stage['output_key'] = key
        return {'executor_id': 'saved-budget-workflow.1', 'implementation_sha256': implementation_digest(),
                'runtime_config_sha256': runtime_digest(system_config), 'input_snapshot_sha256': digest,
                'case_sha256': case.digest, 'source_document_id': source['document_id'],
                'calculation_snapshot_id': calculation['uuid'], 'calculation_snapshot_sha256': encode(calculation)[1],
                'calculation_context_sha256': encode(evidence)[1], 'default_model': base_model,
                'model_names': sorted(used_models), 'stage_plans': stage_plans, 'engine_steps': engine_steps,
                'output_step_key': output_keys[-1], 'execution_authorized': False, 'credit_awarded': False,
                'arithmetic_supported': calculation['checks']['all_arithmetic_supported'],
                'scope': 'assigned_budget_and_saved_calculations_internal_memo_only'}
    except EnrollmentConflict:
        raise
    except (CourseCatalogError, KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        raise EnrollmentConflict('The budget workflow cannot be planned without changing its saved evidence') from exc
