"""Internal approved-chain worker with synchronous stage checkpoint boundaries.

The caller must claim one durable execution before invoking this worker and
persist each checkpoint before returning. This module provides no HTTP dispatch
or retry. Callback failure stops the chain; completed provider work is never
silently replayed here.
"""
from copy import deepcopy

from .attempts import encode
from .output_workflow_approval import OutputScopeRepository
from .output_workflow_plan import output_workflow_plan
from .enrollments import EnrollmentConflict

MAX_STAGE_BYTES = 4 * 1024 * 1024


def execute_approved_generation(run, case, system_config, *, checkpoint, should_stop):
    from app.services import workflow_engine

    try:
        plan, authorization = run['plan'], run['authorization']
        decision = authorization['decision']
        snapshot = plan['input_snapshot']
        identity_keys = ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256')
        from .output_workflow_preparation import SCOPE_QUESTION
        question = SCOPE_QUESTION
        decision_json, decision_hash = encode(decision)
        OutputScopeRepository.decode({**decision, 'record_json': decision_json, 'record_sha256': decision_hash})
        if (run['state'] != 'executing' or plan['uuid'] != run['run_id'] or encode(plan)[1] != run['plan_sha256']
                or any(snapshot[key] != plan[key] for key in identity_keys)
                or plan['input_snapshot_id'] != snapshot['uuid']
                or plan['approval_requirement'] != {'kind': 'output_generation_scope', 'question': question,
                    'input_snapshot_sha256': plan['input_snapshot_sha256'], 'case_sha256': case.digest}
                or authorization['run_id'] != run['run_id'] or authorization['plan_sha256'] != run['plan_sha256']
                or authorization['decision_sha256'] != decision_hash or run['scope_decision_sha256'] != decision_hash
                or run['scope_decision_id'] != decision['uuid'] or decision['run_id'] != run['run_id']
                or decision['plan_sha256'] != run['plan_sha256'] or decision['case_sha256'] != case.digest
                or decision['input_snapshot_id'] != plan['input_snapshot_id']
                or decision['input_snapshot_sha256'] != plan['input_snapshot_sha256']
                or decision['prompt'] != {**plan['approval_requirement']['question'], 'execution_choice': 'approve'}
                or decision['submission']['choice'] != 'approve'
                or any(decision[key] != plan[key] for key in identity_keys)):
            raise EnrollmentConflict('The worker requires the claimed run and its exact linked learner approval')
        current = output_workflow_plan(plan['input_snapshot'], case, deepcopy(system_config), default_model=plan['default_model'])
        if any(plan[key] != value for key, value in current.items()):
            raise EnrollmentConflict('The approved inputs, runtime or implementation changed before execution')
    except EnrollmentConflict:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise EnrollmentConflict('The output worker requires a complete trusted execution authorization') from exc

    engine = workflow_engine.build_workflow_engine(deepcopy(plan['engine_steps']), plan['default_model'],
        user_id=plan['user_id'], system_config_doc=deepcopy(system_config), allow_code_execution=False)
    nodes, output_keys = engine.get_topological_order(), engine.step_output_keys()
    index, upstream, started = 0, None, None
    completed = []

    def emit(event):
        payload = {**event, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
                   'authorization_sha256': encode(authorization)[1], 'credit_awarded': False}
        serialized, digest = encode(payload)
        if len(serialized.encode()) > MAX_STAGE_BYTES:
            raise EnrollmentConflict('A output stage receipt exceeds the preserved-evidence size limit')
        # A synchronous durable sink is intentional: do not start a provider or
        # its successor while its previous checkpoint has not been acknowledged.
        checkpoint(deepcopy(payload), digest)
        return payload, digest

    def update(event):
        nonlocal index, upstream, started
        if index >= len(nodes):
            raise EnrollmentConflict('The engine emitted an unexpected extra stage')
        node = nodes[index]
        if (set(event) == {'current_step_name', 'current_step_detail'}
                and event['current_step_name'] == node.name and event['current_step_detail'] == 'Starting ' + node.name):
            if index == 0:
                return
            stage = plan['stage_plans'][index - 1]
            data = node.tasks[0].data
            sources = workflow_engine._resolve_input_sources(data, upstream.get('step_name'))
            if sources != stage['effective_input_sources'] or encode(data)[1] != stage['effective_settings_sha256']:
                raise EnrollmentConflict('Effective stage inputs differ from the approved plan')
            if stage['task_type'] in ('DocumentRenderer', 'DataExport'):
                context = {'kind': 'file_generation_input', 'value': deepcopy(upstream.get('output'))}
            else:
                context = {'kind': 'combined_context', 'value': workflow_engine._build_combined_context(data, upstream, sources)}
            started = emit({'kind': 'stage_started', 'stage_index': index - 1, 'output_key': output_keys[index],
                'stage': stage, 'consumed_context': context, 'upstream_result_sha256': encode(upstream)[1],
                'previous_stage_receipt_sha256': completed[-1]['receipt_sha256'] if completed else None})
            if should_stop():
                raise workflow_engine.WorkflowCancelled()
            return
        output_field = 'steps_output.' + output_keys[index]
        if output_field not in event:
            return  # Task progress previews are not execution or source evidence.
        output = deepcopy(event[output_field])
        if index > 0:
            if output.get('error'):
                # Provider exception text can contain source data or credentials.
                output = {'step_name': plan['stage_plans'][index - 1]['task_type'],
                          'error': 'task_execution_unavailable', 'output': None}
            if started is None:
                raise EnrollmentConflict('The engine produced a stage result without a saved start checkpoint')
            payload, digest = emit({'kind': 'stage_completed', 'stage_index': index - 1,
                'output_key': output_keys[index], 'started_receipt_sha256': started[1],
                'status': 'failed' if output.get('error') else 'completed', 'result': output})
            completed.append({'receipt': payload, 'receipt_sha256': digest})
            started = None
        upstream = output
        index += 1

    engine.execute(workflow_result_updater=update, should_cancel=should_stop)
    if len(completed) != 4 or any(item['receipt']['status'] != 'completed' for item in completed):
        raise EnrollmentConflict('The output generation did not preserve every completed stage')
    from .output_artifacts import capture_generated_artifacts
    artifacts = capture_generated_artifacts({'status': 'completed',
        'steps_output': {item['receipt']['output_key']: item['receipt']['result'] for item in completed},
        'output_step_names': plan['output_step_keys']})
    return {'status': 'completed', 'generated_artifacts': artifacts, 'stage_receipts': completed,
            'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
            'authorization_sha256': encode(authorization)[1], 'credit_awarded': False}
