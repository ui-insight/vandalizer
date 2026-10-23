"""Persist a budget plan for separate explicit scope approval, without dispatch."""
from copy import deepcopy
import datetime
from typing import Literal

from pydantic import Field
from pymongo.errors import DuplicateKeyError

from .advanced_case import load_advanced_case
from .advanced_workflow_inputs import AdvancedWorkflowInputRepository
from .advanced_workflow_plan import advanced_workflow_plan
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel

MAX_PLAN_BYTES = 4 * 1024 * 1024
SCOPE_QUESTION = {
    'id': 'budget_scope_approval', 'phase': 'before_execution',
    'prompt': 'Approve or hold this exact saved workflow, assigned budget and calculation record for an internal memo. Review every effective input and model. This approval does not authorize external actions, approve a budget or award credit.',
}


class AdvancedPlanRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    input_snapshot_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    input_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['prepare_budget_workflow_plan']


class AdvancedWorkflowPreparation(LabExecutionRepository):
    @staticmethod
    def decode(raw):
        saved = LabExecutionRepository.decode(raw)
        try:
            plan = saved['plan']
            body = AdvancedPlanRequest.model_validate(plan['request'])
            snapshot = plan['input_snapshot']
            serialized, digest = encode(snapshot)
            AdvancedWorkflowInputRepository.decode({**snapshot, 'record_json': serialized, 'record_sha256': digest})
            if (plan['executor_id'] != 'saved-budget-workflow.1' or plan['module_id'] != 'advanced_nodes'
                    or body.request_id != plan['uuid'] or body.input_snapshot_id != snapshot['uuid']
                    or plan['input_snapshot_id'] != snapshot['uuid']
                    or body.input_snapshot_sha256 != digest or plan['input_snapshot_sha256'] != digest
                    or body.case_sha256 != snapshot['case']['case_sha256'] or plan['case_sha256'] != body.case_sha256
                    or encode(body.model_dump(mode='json'))[1] != plan['request_sha256']
                    or any(plan[key] != snapshot[key] for key in
                           ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or plan['approval_requirement'] != {'kind': 'budget_workflow_scope', 'question': SCOPE_QUESTION,
                        'input_snapshot_sha256': digest, 'case_sha256': body.case_sha256}
                    or plan['execution_authorized'] is not False or plan['credit_awarded'] is not False):
                raise ValueError('Budget plan binding changed')
            from .advanced_workflow_checkpoints import decode_checkpoints
            if saved['authorization'] is not None:
                from .advanced_workflow_approval import AdvancedScopeRepository
                decision = saved['authorization']['decision']
                serialized_decision, decision_hash = encode(decision)
                AdvancedScopeRepository.decode({**decision, 'record_json': serialized_decision, 'record_sha256': decision_hash})
                if (any(decision[key] != plan[key] for key in
                        ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'input_snapshot_id', 'input_snapshot_sha256'))
                        or decision['case_sha256'] != plan['case_sha256'] or decision['submission']['choice'] != 'approve'
                        or decision['prompt'] != {**SCOPE_QUESTION, 'execution_choice': 'approve'}):
                    raise ValueError('Saved execution authorization changed')
            events = decode_checkpoints(raw, saved)
            if saved['result'] is not None:
                result = saved['result']
                if (result.get('task_events_sha256') != raw.get('task_events_sha256')
                        or result.get('task_event_count') != len(events) or result.get('credit_awarded') is not False):
                    raise ValueError('Terminal receipt does not bind the saved task log')
                if saved['state'] == 'completed':
                    from app.services.workflow_engine import WorkflowEngine
                    memo = next(item['receipt']['result'] for item in events
                                if item['receipt']['stage_index'] == 1 and item['receipt']['kind'] == 'task_completed')
                    if (result.get('final_output') != WorkflowEngine()._format_final_output(memo['output'])
                            or result.get('task_receipt_sha256s') != [item['receipt_sha256'] for item in events
                                                                    if item['receipt']['kind'] == 'task_completed']):
                        raise ValueError('Final memo differs from the actual completed task')
                    if result.get('completion_mode') is not None:
                        from .advanced_workflow_recovery import AdvancedFinalizationRequest
                        finalization = AdvancedFinalizationRequest.model_validate(result['finalization_request'])
                        if (result['completion_mode'] != 'finalized_from_saved_task_receipts'
                                or finalization.run_id != saved['run_id'] or finalization.plan_sha256 != saved['plan_sha256']
                                or finalization.authorization_sha256 != result['authorization_sha256']
                                or finalization.task_events_sha256 != result['task_events_sha256']
                                or result['finalization_actor_user_id'] != plan['user_id']
                                or result['execution_finished_at'] is not None
                                or datetime.datetime.fromisoformat(result['receipt_finalized_at']).tzinfo is None):
                            raise ValueError('Finalization changed its original evidence or learner binding')
            return {**saved, 'task_events': events}
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The saved budget workflow plan failed integrity verification') from exc

    async def prepare(self, operation, body, system_config_doc, *, actor_user_id, default_model):
        body = AdvancedPlanRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can prepare this budget plan')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'advanced_nodes', 'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256, 'input_snapshot_id': body.input_snapshot_id}
        lease = self.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            saved = self.decode(raw)
            if any(saved['plan'][key] != value for key, value in identity.items()) or saved['plan']['request_sha256'] != request_hash:
                raise EnrollmentConflict('This plan reference belongs to different saved evidence')
            return saved

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        snapshot = await AdvancedWorkflowInputRepository().get(actor_user_id, body.input_snapshot_id)
        if snapshot is None or encode(snapshot)[1] != body.input_snapshot_sha256:
            raise EnrollmentConflict('Inspect the exact owned workflow and calculation capture before preparing it')
        self.check_operation(operation, snapshot)
        case = load_advanced_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('The request belongs to another budget case')
        resolved = advanced_workflow_plan(snapshot, case, deepcopy(system_config_doc), default_model=default_model)
        plan = {**identity, **resolved, 'request': request, 'request_sha256': request_hash, 'input_snapshot': snapshot,
                'approval_requirement': {'kind': 'budget_workflow_scope', 'question': deepcopy(SCOPE_QUESTION),
                    'input_snapshot_sha256': body.input_snapshot_sha256, 'case_sha256': case.digest},
                'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(plan)
        if len(serialized.encode()) > MAX_PLAN_BYTES:
            raise EnrollmentConflict('The budget plan exceeds the immutable receipt size limit')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'plan_json': serialized, 'plan_sha256': digest, 'state': 'prepared'})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The budget plan reference was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return await self.get(actor_user_id, body.request_id)

    async def execute(self, *args, **kwargs):
        raise EnrollmentConflict('Budget dispatch requires its approved task-receipt executor')
