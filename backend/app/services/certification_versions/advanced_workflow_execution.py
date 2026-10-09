"""Claim one approved internal run and retain its bounded task evidence."""
import asyncio
from copy import deepcopy
import datetime
import threading
from typing import Literal

from pydantic import Field

from .attempts import encode
from .advanced_workflow_approval import AdvancedScopeRepository
from .advanced_workflow_checkpoints import AdvancedWorkflowCheckpoints
from .advanced_workflow_plan import advanced_workflow_plan
from .advanced_workflow_preparation import AdvancedWorkflowPreparation
from .advanced_workflow_runtime import execute_approved_budget
from .enrollments import EnrollmentConflict
from .lab_inputs import LabInputRepository
from .advanced_case import load_advanced_case
from .outcomes import ContractModel

RUN_TIMEOUT_SECONDS = 360
MAX_TERMINAL_BYTES = 4 * 1024 * 1024


class AdvancedExecutionRequest(ContractModel):
    run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    plan_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    scope_decision_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    scope_decision_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['execute_approved_budget_workflow']


class AdvancedWorkflowExecution(AdvancedWorkflowPreparation):
    async def execute(self, operation, body, system_config_doc, *, actor_user_id):
        body = AdvancedExecutionRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can dispatch this approved run')
        run = await self.get(operation.user_id, body.run_id)
        if run is None:
            raise EnrollmentConflict('Prepare and approve an owned budget workflow run before dispatch')
        lease = self.check_operation(operation, run['plan'])
        if any(run.get(key) != getattr(body, key) for key in ('plan_sha256', 'scope_decision_id', 'scope_decision_sha256')):
            raise EnrollmentConflict('The displayed plan or scope choice changed; inspect the saved run before dispatch')
        if run['state'] != 'prepared':
            return run  # Inspection only. No implicit retry of any claimed run.
        config = deepcopy(system_config_doc)
        case = load_advanced_case(operation.package)
        plan = run['plan']
        current = advanced_workflow_plan(plan['input_snapshot'], case, config, default_model=plan['default_model'])
        if any(plan[key] != value for key, value in current.items()):
            raise EnrollmentConflict('The approved inputs, runtime or implementation changed; prepare a new run')
        authorization = await AdvancedScopeRepository().authorize(operation, run)
        approval_json, approval_hash = encode(authorization)
        await LabInputRepository._check_lease(lease)
        claimed = await self.records.update_one({'uuid': run['run_id'], 'user_id': operation.user_id,
            'state': 'prepared', 'plan_sha256': run['plan_sha256'],
            'scope_decision_id': body.scope_decision_id, 'scope_decision_sha256': body.scope_decision_sha256},
            {'$set': {'state': 'executing', 'worker_id': lease.write_id,
                      'authorization_json': approval_json, 'authorization_sha256': approval_hash}})
        if claimed.modified_count != 1:
            latest = await self.get(operation.user_id, body.run_id)
            if latest is None or latest['state'] == 'prepared':
                raise EnrollmentConflict('The saved scope choice changed before this run was claimed')
            return latest
        run = await self.get(operation.user_id, body.run_id)
        started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        stop = threading.Event()
        loop = asyncio.get_running_loop()
        checkpoints = AdvancedWorkflowCheckpoints()

        def checkpoint(event, digest):
            # The worker waits for durable acknowledgement. The event loop stays
            # available for writes and cancellation while providers run in threads.
            if stop.is_set():
                raise EnrollmentConflict('The stopped worker cannot append another task')
            future = asyncio.run_coroutine_threadsafe(checkpoints.append(operation, run, event, digest), loop)
            try:
                return future.result(timeout=RUN_TIMEOUT_SECONDS)
            except TimeoutError:
                future.cancel()
                stop.set()
                raise

        try:
            output = await asyncio.wait_for(asyncio.to_thread(execute_approved_budget, run, case, config,
                checkpoint=checkpoint, should_stop=stop.is_set), timeout=RUN_TIMEOUT_SECONDS)
            saved = await self.get(operation.user_id, body.run_id)
            completed = [item for item in saved['task_events'] if item['receipt']['kind'] == 'task_completed']
            if saved['task_events'] != output['task_events']:
                raise EnrollmentConflict('The final output does not match every durable completed stage')
            result = {'status': 'completed', 'final_output': output['final_output'], 'credit_awarded': False,
                      'task_receipt_sha256s': [item['receipt_sha256'] for item in completed]}
            if len(encode(result)[0].encode()) > MAX_TERMINAL_BYTES:
                raise ValueError('Terminal budget result exceeds the receipt size limit')
        except asyncio.CancelledError:
            stop.set()
            await asyncio.shield(self._finish_budget(run, lease, {'status': 'uncertain', 'reason': 'caller_cancelled',
                'credit_awarded': False}, started_at))
            raise
        except TimeoutError:
            stop.set()
            result = {'status': 'uncertain', 'reason': 'provider_timeout', 'credit_awarded': False}
        except Exception as exc:
            stop.set()
            # Provider exceptions may contain source text or credentials. Store
            # the type, never the exception message, and award no learner grade.
            result = {'status': 'failed', 'reason': 'execution_error', 'error_type': type(exc).__name__, 'credit_awarded': False}
        await self._finish_budget(run, lease, result, started_at)
        return await self.get(operation.user_id, body.run_id)

    async def _finish_budget(self, run, lease, result, started_at):
        # Close the log atomically before reading the terminal prefix. A sibling
        # checkpoint may already be queued when the caller cancels; it must
        # either land before this fence or fail without changing the prefix.
        fenced = await self.records.update_one({'uuid': run['run_id'], 'plan_sha256': run['plan_sha256'],
            'state': 'executing', 'worker_id': lease.write_id,
            'authorization_sha256': encode(run['authorization'])[1]}, {'$set': {'checkpoint_closed': True}})
        if fenced.matched_count != 1:
            raise EnrollmentConflict('This worker no longer owns the budget run terminal boundary')
        raw = await self.records.find_one({'uuid': run['run_id'], 'user_id': run['plan']['user_id']})
        if raw is None or raw.get('authorization_sha256') != encode(run['authorization'])[1]:
            raise EnrollmentConflict('The budget run disappeared before its terminal receipt was saved')
        saved = self.decode(raw)
        payload = {**result, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
                   'authorization_sha256': encode(run['authorization'])[1],
                   'task_events_sha256': raw.get('task_events_sha256'), 'task_event_count': len(saved['task_events']),
                   'started_at': started_at, 'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(payload)
        if len(serialized.encode()) > MAX_TERMINAL_BYTES:
            raise EnrollmentConflict('The terminal budget receipt exceeds its reserved storage budget')
        updated = await self.records.update_one({'uuid': run['run_id'], 'plan_sha256': run['plan_sha256'],
            'state': 'executing', 'worker_id': lease.write_id, 'checkpoint_closed': True,
            'authorization_sha256': raw.get('authorization_sha256'),
            'task_events_sha256': raw.get('task_events_sha256'), 'task_event_count': raw.get('task_event_count')},
            {'$set': {'state': result['status'], 'result_json': serialized, 'result_sha256': digest}})
        if updated.modified_count != 1:
            raise EnrollmentConflict('The task evidence changed before the terminal receipt was saved; inspect the saved run')
