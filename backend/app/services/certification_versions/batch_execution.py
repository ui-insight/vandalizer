"""Claim an explicitly approved batch action once and preserve its durable item prefix."""
import asyncio
from copy import deepcopy
import datetime
import threading
from typing import Literal

from .attempts import encode
from .enrollments import EnrollmentConflict
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel
from .batch_approval import BatchScopeRepository
from .batch_case import load_batch_case
from .batch_checkpoints import BatchCheckpoints
from .batch_plan import batch_plan
from .batch_preparation import BatchPreparation
from .batch_runtime import execute_approved_batch
from .batch_preparation import Digest, Identity

RUN_TIMEOUT_SECONDS = 300
MAX_TERMINAL_BYTES = 2 * 1024 * 1024


class BatchExecutionRequest(ContractModel):
    run_id: Identity
    plan_sha256: Digest
    scope_decision_id: Identity
    scope_decision_sha256: Digest
    consent: Literal['execute_approved_bounded_batch_action']


class BatchExecution(BatchPreparation):
    async def reserve_retry(self, operation, run):
        """One active retry identity per failed original input, even across plans.

        A crash after reservation is resumed only by the same request. Scope
        changes can hold it, but cannot create another concurrent retry. The
        immutable original plan/results stay unchanged; the head is claim data.
        """
        plan = run['plan']
        lease = self.check_operation(operation, plan)
        parent = self.decode(plan['parent_run_record'])
        raw = await self.records.find_one({'uuid': plan['batch_id'], 'user_id': operation.user_id})
        if raw is None or self.decode(raw) != parent:
            raise EnrollmentConflict('The original batch receipt is unavailable or changed; no retry was claimed')
        field = 'retry_heads.' + plan['failed_source_id']
        head = raw.get('retry_heads', {}).get(plan['failed_source_id'])
        if head != run['run_id']:
            if head != plan['previous_retry_id']:
                raise EnrollmentConflict('Another retry already owns this failed item; read that original request before continuing')
            await LabInputRepository._check_lease(lease)
            claimed = await self.records.update_one({'uuid': plan['batch_id'], 'user_id': operation.user_id,
                'state': 'completed', 'plan_sha256': parent['plan_sha256'], 'result_sha256': encode(parent['result'])[1], field: head},
                {'$set': {field: run['run_id']}})
            if claimed.modified_count != 1:
                latest = await self.records.find_one({'uuid': plan['batch_id'], 'user_id': operation.user_id})
                if latest is None or latest.get('retry_heads', {}).get(plan['failed_source_id']) != run['run_id']:
                    raise EnrollmentConflict('The failed item was claimed by another retry; no duplicate extraction was started')
        return {'batch_id': plan['batch_id'], 'source_id': plan['failed_source_id'],
                'run_id': run['run_id'], 'previous_retry_id': plan['previous_retry_id']}

    async def execute(self, operation, body, system_config_doc, *, actor_user_id):
        body = BatchExecutionRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can execute the approved batch action')
        run = await self.get(actor_user_id, body.run_id)
        if run is None:
            raise EnrollmentConflict('Prepare and approve an owned batch action before execution')
        lease = self.check_operation(operation, run['plan'])
        if any(run.get(key) != getattr(body, key) for key in ('plan_sha256', 'scope_decision_id', 'scope_decision_sha256')):
            raise EnrollmentConflict('The displayed plan or current scope decision changed')
        if run['state'] != 'prepared':
            return run  # Claimed requests never dispatch again, even after failure.
        plan, config = run['plan'], deepcopy(system_config_doc)
        case = load_batch_case(operation.package)
        parent = self.decode(plan['parent_run_record']) if plan['parent_run_record'] else None
        previous = self.decode(plan['previous_retry_record']) if plan['previous_retry_record'] else None
        current = batch_plan(plan['input_snapshot'], case, config, run_id=run['run_id'], phase=plan['phase'],
            parent=parent, failed_source_id=plan['failed_source_id'], previous_retry=previous)
        if any(plan[key] != value for key, value in current.items()):
            raise EnrollmentConflict('The approved runtime, batch action or implementation changed; prepare a new plan')
        authorization = await BatchScopeRepository().authorize(operation, run)
        if plan['phase'] == 'retry':
            authorization['retry_claim'] = await self.reserve_retry(operation, run)
        serialized, digest = encode(authorization)
        await LabInputRepository._check_lease(lease)
        claimed = await self.records.update_one({'uuid': run['run_id'], 'user_id': actor_user_id, 'state': 'prepared',
            'plan_sha256': run['plan_sha256'], 'scope_decision_id': body.scope_decision_id,
            'scope_decision_sha256': body.scope_decision_sha256},
            {'$set': {'state': 'executing', 'worker_id': lease.write_id, 'authorization_json': serialized, 'authorization_sha256': digest}})
        if claimed.modified_count != 1:
            latest = await self.get(actor_user_id, body.run_id)
            if latest is None or latest['state'] == 'prepared':
                raise EnrollmentConflict('The approval changed before this batch action was claimed')
            return latest
        run = await self.get(actor_user_id, body.run_id)
        started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        stop, loop = threading.Event(), asyncio.get_running_loop()
        checkpoints = BatchCheckpoints()

        def checkpoint(event, event_hash):
            if stop.is_set():
                raise EnrollmentConflict('A stopped worker cannot append another item')
            future = asyncio.run_coroutine_threadsafe(checkpoints.append(operation, run, event, event_hash), loop)
            try:
                return future.result(timeout=RUN_TIMEOUT_SECONDS)
            except TimeoutError:
                future.cancel()
                stop.set()
                raise

        try:
            result = await asyncio.wait_for(asyncio.to_thread(execute_approved_batch, run, config,
                checkpoint=checkpoint, should_stop=stop.is_set), timeout=RUN_TIMEOUT_SECONDS)
            latest = await self.get(actor_user_id, body.run_id)
            if [e['receipt']['result'] for e in latest['item_events'][1::2]] != result['item_results']:
                raise EnrollmentConflict('The complete result differs from its durable item receipts')
            if len(encode(result)[0].encode()) > MAX_TERMINAL_BYTES:
                raise ValueError('The complete result exceeds its terminal storage budget')
        except asyncio.CancelledError:
            stop.set()
            await asyncio.shield(self._finish(run, lease, {'status': 'uncertain', 'reason': 'caller_cancelled', 'credit_awarded': False}, started_at))
            raise
        except TimeoutError:
            stop.set()
            result = {'status': 'uncertain', 'reason': 'provider_timeout', 'credit_awarded': False}
        except Exception as exc:
            stop.set()
            result = {'status': 'failed', 'reason': 'execution_unavailable', 'error_type': type(exc).__name__, 'credit_awarded': False}
        await self._finish(run, lease, result, started_at)
        return await self.get(actor_user_id, body.run_id)

    async def _finish(self, run, lease, result, started_at):
        fenced = await self.records.update_one({'uuid': run['run_id'], 'plan_sha256': run['plan_sha256'],
            'state': 'executing', 'worker_id': lease.write_id, 'authorization_sha256': encode(run['authorization'])[1]},
            {'$set': {'checkpoint_closed': True}})
        if fenced.matched_count != 1:
            raise EnrollmentConflict('This worker no longer owns the terminal batch boundary')
        raw = await self.records.find_one({'uuid': run['run_id'], 'user_id': run['plan']['user_id']})
        if raw is None or raw.get('authorization_sha256') != encode(run['authorization'])[1]:
            raise EnrollmentConflict('The batch action disappeared before its terminal receipt could be saved')
        saved = self.decode(raw)
        payload = {**result, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
            'authorization_sha256': encode(run['authorization'])[1], 'item_events_sha256': raw.get('item_events_sha256'),
            'item_event_count': len(saved['item_events']), 'started_at': started_at,
            'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(payload)
        if len(serialized.encode()) > MAX_TERMINAL_BYTES:
            raise EnrollmentConflict('The terminal batch action exceeds its reserved storage budget')
        updated = await self.records.update_one({'uuid': run['run_id'], 'state': 'executing', 'worker_id': lease.write_id,
            'plan_sha256': run['plan_sha256'], 'checkpoint_closed': True, 'authorization_sha256': raw['authorization_sha256'],
            'item_events_sha256': raw.get('item_events_sha256'), 'item_event_count': raw.get('item_event_count')},
            {'$set': {'state': result['status'], 'result_json': serialized, 'result_sha256': digest}})
        if updated.modified_count != 1:
            raise EnrollmentConflict('The item evidence changed before the terminal receipt could be saved')
