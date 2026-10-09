"""Preserve the learner's delivery interpretation alongside the exact file review."""
from copy import deepcopy
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
from .output_file_reviews import OutputFileReviewRepository
from .output_private_handoff import OutputPrivateHandoffRepository, release_authorization
from .output_workflow_preparation import OutputWorkflowPreparation

PROMPT_ID = 'output_delivery_result_review'
MAX_REVIEW_BYTES = 15 * 1024 * 1024
Identity = Annotated[str, Field(pattern=r'^[a-f0-9]{32}$')]
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


class OutputOutcomeReviewRequest(ContractModel):
    request_id: Identity
    file_review_id: Identity
    file_review_sha256: Digest
    handoff_id: Identity
    handoff_sha256: Digest
    case_sha256: Digest
    delivery_review: str = Field(min_length=10, max_length=8000)
    previous_submission_id: Identity | None = None
    consent: Literal['save_output_delivery_interpretation']

    @model_validator(mode='after')
    def actual_answer(self):
        if len(self.delivery_review.strip()) < 10 or self.previous_submission_id == self.request_id:
            raise ValueError('Explain the actual delivery result; a revision needs a new request identity')
        return self


def compact_handoff(handoff):
    value = deepcopy(handoff)
    artifacts = value.pop('destination_copy')
    value['destination_copy_sha256'] = encode(artifacts)[1] if artifacts is not None else None
    return value


def restore_handoff(value, artifacts):
    value = deepcopy(value)
    reference = value.pop('destination_copy_sha256')
    if reference is not None and reference != encode(artifacts)[1]:
        raise CourseCatalogError('The private copy differs from the preserved generation')
    value['destination_copy'] = deepcopy(artifacts) if reference is not None else None
    serialized, digest = encode(value)
    return OutputPrivateHandoffRepository.decode({**value, 'record_json': serialized, 'record_sha256': digest})


def embedded_review(review):
    serialized, digest = encode(review)
    return {**{key: review[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version',
        'manifest_sha256', 'request_sha256', 'run_id', 'prompt_id')}, 'record_json': serialized, 'record_sha256': digest}


class OutputOutcomeReviewRepository(LearnerDecisionRepository):
    @staticmethod
    def decode(raw):
        saved = LearnerDecisionRepository.decode(raw)
        try:
            body = OutputOutcomeReviewRequest.model_validate(saved['submission'])
            review = OutputFileReviewRepository.decode(saved['file_review'])
            run = OutputWorkflowPreparation.decode(review['execution'])
            handoff = restore_handoff(saved['handoff'], run['result']['generated_artifacts'])
            if (saved['record_kind'] != PROMPT_ID or saved['prompt_id'] != PROMPT_ID or saved['module_id'] != 'output_delivery'
                    or saved['uuid'] != body.request_id or saved['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or saved['case'] != review['case'] or body.case_sha256 != review['case']['case_sha256']
                    or body.file_review_id != review['uuid'] or body.file_review_sha256 != encode(review)[1]
                    or body.handoff_id != handoff['uuid'] or body.handoff_sha256 != encode(handoff)[1]
                    or handoff['submission']['review_id'] != review['uuid']
                    or handoff['submission']['review_sha256'] != encode(review)[1]
                    or handoff['release_authorization'] != release_authorization(review)
                    or any(saved[key] != review[key] or saved[key] != handoff[key] for key in
                           ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'run_id'))
                    or saved['submission_channel'] != 'authenticated_learner_output_outcome_review_request'
                    or saved['credit_awarded'] is not False or saved['module_completion_eligible'] is not False):
                raise ValueError('The delivery interpretation changed its original files, authorization or receipt')
            return saved
        except (KeyError, TypeError, ValueError, EnrollmentConflict) as exc:
            raise CourseCatalogError('The saved output outcome review failed integrity verification') from exc

    async def get(self, user_id, submission_id):
        raw = await self.records.find_one({'uuid': submission_id, 'user_id': user_id, 'module_id': 'output_delivery', 'prompt_id': PROMPT_ID})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        body = OutputOutcomeReviewRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Output interpretation requires the authenticated learner')
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            saved = self.decode(existing)
            LabExecutionRepository.check_operation(operation, saved)
            if saved['request_sha256'] != request_hash:
                raise EnrollmentConflict('This review request already preserves different answers')
            return saved
        previous = await self.get(actor_user_id, body.previous_submission_id) if body.previous_submission_id else None
        if body.previous_submission_id and previous is None:
            raise EnrollmentConflict('A revision must preserve an owned original review in this course')
        if previous is not None:
            LabExecutionRepository.check_operation(operation, previous)
        review = (OutputFileReviewRepository.decode(previous['file_review'])
                  if previous and previous['submission']['file_review_id'] == body.file_review_id
                  else await OutputFileReviewRepository().get(actor_user_id, body.file_review_id))
        handoff = (restore_handoff(previous['handoff'], OutputWorkflowPreparation.decode(review['execution'])['result']['generated_artifacts'])
                   if previous and review and previous['submission']['handoff_id'] == body.handoff_id
                   else await OutputPrivateHandoffRepository().get(actor_user_id, body.handoff_id))
        if review is None or handoff is None:
            raise EnrollmentConflict('Select the exact saved file inspection and actual handoff receipt')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
            'module_id': 'output_delivery', 'course_version': operation.package.manifest.release_id,
            'manifest_sha256': operation.package.manifest_sha256, 'run_id': review['run_id'], 'prompt_id': PROMPT_ID}
        lease = LabExecutionRepository.check_operation(operation, identity)
        LabExecutionRepository.check_operation(operation, review)
        LabExecutionRepository.check_operation(operation, handoff)
        case = load_output_case(operation.package)
        if (body.case_sha256 != case.digest or review['case'] != case.public_definition()
                or encode(review)[1] != body.file_review_sha256 or encode(handoff)[1] != body.handoff_sha256
                or handoff['submission']['review_id'] != body.file_review_id
                or handoff['submission']['review_sha256'] != body.file_review_sha256
                or handoff['release_authorization'] != release_authorization(review)):
            raise EnrollmentConflict('Inspect the exact files and their actual authorized handoff before reviewing the outcome')
        if body.previous_submission_id:
            if (previous is None or previous['case'] != case.public_definition()
                    or any(previous[key] != identity[key] for key in
                           ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))):
                raise EnrollmentConflict('A revision must preserve an owned original review in this course')
        saved = {**identity, 'record_kind': PROMPT_ID, 'request_sha256': request_hash, 'submission': request,
            'case': case.public_definition(), 'file_review': embedded_review(review), 'handoff': compact_handoff(handoff),
            'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'submission_channel': 'authenticated_learner_output_outcome_review_request',
            'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > MAX_REVIEW_BYTES:
            raise EnrollmentConflict('The complete output review exceeds its storage limit; evidence was not truncated')
        self.decode({**saved, 'record_json': serialized, 'record_sha256': digest})
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None or existing.get('request_sha256') != request_hash:
                raise EnrollmentConflict('The outcome review request was claimed by another operation')
            return self.decode(existing)
        return saved
