"""Durable, ordered per-item starts and results before a successor can run."""
from copy import deepcopy
import hashlib
import json

from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository

MAX_CHECKPOINT_BYTES = 2 * 1024 * 1024


def validate_event(event, previous, run):
    sequence = len(previous)
    if sequence >= len(run['plan']['item_plans']) * 2:
        raise ValueError('The batch action already contains every required checkpoint')
    index, start = sequence // 2, sequence % 2 == 0
    plan = run['plan']
    common = {'kind', 'item_index', 'run_id', 'plan_sha256', 'authorization_sha256', 'credit_awarded'}
    extra = {'consumed_input', 'previous_receipt_sha256'} if start else {'started_receipt_sha256', 'result'}
    if (set(event) != common | extra or event['kind'] != ('item_started' if start else 'item_completed')
            or type(event['item_index']) is not int or event['item_index'] != index
            or event['run_id'] != run['run_id'] or event['plan_sha256'] != run['plan_sha256']
            or event['authorization_sha256'] != encode(run['authorization'])[1] or event['credit_awarded'] is not False):
        raise ValueError('The checkpoint must bind the exact authorized item and position')
    item = plan['item_plans'][index]
    if start:
        if (event['consumed_input'] != item
                or event['previous_receipt_sha256'] != (previous[-1]['receipt_sha256'] if previous else None)):
            raise ValueError('A successor requires the saved complete predecessor and exact original input')
    else:
        result = event['result']
        if (event['started_receipt_sha256'] != previous[-1]['receipt_sha256']
                or result.get('source_id') != item['source_id']
                or set(result) != {'item_id', 'batch_id', 'run_id', 'attempt_kind', 'source_id', 'document_id',
                    'source_sha256', 'artifact_sha256', 'status', 'reason', 'entities', 'extraction_started',
                    'started_at', 'finished_at', 'elapsed_ms', 'usage', 'cost', 'external_effects'}):
            raise ValueError('The item result changed its source, revision or durable start')
        from .batch_case import BatchCase
        from .batch_checks import check_item
        check_item(BatchCase.model_validate(plan['input_snapshot']['authored_case']), plan['input_snapshot'], result,
                   batch_id=plan['batch_id'], run_id=run['run_id'], attempt_kind=plan['phase'])


def decode_checkpoints(raw, run):
    try:
        if raw.get('item_events_json') is None:
            if raw.get('item_events_sha256') is not None or raw.get('item_event_count', 0) != 0 or run['state'] == 'completed':
                raise ValueError('The checkpoint header is incomplete')
            return []
        serialized = raw['item_events_json']
        if hashlib.sha256(serialized.encode()).hexdigest() != raw['item_events_sha256']:
            raise ValueError('The item checkpoint digest changed')
        events = json.loads(serialized)
        if not isinstance(events, list) or len(events) != raw['item_event_count'] or len(events) > len(run['plan']['item_plans']) * 2:
            raise ValueError('The item checkpoint count changed')
        previous = []
        for item in events:
            if set(item) != {'receipt', 'receipt_sha256'} or encode(item['receipt'])[1] != item['receipt_sha256']:
                raise ValueError('An individual item checkpoint changed')
            validate_event(item['receipt'], previous, run)
            previous.append(item)
        if run['state'] == 'prepared' and events:
            raise ValueError('An unclaimed plan cannot contain execution evidence')
        if run['state'] == 'completed' and len(events) != len(run['plan']['item_plans']) * 2:
            raise ValueError('A completed batch action requires every original item terminal receipt')
        return events
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise CourseCatalogError('The saved batch item checkpoints failed integrity verification') from exc


class BatchCheckpoints:
    async def append(self, operation, run, event, digest):
        lease = LabExecutionRepository.check_operation(operation, run['plan'])
        records = LabExecutionRepository().records
        raw = await records.find_one({'uuid': run['run_id'], 'user_id': operation.user_id})
        if (raw is None or raw['state'] != 'executing' or raw.get('checkpoint_closed') is True
                or raw.get('worker_id') != lease.write_id or raw['plan_sha256'] != run['plan_sha256']
                or raw.get('authorization_sha256') != encode(run['authorization'])[1]):
            raise EnrollmentConflict('This worker no longer owns the exact executing batch action')
        LabExecutionRepository.decode(raw)
        existing = decode_checkpoints(raw, run)
        if (encode(event)[1] != digest or type(event.get('item_index')) is not int
                or event.get('kind') not in ('item_started', 'item_completed')):
            raise EnrollmentConflict('The item checkpoint identity is invalid')
        sequence = event['item_index'] * 2 + int(event['kind'] == 'item_completed')
        if sequence < 0 or sequence >= len(run['plan']['item_plans']) * 2:
            raise EnrollmentConflict('The item checkpoint position is invalid')
        if sequence < len(existing):
            if existing[sequence] != {'receipt': event, 'receipt_sha256': digest}:
                raise EnrollmentConflict('This item position already preserves different evidence')
            return deepcopy(existing[sequence])
        try:
            validate_event(event, existing, run)
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise EnrollmentConflict('The item checkpoint does not follow the saved execution chain') from exc
        item = {'receipt': deepcopy(event), 'receipt_sha256': digest}
        serialized, log_hash = encode([*existing, item])
        if len(serialized.encode()) > MAX_CHECKPOINT_BYTES:
            raise EnrollmentConflict('The complete item log exceeds its storage limit')
        await LabInputRepository._check_lease(lease)
        result = await records.update_one({'uuid': run['run_id'], 'state': 'executing', 'worker_id': lease.write_id,
            'checkpoint_closed': {'$ne': True}, 'plan_sha256': run['plan_sha256'], 'authorization_sha256': raw['authorization_sha256'],
            'item_events_sha256': raw.get('item_events_sha256'), 'item_event_count': raw.get('item_event_count')},
            {'$set': {'item_events_json': serialized, 'item_events_sha256': log_hash, 'item_event_count': len(existing) + 1}})
        if result.modified_count != 1:
            raise EnrollmentConflict('The item log changed before this checkpoint was acknowledged')
        return item
