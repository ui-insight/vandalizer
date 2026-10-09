"""Assess bounded recovery choices against the learner's actual stopped run.

The finite choices can be checked directly. Free text is preserved without a
quality claim; this practice never awards an outcome, XP or module completion.
"""
import datetime
from typing import Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .catalog import CourseCatalogError
from .connected_failure_practice import is_failure_practice, STOP_MARKER, stopped_stage_result
from .connected_workflow_preparation import ConnectedWorkflowPreparation
from .connected_workflow_reviews import embedded_execution
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository
from .multi_step_case import load_multi_step_case
from .outcomes import ContractModel

PROMPT_ID = 'own_stopped_run_recovery'
MAX_BYTES = 8 * 1024 * 1024
IDENTITY = ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256')


class ConnectedRecoveryDecisionRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    result_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    stage_events_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    failed_stage: Literal['extract', 'reason', 'format', 'unknown']
    preserve: Literal['keep_original_run_and_completed_outputs', 'replace_original_history', 'partial_is_complete']
    next_action: Literal['prepare_separate_bounded_run', 'resume_in_place', 'restart_all_writes', 'publish_partial']
    explanation: str = Field(min_length=40, max_length=8000)
    previous_submission_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    consent: Literal['save_my_actual_stopped_run_recovery_choices']

    @model_validator(mode='after')
    def nonblank_explanation(self):
        if len(self.explanation.strip()) < 40:
            raise ValueError('Explain the evidence you inspected and your recovery choice')
        return self


def recovery_checks(run, body):
    if (not is_failure_practice(run['plan']) or run['state'] != 'failed'
            or not run['result'] or run['result'].get('reason') != STOP_MARKER
            or len(run['stage_events']) != 4
            or run['stage_events'][1]['receipt']['status'] != 'completed'
            or run['stage_events'][-1]['receipt']['result'] != stopped_stage_result()):
        raise EnrollmentConflict('This exercise requires your confirmed controlled stop and preserved successful extraction; unknown or authored outcomes cannot substitute')
    checks = [
        {'id': 'first_failed_stage', 'supported': body.failed_stage == 'reason',
         'feedback': 'Reasoning was deliberately rejected before provider dispatch. Extraction completed; Formatter never started.'},
        {'id': 'preserve_successful_work', 'supported': body.preserve == 'keep_original_run_and_completed_outputs',
         'feedback': 'Keep the original run, successful extraction, failed-stage input and rejection. A partial chain is not a completed deliverable.'},
        {'id': 'bounded_recovery_route', 'supported': body.next_action == 'prepare_separate_bounded_run',
         'feedback': 'This screen supports a separate prepared and approved internal run, not in-place stage resume. Inspect its scope again. Repeating these internal computations never authorizes repeating external writes.'},
    ]
    return {'checks': checks, 'choices_supported': all(item['supported'] for item in checks),
            'explanation_quality_assessed': False, 'execution_authorized': False,
            'credit_awarded': False, 'module_completion_eligible': False,
            'successful_extraction_receipt_sha256': run['stage_events'][1]['receipt_sha256'],
            'failed_stage_start_sha256': run['stage_events'][2]['receipt_sha256'],
            'controlled_rejection_receipt_sha256': run['stage_events'][3]['receipt_sha256']}


class ConnectedRecoveryDecisionRepository(LearnerDecisionRepository):
    @staticmethod
    def decode(raw):
        record = LearnerDecisionRepository.decode(raw)
        try:
            body = ConnectedRecoveryDecisionRequest.model_validate(record['submission'])
            run = ConnectedWorkflowPreparation.decode(record['stopped_execution'])
            if (record['record_kind'] != 'connected_stopped_run_recovery_decision'
                    or record['module_id'] != 'multi_step' or record['prompt_id'] != PROMPT_ID
                    or record['uuid'] != body.request_id or record['run_id'] != body.run_id or run['run_id'] != body.run_id
                    or record['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or any(record[key] != run['plan'][key] for key in IDENTITY)
                    or record['case'] != run['plan']['input_snapshot']['case']
                    or body.case_sha256 != record['case']['case_sha256']
                    or body.result_sha256 != encode(run['result'])[1] or body.stage_events_sha256 != encode(run['stage_events'])[1]
                    or record['question'] != record['case']['controlled_failure_practice']['question']
                    or record['checks'] != recovery_checks(run, body)
                    or record['submission_channel'] != 'authenticated_learner_stopped_run_choices'
                    or datetime.datetime.fromisoformat(record['submitted_at']).tzinfo is None
                    or record['credit_awarded'] is not False or record['module_completion_eligible'] is not False):
                raise ValueError('Recovery choice identity, evidence or feedback changed')
            return record
        except (KeyError, TypeError, ValueError, EnrollmentConflict) as exc:
            raise CourseCatalogError('The saved stopped-run recovery choices failed integrity verification') from exc

    async def get(self, user_id, submission_id):
        raw = await self.records.find_one({'uuid': submission_id, 'user_id': user_id,
                                          'module_id': 'multi_step', 'prompt_id': PROMPT_ID})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        body = ConnectedRecoveryDecisionRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can record recovery choices')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'multi_step', 'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256, 'run_id': body.run_id, 'prompt_id': PROMPT_ID}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            if any(raw.get(key) != value for key, value in identity.items()) or raw['request_sha256'] != request_hash:
                raise EnrollmentConflict('This recovery reference already belongs to different work or answers')
            return self.decode(raw)

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        case = load_multi_step_case(operation.package)
        if not case.controlled_failure_practice or body.case_sha256 != case.digest:
            raise EnrollmentConflict('Use the original recovery assignment for this course')
        previous = None
        if body.previous_submission_id:
            previous = await self.get(actor_user_id, body.previous_submission_id)
            if previous is None or any(previous[key] != identity[key] for key in (*IDENTITY, 'run_id')):
                raise EnrollmentConflict('A revised recovery answer must preserve this owned original stopped run')
        run = (ConnectedWorkflowPreparation.decode(previous['stopped_execution']) if previous
               else await ConnectedWorkflowPreparation().get(actor_user_id, body.run_id))
        if run is None:
            raise EnrollmentConflict('Inspect your owned stopped run before recording recovery choices')
        LabExecutionRepository.check_operation(operation, run['plan'])
        if (run['plan']['input_snapshot']['case'] != case.public_definition()
                or body.result_sha256 != encode(run['result'])[1] or body.stage_events_sha256 != encode(run['stage_events'])[1]):
            raise EnrollmentConflict('Inspect the exact original result and stage evidence before choosing recovery')
        record = {**identity, 'record_kind': 'connected_stopped_run_recovery_decision', 'request_sha256': request_hash,
                  'submission': request, 'case': case.public_definition(), 'question': case.controlled_failure_practice.question,
                  'stopped_execution': embedded_execution(run), 'checks': recovery_checks(run, body),
                  'submission_channel': 'authenticated_learner_stopped_run_choices',
                  'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(record)
        if len(serialized.encode()) > MAX_BYTES:
            raise EnrollmentConflict('The complete recovery evidence exceeds the saved-record limit; nothing was truncated')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            raw = await self.records.find_one({'uuid': body.request_id})
            if raw is None:
                raise EnrollmentConflict('This recovery request was claimed by another operation')
            return replay(raw)
        await LabInputRepository._check_lease(lease)
        return record
