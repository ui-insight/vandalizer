"""Preserve authenticated budget interpretations with the actual completed run."""
import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .advanced_case import load_advanced_case
from .advanced_workflow_preparation import AdvancedWorkflowPreparation
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository
from .outcomes import ContractModel

MAX_REVIEW_BYTES = 8 * 1024 * 1024
PROMPT_ID = 'budget_result_review'
Answer = Annotated[str, Field(min_length=1, max_length=8000)]


class AdvancedReviewRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    result_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    answers: dict[str, Answer] = Field(min_length=2, max_length=2)
    previous_submission_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    consent: Literal['save_budget_calculation_and_dependency_review']

    @model_validator(mode='after')
    def complete_answers(self):
        if (set(self.answers) != {'calculation_review', 'dependency_review'}
                or any(not value.strip() for value in self.answers.values()) or self.previous_submission_id == self.request_id):
            raise ValueError('Answer both actual-result questions; revised answers require a new request identity')
        return self


def embedded_execution(run):
    plan = run['plan']
    raw = {key: plan[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version',
                                    'manifest_sha256', 'input_snapshot_id')}
    raw.update(state=run['state'], scope_decision_id=run['scope_decision_id'], scope_decision_sha256=run['scope_decision_sha256'])
    for value, prefix in ((plan, 'plan'), (run['authorization'], 'authorization'), (run['result'], 'result'), (run['task_events'], 'task_events')):
        raw[prefix + '_json'], raw[prefix + '_sha256'] = encode(value)
    raw['task_event_count'] = len(run['task_events'])
    if raw['plan_sha256'] != run['plan_sha256'] or AdvancedWorkflowPreparation.decode(raw) != run:
        raise CourseCatalogError('The original budget execution cannot be preserved exactly')
    return raw


class AdvancedReviewRepository(LearnerDecisionRepository):
    @staticmethod
    def decode(raw):
        saved = LearnerDecisionRepository.decode(raw)
        try:
            body = AdvancedReviewRequest.model_validate(saved['submission'])
            run = AdvancedWorkflowPreparation.decode(saved['execution'])
            if (saved['record_kind'] != 'budget_result_review' or saved['module_id'] != 'advanced_nodes'
                    or saved['prompt_id'] != PROMPT_ID or saved['uuid'] != body.request_id
                    or saved['run_id'] != body.run_id or run['run_id'] != body.run_id or run['state'] != 'completed'
                    or encode(run['result'])[1] != body.result_sha256
                    or saved['case'] != run['plan']['input_snapshot']['case'] or body.case_sha256 != saved['case']['case_sha256']
                    or saved['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or any(saved[key] != run['plan'][key] for key in
                           ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or saved['submission_channel'] != 'authenticated_learner_budget_review_request'
                    or saved['credit_awarded'] is not False or saved['module_completion_eligible'] is not False):
                raise ValueError('The saved budget review differs from its exact execution or learner decisions')
            return saved
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The saved budget result review failed integrity verification') from exc

    async def get(self, user_id, submission_id):
        raw = await self.records.find_one({'uuid': submission_id, 'user_id': user_id, 'module_id': 'advanced_nodes', 'prompt_id': PROMPT_ID})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        body = AdvancedReviewRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Budget result review requires the authenticated learner')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'advanced_nodes', 'course_version': operation.package.manifest.release_id,
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
        case = load_advanced_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('Review the exact assigned budget case')
        previous = None
        if body.previous_submission_id:
            previous = await self.get(actor_user_id, body.previous_submission_id)
            if (previous is None or any(previous[key] != identity[key] for key in
                    ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or previous['case'] != case.public_definition()):
                raise EnrollmentConflict('A revision must preserve an owned original budget review in this course')
        run = (AdvancedWorkflowPreparation.decode(previous['execution'])
               if previous is not None and previous['run_id'] == body.run_id
               else await AdvancedWorkflowPreparation().get(actor_user_id, body.run_id))
        if run is None or run['state'] != 'completed':
            raise EnrollmentConflict('Select a completed owned budget execution; incomplete work is not a completed result')
        LabExecutionRepository.check_operation(operation, run['plan'])
        if encode(run['result'])[1] != body.result_sha256 or run['plan']['input_snapshot']['case'] != case.public_definition():
            raise EnrollmentConflict('Inspect the exact saved budget result and case before reviewing it')
        saved = {**identity, 'record_kind': 'budget_result_review', 'request_sha256': request_hash,
                 'submission': request, 'case': case.public_definition(), 'execution': embedded_execution(run),
                 'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'submission_channel': 'authenticated_learner_budget_review_request',
                 'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > MAX_REVIEW_BYTES:
            raise EnrollmentConflict('The complete budget review exceeds its storage budget; no evidence was truncated')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The budget review reference was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return saved
