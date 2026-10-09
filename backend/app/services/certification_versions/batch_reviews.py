"""Preserve a learner's interpretation and exact original/recovery inventories."""
import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .batch_case import BatchCase, load_batch_case
from .batch_checks import check_recovery
from .batch_preparation import BatchPreparation, Digest, Identity
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository
from .outcomes import ContractModel

MAX_REVIEW_BYTES = 15 * 1024 * 1024
PROMPT_ID = 'batch_result_review'
Answer = Annotated[str, Field(min_length=1, max_length=8000)]


class BatchRetryReference(ContractModel):
    run_id: Identity
    result_sha256: Digest


class BatchReviewRequest(ContractModel):
    request_id: Identity
    run_id: Identity
    result_sha256: Digest
    case_sha256: Digest
    retries: tuple[BatchRetryReference, ...] = Field(min_length=1, max_length=3)
    answers: dict[str, Answer] = Field(min_length=1, max_length=1)
    previous_submission_id: Identity | None = None
    consent: Literal['save_batch_recovery_interpretation']

    @model_validator(mode='after')
    def complete_answers(self):
        if (set(self.answers) != {'batch_review'} or any(not value.strip() for value in self.answers.values())
                or self.previous_submission_id == self.request_id or len({r.run_id for r in self.retries}) != len(self.retries)
                or self.run_id in {r.run_id for r in self.retries}):
            raise ValueError('Explain the actual inventory and distinct targeted retries; revised answers require a new identity')
        return self


def embedded_execution(run):
    plan = run['plan']
    raw = {key: plan[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'input_snapshot_id')}
    raw.update(state=run['state'], scope_decision_id=run['scope_decision_id'], scope_decision_sha256=run['scope_decision_sha256'])
    for value, prefix in ((plan, 'plan'), (run['authorization'], 'authorization'), (run['result'], 'result'), (run['item_events'], 'item_events')):
        raw[prefix + '_json'], raw[prefix + '_sha256'] = encode(value)
    raw['item_event_count'] = len(run['item_events'])
    if raw['plan_sha256'] != run['plan_sha256'] or BatchPreparation.decode(raw) != run:
        raise CourseCatalogError('The original batch execution cannot be preserved exactly')
    return raw


def reconcile(original, retries):
    if original['state'] != 'completed' or original['plan']['phase'] != 'batch':
        raise EnrollmentConflict('Select the original complete batch inventory')
    for retry in retries:
        if (retry['state'] != 'completed' or retry['plan']['phase'] != 'retry'
                or BatchPreparation.decode(retry['plan']['parent_run_record']) != original):
            raise EnrollmentConflict('Each recovery must retain this exact original batch and its actual terminal item')
    case = BatchCase.model_validate(original['plan']['input_snapshot']['authored_case'])
    return check_recovery(case, original['plan']['input_snapshot'], original['result']['item_results'],
        [run['result']['item_results'][0] for run in retries], batch_id=original['run_id'])


class BatchReviewRepository(LearnerDecisionRepository):
    @staticmethod
    def decode(raw):
        saved = LearnerDecisionRepository.decode(raw)
        try:
            body = BatchReviewRequest.model_validate(saved['submission'])
            original = BatchPreparation.decode(saved['execution'])
            retries = [BatchPreparation.decode(item) for item in saved['retry_executions']]
            if (saved['record_kind'] != PROMPT_ID or saved['module_id'] != 'batch_processing'
                    or saved['prompt_id'] != PROMPT_ID or saved['uuid'] != body.request_id
                    or saved['run_id'] != body.run_id or original['run_id'] != body.run_id
                    or encode(original['result'])[1] != body.result_sha256
                    or [(r['run_id'], encode(r['result'])[1]) for r in retries] != [(r.run_id, r.result_sha256) for r in body.retries]
                    or saved['reconciliation'] != reconcile(original, retries)
                    or saved['case'] != original['plan']['input_snapshot']['case'] or body.case_sha256 != saved['case']['case_sha256']
                    or saved['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or any(saved[key] != original['plan'][key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or saved['submission_channel'] != 'authenticated_learner_batch_review_request'
                    or saved['credit_awarded'] is not False or saved['module_completion_eligible'] is not False):
                raise ValueError('The saved review changed its original batch, retries or learner answers')
            return saved
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The saved batch result review failed integrity verification') from exc

    async def get(self, user_id, submission_id):
        raw = await self.records.find_one({'uuid': submission_id, 'user_id': user_id, 'module_id': 'batch_processing', 'prompt_id': PROMPT_ID})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        body = BatchReviewRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Batch result review requires the authenticated learner')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'batch_processing', 'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256, 'run_id': body.run_id, 'prompt_id': PROMPT_ID}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            if any(raw.get(key) != value for key, value in identity.items()) or raw.get('request_sha256') != request_hash:
                raise EnrollmentConflict('This review identity belongs to different answers or another learner')
            return self.decode(raw)

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        case = load_batch_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('Review the exact assigned batch case')
        previous = None
        if body.previous_submission_id:
            previous = await self.get(actor_user_id, body.previous_submission_id)
            if (previous is None or any(previous[key] != identity[key] for key in
                    ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256')) or previous['case'] != case.public_definition()):
                raise EnrollmentConflict('A revision must preserve an owned original batch review in this course')
        preserved = ([previous['execution'], *previous['retry_executions']] if previous else [])
        preserved_runs = {run['run_id']: run for run in (BatchPreparation.decode(raw) for raw in preserved)}

        async def owned(reference, digest):
            run = preserved_runs.get(reference) or await BatchPreparation().get(actor_user_id, reference)
            if run is None or run['state'] != 'completed' or encode(run['result'])[1] != digest:
                raise EnrollmentConflict('Inspect the exact complete saved batch or retry result before reviewing it')
            LabExecutionRepository.check_operation(operation, run['plan'])
            if run['plan']['input_snapshot']['case'] != case.public_definition():
                raise EnrollmentConflict('The original result belongs to another assignment')
            return run

        original = await owned(body.run_id, body.result_sha256)
        retries = [await owned(ref.run_id, ref.result_sha256) for ref in body.retries]
        reconciliation = reconcile(original, retries)
        # New live evidence must be the current claimed terminal recovery for its
        # item; an older failed retry cannot hide a later uncertain/in-flight one.
        raw_original = await self.records_for_runs().find_one({'uuid': original['run_id'], 'user_id': actor_user_id})
        for retry in retries:
            if retry['run_id'] not in preserved_runs and (raw_original is None
                    or raw_original.get('retry_heads', {}).get(retry['plan']['failed_source_id']) != retry['run_id']):
                raise EnrollmentConflict('Inspect the current original-item retry receipt before saving a new review')
        saved = {**identity, 'record_kind': PROMPT_ID, 'request_sha256': request_hash, 'submission': request,
            'case': case.public_definition(), 'execution': embedded_execution(original),
            'retry_executions': [embedded_execution(run) for run in retries], 'reconciliation': reconciliation,
            'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'submission_channel': 'authenticated_learner_batch_review_request', 'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > MAX_REVIEW_BYTES:
            raise EnrollmentConflict('The complete batch review exceeds its storage limit; no evidence was truncated')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('This review reference was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return saved

    @staticmethod
    def records_for_runs():
        return BatchPreparation().records
