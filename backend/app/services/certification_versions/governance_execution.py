"""Claim an explicitly approved capstone extraction once and preserve its durable case prefix."""
import asyncio
from copy import deepcopy
import datetime
import threading
from typing import Literal

from .attempts import encode
from .enrollments import EnrollmentConflict
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel
from .governance_approval import GovernanceApprovalRepository
from .governance_case import load_governance_case
from .governance_checkpoints import GovernanceCheckpoints
from .governance_plan import governance_plan
from .governance_preparation import GovernancePreparation
from .governance_runtime import execute_approved_capstone
from .governance_scope import Digest, Identity

RUN_TIMEOUT_SECONDS = 300
MAX_TERMINAL_BYTES = 2 * 1024 * 1024


class GovernanceExecutionRequest(ContractModel):
    run_id: Identity
    plan_sha256: Digest
    scope_decision_id: Identity
    scope_decision_sha256: Digest
    consent: Literal['execute_approved_bounded_capstone_extraction']


class GovernanceExecution(GovernancePreparation):
    async def execute(self, operation, body, system_config_doc, *, actor_user_id):
        body = GovernanceExecutionRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can execute the approved capstone extraction')
        run = await self.get(actor_user_id, body.run_id)
        if run is None:
            raise EnrollmentConflict('Prepare and approve an owned capstone extraction before execution')
        lease = self.check_operation(operation, run['plan'])
        if any(run.get(key) != getattr(body, key) for key in ('plan_sha256', 'scope_decision_id', 'scope_decision_sha256')):
            raise EnrollmentConflict('The displayed plan or current scope decision changed')
        if run['state'] != 'prepared':
            return run  # Claimed requests never dispatch again, even after failure.
        plan, config = run['plan'], deepcopy(system_config_doc)
        case = load_governance_case(operation.package)
        current = governance_plan(plan['input_snapshot'], plan['scope_correction'], case, config, run_id=run['run_id'], finding=plan['source_finding'])
        if any(plan[key] != value for key, value in current.items()):
            raise EnrollmentConflict('The approved runtime, capstone extraction or implementation changed; prepare a new plan')
        authorization = await GovernanceApprovalRepository().authorize(operation, run)
        serialized, digest = encode(authorization)
        await LabInputRepository._check_lease(lease)
        claimed = await self.records.update_one({'uuid': run['run_id'], 'user_id': actor_user_id, 'state': 'prepared',
            'plan_sha256': run['plan_sha256'], 'scope_decision_id': body.scope_decision_id,
            'scope_decision_sha256': body.scope_decision_sha256},
            {'$set': {'state': 'executing', 'worker_id': lease.write_id, 'authorization_json': serialized, 'authorization_sha256': digest}})
        if claimed.modified_count != 1:
            latest = await self.get(actor_user_id, body.run_id)
            if latest is None or latest['state'] == 'prepared':
                raise EnrollmentConflict('The approval changed before this capstone extraction was claimed')
            return latest
        run = await self.get(actor_user_id, body.run_id)
        started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        stop, loop = threading.Event(), asyncio.get_running_loop()
        checkpoints = GovernanceCheckpoints()

        def checkpoint(event, event_hash):
            if stop.is_set():
                raise EnrollmentConflict('A stopped worker cannot append another case')
            future = asyncio.run_coroutine_threadsafe(checkpoints.append(operation, run, event, event_hash), loop)
            try:
                return future.result(timeout=RUN_TIMEOUT_SECONDS)
            except TimeoutError:
                future.cancel()
                stop.set()
                raise

        try:
            result = await asyncio.wait_for(asyncio.to_thread(execute_approved_capstone, run, config,
                checkpoint=checkpoint, should_stop=stop.is_set), timeout=RUN_TIMEOUT_SECONDS)
            latest = await self.get(actor_user_id, body.run_id)
            if latest['extraction_events'][-1]['receipt']['result'] != result['extraction']:
                raise EnrollmentConflict('The complete result differs from its durable case receipts')
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
            raise EnrollmentConflict('This worker no longer owns the terminal capstone boundary')
        raw = await self.records.find_one({'uuid': run['run_id'], 'user_id': run['plan']['user_id']})
        if raw is None or raw.get('authorization_sha256') != encode(run['authorization'])[1]:
            raise EnrollmentConflict('The capstone extraction disappeared before its terminal receipt could be saved')
        saved = self.decode(raw)
        payload = {**result, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
            'authorization_sha256': encode(run['authorization'])[1], 'extraction_events_sha256': raw.get('extraction_events_sha256'),
            'extraction_event_count': len(saved['extraction_events']), 'started_at': started_at,
            'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(payload)
        if len(serialized.encode()) > MAX_TERMINAL_BYTES:
            raise EnrollmentConflict('The terminal capstone extraction exceeds its reserved storage budget')
        updated = await self.records.update_one({'uuid': run['run_id'], 'state': 'executing', 'worker_id': lease.write_id,
            'plan_sha256': run['plan_sha256'], 'checkpoint_closed': True, 'authorization_sha256': raw['authorization_sha256'],
            'extraction_events_sha256': raw.get('extraction_events_sha256'), 'extraction_event_count': raw.get('extraction_event_count')},
            {'$set': {'state': result['status'], 'result_json': serialized, 'result_sha256': digest}})
        if updated.modified_count != 1:
            raise EnrollmentConflict('The case evidence changed before the terminal receipt could be saved')
