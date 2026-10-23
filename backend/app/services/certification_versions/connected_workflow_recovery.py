"""Explicitly finalize an unsealed run only when every result is durable.

No provider is invoked and no prior terminal receipt is overwritten. Incomplete
or uncertain runs require a separate recovery design, not a guessed success or
automatic replay of their completed stages.
"""
import datetime
from typing import Literal

from pydantic import Field

from .attempts import encode
from .connected_workflow_approval import ConnectedScopeRepository
from .connected_workflow_execution import MAX_TERMINAL_BYTES
from .connected_workflow_preparation import ConnectedWorkflowPreparation
from .enrollments import EnrollmentConflict
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel


class ConnectedFinalizationRequest(ContractModel):
    run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    plan_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    authorization_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    stage_events_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['finalize_saved_connected_results_without_reexecution']


class ConnectedWorkflowRecovery(ConnectedWorkflowPreparation):
    async def finalize(self, operation, body, *, actor_user_id):
        from app.services.workflow_engine import WorkflowEngine
        body = ConnectedFinalizationRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can finalize these saved results')
        raw = await self.records.find_one({'uuid': body.run_id, 'user_id': operation.user_id})
        if raw is None:
            raise EnrollmentConflict('Select an owned saved connected run before finalizing its results')
        run = self.decode(raw)
        lease = self.check_operation(operation, run['plan'])
        if any(raw.get(key) != getattr(body, key) for key in ('plan_sha256', 'authorization_sha256', 'stage_events_sha256')):
            raise EnrollmentConflict('The saved plan, approval or stage evidence changed; inspect the run again')
        if run['state'] == 'completed':
            return run
        if run['state'] != 'executing' or run['result'] is not None:
            raise EnrollmentConflict('Finalization cannot replace an existing terminal receipt or execute a prepared plan')
        events = run['stage_events']
        if len(events) != 6 or any(item['receipt'].get('status') == 'failed' for item in events):
            raise EnrollmentConflict('Every stage must have a durable successful result; incomplete work cannot be finalized')
        authorization, plan = run['authorization'], run['plan']
        decision = authorization['decision']
        serialized_decision, decision_hash = encode(decision)
        ConnectedScopeRepository.decode({**decision, 'record_json': serialized_decision, 'record_sha256': decision_hash})
        if (decision['submission']['choice'] != 'approve' or decision['run_id'] != run['run_id']
                or decision['plan_sha256'] != run['plan_sha256'] or decision['case_sha256'] != plan['case_sha256']
                or decision['input_snapshot_id'] != plan['input_snapshot_id']
                or decision['input_snapshot_sha256'] != plan['input_snapshot_sha256']
                or decision['prompt'] != {**plan['approval_requirement']['question'], 'execution_choice': 'approve'}
                or any(decision[key] != plan[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))):
            raise EnrollmentConflict('The original stage results do not belong to this exact approved plan')
        final = events[-1]['receipt']['result']
        result = {'status': 'completed', 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
                  'authorization_sha256': body.authorization_sha256, 'stage_events_sha256': body.stage_events_sha256,
                  'stage_event_count': 6, 'stage_receipt_sha256s': [item['receipt_sha256'] for item in events
                      if item['receipt']['kind'] == 'stage_completed'],
                  'final_output': WorkflowEngine()._format_final_output(final.get('formatted_output') or final.get('output')),
                  'completion_mode': 'finalized_from_saved_stage_receipts', 'credit_awarded': False,
                  'execution_finished_at': None, 'receipt_finalized_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'finalization_request': body.model_dump(mode='json'), 'finalization_actor_user_id': actor_user_id}
        serialized, digest = encode(result)
        if len(serialized.encode()) > MAX_TERMINAL_BYTES:
            raise EnrollmentConflict('The final saved output exceeds the reserved receipt storage budget')
        await LabInputRepository._check_lease(lease)
        updated = await self.records.update_one({'uuid': body.run_id, 'user_id': actor_user_id,
            'state': 'executing', 'plan_sha256': body.plan_sha256, 'authorization_sha256': body.authorization_sha256,
            'stage_events_sha256': body.stage_events_sha256, 'stage_event_count': 6, 'result_json': None},
            {'$set': {'state': 'completed', 'result_json': serialized, 'result_sha256': digest}})
        if updated.modified_count != 1:
            latest = await self.get(actor_user_id, body.run_id)
            if latest is not None and latest['state'] == 'completed' and latest['plan_sha256'] == body.plan_sha256:
                return latest
            raise EnrollmentConflict('The saved run changed before finalization; inspect its current receipt')
        return await self.get(actor_user_id, body.run_id)
