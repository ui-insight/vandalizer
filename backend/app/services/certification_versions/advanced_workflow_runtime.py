"""Run an exactly approved budget plan with per-task synchronous checkpoints.

The caller must first claim a durable run and persist every checkpoint before
acknowledging it. This internal worker exposes no dispatch or replay endpoint.
"""
from copy import deepcopy
from threading import Lock

from .advanced_workflow_approval import AdvancedScopeRepository
from .advanced_workflow_plan import advanced_workflow_plan
from .attempts import encode
from .enrollments import EnrollmentConflict

MAX_EVENT_BYTES = 8 * 1024 * 1024


def execute_approved_budget(run, case, system_config, *, checkpoint, should_stop):
    from app.services import workflow_engine

    try:
        plan, authorization = run['plan'], run['authorization']
        decision = authorization['decision']
        serialized, decision_digest = encode(decision)
        AdvancedScopeRepository.decode({**decision, 'record_json': serialized, 'record_sha256': decision_digest})
        if (run['state'] != 'executing' or plan['uuid'] != run['run_id'] or encode(plan)[1] != run['plan_sha256']
                or authorization['run_id'] != run['run_id'] or authorization['plan_sha256'] != run['plan_sha256']
                or authorization['decision_sha256'] != decision_digest or run['scope_decision_sha256'] != decision_digest
                or run['scope_decision_id'] != decision['uuid'] or decision['run_id'] != run['run_id']
                or decision['plan_sha256'] != run['plan_sha256'] or decision['case_sha256'] != case.digest
                or decision['input_snapshot_id'] != plan['input_snapshot_id']
                or decision['input_snapshot_sha256'] != plan['input_snapshot_sha256']
                or decision['prompt'] != {**plan['approval_requirement']['question'], 'execution_choice': 'approve'}
                or decision['submission']['choice'] != 'approve'
                or any(decision[key] != plan[key] for key in
                       ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))):
            raise EnrollmentConflict('The budget worker requires the exact claimed plan and linked approval')
        current = advanced_workflow_plan(plan['input_snapshot'], case, deepcopy(system_config), default_model=plan['default_model'])
        if any(plan[key] != value for key, value in current.items()):
            raise EnrollmentConflict('The approved inputs or runtime changed before budget execution')
    except EnrollmentConflict:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise EnrollmentConflict('The budget worker requires complete trusted authorization') from exc

    engine = workflow_engine.build_workflow_engine(deepcopy(plan['engine_steps']), plan['default_model'],
        user_id=plan['user_id'], system_config_doc=deepcopy(system_config), allow_code_execution=False)
    nodes = engine.get_topological_order()
    lock, events = Lock(), []

    def emit(event):
        # Parallel tasks share one ordered durable log. Completion means the
        # sink acknowledged the record, not merely that a model returned text.
        with lock:
            if event['kind'] == 'task_started' and should_stop():
                raise workflow_engine.WorkflowCancelled()
            payload = {**event, 'sequence': len(events), 'run_id': run['run_id'],
                       'plan_sha256': run['plan_sha256'], 'authorization_sha256': encode(authorization)[1],
                       'previous_event_sha256': events[-1]['receipt_sha256'] if events else None,
                       'credit_awarded': False}
            serialized, digest = encode(payload)
            if len(serialized.encode()) > MAX_EVENT_BYTES:
                raise EnrollmentConflict('A budget task receipt exceeds the preserved-evidence size limit')
            checkpoint(deepcopy(payload), digest)
            events.append({'receipt': payload, 'receipt_sha256': digest})
            return digest

    for index, (node, stage) in enumerate(zip(nodes[1:], plan['stage_plans'])):
        original = node.process_task
        task_indices = {id(task): offset for offset, task in enumerate(node.tasks)}

        def process_task(task, *, stage_index=index, stage_plan=deepcopy(stage), task_index_by_id=task_indices,
                         process_original=original):
            offset = task_index_by_id[id(task)]
            spec = stage_plan['tasks'][offset]
            if should_stop():
                raise workflow_engine.WorkflowCancelled()
            sources = workflow_engine._resolve_input_sources(task.data, task.inputs.get('step_name'))
            if sources != spec['effective_input_sources'] or encode(task.data)[1] != spec['effective_settings_sha256']:
                raise EnrollmentConflict('Actual task inputs differ from the approved budget plan')
            context = workflow_engine._build_combined_context(task.data, task.inputs, sources)
            identity = {'stage_index': stage_index, 'task_index': offset, 'task_id': spec['task_id'],
                        'output_key': stage_plan['output_key']}
            start = emit({**identity, 'kind': 'task_started', 'task': spec,
                          'consumed_context': deepcopy(context), 'upstream_result': deepcopy(task.inputs),
                          'upstream_result_sha256': encode(task.inputs)[1]})
            if should_stop():
                raise workflow_engine.WorkflowCancelled()
            try:
                result = process_original(task)
            except Exception:
                # Provider exceptions can contain credentials or request URLs.
                # Preserve the attempted context, not an untrusted exception.
                emit({**identity, 'kind': 'task_failed', 'started_receipt_sha256': start,
                      'failure_kind': 'task_execution_unavailable'})
                raise
            if (not isinstance(result, dict) or result.get('error') or result.get('output') is None
                    or result.get('output') == [] or result.get('output') == {}
                    or isinstance(result.get('output'), str) and not result['output'].strip()):
                emit({**identity, 'kind': 'task_failed', 'started_receipt_sha256': start,
                      'failure_kind': 'required_task_result_missing'})
                raise EnrollmentConflict('A required budget review result is missing; dependent work cannot continue')
            emit({**identity, 'kind': 'task_completed', 'started_receipt_sha256': start, 'result': deepcopy(result)})
            return result

        node.process_task = process_task

    final, _ = engine.execute(should_cancel=should_stop)
    expected_tasks = sum(len(stage['tasks']) for stage in plan['stage_plans'])
    if len([event for event in events if event['receipt']['kind'] == 'task_completed']) != expected_tasks:
        raise EnrollmentConflict('Every required task must have preserved completion evidence')
    return {'status': 'completed', 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
            'authorization_sha256': encode(authorization)[1], 'final_output': final,
            'task_events': events, 'credit_awarded': False}
