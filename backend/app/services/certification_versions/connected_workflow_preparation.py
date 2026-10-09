"""Persist a reviewable connected-run plan; dispatch remains separately gated."""
from copy import deepcopy
import datetime
from typing import Literal

from pydantic import Field
from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .catalog import CourseCatalogError
from .connected_workflow_inputs import ConnectedWorkflowInputRepository
from .connected_workflow_plan import connected_workflow_plan
from .connected_failure_practice import approval_question, is_failure_practice, STOP_MARKER, stopped_stage_result
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .multi_step_case import load_multi_step_case
from .outcomes import ContractModel

MAX_PLAN_BYTES = 4 * 1024 * 1024


class ConnectedPlanRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    input_snapshot_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    input_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['prepare_connected_workflow_plan', 'prepare_controlled_failure_rehearsal']


class ConnectedWorkflowPreparation(LabExecutionRepository):
    @staticmethod
    def decode(raw):
        saved = LabExecutionRepository.decode(raw)
        try:
            plan = saved['plan']
            request = ConnectedPlanRequest.model_validate(plan['request'])
            snapshot = plan['input_snapshot']
            serialized, digest = encode(snapshot)
            ConnectedWorkflowInputRepository.decode({**snapshot, 'record_json': serialized, 'record_sha256': digest})
            identity_keys = ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256')
            question = approval_question(snapshot['case'], request.consent)
            if (plan['executor_id'] != 'saved-internal-workflow.1' or plan['module_id'] != 'multi_step'
                    or request.request_id != plan['uuid'] or request.input_snapshot_id != snapshot['uuid']
                    or plan['input_snapshot_id'] != snapshot['uuid']
                    or request.input_snapshot_sha256 != digest or plan['input_snapshot_sha256'] != digest
                    or request.case_sha256 != snapshot['case']['case_sha256'] or plan['case_sha256'] != request.case_sha256
                    or encode(request.model_dump(mode='json'))[1] != plan['request_sha256']
                    or any(plan[key] != snapshot[key] for key in identity_keys)
                    or plan['approval_requirement'] != {'kind': 'connected_workflow_scope', 'question': question,
                        'input_snapshot_sha256': digest, 'case_sha256': request.case_sha256}
                    or plan['execution_authorized'] is not False or plan['credit_awarded'] is not False):
                raise ValueError('Connected plan binding changed')
            from .connected_workflow_checkpoints import decode_checkpoints
            events = decode_checkpoints(raw, saved)
            result = saved['result']
            if result is not None:
                if result.get('reason') == STOP_MARKER:
                    if (saved['state'] != 'failed' or not is_failure_practice(plan) or len(events) != 4
                            or events[-1]['receipt'].get('result') != stopped_stage_result()):
                        raise ValueError('The controlled rejection lacks its exact preserved stage boundary')
                if (result.get('stage_events_sha256') != raw.get('stage_events_sha256')
                        or result.get('stage_event_count') != len(events) or result.get('credit_awarded') is not False):
                    raise ValueError('Terminal receipt changed its stage evidence binding')
                if saved['state'] == 'completed':
                    from app.services.workflow_engine import WorkflowEngine
                    final = events[-1]['receipt']['result']
                    expected = WorkflowEngine()._format_final_output(final.get('formatted_output') or final.get('output'))
                    if (result.get('final_output') != expected or result.get('stage_receipt_sha256s') != [
                            item['receipt_sha256'] for item in events if item['receipt']['kind'] == 'stage_completed']):
                        raise ValueError('Terminal deliverable differs from the completed stage receipts')
                    if result.get('completion_mode') is not None:
                        from .connected_workflow_recovery import ConnectedFinalizationRequest
                        finalization = ConnectedFinalizationRequest.model_validate(result['finalization_request'])
                        if (result['completion_mode'] != 'finalized_from_saved_stage_receipts'
                                or finalization.run_id != saved['run_id'] or finalization.plan_sha256 != saved['plan_sha256']
                                or finalization.authorization_sha256 != result['authorization_sha256']
                                or finalization.stage_events_sha256 != result['stage_events_sha256']
                                or result['finalization_actor_user_id'] != plan['user_id']
                                or result['execution_finished_at'] is not None
                                or datetime.datetime.fromisoformat(result['receipt_finalized_at']).tzinfo is None):
                            raise ValueError('Finalization does not bind the original saved results and learner')
            return {**saved, 'stage_events': events}
        except (KeyError, TypeError, ValueError, StopIteration) as exc:
            raise CourseCatalogError('The saved connected-workflow plan failed integrity verification') from exc

    async def prepare(self, operation, body, system_config_doc, *, actor_user_id, default_model):
        body = ConnectedPlanRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can prepare this plan')
        identity = {'uuid': body.request_id, 'user_id': operation.user_id,
                    'enrollment_id': operation.progress.enrollment_id, 'module_id': 'multi_step',
                    'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256, 'input_snapshot_id': body.input_snapshot_id}
        lease = self.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            saved = self.decode(raw)
            if any(saved['plan'][key] != value for key, value in identity.items()) or saved['plan']['request_sha256'] != request_hash:
                raise EnrollmentConflict('This plan reference was used for different captured inputs')
            return saved

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        snapshot = await ConnectedWorkflowInputRepository().get(operation.user_id, body.input_snapshot_id)
        if snapshot is None:
            raise EnrollmentConflict('Capture the assigned workflow and source before preparing its plan')
        self.check_operation(operation, snapshot)
        if body.input_snapshot_sha256 != encode(snapshot)[1]:
            raise EnrollmentConflict('Inspect the exact captured revision before preparing its plan')
        case = load_multi_step_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('The plan request belongs to another connected case')
        resolved = connected_workflow_plan(snapshot, case, deepcopy(system_config_doc), default_model=default_model)
        question = approval_question(snapshot['case'], body.consent)
        plan = {**identity, **resolved, 'request': request, 'request_sha256': request_hash,
                'input_snapshot': snapshot,
                'approval_requirement': {'kind': 'connected_workflow_scope', 'question': question,
                    'input_snapshot_sha256': body.input_snapshot_sha256, 'case_sha256': case.digest},
                'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(plan)
        if len(serialized.encode()) > MAX_PLAN_BYTES:
            raise EnrollmentConflict('The connected plan exceeds the immutable receipt size limit')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'plan_json': serialized, 'plan_sha256': digest, 'state': 'prepared'})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The plan reference was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return await self.get(operation.user_id, body.request_id)

    async def execute(self, *args, **kwargs):
        raise EnrollmentConflict('Connected workflow dispatch requires its own approved stage-receipt executor')
