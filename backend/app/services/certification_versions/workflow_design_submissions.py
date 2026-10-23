"""Learner approval of an exact captured design, never execution authority."""
import datetime
import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationWorkflowDesignSubmission
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository, MAX_SNAPSHOT_BYTES
from .outcomes import ContractModel
from .process_submissions import Answer
from .workflow_design_case import load_workflow_design_case
from .workflow_design_inputs import WorkflowDesignInputRepository


class WorkflowDesignSubmission(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    input_snapshot_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    input_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    answers: dict[str, Answer] = Field(min_length=3, max_length=3)
    consent: Literal['approve_saved_workflow_design_for_assessment']
    previous_submission_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

    @model_validator(mode='after')
    def require_decisions(self):
        if set(self.answers) != {'data_flow', 'approval_boundary', 'reviewable_design'} or any(not v.strip() for v in self.answers.values()):
            raise ValueError('Provide all three decisions about the saved workflow revision')
        return self


class WorkflowDesignSubmissionRepository:
    @property
    def records(self):
        return CertificationWorkflowDesignSubmission.get_motor_collection()

    @staticmethod
    def decode(raw):
        try:
            if hashlib.sha256(raw['record_json'].encode()).hexdigest() != raw['record_sha256']:
                raise ValueError('Digest mismatch')
            saved = json.loads(raw['record_json'])
            keys = ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256')
            if any(saved[key] != raw[key] for key in (*keys, 'request_sha256')):
                raise ValueError('Identity mismatch')
            body = WorkflowDesignSubmission.model_validate(saved['submission'])
            snapshot = saved['input_snapshot']
            serialized, digest = encode(snapshot)
            WorkflowDesignInputRepository.decode({**snapshot, 'record_json': serialized, 'record_sha256': digest})
            if (saved['module_id'] != 'workflow_design' or body.request_id != saved['uuid']
                    or snapshot['uuid'] != body.input_snapshot_id or digest != body.input_snapshot_sha256
                    or any(snapshot[key] != saved[key] for key in keys if key != 'uuid')
                    or snapshot['case']['case_sha256'] != body.case_sha256
                    or saved['submission_channel'] != 'authenticated_learner_workflow_design_request'
                    or saved['credit_awarded'] is not False or saved['module_completion_eligible'] is not False
                    or saved['execution_authorized'] is not False
                    or encode({**{key: saved[key] for key in keys}, 'submission': body.model_dump(mode='json')})[1] != saved['request_sha256']):
                raise ValueError('Saved approval does not bind the original design')
            return saved
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The saved workflow approval failed integrity verification') from exc

    async def get(self, user_id, submission_id):
        raw = await self.records.find_one({'uuid': submission_id, 'user_id': user_id})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        body = WorkflowDesignSubmission.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Workflow Design approval requires the authenticated learner')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'workflow_design', 'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256}
        lease = LabExecutionRepository.check_operation(operation, identity)
        case = load_workflow_design_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('Approve the original assigned design case')
        request_hash = encode({**identity, 'submission': body.model_dump(mode='json')})[1]

        def replay(raw):
            if any(raw.get(key) != value for key, value in identity.items()) or raw.get('request_sha256') != request_hash:
                raise EnrollmentConflict('This approval reference already belongs to different work')
            return self.decode(raw)

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        snapshot = await WorkflowDesignInputRepository().get(actor_user_id, body.input_snapshot_id)
        if (snapshot is None or any(snapshot[key] != identity[key] for key in identity if key != 'uuid')
                or encode(snapshot)[1] != body.input_snapshot_sha256 or snapshot['case'] != case.public_definition()):
            raise EnrollmentConflict('Inspect the exact owned captured workflow revision before approving it')
        if body.previous_submission_id:
            previous = await self.get(actor_user_id, body.previous_submission_id)
            if (previous is None or any(previous[key] != identity[key] for key in identity if key != 'uuid')
                    or previous['submission']['case_sha256'] != body.case_sha256):
                raise EnrollmentConflict('A revision must preserve an owned original approval from this course and case')
        saved = {**identity, 'request_sha256': request_hash, 'submission': body.model_dump(mode='json'),
                 'input_snapshot': snapshot, 'submission_channel': 'authenticated_learner_workflow_design_request',
                 'submitted_at': datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
                 'credit_awarded': False, 'module_completion_eligible': False, 'execution_authorized': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > MAX_SNAPSHOT_BYTES:
            raise EnrollmentConflict('The saved approval exceeds the immutable evidence limit; nothing was truncated')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The original approval could not be recovered')
            saved = replay(existing)
        await LabInputRepository._check_lease(lease)
        return saved
