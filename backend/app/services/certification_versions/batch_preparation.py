"""Persist exact bounded batch plans for separate learner approval."""
from copy import deepcopy
import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .batch_case import BatchCase, load_batch_case
from .batch_inputs import BatchInputRepository
from .batch_plan import batch_plan, bind_inputs, embedded_input, item_plans
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel

Identity = Annotated[str, Field(pattern=r'^[a-f0-9]{32}$')]
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
MAX_PLAN_BYTES = 8 * 1024 * 1024


class BatchPlanRequest(ContractModel):
    request_id: Identity
    input_snapshot_id: Identity
    input_snapshot_sha256: Digest
    case_sha256: Digest
    phase: Literal['pilot', 'batch', 'retry']
    parent_run_id: Identity | None = None
    parent_run_sha256: Digest | None = None
    failed_source_id: Literal['proposal_1', 'proposal_2', 'proposal_3'] | None = None
    previous_retry_id: Identity | None = None
    previous_retry_sha256: Digest | None = None
    consent: Literal['prepare_bounded_batch_action']

    @model_validator(mode='after')
    def complete_references(self):
        if (self.parent_run_id is None) != (self.parent_run_sha256 is None) or (self.previous_retry_id is None) != (self.previous_retry_sha256 is None):
            raise ValueError('A saved parent requires both its identity and exact digest')
        if (self.phase == 'pilot' and (self.parent_run_id or self.failed_source_id or self.previous_retry_id)
                or self.phase != 'pilot' and not self.parent_run_id
                or self.phase == 'batch' and (self.failed_source_id or self.previous_retry_id)
                or self.phase == 'retry' and not self.failed_source_id
                or self.request_id in (self.parent_run_id, self.previous_retry_id)):
            raise ValueError('Keep pilot, complete batch and exact failed-item recovery scopes distinct')
        return self


def scope_question(case, phase):
    key = {'pilot': 'pilot_choice', 'batch': 'scale_choice', 'retry': 'recovery_choice'}[phase]
    question = next(q for q in case.questions if q.id == key)
    return {'id': 'batch_scope_approval', 'phase': 'before_execution', 'batch_phase': phase,
        'case_question_id': key, 'prompt': question.prompt + ' Model usage may be incurred. This choice authorizes only the displayed internal action; it does not award credit or authorize external effects.'}


class BatchPreparation(LabExecutionRepository):
    @staticmethod
    def decode(raw, _depth=0):
        if _depth > 8:
            raise CourseCatalogError('This saved recovery ancestry exceeds its bounded depth')
        saved = LabExecutionRepository.decode(raw)
        try:
            plan = saved['plan']
            body = BatchPlanRequest.model_validate(plan['request'])
            snapshot = BatchInputRepository.decode(embedded_input(plan['input_snapshot']))
            case = BatchCase.model_validate(snapshot['authored_case'])
            parent = BatchPreparation.decode(plan['parent_run_record'], _depth + 1) if plan['parent_run_record'] else None
            previous = BatchPreparation.decode(plan['previous_retry_record'], _depth + 1) if plan['previous_retry_record'] else None
            binding = bind_inputs(snapshot, case, run_id=saved['run_id'], phase=body.phase, parent=parent,
                failed_source_id=body.failed_source_id, previous_retry=previous)
            if (plan['executor_id'] != 'saved-bounded-batch.1' or plan['module_id'] != 'batch_processing'
                    or body.request_id != plan['uuid'] or body.input_snapshot_id != snapshot['uuid']
                    or plan['input_snapshot_id'] != snapshot['uuid'] or body.input_snapshot_sha256 != encode(snapshot)[1]
                    or plan['input_snapshot_sha256'] != body.input_snapshot_sha256
                    or body.case_sha256 != case.digest or plan['case_sha256'] != case.digest
                    or plan['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or any(plan.get(key) != value for key, value in binding.items())
                    or any(getattr(body, key) != binding[key] for key in ('parent_run_id', 'parent_run_sha256', 'previous_retry_id', 'previous_retry_sha256'))
                    or any(plan[key] != snapshot[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or plan['item_plans'] != item_plans(snapshot, run_id=saved['run_id'], batch_id=binding['batch_id'], phase=body.phase, source_ids=binding['source_ids'])
                    or plan['approval_requirement'] != {'kind': 'bounded_batch_scope', 'question': scope_question(case, body.phase),
                        'input_snapshot_sha256': body.input_snapshot_sha256, 'case_sha256': case.digest}
                    or plan['execution_authorized'] is not False or plan['credit_awarded'] is not False or plan['external_effects_authorized'] is not False):
                raise ValueError('The saved batch plan changed its exact inputs, ancestry or approval scope')
            for prior in (parent, previous):
                if prior and any(prior['plan'][key] != plan[key] for key in
                        ('runtime_config_sha256', 'effective_extraction_config', 'model_info', 'model_names', 'capture_sources')):
                    raise ValueError('The saved batch plan changed the checked model or extraction configuration')
            if saved['authorization'] is not None:
                from .batch_approval import BatchScopeRepository
                decision = saved['authorization']['decision']
                serialized, digest = encode(decision)
                BatchScopeRepository.decode({**decision, 'record_json': serialized, 'record_sha256': digest})
                if (saved['state'] == 'prepared' or decision['submission']['choice'] != 'approve'
                        or decision['case_sha256'] != case.digest
                        or decision['prompt'] != {**scope_question(case, body.phase), 'execution_choice': 'approve'}
                        or any(decision[key] != plan[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version',
                                                                    'manifest_sha256', 'input_snapshot_id', 'input_snapshot_sha256'))):
                    raise ValueError('The saved batch authorization differs from this exact phase and plan')
                expected_claim = {'batch_id': plan['batch_id'], 'source_id': plan['failed_source_id'],
                                  'run_id': saved['run_id'], 'previous_retry_id': plan['previous_retry_id']}
                if (body.phase == 'retry' and saved['authorization'].get('retry_claim') != expected_claim
                        or body.phase != 'retry' and saved['authorization'].get('retry_claim') is not None):
                    raise ValueError('The retry authorization changed its exact item claim')
            from .batch_checkpoints import decode_checkpoints
            events = decode_checkpoints(raw, saved)
            if saved['result'] is not None:
                result = saved['result']
                if (result.get('item_events_sha256') != raw.get('item_events_sha256')
                        or result.get('item_event_count') != len(events) or result.get('credit_awarded') is not False):
                    raise ValueError('The terminal result changed its original item receipts')
                if saved['state'] == 'completed':
                    from .batch_runtime import complete_result
                    expected = complete_result(plan, [e['receipt']['result'] for e in events[1::2]])
                    if any(result.get(key) != value for key, value in expected.items()):
                        raise ValueError('The terminal batch changed its actual item inventory or source checks')
                    if result.get('completion_mode') is not None:
                        from .batch_recovery import BatchFinalizationRequest
                        finalization = BatchFinalizationRequest.model_validate(result['finalization_request'])
                        if (result['completion_mode'] != 'finalized_from_saved_item_receipts'
                                or finalization.run_id != saved['run_id'] or finalization.plan_sha256 != saved['plan_sha256']
                                or finalization.authorization_sha256 != result['authorization_sha256']
                                or finalization.item_events_sha256 != result['item_events_sha256']
                                or result['finalization_actor_user_id'] != plan['user_id']
                                or result['started_at'] is not None or result['finished_at'] is not None
                                or datetime.datetime.fromisoformat(result['receipt_finalized_at']).tzinfo is None):
                            raise ValueError('Finalization changed the original item evidence, timing or actor')
            return {**saved, 'item_events': events}
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise CourseCatalogError('The saved bounded batch plan failed integrity verification') from exc

    async def prepare(self, operation, body, system_config_doc, *, actor_user_id):
        body = BatchPlanRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can prepare this bounded action')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'batch_processing', 'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256, 'input_snapshot_id': body.input_snapshot_id}
        lease = self.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            saved = self.decode(raw)
            if any(saved['plan'][key] != value for key, value in identity.items()) or saved['plan']['request_sha256'] != request_hash:
                raise EnrollmentConflict('This plan request belongs to different original work or another learner')
            return saved

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        snapshot = await BatchInputRepository().get(actor_user_id, body.input_snapshot_id)
        if snapshot is None or encode(snapshot)[1] != body.input_snapshot_sha256:
            raise EnrollmentConflict('Inspect the exact owned batch input capture before preparing this action')
        self.check_operation(operation, snapshot)
        parents = {}
        for key, reference, digest in (('parent', body.parent_run_id, body.parent_run_sha256),
                                        ('previous_retry', body.previous_retry_id, body.previous_retry_sha256)):
            raw = await self.records.find_one({'uuid': reference, 'user_id': actor_user_id}, {'_id': 0}) if reference else None
            saved = self.decode(raw) if raw else None
            if reference and (saved is None or encode(saved)[1] != digest):
                raise EnrollmentConflict('Inspect the exact saved pilot or failed item before planning the next action')
            if saved:
                self.check_operation(operation, saved['plan'])
            parents[key] = saved
            parents[key + '_raw'] = raw
        case = load_batch_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('This bounded action belongs to a different original assignment')
        resolved = batch_plan(snapshot, case, deepcopy(system_config_doc), run_id=body.request_id, phase=body.phase,
            parent=parents['parent'], failed_source_id=body.failed_source_id, previous_retry=parents['previous_retry'])
        plan = {**identity, **resolved, 'request': request, 'request_sha256': request_hash, 'input_snapshot': snapshot,
            'parent_run_record': parents['parent_raw'], 'previous_retry_record': parents['previous_retry_raw'],
            'approval_requirement': {'kind': 'bounded_batch_scope', 'question': scope_question(case, body.phase),
                'input_snapshot_sha256': body.input_snapshot_sha256, 'case_sha256': case.digest},
            'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(plan)
        if len(serialized.encode()) > MAX_PLAN_BYTES:
            raise EnrollmentConflict('The complete batch plan exceeds its storage limit; no evidence was truncated')
        candidate = {**identity, 'plan_json': serialized, 'plan_sha256': digest, 'state': 'prepared'}
        self.decode(candidate)
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one(candidate)
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The batch plan reference was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return await self.get(actor_user_id, body.request_id)

    async def execute(self, *args, **kwargs):
        raise EnrollmentConflict('Batch dispatch requires the separately approved durable item executor')
