"""Save authenticated comparisons of two exact owned executions, without grading."""
import datetime
from types import SimpleNamespace
from typing import Annotated, Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .catalog import CourseCatalogError
from .connected_workflow_checks import compare_connected_runs
from .connected_workflow_preparation import ConnectedWorkflowPreparation
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository
from .multi_step_case import load_multi_step_case
from .outcomes import ContractModel

MAX_REVIEW_BYTES = 8 * 1024 * 1024
PROMPT_ID = 'connected_run_comparison'
Answer = Annotated[str, Field(min_length=1, max_length=8000)]


class ConnectedReviewRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    original_run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    original_result_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    corrected_run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    corrected_result_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    answers: dict[str, Answer] = Field(min_length=2, max_length=2)
    previous_submission_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    consent: Literal['save_connected_workflow_result_review']

    @model_validator(mode='after')
    def complete_answers(self):
        if (set(self.answers) != {'connection_repair', 'source_review'} or any(not value.strip() for value in self.answers.values())
                or self.original_run_id == self.corrected_run_id):
            raise ValueError('Select distinct original/corrected runs and answer both result-review questions')
        return self


def embedded_execution(run):
    """Preserve the original verified execution, excluding database/worker internals."""
    plan = run['plan']
    raw = {key: plan[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version',
                                    'manifest_sha256', 'input_snapshot_id')}
    raw.update(state=run['state'], scope_decision_id=run['scope_decision_id'], scope_decision_sha256=run['scope_decision_sha256'])
    for value, prefix in ((plan, 'plan'), (run['authorization'], 'authorization'), (run['result'], 'result'), (run['stage_events'], 'stage_events')):
        raw[prefix + '_json'], raw[prefix + '_sha256'] = encode(value)
    raw['stage_event_count'] = len(run['stage_events'])
    if raw['plan_sha256'] != run['plan_sha256'] or ConnectedWorkflowPreparation.decode(raw) != run:
        raise CourseCatalogError('The original connected execution cannot be preserved exactly')
    return raw


class ConnectedReviewRepository(LearnerDecisionRepository):
    @staticmethod
    def decode(raw):
        record = LearnerDecisionRepository.decode(raw)
        try:
            body = ConnectedReviewRequest.model_validate(record['submission'])
            public = record['case']
            original = ConnectedWorkflowPreparation.decode(record['original_execution'])
            corrected = ConnectedWorkflowPreparation.decode(record['corrected_execution'])
            case = SimpleNamespace(digest=public['case_sha256'], source_filename=public['source_filename'],
                                   source_sha256=public['source_sha256'], public_definition=lambda: public)
            if (record['record_kind'] != 'connected_workflow_result_review' or record['module_id'] != 'multi_step'
                    or record['prompt_id'] != PROMPT_ID or record['run_id'] != body.corrected_run_id
                    or record['uuid'] != body.request_id or record['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or body.case_sha256 != case.digest or public['module_id'] != 'multi_step'
                    or 'review_guidance' in public or 'source_expectations' in public
                    or original['run_id'] != body.original_run_id or corrected['run_id'] != body.corrected_run_id
                    or encode(original['result'])[1] != body.original_result_sha256
                    or encode(corrected['result'])[1] != body.corrected_result_sha256
                    or any(record[key] != original['plan'][key] or record[key] != corrected['plan'][key]
                           for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or record['comparison'] != compare_connected_runs(case, original, corrected)
                    or record['submission_channel'] != 'authenticated_learner_connected_review_request'
                    or record['credit_awarded'] is not False or record['module_completion_eligible'] is not False):
                raise ValueError('The result review differs from its original case, executions or learner decisions')
            return record
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The saved connected-workflow result review failed integrity verification') from exc

    async def get(self, user_id, submission_id):
        raw = await self.records.find_one({'uuid': submission_id, 'user_id': user_id, 'module_id': 'multi_step', 'prompt_id': PROMPT_ID})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        body = ConnectedReviewRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can record this result comparison')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id,
                    'enrollment_id': operation.progress.enrollment_id, 'module_id': 'multi_step',
                    'course_version': operation.package.manifest.release_id, 'manifest_sha256': operation.package.manifest_sha256,
                    'run_id': body.corrected_run_id, 'prompt_id': PROMPT_ID}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            if any(raw.get(key) != value for key, value in identity.items()) or raw.get('request_sha256') != request_hash:
                raise EnrollmentConflict('This comparison reference already belongs to different work or another learner')
            return self.decode(raw)

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        case = load_multi_step_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('Review the original assigned case before recording the run comparison')
        previous = None
        if body.previous_submission_id:
            previous = await self.get(actor_user_id, body.previous_submission_id)
            if previous is None or any(previous[key] != identity[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256')):
                raise EnrollmentConflict('A revised comparison must preserve an owned original review in this course')
            if previous['case'] != case.public_definition():
                raise EnrollmentConflict('A revised review cannot silently replace the original assignment')
        runs = []
        for kind in ('original', 'corrected'):
            run_id = getattr(body, kind + '_run_id')
            if previous is not None and previous['submission'][kind + '_run_id'] == run_id:
                run = ConnectedWorkflowPreparation.decode(previous[kind + '_execution'])
            else:
                run = await ConnectedWorkflowPreparation().get(actor_user_id, run_id)
            if run is None or run['state'] != 'completed':
                raise EnrollmentConflict('Select two completed owned executions; partial or invented runs cannot substitute')
            LabExecutionRepository.check_operation(operation, run['plan'])
            if encode(run['result'])[1] != getattr(body, kind + '_result_sha256'):
                raise EnrollmentConflict('Inspect the exact saved results before recording the comparison')
            runs.append(run)
        try:
            comparison = compare_connected_runs(case, *runs)
        except CourseCatalogError as exc:
            raise EnrollmentConflict('Compare two owned revisions of the same workflow on the exact assigned source') from exc
        record = {**identity, 'request_sha256': request_hash, 'record_kind': 'connected_workflow_result_review',
                  'submission': request, 'case': case.public_definition(), 'comparison': comparison,
                  'original_execution': embedded_execution(runs[0]), 'corrected_execution': embedded_execution(runs[1]),
                  'submission_channel': 'authenticated_learner_connected_review_request',
                  'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(record)
        if len(serialized.encode()) > MAX_REVIEW_BYTES:
            raise EnrollmentConflict('The preserved comparison exceeds the review receipt size limit; no evidence was truncated')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The comparison reference was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return record
