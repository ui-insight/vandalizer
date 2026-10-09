"""Save learner inspection and exact private-release choices before any handoff.

Opening acknowledgements and explanations are evidence to assess, never proof
of source correctness or an automatic passing grade.
"""
import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository
from .outcomes import ContractModel
from .output_case import load_output_case
from .output_workflow_preparation import OutputWorkflowPreparation

MAX_REVIEW_BYTES = 14 * 1024 * 1024
PROMPT_ID = 'output_file_inspection_and_release'
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
Answer = Annotated[str, Field(min_length=10, max_length=8000)]


class FileInspection(ContractModel):
    sha256: Digest
    opened: bool = Field(strict=True)
    judgment: Literal['usable', 'needs_repair', 'unresolved']
    observations: Answer


class OutputFileReviewRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    result_sha256: Digest
    case_sha256: Digest
    artifacts_sha256: Digest
    file_inspections: tuple[FileInspection, ...] = Field(min_length=1, max_length=8)
    bundle_sha256: Digest
    bundle_opened: bool = Field(strict=True)
    answers: dict[str, Answer] = Field(min_length=2, max_length=2)
    choice: Literal['approve', 'hold']
    destination_id: Literal['private_training_inbox']
    audience: Literal['enrolled_learner_only']
    data_scope: Literal['approved_generated_files_only']
    consent: Literal['save_exact_output_inspection_and_release_choice']

    @model_validator(mode='after')
    def complete_inspection(self):
        if (set(self.answers) != {'artifact_review', 'release_decision'}
                or any(len(value.strip()) < 10 for value in self.answers.values())
                or any(len(item.observations.strip()) < 10 for item in self.file_inspections)
                or len({item.sha256 for item in self.file_inspections}) != len(self.file_inspections)):
            raise ValueError('Inspect each distinct file and explain both artifact and release decisions')
        if self.choice == 'approve' and (not self.bundle_opened
                or any(not item.opened or item.judgment != 'usable' for item in self.file_inspections)):
            raise ValueError('Hold release until every file and bundle is opened and reviewed as usable')
        return self


def embedded_execution(run):
    plan = run['plan']
    raw = {key: plan[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version',
                                    'manifest_sha256', 'input_snapshot_id')}
    raw.update(state=run['state'], scope_decision_id=run['scope_decision_id'], scope_decision_sha256=run['scope_decision_sha256'])
    for value, prefix in ((plan, 'plan'), (run['authorization'], 'authorization'), (run['result'], 'result'), (run['stage_events'], 'stage_events')):
        raw[prefix + '_json'], raw[prefix + '_sha256'] = encode(value)
    raw['stage_event_count'] = len(run['stage_events'])
    if raw['plan_sha256'] != run['plan_sha256'] or OutputWorkflowPreparation.decode(raw) != run:
        raise CourseCatalogError('The original output generation cannot be preserved exactly')
    return raw


def validate_inspection(body, run):
    artifacts = run['result']['generated_artifacts']
    case = run['plan']['input_snapshot']['case']
    if (run['state'] != 'completed' or body.result_sha256 != encode(run['result'])[1]
            or body.case_sha256 != case['case_sha256'] or body.artifacts_sha256 != encode(artifacts)[1]
            or body.bundle_sha256 != artifacts['download']['sha256']
            or {item.sha256 for item in body.file_inspections} != {item['sha256'] for item in artifacts['files']}
            or any(getattr(body, key) != case['destination'][field] for key, field in
                   (('destination_id', 'id'), ('audience', 'audience'), ('data_scope', 'data_scope')))):
        raise EnrollmentConflict('Inspection must bind every original file, bundle and private destination in this exact run')
    if body.choice == 'approve' and not artifacts['all_required_files_parseable']:
        raise EnrollmentConflict('Repair the invalid or incomplete generated files before approving release')


class OutputFileReviewRepository(LearnerDecisionRepository):
    @staticmethod
    def decode(raw):
        saved = LearnerDecisionRepository.decode(raw)
        try:
            body = OutputFileReviewRequest.model_validate(saved['submission'])
            run = OutputWorkflowPreparation.decode(saved['execution'])
            validate_inspection(body, run)
            if (saved['record_kind'] != PROMPT_ID or saved['module_id'] != 'output_delivery'
                    or saved['prompt_id'] != PROMPT_ID or saved['uuid'] != body.request_id
                    or saved['run_id'] != body.run_id or run['run_id'] != body.run_id
                    or saved['case'] != run['plan']['input_snapshot']['case']
                    or saved['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or any(saved[key] != run['plan'][key] for key in
                           ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or saved['submission_channel'] != 'authenticated_learner_output_inspection_request'
                    or saved['credit_awarded'] is not False or saved['module_completion_eligible'] is not False
                    or saved['delivery_confirmed'] is not False):
                raise ValueError('The saved inspection changed its learner, exact files or authority')
            return saved
        except (KeyError, TypeError, ValueError, EnrollmentConflict) as exc:
            raise CourseCatalogError('The saved output inspection failed integrity verification') from exc

    async def get(self, user_id, submission_id):
        raw = await self.records.find_one({'uuid': submission_id, 'user_id': user_id, 'module_id': 'output_delivery', 'prompt_id': PROMPT_ID})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        body = OutputFileReviewRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Output inspection requires the authenticated learner')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'output_delivery', 'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256, 'run_id': body.run_id, 'prompt_id': PROMPT_ID}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        async def replay(raw):
            if any(raw.get(key) != value for key, value in identity.items()) or raw.get('request_sha256') != request_hash:
                raise EnrollmentConflict('This inspection reference belongs to different answers or another learner')
            saved = self.decode(raw)
            await self._link(operation, saved, replay=True)
            return saved

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return await replay(existing)
        case = load_output_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('Inspect the exact assigned output case')
        run = await OutputWorkflowPreparation().get(actor_user_id, body.run_id)
        if run is None or run['state'] != 'completed':
            raise EnrollmentConflict('Select completed owned generation before reviewing its files')
        LabExecutionRepository.check_operation(operation, run['plan'])
        if run['plan']['input_snapshot']['case'] != case.public_definition():
            raise EnrollmentConflict('The generated files belong to another assignment')
        validate_inspection(body, run)
        raw_run = await LabExecutionRepository().records.find_one({'uuid': body.run_id, 'user_id': actor_user_id})
        if raw_run.get('output_handoff_claimed') is True:
            raise EnrollmentConflict('This release has already been claimed; preserve its original inspection and receipt')
        saved = {**identity, 'record_kind': PROMPT_ID, 'request_sha256': request_hash,
                 'submission': request, 'case': case.public_definition(), 'execution': embedded_execution(run),
                 'previous_release_decision_id': raw_run.get('release_decision_id'),
                 'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'submission_channel': 'authenticated_learner_output_inspection_request',
                 'credit_awarded': False, 'module_completion_eligible': False, 'delivery_confirmed': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > MAX_REVIEW_BYTES:
            raise EnrollmentConflict('The full output inspection exceeds its storage limit; no evidence was truncated')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The inspection reference was claimed by another operation')
            return await replay(existing)
        await self._link(operation, saved, replay=False)
        return saved

    async def _link(self, operation, saved, *, replay):
        lease = LabExecutionRepository.check_operation(operation, saved)
        records = LabExecutionRepository().records
        current = await records.find_one({'uuid': saved['run_id'], 'user_id': operation.user_id})
        if current is None:
            if replay:
                return  # Original inspection remains readable after run deletion.
            raise EnrollmentConflict('The inspected run is unavailable')
        if current.get('release_decision_id') == saved['uuid']:
            return
        if current.get('release_decision_id') != saved['previous_release_decision_id']:
            if replay:
                return
            raise EnrollmentConflict('A newer release decision was saved; inspect the current choice')
        await LabInputRepository._check_lease(lease)
        result = await records.update_one({'uuid': saved['run_id'], 'user_id': operation.user_id,
            'state': 'completed', 'result_sha256': saved['submission']['result_sha256'],
            'release_decision_id': saved['previous_release_decision_id'], 'output_handoff_claimed': {'$ne': True}},
            {'$set': {'release_decision_id': saved['uuid'], 'release_decision_sha256': encode(saved)[1]}})
        if result.modified_count != 1:
            raise EnrollmentConflict('The release changed or was claimed before this choice could be linked')
