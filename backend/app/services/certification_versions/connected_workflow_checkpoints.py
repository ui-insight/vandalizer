"""Append-only stage evidence within the existing owned execution record."""
from copy import deepcopy
import hashlib
import json

from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .connected_failure_practice import is_failure_practice, stopped_stage_result

# Plan + checkpoint log + terminal result each cap at 4 MiB, keeping the single
# MongoDB document below its 16 MiB limit even with metadata and encoded strings.
MAX_CHECKPOINT_BYTES = 4 * 1024 * 1024


def validate_event(event, previous, run):
    from app.services.workflow_engine import _build_combined_context, _build_extraction_inputs
    sequence = len(previous)
    if sequence >= 6:
        raise ValueError('The chain already has every stage checkpoint')
    index, is_start = sequence // 2, sequence % 2 == 0
    plan = run['plan']
    stage = plan['stage_plans'][index]
    if is_failure_practice(plan) and index > 1:
        raise ValueError('A controlled failure rehearsal cannot start Formatter')
    common = {'kind', 'stage_index', 'output_key', 'run_id', 'plan_sha256', 'authorization_sha256', 'credit_awarded'}
    fields = ({'stage', 'consumed_context', 'upstream_result_sha256', 'previous_stage_receipt_sha256'} if is_start
              else {'started_receipt_sha256', 'status', 'result'})
    if (set(event) != common | fields or event['kind'] != ('stage_started' if is_start else 'stage_completed')
            or event['stage_index'] != index or type(event['stage_index']) is not int
            or event['output_key'] != stage['output_key'] or event['run_id'] != run['run_id']
            or event['plan_sha256'] != run['plan_sha256']
            or event['authorization_sha256'] != encode(run['authorization'])[1] or event['credit_awarded'] is not False):
        raise ValueError('The checkpoint does not bind the exact authorized stage')
    if is_start:
        upstream = previous[-1]['receipt']['result'] if previous else {
            'step_name': 'Document', 'output': [plan['source_document_id']], 'input': None}
        data = plan['engine_steps'][index + 1]['tasks'][0]['data']
        sources = stage['effective_input_sources']
        if stage['task_type'] == 'Extraction':
            expected = {'kind': 'extraction_documents', 'documents': [{'text': text, 'metadata': metadata}
                for text, metadata in _build_extraction_inputs(data, upstream, sources)]}
        else:
            expected = {'kind': 'combined_context', 'value': _build_combined_context(data, upstream, sources)}
        if (event['stage'] != stage or event['consumed_context'] != expected
                or event['upstream_result_sha256'] != encode(upstream)[1]
                or event['previous_stage_receipt_sha256'] != (previous[-1]['receipt_sha256'] if previous else None)
                or (previous and previous[-1]['receipt']['status'] != 'completed')):
            raise ValueError('The consumed inputs do not match the saved source and completed predecessor')
    elif (event['started_receipt_sha256'] != previous[-1]['receipt_sha256']
            or not isinstance(event['result'], dict) or event['result'].get('step_name') != stage['task_type']
            or event['status'] != ('failed' if event['result'].get('error') else 'completed')):
        raise ValueError('The result checkpoint does not match its saved stage start')
    if not is_start and event['result'].get('training_stop') is not None:
        if not is_failure_practice(plan) or index != 1 or event['result'] != stopped_stage_result():
            raise ValueError('A training rejection requires the exact separately approved practice boundary')
    if not is_start and is_failure_practice(plan) and index == 1 and event['result'] != stopped_stage_result():
        raise ValueError('The controlled rehearsal cannot dispatch reasoning or invent its result')


def decode_checkpoints(raw, run):
    try:
        if raw.get('stage_events_json') is None:
            if (raw.get('stage_events_sha256') is not None or raw.get('stage_event_count', 0) != 0
                    or run['state'] == 'completed'):
                raise ValueError('Incomplete checkpoint header')
            return []
        serialized = raw['stage_events_json']
        if hashlib.sha256(serialized.encode()).hexdigest() != raw['stage_events_sha256']:
            raise ValueError('Checkpoint log digest mismatch')
        events = json.loads(serialized)
        if not isinstance(events, list) or len(events) != raw['stage_event_count'] or len(events) > 6:
            raise ValueError('Checkpoint count mismatch')
        previous = []
        for item in events:
            if set(item) != {'receipt', 'receipt_sha256'} or encode(item['receipt'])[1] != item['receipt_sha256']:
                raise ValueError('Stage receipt digest mismatch')
            validate_event(item['receipt'], previous, run)
            previous.append(item)
        if run['state'] == 'prepared' and events:
            raise ValueError('An unclaimed plan cannot contain stage executions')
        if run['state'] == 'completed' and (len(events) != 6 or any(item['receipt'].get('status') == 'failed' for item in events)):
            raise ValueError('A completed connected run requires every successful stage')
        return events
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise CourseCatalogError('The saved connected stage checkpoints failed integrity verification') from exc


class ConnectedWorkflowCheckpoints:
    async def append(self, operation, run, event, digest):
        lease = LabExecutionRepository.check_operation(operation, run['plan'])
        records = LabExecutionRepository().records
        raw = await records.find_one({'uuid': run['run_id'], 'user_id': operation.user_id})
        if (raw is None or raw['state'] != 'executing' or raw.get('worker_id') != lease.write_id
                or raw['plan_sha256'] != run['plan_sha256']
                or raw.get('authorization_sha256') != encode(run['authorization'])[1]):
            raise EnrollmentConflict('The stage writer no longer owns this exact executing run')
        LabExecutionRepository.decode(raw)
        existing = decode_checkpoints(raw, run)
        if encode(event)[1] != digest:
            raise EnrollmentConflict('The stage payload differs from its receipt digest')
        if type(event.get('stage_index')) is not int or event.get('kind') not in ('stage_started', 'stage_completed'):
            raise EnrollmentConflict('The stage checkpoint has an invalid position')
        sequence = event['stage_index'] * 2 + int(event['kind'] == 'stage_completed')
        if sequence < 0 or sequence >= 6:
            raise EnrollmentConflict('The stage checkpoint has an invalid position')
        if sequence < len(existing):
            if existing[sequence] != {'receipt': event, 'receipt_sha256': digest}:
                raise EnrollmentConflict('This stage position already contains different evidence')
            return deepcopy(existing[sequence])
        try:
            validate_event(event, existing, run)
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise EnrollmentConflict('The stage checkpoint does not follow the exact saved input/result chain') from exc
        item = {'receipt': deepcopy(event), 'receipt_sha256': digest}
        serialized, log_digest = encode([*existing, item])
        if len(serialized.encode()) > MAX_CHECKPOINT_BYTES:
            raise EnrollmentConflict('The complete stage evidence exceeds the immutable receipt size limit')
        await LabInputRepository._check_lease(lease)
        result = await records.update_one({'uuid': run['run_id'], 'user_id': operation.user_id,
            'state': 'executing', 'worker_id': lease.write_id, 'plan_sha256': run['plan_sha256'],
            'authorization_sha256': raw['authorization_sha256'], 'stage_events_sha256': raw.get('stage_events_sha256'),
            'stage_event_count': raw.get('stage_event_count')},
            {'$set': {'stage_events_json': serialized, 'stage_events_sha256': log_digest, 'stage_event_count': len(existing) + 1}})
        if result.modified_count != 1:
            raise EnrollmentConflict('The saved stage evidence changed before this checkpoint was acknowledged')
        return item
