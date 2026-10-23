"""Persist an output plan for separate explicit scope approval, without dispatch."""
from copy import deepcopy
import datetime
from typing import Literal

from pydantic import Field
from pymongo.errors import DuplicateKeyError

from .output_case import load_output_case
from .output_workflow_inputs import OutputWorkflowInputRepository
from .output_workflow_plan import output_workflow_plan
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel

MAX_PLAN_BYTES = 4 * 1024 * 1024
SCOPE_QUESTION = {
    'id': 'output_scope_approval', 'phase': 'before_execution',
    'prompt': 'Approve or hold this exact saved workflow and assigned progress report for internal PDF/CSV generation. Review every input, output and model. This approval does not authorize a handoff, external action or earned credit.',
}


class OutputPlanRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    input_snapshot_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    input_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['prepare_output_workflow_plan']


class OutputWorkflowPreparation(LabExecutionRepository):
    @staticmethod
    def decode(raw):
        saved = LabExecutionRepository.decode(raw)
        try:
            plan = saved['plan']
            body = OutputPlanRequest.model_validate(plan['request'])
            snapshot = plan['input_snapshot']
            serialized, digest = encode(snapshot)
            OutputWorkflowInputRepository.decode({**snapshot, 'record_json': serialized, 'record_sha256': digest})
            if (plan['executor_id'] != 'saved-output-workflow.1' or plan['module_id'] != 'output_delivery'
                    or body.request_id != plan['uuid'] or body.input_snapshot_id != snapshot['uuid']
                    or plan['input_snapshot_id'] != snapshot['uuid']
                    or body.input_snapshot_sha256 != digest or plan['input_snapshot_sha256'] != digest
                    or body.case_sha256 != snapshot['case']['case_sha256'] or plan['case_sha256'] != body.case_sha256
                    or encode(body.model_dump(mode='json'))[1] != plan['request_sha256']
                    or any(plan[key] != snapshot[key] for key in
                           ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or plan['approval_requirement'] != {'kind': 'output_generation_scope', 'question': SCOPE_QUESTION,
                        'input_snapshot_sha256': digest, 'case_sha256': body.case_sha256}
                    or plan['execution_authorized'] is not False or plan['release_authorized'] is not False or plan['credit_awarded'] is not False):
                raise ValueError('Output plan binding changed')
            from .output_workflow_checkpoints import decode_checkpoints
            if saved['authorization'] is not None:
                from .output_workflow_approval import OutputScopeRepository
                decision = saved['authorization']['decision']
                serialized_decision, decision_hash = encode(decision)
                OutputScopeRepository.decode({**decision, 'record_json': serialized_decision, 'record_sha256': decision_hash})
                if (any(decision[key] != plan[key] for key in
                        ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'input_snapshot_id', 'input_snapshot_sha256'))
                        or decision['case_sha256'] != plan['case_sha256'] or decision['submission']['choice'] != 'approve'
                        or decision['prompt'] != {**SCOPE_QUESTION, 'execution_choice': 'approve'}):
                    raise ValueError('Saved execution authorization changed')
            events = decode_checkpoints(raw, saved)
            if saved['result'] is not None:
                result = saved['result']
                if (result.get('stage_events_sha256') != raw.get('stage_events_sha256')
                        or result.get('stage_event_count') != len(events) or result.get('credit_awarded') is not False):
                    raise ValueError('Terminal receipt does not bind the saved task log')
                if saved['state'] == 'completed':
                    from .output_artifacts import verify_artifacts_for_events
                    verify_artifacts_for_events(result['generated_artifacts'], events, plan)
                    if (result.get('release_authorized') is not False or result.get('delivery_confirmed') is not False
                            or result.get('stage_receipt_sha256s') != [item['receipt_sha256'] for item in events
                                                                     if item['receipt']['kind'] == 'stage_completed']):
                        raise ValueError('Completed generation changed its authority or stage evidence')
                    if result.get('completion_mode') is not None:
                        from .output_workflow_recovery import OutputFinalizationRequest
                        finalization = OutputFinalizationRequest.model_validate(result['finalization_request'])
                        if (result['completion_mode'] != 'finalized_from_saved_stage_receipts'
                                or finalization.run_id != saved['run_id'] or finalization.plan_sha256 != saved['plan_sha256']
                                or finalization.authorization_sha256 != result['authorization_sha256']
                                or finalization.stage_events_sha256 != result['stage_events_sha256']
                                or result['finalization_actor_user_id'] != plan['user_id']
                                or result['execution_finished_at'] is not None
                                or datetime.datetime.fromisoformat(result['receipt_finalized_at']).tzinfo is None):
                            raise ValueError('Finalization changed its original evidence or learner binding')
            return {**saved, 'stage_events': events}
        except (KeyError, TypeError, ValueError, EnrollmentConflict) as exc:
            raise CourseCatalogError('The saved output workflow plan failed integrity verification') from exc

    async def prepare(self, operation, body, system_config_doc, *, actor_user_id, default_model):
        body = OutputPlanRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can prepare this output plan')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'output_delivery', 'course_version': operation.package.manifest.release_id,
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
        snapshot = await OutputWorkflowInputRepository().get(actor_user_id, body.input_snapshot_id)
        if snapshot is None or encode(snapshot)[1] != body.input_snapshot_sha256:
            raise EnrollmentConflict('Inspect the exact owned workflow and source capture before preparing it')
        self.check_operation(operation, snapshot)
        case = load_output_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('The request belongs to another output case')
        resolved = output_workflow_plan(snapshot, case, deepcopy(system_config_doc), default_model=default_model)
        plan = {**identity, **resolved, 'request': request, 'request_sha256': request_hash, 'input_snapshot': snapshot,
                'approval_requirement': {'kind': 'output_generation_scope', 'question': deepcopy(SCOPE_QUESTION),
                    'input_snapshot_sha256': body.input_snapshot_sha256, 'case_sha256': case.digest},
                'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(plan)
        if len(serialized.encode()) > MAX_PLAN_BYTES:
            raise EnrollmentConflict('The output plan exceeds the immutable receipt size limit')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'plan_json': serialized, 'plan_sha256': digest, 'state': 'prepared'})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The output plan reference was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return await self.get(actor_user_id, body.request_id)

    async def execute(self, *args, **kwargs):
        raise EnrollmentConflict('Output dispatch requires its approved generation executor')
