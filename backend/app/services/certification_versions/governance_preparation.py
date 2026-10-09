"""Persist exact diagnostic plans; preparation does not execute the capstone."""
import datetime
from typing import Literal

from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .governance_case import GovernanceCase, load_governance_case
from .governance_checks import embedded_input
from .governance_inputs import GovernanceInputRepository
from .governance_plan import extraction_input, governance_plan, validate_scope_binding, validate_repair_binding
from .governance_scope import Digest, Identity, GovernanceScopeCorrection
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel

MAX_PLAN_BYTES = 8 * 1024 * 1024


class GovernancePlanRequest(ContractModel):
    request_id: Identity
    input_snapshot_id: Identity
    input_snapshot_sha256: Digest
    scope_correction_id: Identity
    scope_correction_sha256: Digest
    case_sha256: Digest
    source_finding_id: Identity | None = None
    source_finding_sha256: Digest | None = None
    consent: Literal['prepare_original_bounded_capstone_extraction', 'prepare_repaired_bounded_capstone_extraction']


def scope_question(phase='original'):
    detail = ('original diagnostic extraction. Its disclosed funding instruction may produce an unsupported value for you to inspect.'
        if phase == 'original' else 'changed-revision repair extraction, preserving your original source finding and rerunning both complete records with unchanged models and settings.')
    return {'id': 'governance_execution_approval', 'phase': 'before_execution', 'extraction_phase': phase,
        'prompt': 'Inspect the saved learner scope correction, both complete fictional sources, exact six-field revision and resolved model. Approve or hold only this bounded ' + detail + ' Model usage may be incurred; this does not authorize any handoff, external effect, recurring action or earned credit.'}


def validate_authorization(saved):
    from .governance_approval import GovernanceApprovalRepository
    plan, authorization = saved['plan'], saved['authorization']
    if authorization is None:
        return
    decision = authorization['decision']
    serialized, digest = encode(decision)
    GovernanceApprovalRepository.decode({**decision, 'record_json': serialized, 'record_sha256': digest})
    if (set(authorization) != {'run_id', 'plan_sha256', 'decision', 'decision_sha256'}
            or saved['state'] == 'prepared' or decision['submission']['choice'] != 'approve'
            or authorization['run_id'] != saved['run_id'] or authorization['plan_sha256'] != saved['plan_sha256']
            or authorization['decision_sha256'] != digest or saved['scope_decision_id'] != decision['uuid']
            or saved['scope_decision_sha256'] != digest or decision['run_id'] != saved['run_id']
            or decision['plan_sha256'] != saved['plan_sha256'] or decision['case_sha256'] != plan['case_sha256']
            or decision['prompt'] != {**scope_question(plan['phase']), 'execution_choice': 'approve'}
            or any(decision[key] != plan[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version',
                'manifest_sha256', 'input_snapshot_id', 'input_snapshot_sha256'))):
        raise ValueError('The saved capstone claim changed its exact authenticated approval')


class GovernancePreparation(LabExecutionRepository):
    @staticmethod
    def decode(raw):
        saved = LabExecutionRepository.decode(raw)
        try:
            plan = saved['plan']
            body = GovernancePlanRequest.model_validate(plan['request'])
            snapshot = GovernanceInputRepository.decode(embedded_input(plan['input_snapshot']))
            case = GovernanceCase.model_validate(snapshot['authored_case'])
            if plan['phase'] == 'original':
                digest = validate_scope_binding(snapshot, plan['scope_correction'], case)
                if (body.consent != 'prepare_original_bounded_capstone_extraction' or body.source_finding_id is not None
                        or body.source_finding_sha256 is not None or plan['source_finding'] is not None
                        or plan['source_finding_id'] is not None or plan['source_finding_sha256'] is not None
                        or plan['original_run_id'] is not None or plan['original_run_sha256'] is not None or plan['changed_fields'] != []):
                    raise ValueError('An original diagnostic plan cannot claim repair lineage')
            elif plan['phase'] == 'repair':
                original, changed, finding_hash = validate_repair_binding(snapshot, plan['scope_correction'], case, plan['source_finding'])
                digest = encode(plan['scope_correction'])[1]
                if (body.consent != 'prepare_repaired_bounded_capstone_extraction'
                        or body.source_finding_id != plan['source_finding']['uuid'] or plan['source_finding_id'] != body.source_finding_id
                        or body.source_finding_sha256 != finding_hash or plan['source_finding_sha256'] != finding_hash
                        or plan['original_run_id'] != original['run_id'] or plan['original_run_sha256'] != encode(original)[1]
                        or plan['changed_fields'] != changed or any(plan[k] != original['plan'][k] for k in
                            ('runtime_config_sha256', 'effective_extraction_config', 'model_info', 'model_names', 'capture_sources'))):
                    raise ValueError('The repair plan changed its original finding, revision or model settings')
            else:
                raise ValueError('Unsupported capstone extraction phase')
            if (plan['executor_id'] != 'saved-governance-capstone.1' or plan['module_id'] != 'governance'
                    or body.request_id != plan['uuid'] or body.input_snapshot_id != snapshot['uuid'] or plan['input_snapshot_id'] != snapshot['uuid']
                    or body.input_snapshot_sha256 != encode(snapshot)[1] or plan['input_snapshot_sha256'] != body.input_snapshot_sha256
                    or body.scope_correction_id != plan['scope_correction']['uuid'] or plan['scope_correction_id'] != body.scope_correction_id
                    or body.scope_correction_sha256 != digest or plan['scope_correction_sha256'] != digest
                    or body.case_sha256 != case.digest or plan['case_sha256'] != case.digest
                    or plan['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or plan['extraction_input'] != extraction_input(snapshot, saved['run_id'], plan['phase'])
                    or any(plan[key] != snapshot[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or plan['approval_requirement'] != {'kind': 'bounded_governance_execution', 'question': scope_question(plan['phase']),
                        'input_snapshot_sha256': body.input_snapshot_sha256, 'case_sha256': case.digest}
                    or any(plan[key] is not False for key in ('execution_authorized', 'external_effects_authorized', 'credit_awarded'))):
                raise ValueError('The saved diagnostic plan changed its exact inputs, learner correction or approval scope')
            validate_authorization(saved)
            from .governance_checkpoints import decode_checkpoints
            events = decode_checkpoints(raw, saved)
            if saved['result'] is not None:
                result = saved['result']
                if (result.get('extraction_events_sha256') != raw.get('extraction_events_sha256')
                        or result.get('extraction_event_count') != len(events) or result.get('credit_awarded') is not False):
                    raise ValueError('The terminal receipt changed its original execution prefix')
                if saved['state'] == 'completed':
                    from .governance_runtime import complete_result
                    expected = complete_result(plan, events[-1]['receipt']['result'])
                    if any(result.get(key) != value for key, value in expected.items()):
                        raise ValueError('The terminal receipt changed the actual extraction or source checks')
                    if result.get('completion_mode') is not None:
                        from .governance_recovery import GovernanceFinalizationRequest
                        finalization = GovernanceFinalizationRequest.model_validate(result['finalization_request'])
                        if (result['completion_mode'] != 'finalized_from_saved_extraction_receipts'
                                or finalization.run_id != saved['run_id'] or finalization.plan_sha256 != saved['plan_sha256']
                                or finalization.authorization_sha256 != result['authorization_sha256']
                                or finalization.extraction_events_sha256 != result['extraction_events_sha256']
                                or result['finalization_actor_user_id'] != plan['user_id']
                                or result['started_at'] is not None or result['finished_at'] is not None
                                or datetime.datetime.fromisoformat(result['receipt_finalized_at']).tzinfo is None):
                            raise ValueError('Finalization changed the evidence, actor or original execution timing')
            return {**saved, 'extraction_events': events}
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise CourseCatalogError('The saved Governance plan failed integrity verification') from exc

    async def prepare(self, operation, body, system_config_doc, *, actor_user_id):
        body = GovernancePlanRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can prepare the bounded capstone')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
            'module_id': 'governance', 'course_version': operation.package.manifest.release_id,
            'manifest_sha256': operation.package.manifest_sha256, 'input_snapshot_id': body.input_snapshot_id}
        lease = self.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            saved = self.decode(raw)
            if any(saved['plan'][key] != value for key, value in identity.items()) or saved['plan']['request_sha256'] != request_hash:
                raise EnrollmentConflict('This plan identity belongs to different capstone work or another learner')
            return saved

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        snapshot = await GovernanceInputRepository().get(actor_user_id, body.input_snapshot_id)
        correction = await GovernanceScopeCorrection().get(actor_user_id, body.scope_correction_id)
        if (snapshot is None or correction is None or encode(snapshot)[1] != body.input_snapshot_sha256
                or encode(correction)[1] != body.scope_correction_sha256):
            raise EnrollmentConflict('Inspect the exact owned capture and saved learner scope correction before preparation')
        self.check_operation(operation, snapshot)
        self.check_operation(operation, correction)
        case = load_governance_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('This plan belongs to a different original capstone')
        finding = None
        if body.source_finding_id is not None:
            from .governance_findings import GovernanceFindingRepository
            finding = await GovernanceFindingRepository().get(actor_user_id, body.source_finding_id)
            if finding is None or encode(finding)[1] != body.source_finding_sha256:
                raise EnrollmentConflict('Read your exact saved original source finding before planning its repair')
            self.check_operation(operation, finding)
        if ((finding is None) != (body.consent == 'prepare_original_bounded_capstone_extraction')
                or (body.source_finding_id is None) != (body.source_finding_sha256 is None)):
            raise EnrollmentConflict('A repair requires both the original finding identity and digest with explicit repair consent')
        resolved = governance_plan(snapshot, correction, case, system_config_doc, run_id=body.request_id, finding=finding)
        plan = {**identity, **resolved, 'request': request, 'request_sha256': request_hash, 'input_snapshot': snapshot,
            'scope_correction': correction, 'source_finding': finding, 'approval_requirement': {'kind': 'bounded_governance_execution', 'question': scope_question(resolved['phase']),
                'input_snapshot_sha256': body.input_snapshot_sha256, 'case_sha256': case.digest},
            'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(plan)
        if len(serialized.encode()) > MAX_PLAN_BYTES:
            raise EnrollmentConflict('The complete capstone plan exceeds its storage limit; no sources were truncated')
        candidate = {**identity, 'plan_json': serialized, 'plan_sha256': digest, 'state': 'prepared'}
        self.decode(candidate)
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one(candidate)
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The plan identity was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return await self.get(actor_user_id, body.request_id)

    async def execute(self, *args, **kwargs):
        raise EnrollmentConflict('Capstone execution requires the separately approved durable executor')
