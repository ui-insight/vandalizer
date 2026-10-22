"""Contained learner-only handoff rehearsal with an atomic destination receipt.

The first authorized attempt deliberately rejects before writing destination
bytes. Explicit retry copies only the reviewed files into this private record.
The copy and success receipt are one MongoDB insert, so a lost reply is resolved
by reading the original request, never repeating generation or an external send.
"""
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
from .output_artifacts import verify_generated_artifacts
from .output_file_reviews import OutputFileReviewRepository, OutputFileReviewRequest
from .output_workflow_preparation import OutputWorkflowPreparation

PROMPT_ID = 'output_private_training_handoff'
MAX_HANDOFF_BYTES = 7 * 1024 * 1024
Identity = Annotated[str, Field(pattern=r'^[a-f0-9]{32}$')]
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


class OutputHandoffRequest(ContractModel):
    request_id: Identity
    run_id: Identity
    result_sha256: Digest
    review_id: Identity
    review_sha256: Digest
    artifacts_sha256: Digest
    destination_id: Literal['private_training_inbox']
    action: Literal['attempt', 'retry_failed_handoff']
    previous_failed_id: Identity | None = None
    previous_failed_sha256: Digest | None = None
    consent: Literal['attempt_approved_private_training_handoff', 'retry_only_failed_private_training_handoff']

    @model_validator(mode='after')
    def explicit_action(self):
        if self.action == 'attempt':
            if (self.previous_failed_id is not None or self.previous_failed_sha256 is not None
                    or self.consent != 'attempt_approved_private_training_handoff'):
                raise ValueError('The first training attempt cannot claim a previous failure')
        elif (self.previous_failed_id is None or self.previous_failed_sha256 is None
                or self.previous_failed_id == self.request_id
                or self.consent != 'retry_only_failed_private_training_handoff'):
            raise ValueError('Explicit retry requires the exact original failed receipt')
        return self


def release_authorization(review):
    return {key: deepcopy(review[key]) for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version',
        'manifest_sha256', 'run_id', 'submission', 'submitted_at', 'submission_channel')}


class OutputPrivateHandoffRepository(LearnerDecisionRepository):
    @staticmethod
    def decode(raw):
        saved = LearnerDecisionRepository.decode(raw)
        try:
            body = OutputHandoffRequest.model_validate(saved['submission'])
            authorization = saved['release_authorization']
            review = OutputFileReviewRequest.model_validate(authorization['submission'])
            if (saved['record_kind'] != PROMPT_ID or saved['prompt_id'] != PROMPT_ID or saved['module_id'] != 'output_delivery'
                    or saved['uuid'] != body.request_id or saved['run_id'] != body.run_id
                    or saved['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or any(authorization[key] != saved[key] for key in
                           ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'run_id'))
                    or authorization['uuid'] != body.review_id or review.request_id != body.review_id
                    or review.run_id != body.run_id or review.result_sha256 != body.result_sha256
                    or review.artifacts_sha256 != body.artifacts_sha256 or review.choice != 'approve'
                    or authorization['submission_channel'] != 'authenticated_learner_output_inspection_request'
                    or saved['destination'] != {'id': 'private_training_inbox', 'audience': 'enrolled_learner_only',
                        'data_scope': 'approved_generated_files_only', 'owner_user_id': saved['user_id']}
                    or saved['external_delivery'] is not False or saved['credit_awarded'] is not False
                    or saved['submission_channel'] != 'authenticated_learner_private_handoff_request'):
                raise ValueError('Handoff identity, approval or destination changed')
            if body.action == 'attempt':
                if (saved['status'] != 'failed' or saved['reason'] != 'controlled_training_rejection_before_write'
                        or saved['destination_written'] is not False or saved['destination_copy'] is not None
                        or saved['previous_failed_receipt'] is not None):
                    raise ValueError('The authored first attempt must preserve rejection before any destination copy')
            else:
                previous = saved['previous_failed_receipt']
                serialized, digest = encode(previous)
                if (digest != body.previous_failed_sha256 or previous['uuid'] != body.previous_failed_id
                        or previous['status'] != 'failed' or previous['submission']['action'] != 'attempt'
                        or previous['submission']['artifacts_sha256'] != body.artifacts_sha256
                        or previous['submission']['result_sha256'] != body.result_sha256
                        or any(previous[key] != saved[key] for key in
                               ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'run_id'))):
                    raise ValueError('Retry lost the original exact failed handoff')
                OutputPrivateHandoffRepository.decode({**previous, 'record_json': serialized, 'record_sha256': digest})
                artifacts = verify_generated_artifacts(saved['destination_copy'])
                if (encode(artifacts)[1] != body.artifacts_sha256 or not artifacts['all_required_files_parseable']
                        or saved['status'] != 'delivered' or saved['reason'] != 'private_training_copy_saved'
                        or saved['destination_written'] is not True
                        or review.bundle_sha256 != artifacts['download']['sha256']
                        or {item.sha256 for item in review.file_inspections} != {item['sha256'] for item in artifacts['files']}):
                    raise ValueError('The private destination copy differs from the exact approved files')
            return saved
        except (KeyError, TypeError, ValueError, EnrollmentConflict) as exc:
            raise CourseCatalogError('The private training handoff failed integrity verification') from exc

    async def get(self, user_id, request_id):
        raw = await self.records.find_one({'uuid': request_id, 'user_id': user_id, 'prompt_id': PROMPT_ID, 'module_id': 'output_delivery'})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        body = OutputHandoffRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can send to this private training inbox')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'output_delivery', 'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256, 'run_id': body.run_id, 'prompt_id': PROMPT_ID}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        async def replay(raw):
            if any(raw.get(key) != value for key, value in identity.items()) or raw.get('request_sha256') != request_hash:
                raise EnrollmentConflict('This handoff request belongs to different files, approval or learner')
            saved = self.decode(raw)
            await self._finish_claim(operation, saved)
            return saved

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return await replay(existing)
        review = await OutputFileReviewRepository().get(actor_user_id, body.review_id)
        if review is None or encode(review)[1] != body.review_sha256:
            raise EnrollmentConflict('Inspect the original owned release decision before attempting this handoff')
        LabExecutionRepository.check_operation(operation, review)
        run = OutputWorkflowPreparation.decode(review['execution'])
        if (run['run_id'] != body.run_id or encode(run['result'])[1] != body.result_sha256
                or review['submission']['choice'] != 'approve'
                or review['submission']['artifacts_sha256'] != body.artifacts_sha256):
            raise EnrollmentConflict('This decision does not approve these exact generated files')
        previous = None
        if body.action == 'retry_failed_handoff':
            previous = await self.get(actor_user_id, body.previous_failed_id)
            if (previous is None or encode(previous)[1] != body.previous_failed_sha256
                    or previous['status'] != 'failed' or previous['submission']['action'] != 'attempt'
                    or previous['run_id'] != body.run_id or previous['submission']['artifacts_sha256'] != body.artifacts_sha256
                    or previous['submission']['result_sha256'] != body.result_sha256):
                raise EnrollmentConflict('Retry only the original failed private handoff with the same generated files')
            LabExecutionRepository.check_operation(operation, previous)
        records = LabExecutionRepository().records
        slot = 'output_handoff_request_id' if body.action == 'attempt' else 'output_retry_request_id'
        raw_run = await records.find_one({'uuid': body.run_id, 'user_id': actor_user_id})
        if (raw_run is None or raw_run.get('state') != 'completed'
                or raw_run.get('result_sha256') != body.result_sha256
                or raw_run.get('release_decision_id') != body.review_id
                or raw_run.get('release_decision_sha256') != body.review_sha256):
            raise EnrollmentConflict('The latest release choice does not approve this exact handoff')
        if body.action == 'retry_failed_handoff' and raw_run.get('output_handoff_request_id') != body.previous_failed_id:
            raise EnrollmentConflict('The failed receipt is not this run’s original handoff')
        if raw_run.get(slot) not in (None, body.request_id):
            raise EnrollmentConflict('This action already has an original request; read its receipt before any retry')
        if raw_run.get(slot) == body.request_id:
            if (raw_run.get('output_active_request_id') != body.request_id
                    or raw_run.get('output_active_request_sha256') != request_hash
                    or raw_run.get('output_handoff_claimed') is not True):
                raise EnrollmentConflict('This claimed request changed; inspect its original saved state')
            claimed_at = raw_run['output_claimed_at']
        else:
            claimed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            await LabInputRepository._check_lease(lease)
            claimed = await records.update_one({'uuid': body.run_id, 'user_id': actor_user_id, 'state': 'completed',
                'result_sha256': body.result_sha256, 'release_decision_id': body.review_id,
                'release_decision_sha256': body.review_sha256, slot: None, 'output_handoff_claimed': {'$ne': True}},
                {'$set': {slot: body.request_id, 'output_active_request_id': body.request_id,
                          'output_active_request_sha256': request_hash, 'output_handoff_claimed': True, 'output_claimed_at': claimed_at}})
            if claimed.modified_count != 1:
                raise EnrollmentConflict('The release or handoff changed before this request was claimed')
        delivered = body.action == 'retry_failed_handoff'
        saved = {**identity, 'record_kind': PROMPT_ID, 'request_sha256': request_hash, 'submission': request,
            'release_authorization': release_authorization(review), 'previous_failed_receipt': previous,
            'destination': {'id': 'private_training_inbox', 'audience': 'enrolled_learner_only',
                            'data_scope': 'approved_generated_files_only', 'owner_user_id': actor_user_id},
            'status': 'delivered' if delivered else 'failed',
            'reason': 'private_training_copy_saved' if delivered else 'controlled_training_rejection_before_write',
            'destination_written': delivered,
            'destination_copy': deepcopy(run['result']['generated_artifacts']) if delivered else None,
            'submitted_at': claimed_at, 'submission_channel': 'authenticated_learner_private_handoff_request',
            'external_delivery': False, 'credit_awarded': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > MAX_HANDOFF_BYTES:
            raise EnrollmentConflict('The private copy exceeds its storage budget; no file was truncated')
        self.decode({**saved, 'record_json': serialized, 'record_sha256': digest})
        await LabInputRepository._check_lease(lease)
        try:
            # The destination bytes and confirming receipt commit together.
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The handoff request identity was claimed by another operation')
            return await replay(existing)
        await self._finish_claim(operation, saved)
        return saved

    async def _finish_claim(self, operation, saved):
        lease = LabExecutionRepository.check_operation(operation, saved)
        await LabInputRepository._check_lease(lease)
        # First failure releases the decision lock, permitting a subsequent hold.
        # Completed delivery retains it. A historical replay cannot unlock a retry.
        await LabExecutionRepository().records.update_one({'uuid': saved['run_id'], 'user_id': operation.user_id,
            'output_active_request_id': saved['uuid'], 'output_active_request_sha256': saved['request_sha256']},
            {'$set': {'output_handoff_claimed': saved['status'] == 'delivered',
                      'output_handoff_receipt_id': saved['uuid'], 'output_handoff_receipt_sha256': encode(saved)[1]}})
