"""Append-only task receipts with parallel starts and a complete-result barrier."""
from copy import deepcopy
import hashlib
import json

from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository

MAX_CHECKPOINT_BYTES = 4 * 1024 * 1024


def review_output(previous, plan):
    """Reconstruct the real engine's bounded Prompt-step aggregation in task order."""
    completed = {item['receipt']['task_index']: item['receipt']['result'] for item in previous
                 if item['receipt']['kind'] == 'task_completed' and item['receipt']['stage_index'] == 0}
    count = len(plan['stage_plans'][0]['tasks'])
    if set(completed) != set(range(count)):
        raise ValueError('Every required review must complete before synthesis')
    outputs, warnings = [], []
    for index in range(count):
        result = completed[index]
        value = result['output']
        outputs.extend(value if isinstance(value, list) else [value])
        if result.get('warning'):
            warnings.append(result['warning'])
    combined = {'input': None, 'output': outputs[0] if len(outputs) == 1 else outputs, 'step_name': 'Prompt'}
    if warnings:
        combined['warning'] = ' | '.join(warnings)
    return combined


def validate_event(event, previous, run):
    from app.services.workflow_engine import _build_combined_context
    plan = run['plan']
    stage_index, task_index = event['stage_index'], event['task_index']
    if (type(stage_index) is not int or stage_index not in (0, 1) or type(task_index) is not int
            or task_index < 0 or task_index >= len(plan['stage_plans'][stage_index]['tasks'])):
        raise ValueError('Invalid task position')
    stage = plan['stage_plans'][stage_index]
    task = stage['tasks'][task_index]
    common = {'kind', 'sequence', 'stage_index', 'task_index', 'task_id', 'output_key', 'run_id', 'plan_sha256',
              'authorization_sha256', 'previous_event_sha256', 'credit_awarded'}
    kind = event['kind']
    fields = {'task_started': {'task', 'consumed_context', 'upstream_result', 'upstream_result_sha256'},
              'task_completed': {'started_receipt_sha256', 'result'},
              'task_failed': {'started_receipt_sha256', 'failure_kind'}}
    if (kind not in fields or set(event) != common | fields[kind]
            or type(event['sequence']) is not int or event['sequence'] != len(previous)
            or event['previous_event_sha256'] != (previous[-1]['receipt_sha256'] if previous else None)
            or event['task_id'] != task['task_id'] or event['output_key'] != stage['output_key']
            or event['run_id'] != run['run_id'] or event['plan_sha256'] != run['plan_sha256']
            or event['authorization_sha256'] != encode(run['authorization'])[1] or event['credit_awarded'] is not False):
        raise ValueError('The task event does not bind its exact approved plan and log position')
    same_task = [item for item in previous if item['receipt']['stage_index'] == stage_index
                 and item['receipt']['task_index'] == task_index]
    if kind == 'task_started':
        if same_task or any(item['receipt']['stage_index'] > stage_index for item in previous):
            raise ValueError('An already started task or previous stage cannot be restarted')
        upstream = ({'step_name': 'Document', 'output': [plan['source_document_id']], 'input': None}
                    if stage_index == 0 else review_output(previous, plan))
        data = plan['engine_steps'][stage_index + 1]['tasks'][task_index]['data']
        if (event['task'] != task or event['upstream_result'] != upstream
                or event['upstream_result_sha256'] != encode(upstream)[1]
                or event['consumed_context'] != _build_combined_context(data, upstream, task['effective_input_sources'])):
            raise ValueError('Consumed evidence differs from the assigned source, calculations or completed branches')
    else:
        if (len(same_task) != 1 or same_task[0]['receipt']['kind'] != 'task_started'
                or event['started_receipt_sha256'] != same_task[0]['receipt_sha256']):
            raise ValueError('Task result requires its unique original start receipt')
        if kind == 'task_failed':
            if event['failure_kind'] not in ('task_execution_unavailable', 'required_task_result_missing'):
                raise ValueError('Unexpected failure payload')
        else:
            result = event['result']
            data = plan['engine_steps'][stage_index + 1]['tasks'][task_index]['data']
            prompt = data['prompt'] if task['task_type'] == 'Prompt' else data.get('format_template') or data.get('prompt')
            expected_prompt = prompt.strip() if task['task_type'] == 'Prompt' else prompt
            if (not isinstance(result, dict) or set(result) - {'input', 'output', 'step_name', 'warning'}
                    or result.get('step_name') != task['task_type'] or result.get('input') != expected_prompt
                    or result.get('output') is None or result.get('output') == [] or result.get('output') == {}
                    or isinstance(result.get('output'), str) and not result['output'].strip()
                    or 'warning' in result and not isinstance(result['warning'], str)):
                raise ValueError('Completed task receipt must preserve a usable result and the actual instructions')


def decode_checkpoints(raw, run):
    try:
        serialized = raw.get('task_events_json')
        if serialized is None:
            if raw.get('task_events_sha256') is not None or raw.get('task_event_count', 0) != 0 or run['state'] == 'completed':
                raise ValueError('Incomplete task log header')
            return []
        if hashlib.sha256(serialized.encode()).hexdigest() != raw['task_events_sha256']:
            raise ValueError('Task log hash changed')
        events = json.loads(serialized)
        expected_count = 2 * sum(len(stage['tasks']) for stage in run['plan']['stage_plans'])
        if not isinstance(events, list) or len(events) != raw['task_event_count'] or len(events) > expected_count:
            raise ValueError('Task event count mismatch')
        previous = []
        for item in events:
            if set(item) != {'receipt', 'receipt_sha256'} or encode(item['receipt'])[1] != item['receipt_sha256']:
                raise ValueError('Task receipt hash changed')
            validate_event(item['receipt'], previous, run)
            previous.append(item)
        if run['state'] == 'prepared' and events:
            raise ValueError('An unclaimed plan cannot contain task events')
        if run['state'] == 'completed' and (len(events) != expected_count
                or any(item['receipt']['kind'] == 'task_failed' for item in events)):
            raise ValueError('A completed budget run requires all successful task receipts')
        return events
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        raise CourseCatalogError('Saved budget task checkpoints failed integrity verification') from exc


class AdvancedWorkflowCheckpoints:
    async def append(self, operation, run, event, digest):
        lease = LabExecutionRepository.check_operation(operation, run['plan'])
        records = LabExecutionRepository().records
        raw = await records.find_one({'uuid': run['run_id'], 'user_id': operation.user_id})
        if (raw is None or raw['state'] != 'executing' or raw.get('checkpoint_closed') is True or raw.get('worker_id') != lease.write_id
                or raw['plan_sha256'] != run['plan_sha256']
                or raw.get('authorization_sha256') != encode(run['authorization'])[1]):
            raise EnrollmentConflict('The task writer no longer owns this executing budget run')
        LabExecutionRepository.decode(raw)
        existing = decode_checkpoints(raw, run)
        sequence = event.get('sequence')
        if encode(event)[1] != digest or type(sequence) is not int or sequence < 0:
            raise EnrollmentConflict('The task payload or event position is invalid')
        if sequence < len(existing):
            if existing[sequence] != {'receipt': event, 'receipt_sha256': digest}:
                raise EnrollmentConflict('This task position already preserves different evidence')
            return deepcopy(existing[sequence])
        try:
            validate_event(event, existing, run)
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise EnrollmentConflict('Task evidence does not follow the approved inputs and completed dependencies') from exc
        item = {'receipt': deepcopy(event), 'receipt_sha256': digest}
        serialized, log_digest = encode([*existing, item])
        if len(serialized.encode()) > MAX_CHECKPOINT_BYTES:
            raise EnrollmentConflict('The complete task log exceeds its immutable evidence budget')
        await LabInputRepository._check_lease(lease)
        result = await records.update_one({'uuid': run['run_id'], 'user_id': operation.user_id, 'state': 'executing',
            'checkpoint_closed': {'$ne': True},
            'worker_id': lease.write_id, 'plan_sha256': run['plan_sha256'], 'authorization_sha256': raw['authorization_sha256'],
            'task_events_sha256': raw.get('task_events_sha256'), 'task_event_count': raw.get('task_event_count')},
            {'$set': {'task_events_json': serialized, 'task_events_sha256': log_digest, 'task_event_count': len(existing) + 1}})
        if result.modified_count != 1:
            raise EnrollmentConflict('Task evidence changed before this receipt was acknowledged')
        return item
