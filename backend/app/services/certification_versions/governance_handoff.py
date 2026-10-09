"""Atomic private JSON-copy rehearsal: disclosed no-write rejection, explicit exact retry."""
from copy import deepcopy
import datetime
from typing import Literal

from pydantic import model_validator

from .attempts import encode
from .enrollments import EnrollmentConflict
from .governance_records import GovernanceJournal, IDENTITY_KEYS, embedded_record
from .governance_release import GovernanceReleaseRepository
from .governance_scope import Digest, Identity
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel


class GovernanceHandoffRequest(ContractModel):
    request_id: Identity
    run_id: Identity
    case_sha256: Digest
    memo_id: Identity
    memo_sha256: Digest
    file_sha256: Digest
    release_id: Identity
    release_sha256: Digest
    destination_id: Literal['private_training_inbox']
    action: Literal['attempt', 'retry_failed_handoff']
    previous_failed_id: Identity | None = None
    previous_failed_sha256: Digest | None = None
    consent: Literal['attempt_approved_private_capstone_handoff', 'retry_only_failed_private_capstone_handoff']

    @model_validator(mode='after')
    def explicit_action(self):
        if self.action == 'attempt':
            if self.previous_failed_id is not None or self.previous_failed_sha256 is not None or self.consent != 'attempt_approved_private_capstone_handoff':
                raise ValueError('The first handoff attempt cannot claim a previous failure')
        elif (self.previous_failed_id is None or self.previous_failed_sha256 is None or self.previous_failed_id == self.request_id
                or self.consent != 'retry_only_failed_private_capstone_handoff'):
            raise ValueError('An explicit retry requires the exact first confirmed no-write failure')
        return self


def validate_release(body, release):
    if (release['uuid'] != body.release_id or encode(release)[1] != body.release_sha256
            or release['submission']['choice'] != 'approve' or release['run_id'] != body.run_id
            or release['case']['case_sha256'] != body.case_sha256
            or any(release['submission'][k] != getattr(body, k) for k in ('memo_id', 'memo_sha256', 'file_sha256', 'destination_id'))):
        raise EnrollmentConflict('The exact learner release must approve these same private memo bytes')


def validate_previous(body, previous):
    if (previous is None or previous['uuid'] != body.previous_failed_id or encode(previous)[1] != body.previous_failed_sha256
            or previous['status'] != 'failed' or previous['submission']['action'] != 'attempt'
            or any(previous['submission'][k] != getattr(body, k) for k in ('run_id', 'case_sha256', 'memo_id', 'memo_sha256', 'file_sha256', 'destination_id'))):
        raise EnrollmentConflict('Retry only the original confirmed failed handoff with the same checked memo bytes')


class GovernanceHandoffRepository(GovernanceJournal):
    request_model = GovernanceHandoffRequest
    prompt_id = 'governance_private_training_handoff'
    channel = 'authenticated_learner_governance_private_handoff'

    @classmethod
    def validate(cls, saved, body):
        release = GovernanceReleaseRepository.decode(embedded_record(saved['release']))
        validate_release(body, release)
        if (any(saved[k] != release[k] for k in IDENTITY_KEYS) or saved['case'] != release['case']
                or saved['destination'] != {'id': 'private_training_inbox', 'audience': 'enrolled_learner_only',
                    'data_scope': 'exact_checked_memo_only', 'owner_user_id': saved['user_id']}
                or saved['external_delivery'] is not False):
            raise ValueError('The handoff changed its authenticated owner, exact memo or destination')
        if body.action == 'attempt':
            if (saved['status'] != 'failed' or saved['reason'] != 'controlled_training_rejection_before_write'
                    or saved['destination_written'] is not False or saved['destination_copy'] is not None or saved['previous_failed_receipt'] is not None):
                raise ValueError('The first attempt must preserve the disclosed rejection before any destination copy')
        else:
            previous = saved['previous_failed_receipt']
            validate_previous(body, previous)
            cls.decode(embedded_record(previous))
            if (any(previous[k] != saved[k] for k in IDENTITY_KEYS)
                    or saved['status'] != 'delivered' or saved['reason'] != 'private_training_copy_saved'
                    or saved['destination_written'] is not True or saved['destination_copy'] != release['memo']['file']):
                raise ValueError('The destination must contain exactly the originally checked, approved bytes')

    async def build(self, operation, body):
        release = await GovernanceReleaseRepository().get(operation.user_id, body.release_id)
        if release is None:
            raise EnrollmentConflict('Read your saved memo release before attempting a private handoff')
        LabExecutionRepository.check_operation(operation, release)
        validate_release(body, release)
        previous = None
        if body.action == 'retry_failed_handoff':
            previous = await self.get(operation.user_id, body.previous_failed_id)
            validate_previous(body, previous)
            LabExecutionRepository.check_operation(operation, previous)
        raw = await self.records.find_one({'uuid': body.memo_id, 'user_id': operation.user_id})
        if (raw is None or raw.get('record_sha256') != body.memo_sha256
                or raw.get('release_decision_id') != body.release_id or raw.get('release_decision_sha256') != body.release_sha256):
            raise EnrollmentConflict('The latest learner choice does not approve this exact memo handoff')
        if body.action == 'retry_failed_handoff' and raw.get('governance_handoff_request_id') != body.previous_failed_id:
            raise EnrollmentConflict('The failed receipt is not this memo’s original handoff')
        slot = 'governance_handoff_request_id' if body.action == 'attempt' else 'governance_retry_request_id'
        request_hash = encode(body.model_dump(mode='json'))[1]
        if raw.get(slot) not in (None, body.request_id):
            raise EnrollmentConflict('This handoff action already has an original request; read its state before retrying')
        if raw.get(slot) == body.request_id:
            if (raw.get('governance_active_request_id') != body.request_id or raw.get('governance_active_request_sha256') != request_hash
                    or raw.get('governance_handoff_claimed') is not True):
                raise EnrollmentConflict('This claimed request changed; inspect its original state')
            claimed_at = raw['governance_claimed_at']
        else:
            claimed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            lease = LabExecutionRepository.check_operation(operation, release)
            await LabInputRepository._check_lease(lease)
            claimed = await self.records.update_one({'uuid': body.memo_id, 'user_id': operation.user_id,
                'record_sha256': body.memo_sha256, 'release_decision_id': body.release_id, 'release_decision_sha256': body.release_sha256,
                slot: None, 'governance_handoff_claimed': {'$ne': True}},
                {'$set': {slot: body.request_id, 'governance_active_request_id': body.request_id, 'governance_active_request_sha256': request_hash,
                    'governance_handoff_claimed': True, 'governance_claimed_at': claimed_at}})
            if claimed.modified_count != 1:
                raise EnrollmentConflict('The release or original handoff changed before this action could be claimed')
        delivered = body.action == 'retry_failed_handoff'
        return {'release': release, 'previous_failed_receipt': previous,
            'destination': {'id': 'private_training_inbox', 'audience': 'enrolled_learner_only',
                'data_scope': 'exact_checked_memo_only', 'owner_user_id': operation.user_id},
            'status': 'delivered' if delivered else 'failed',
            'reason': 'private_training_copy_saved' if delivered else 'controlled_training_rejection_before_write',
            'destination_written': delivered, 'destination_copy': deepcopy(release['memo']['file']) if delivered else None,
            'submitted_at': claimed_at, 'external_delivery': False}

    async def after_save(self, operation, saved, *, replay):
        lease = LabExecutionRepository.check_operation(operation, saved)
        await LabInputRepository._check_lease(lease)
        # An old failure replay must not unlock a newer retry or delivered copy.
        await self.records.update_one({'uuid': saved['submission']['memo_id'], 'user_id': operation.user_id,
            'governance_active_request_id': saved['uuid'], 'governance_active_request_sha256': saved['request_sha256']},
            {'$set': {'governance_handoff_claimed': saved['status'] == 'delivered',
                'governance_handoff_receipt_id': saved['uuid'], 'governance_handoff_receipt_sha256': encode(saved)[1]}})
