"""Save complete-suite plans for a separate authenticated approve/hold choice."""
from copy import deepcopy
import datetime
from typing import Literal

from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel
from .validation_case import ValidationCase, load_validation_case
from .validation_inputs import ValidationInputRepository
from .validation_plan import validation_plan, case_plans, validate_suite_binding
from .validation_suites import Digest, Identity, ValidationSuiteRepository, embedded_input

MAX_PLAN_BYTES = 8 * 1024 * 1024
SCOPE_QUESTION = {'id': 'validation_scope_approval', 'phase': 'before_execution',
    'prompt': 'Approve or hold this exact owned extraction revision, both complete sources, saved expectations and resolved models for the entire internal validation suite. Model usage may be incurred. A retest preserves the original failure and reruns both cases; no external action or credit is authorized.'}


class ValidationPlanRequest(ContractModel):
    request_id: Identity
    input_snapshot_id: Identity
    input_snapshot_sha256: Digest
    suite_id: Identity
    suite_record_sha256: Digest
    case_sha256: Digest
    original_run_id: Identity | None = None
    original_run_sha256: Digest | None = None
    consent: Literal['prepare_complete_validation_suite']


class ValidationPreparation(LabExecutionRepository):
    @staticmethod
    def decode(raw):
        saved = LabExecutionRepository.decode(raw)
        try:
            plan = saved['plan']
            body = ValidationPlanRequest.model_validate(plan['request'])
            snapshot = ValidationInputRepository.decode(embedded_input(plan['input_snapshot']))
            serialized, digest = encode(plan['suite'])
            suite = ValidationSuiteRepository.decode({**plan['suite'], 'record_json': serialized, 'record_sha256': digest})
            if (plan['executor_id'] != 'saved-representative-validation.1' or plan['module_id'] != 'validation_qa'
                    or body.request_id != plan['uuid'] or body.input_snapshot_id != snapshot['uuid']
                    or plan['input_snapshot_id'] != snapshot['uuid'] or body.input_snapshot_sha256 != encode(snapshot)[1]
                    or plan['input_snapshot_sha256'] != body.input_snapshot_sha256
                    or body.suite_id != suite['uuid'] or body.suite_record_sha256 != digest or plan['suite_record_sha256'] != digest
                    or body.case_sha256 != snapshot['case']['case_sha256'] or plan['case_sha256'] != body.case_sha256
                    or suite['case'] != snapshot['case'] or plan['suite_sha256'] != suite['suite_sha256']
                    or plan['case_plans'] != case_plans(snapshot)
                    or plan['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or any(plan[key] != snapshot[key] or plan[key] != suite[key] for key in
                           ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or plan['approval_requirement'] != {'kind': 'validation_suite_scope', 'question': SCOPE_QUESTION,
                        'input_snapshot_sha256': body.input_snapshot_sha256, 'case_sha256': body.case_sha256}
                    or plan['execution_authorized'] is not False or plan['credit_awarded'] is not False
                    or plan['external_effects_authorized'] is not False):
                raise ValueError('The saved plan changed its original suite, capture or evidence boundary')
            original = None
            if plan['phase'] == 'original':
                if (body.original_run_id is not None or body.original_run_sha256 is not None
                        or plan['original_run_record'] is not None or plan['original_run_id'] is not None
                        or plan['original_run_sha256'] is not None or plan['changed_fields'] != []
                        or snapshot != ValidationInputRepository.decode(suite['input_snapshot'])):
                    raise ValueError('The original plan changed the revision on which expectations were saved')
            elif plan['phase'] == 'retest':
                original_raw = plan['original_run_record']
                # Do not accept recursive retest chains as the original failure.
                import json
                if json.loads(original_raw['plan_json']).get('phase') != 'original':
                    raise ValueError('A retest requires the original run, not another retest')
                original = ValidationPreparation.decode(original_raw)
                if (original['state'] != 'completed' or original['run_id'] != body.original_run_id
                        or plan['original_run_id'] != body.original_run_id
                        or encode(original)[1] != body.original_run_sha256 or plan['original_run_sha256'] != body.original_run_sha256):
                    raise ValueError('The original failed-run reference changed')
            else:
                raise ValueError('Unsupported validation phase')
            phase, changed, _ = validate_suite_binding(snapshot, suite, ValidationCase.model_validate(snapshot['authored_case']), original_run=original)
            if plan['phase'] != phase or plan['changed_fields'] != changed:
                raise ValueError('The saved plan changed its original repair lineage')
            if saved['authorization'] is not None:
                from .validation_approval import ValidationScopeRepository
                decision = saved['authorization']['decision']
                serialized_decision, decision_hash = encode(decision)
                ValidationScopeRepository.decode({**decision, 'record_json': serialized_decision, 'record_sha256': decision_hash})
                if (saved['state'] == 'prepared' or decision['submission']['choice'] != 'approve'
                        or decision['case_sha256'] != plan['case_sha256']
                        or decision['prompt'] != {**SCOPE_QUESTION, 'execution_choice': 'approve'}
                        or any(decision[key] != plan[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version',
                                                                   'manifest_sha256', 'input_snapshot_id', 'input_snapshot_sha256'))):
                    raise ValueError('The saved suite execution authorization changed')
            from .validation_checkpoints import decode_checkpoints
            events = decode_checkpoints(raw, saved)
            if saved['result'] is not None:
                result = saved['result']
                if (result.get('case_events_sha256') != raw.get('case_events_sha256')
                        or result.get('case_event_count') != len(events) or result.get('credit_awarded') is not False):
                    raise ValueError('The terminal result changed its original execution prefix')
                if saved['state'] == 'completed':
                    from .validation_runtime import complete_result
                    expected = complete_result(plan, [e['receipt']['result'] for e in events[1::2]])
                    if any(result.get(key) != value for key, value in expected.items()):
                        raise ValueError('The terminal suite changed its actual case results or source checks')
                    if result.get('completion_mode') is not None:
                        from .validation_recovery import ValidationFinalizationRequest
                        finalization = ValidationFinalizationRequest.model_validate(result['finalization_request'])
                        if (result['completion_mode'] != 'finalized_from_saved_case_receipts'
                                or finalization.run_id != saved['run_id'] or finalization.plan_sha256 != saved['plan_sha256']
                                or finalization.authorization_sha256 != result['authorization_sha256']
                                or finalization.case_events_sha256 != result['case_events_sha256']
                                or result['finalization_actor_user_id'] != plan['user_id']
                                or result['started_at'] is not None or result['finished_at'] is not None
                                or datetime.datetime.fromisoformat(result['receipt_finalized_at']).tzinfo is None):
                            raise ValueError('Finalization changed the original evidence, timing or actor')
            return {**saved, 'case_events': events}
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise CourseCatalogError('The saved representative validation plan failed integrity verification') from exc

    async def prepare(self, operation, body, system_config_doc, *, actor_user_id):
        body = ValidationPlanRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can prepare this suite')
        if (body.original_run_id is None) != (body.original_run_sha256 is None):
            raise EnrollmentConflict('A retest must identify both the original run and its exact saved digest')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'validation_qa', 'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256, 'input_snapshot_id': body.input_snapshot_id}
        lease = self.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            saved = self.decode(raw)
            if any(saved['plan'][key] != value for key, value in identity.items()) or saved['plan']['request_sha256'] != request_hash:
                raise EnrollmentConflict('This plan request already belongs to different saved work')
            return saved

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        snapshot = await ValidationInputRepository().get(actor_user_id, body.input_snapshot_id)
        suite = await ValidationSuiteRepository().get(actor_user_id, body.suite_id)
        if (snapshot is None or suite is None or encode(snapshot)[1] != body.input_snapshot_sha256
                or encode(suite)[1] != body.suite_record_sha256):
            raise EnrollmentConflict('Inspect the exact owned capture and saved source-checked suite before preparing it')
        self.check_operation(operation, snapshot)
        self.check_operation(operation, suite)
        original_raw = None
        original = None
        if body.original_run_id:
            original_raw = await self.records.find_one({'uuid': body.original_run_id, 'user_id': actor_user_id}, {'_id': 0})
            original = self.decode(original_raw) if original_raw else None
            if original is None or encode(original)[1] != body.original_run_sha256:
                raise EnrollmentConflict('Inspect the exact original failed semantic result before planning a retest')
            self.check_operation(operation, original['plan'])
        case = load_validation_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('This request belongs to another representative validation case')
        resolved = validation_plan(snapshot, suite, case, deepcopy(system_config_doc), original_run=original)
        plan = {**identity, **resolved, 'request': request, 'request_sha256': request_hash, 'input_snapshot': snapshot,
            'suite': suite, 'original_run_record': original_raw,
            'approval_requirement': {'kind': 'validation_suite_scope', 'question': deepcopy(SCOPE_QUESTION),
                'input_snapshot_sha256': body.input_snapshot_sha256, 'case_sha256': case.digest},
            'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(plan)
        if len(serialized.encode()) > MAX_PLAN_BYTES:
            raise EnrollmentConflict('The complete validation plan exceeds its storage limit; evidence was not truncated')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'plan_json': serialized, 'plan_sha256': digest, 'state': 'prepared'})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The validation plan reference was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return await self.get(actor_user_id, body.request_id)

    async def execute(self, *args, **kwargs):
        raise EnrollmentConflict('Validation dispatch requires the separately approved bounded suite executor')
