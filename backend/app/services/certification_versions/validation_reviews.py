"""Preserve learner repair explanations with original failure and full retest."""
import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .validation_case import load_validation_case
from .validation_preparation import ValidationPreparation
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository
from .outcomes import ContractModel

MAX_REVIEW_BYTES = 15 * 1024 * 1024
PROMPT_ID = 'validation_result_review'
Answer = Annotated[str, Field(min_length=1, max_length=8000)]


class ValidationReviewRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    result_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    answers: dict[str, Answer] = Field(min_length=1, max_length=1)
    previous_submission_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    consent: Literal['save_validation_repair_interpretation']

    @model_validator(mode='after')
    def complete_answers(self):
        if (set(self.answers) != {'repair_review'}
                or any(not value.strip() for value in self.answers.values()) or self.previous_submission_id == self.request_id):
            raise ValueError('Explain the actual repair and complete regression result; revised answers require a new request identity')
        return self


def embedded_execution(run):
    plan = run['plan']
    raw = {key: plan[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version',
                                    'manifest_sha256', 'input_snapshot_id')}
    raw.update(state=run['state'], scope_decision_id=run['scope_decision_id'], scope_decision_sha256=run['scope_decision_sha256'])
    for value, prefix in ((plan, 'plan'), (run['authorization'], 'authorization'), (run['result'], 'result'), (run['case_events'], 'case_events')):
        raw[prefix + '_json'], raw[prefix + '_sha256'] = encode(value)
    raw['case_event_count'] = len(run['case_events'])
    if raw['plan_sha256'] != run['plan_sha256'] or ValidationPreparation.decode(raw) != run:
        raise CourseCatalogError('The original validation execution cannot be preserved exactly')
    return raw


class ValidationReviewRepository(LearnerDecisionRepository):
    @staticmethod
    def decode(raw):
        saved = LearnerDecisionRepository.decode(raw)
        try:
            body = ValidationReviewRequest.model_validate(saved['submission'])
            run = ValidationPreparation.decode(saved['execution'])
            if (saved['record_kind'] != 'validation_result_review' or saved['module_id'] != 'validation_qa'
                    or saved['prompt_id'] != PROMPT_ID or saved['uuid'] != body.request_id
                    or saved['run_id'] != body.run_id or run['run_id'] != body.run_id or run['state'] != 'completed' or run['plan']['phase'] != 'retest'
                    or encode(run['result'])[1] != body.result_sha256
                    or saved['case'] != run['plan']['input_snapshot']['case'] or body.case_sha256 != saved['case']['case_sha256']
                    or saved['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or any(saved[key] != run['plan'][key] for key in
                           ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or saved['submission_channel'] != 'authenticated_learner_validation_review_request'
                    or saved['credit_awarded'] is not False or saved['module_completion_eligible'] is not False):
                raise ValueError('The saved validation review differs from its exact execution or learner decisions')
            return saved
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The saved validation result review failed integrity verification') from exc

    async def get(self, user_id, submission_id):
        raw = await self.records.find_one({'uuid': submission_id, 'user_id': user_id, 'module_id': 'validation_qa', 'prompt_id': PROMPT_ID})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        body = ValidationReviewRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Validation result review requires the authenticated learner')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'validation_qa', 'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256, 'run_id': body.run_id, 'prompt_id': PROMPT_ID}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            if any(raw.get(key) != value for key, value in identity.items()) or raw.get('request_sha256') != request_hash:
                raise EnrollmentConflict('This review reference belongs to different answers or another learner')
            return self.decode(raw)

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        case = load_validation_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('Review the exact assigned validation case')
        previous = None
        if body.previous_submission_id:
            previous = await self.get(actor_user_id, body.previous_submission_id)
            if (previous is None or any(previous[key] != identity[key] for key in
                    ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or previous['case'] != case.public_definition()):
                raise EnrollmentConflict('A revision must preserve an owned original validation review in this course')
        run = (ValidationPreparation.decode(previous['execution'])
               if previous is not None and previous['run_id'] == body.run_id
               else await ValidationPreparation().get(actor_user_id, body.run_id))
        if run is None or run['state'] != 'completed' or run['plan']['phase'] != 'retest':
            raise EnrollmentConflict('Select a completed owned validation execution; incomplete work is not a completed result')
        LabExecutionRepository.check_operation(operation, run['plan'])
        if encode(run['result'])[1] != body.result_sha256 or run['plan']['input_snapshot']['case'] != case.public_definition():
            raise EnrollmentConflict('Inspect the exact saved validation result and case before reviewing it')
        saved = {**identity, 'record_kind': 'validation_result_review', 'request_sha256': request_hash,
                 'submission': request, 'case': case.public_definition(), 'execution': embedded_execution(run),
                 'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'submission_channel': 'authenticated_learner_validation_review_request',
                 'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > MAX_REVIEW_BYTES:
            raise EnrollmentConflict('The complete validation review exceeds its storage validation; no evidence was truncated')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The validation review reference was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return saved
