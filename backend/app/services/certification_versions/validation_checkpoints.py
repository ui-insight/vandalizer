"""Durable, ordered per-case starts and results before a successor can run."""
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
    if sequence >= 4:
        raise ValueError('The suite already contains every required checkpoint')
    index, start = sequence // 2, sequence % 2 == 0
    plan = run['plan']
    common = {'kind', 'case_index', 'run_id', 'plan_sha256', 'authorization_sha256', 'credit_awarded'}
    extra = {'consumed_input', 'previous_receipt_sha256'} if start else {'started_receipt_sha256', 'result'}
    if (set(event) != common | extra or event['kind'] != ('case_started' if start else 'case_completed')
            or type(event['case_index']) is not int or event['case_index'] != index
            or event['run_id'] != run['run_id'] or event['plan_sha256'] != run['plan_sha256']
            or event['authorization_sha256'] != encode(run['authorization'])[1] or event['credit_awarded'] is not False):
        raise ValueError('The checkpoint must bind the exact authorized case and position')
    case = plan['case_plans'][index]
    if start:
        if (event['consumed_input'] != case
                or event['previous_receipt_sha256'] != (previous[-1]['receipt_sha256'] if previous else None)
                or previous and previous[-1]['receipt']['result']['status'] != 'completed'):
            raise ValueError('A successor requires the saved complete predecessor and exact original input')
    else:
        result = event['result']
        if (event['started_receipt_sha256'] != previous[-1]['receipt_sha256']
                or set(result) != {'source_id', 'source_sha256', 'artifact_sha256', 'status', 'entities', 'reason'}
                or result['source_id'] != case['source_id'] or result['source_sha256'] != case['source_sha256']
                or result['artifact_sha256'] != plan['input_snapshot']['artifact_sha256']
                or result['status'] not in ('completed', 'unavailable')
                or (result['status'] == 'unavailable' and (result['entities'] is not None or result['reason'] != 'extraction_unavailable'))
                or (result['status'] == 'completed' and result['reason'] is not None)):
            raise ValueError('The case result changed its source, revision or durable start')


def decode_checkpoints(raw, run):
    try:
        if raw.get('case_events_json') is None:
            if raw.get('case_events_sha256') is not None or raw.get('case_event_count', 0) != 0 or run['state'] == 'completed':
                raise ValueError('The checkpoint header is incomplete')
            return []
        serialized = raw['case_events_json']
        if hashlib.sha256(serialized.encode()).hexdigest() != raw['case_events_sha256']:
            raise ValueError('The case checkpoint digest changed')
        events = json.loads(serialized)
        if not isinstance(events, list) or len(events) != raw['case_event_count'] or len(events) > 4:
            raise ValueError('The case checkpoint count changed')
        previous = []
        for item in events:
            if set(item) != {'receipt', 'receipt_sha256'} or encode(item['receipt'])[1] != item['receipt_sha256']:
                raise ValueError('An individual case checkpoint changed')
            validate_event(item['receipt'], previous, run)
            previous.append(item)
        if run['state'] == 'prepared' and events:
            raise ValueError('An unclaimed plan cannot contain execution evidence')
        if run['state'] == 'completed' and (len(events) != 4 or any(item['receipt']['result']['status'] != 'completed' for item in events[1::2])):
            raise ValueError('A completed suite requires both actual completed cases')
        return events
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise CourseCatalogError('The saved validation case checkpoints failed integrity verification') from exc


class ValidationCheckpoints:
    async def append(self, operation, run, event, digest):
        lease = LabExecutionRepository.check_operation(operation, run['plan'])
        records = LabExecutionRepository().records
        raw = await records.find_one({'uuid': run['run_id'], 'user_id': operation.user_id})
        if (raw is None or raw['state'] != 'executing' or raw.get('checkpoint_closed') is True
                or raw.get('worker_id') != lease.write_id or raw['plan_sha256'] != run['plan_sha256']
                or raw.get('authorization_sha256') != encode(run['authorization'])[1]):
            raise EnrollmentConflict('This worker no longer owns the exact executing validation suite')
        LabExecutionRepository.decode(raw)
        existing = decode_checkpoints(raw, run)
        if (encode(event)[1] != digest or type(event.get('case_index')) is not int
                or event.get('kind') not in ('case_started', 'case_completed')):
            raise EnrollmentConflict('The case checkpoint identity is invalid')
        sequence = event['case_index'] * 2 + int(event['kind'] == 'case_completed')
        if sequence < 0 or sequence >= 4:
            raise EnrollmentConflict('The case checkpoint position is invalid')
        if sequence < len(existing):
            if existing[sequence] != {'receipt': event, 'receipt_sha256': digest}:
                raise EnrollmentConflict('This case position already preserves different evidence')
            return deepcopy(existing[sequence])
        try:
            validate_event(event, existing, run)
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise EnrollmentConflict('The case checkpoint does not follow the saved execution chain') from exc
        item = {'receipt': deepcopy(event), 'receipt_sha256': digest}
        serialized, log_hash = encode([*existing, item])
        if len(serialized.encode()) > MAX_CHECKPOINT_BYTES:
            raise EnrollmentConflict('The complete case log exceeds its storage limit')
        await LabInputRepository._check_lease(lease)
        result = await records.update_one({'uuid': run['run_id'], 'state': 'executing', 'worker_id': lease.write_id,
            'checkpoint_closed': {'$ne': True}, 'plan_sha256': run['plan_sha256'], 'authorization_sha256': raw['authorization_sha256'],
            'case_events_sha256': raw.get('case_events_sha256'), 'case_event_count': raw.get('case_event_count')},
            {'$set': {'case_events_json': serialized, 'case_events_sha256': log_hash, 'case_event_count': len(existing) + 1}})
        if result.modified_count != 1:
            raise EnrollmentConflict('The case log changed before this checkpoint was acknowledged')
        return item
