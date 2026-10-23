"""Preserve authenticated design decisions; no model, execution or credit here."""
import datetime
import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationProcessSubmission
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel
from .process_case import load_process_case

Answer = Annotated[str, Field(min_length=1, max_length=12000)]


class ProcessSubmission(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    answers: dict[str, Answer] = Field(min_length=3, max_length=3)
    consent: Literal['save_reviewed_process_design']
    previous_submission_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

    @model_validator(mode='after')
    def nonblank_submission(self):
        if any(not answer.strip() for answer in self.answers.values()):
            raise ValueError('Provide each requested decision and map before saving')
        # This only validates a usable submission, never its correctness.
        return self


class ProcessSubmissionRepository:
    @property
    def records(self):
        return CertificationProcessSubmission.get_motor_collection()

    @staticmethod
    def decode(raw):
        try:
            if hashlib.sha256(raw['record_json'].encode()).hexdigest() != raw['record_sha256']:
                raise ValueError('Digest mismatch')
            record = json.loads(raw['record_json'])
            if any(record[key] != raw[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id',
                    'course_version', 'manifest_sha256', 'request_sha256')):
                raise ValueError('Identity mismatch')
            submission = ProcessSubmission.model_validate(record['submission'])
            if (submission.request_id != record['uuid'] or submission.case_sha256 != record['case']['case_sha256']
                    or record['submission_channel'] != 'authenticated_learner_process_request'
                    or record['credit_awarded'] is not False or record['module_completion_eligible'] is not False
                    or record['module_id'] != 'process_mapping'
                    or record['case']['module_id'] != record['module_id']
                    or record['case']['provenance'] != 'authored_fictional_design_case_not_execution'
                    or 'review_guidance' in record['case']
                    or set(submission.answers) != {question['id'] for question in record['case']['questions']}):
                raise ValueError('Submission binding mismatch')
            identity = {key: record[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256')}
            if encode({**identity, 'submission': submission.model_dump(mode='json')})[1] != record['request_sha256']:
                raise ValueError('Request binding mismatch')
            return record
        except (ValueError, TypeError, KeyError) as exc:
            raise CourseCatalogError('The saved process design failed integrity verification') from exc

    async def get(self, user_id, submission_id):
        raw = await self.records.find_one({'user_id': user_id, 'uuid': submission_id})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        submission = ProcessSubmission.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Process design requires the authenticated learner')
        identity = {'uuid': submission.request_id, 'user_id': actor_user_id,
                    'enrollment_id': operation.progress.enrollment_id, 'module_id': 'process_mapping',
                    'course_version': operation.package.manifest.release_id, 'manifest_sha256': operation.package.manifest_sha256}
        lease = LabExecutionRepository.check_operation(operation, identity)
        case = load_process_case(operation.package)
        if submission.case_sha256 != case.digest or set(submission.answers) != {question.id for question in case.questions}:
            raise EnrollmentConflict('The design must answer the original case; reload its current requirements before saving')
        request_sha256 = encode({**identity, 'submission': submission.model_dump(mode='json')})[1]
        existing = await self.records.find_one({'uuid': submission.request_id})
        if existing:
            if any(existing.get(key) != value for key, value in identity.items()) or existing.get('request_sha256') != request_sha256:
                raise EnrollmentConflict('This request already belongs to different work or another learner')
            return self.decode(existing)
        if submission.previous_submission_id:
            previous = await self.get(actor_user_id, submission.previous_submission_id)
            if previous is None or any(previous[key] != identity[key] for key in identity if key != 'uuid'):
                raise EnrollmentConflict('A revision must preserve an owned original design in this course')
            if previous['case'] != case.public_definition():
                raise EnrollmentConflict('A revision cannot silently replace the original case')
        await LabInputRepository._check_lease(lease)
        record = {**identity, 'request_sha256': request_sha256,
                  'submission': submission.model_dump(mode='json'), 'case': case.public_definition(),
                  'submission_channel': 'authenticated_learner_process_request',
                  'submitted_at': datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
                  'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(record)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_sha256,
                                           'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            saved = await self.records.find_one({'uuid': submission.request_id})
            if saved is None or saved.get('request_sha256') != request_sha256:
                raise EnrollmentConflict('This process-design request identity was already claimed')
            record = self.decode(saved)
        await LabInputRepository._check_lease(lease)
        return record
