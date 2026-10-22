"""Separate learner inspection and current approve/hold choice for exact memo bytes."""
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .enrollments import EnrollmentConflict
from .governance_memos import GovernanceMemoRepository
from .governance_records import GovernanceJournal, IDENTITY_KEYS, embedded_record
from .governance_scope import Digest, Identity
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel


class GovernanceReleaseRequest(ContractModel):
    request_id: Identity
    run_id: Identity
    case_sha256: Digest
    memo_id: Identity
    memo_sha256: Digest
    file_sha256: Digest
    opened: bool = Field(strict=True)
    choice: Literal['approve', 'hold']
    reason: str = Field(min_length=40, max_length=8000)
    destination_id: Literal['private_training_inbox']
    audience: Literal['enrolled_learner_only']
    consent: Literal['save_my_exact_capstone_memo_release_choice']

    @model_validator(mode='after')
    def own_inspection(self):
        if len(self.reason.strip()) < 40 or (self.choice == 'approve' and not self.opened):
            raise ValueError('Inspect the actual memo before approval and explain your release or hold decision')
        return self


def validate_memo(body, memo):
    if (memo['uuid'] != body.memo_id or encode(memo)[1] != body.memo_sha256 or memo['run_id'] != body.run_id
            or memo['case']['case_sha256'] != body.case_sha256 or memo['file']['sha256'] != body.file_sha256):
        raise EnrollmentConflict('Inspect this exact saved memo, owned repair and original downloadable bytes')


class GovernanceReleaseRepository(GovernanceJournal):
    request_model = GovernanceReleaseRequest
    prompt_id = 'governance_memo_release_choice'
    channel = 'authenticated_learner_governance_memo_inspection'

    @classmethod
    def validate(cls, saved, body):
        memo = GovernanceMemoRepository.decode(embedded_record(saved['memo']))
        validate_memo(body, memo)
        if (any(saved[k] != memo[k] for k in IDENTITY_KEYS) or saved['case'] != memo['case']
                or saved['prompt'] != next(q for q in memo['case']['questions'] if q['id'] == 'release_review')
                or saved['delivery_confirmed'] is not False):
            raise ValueError('The release decision changed its exact owned memo, question or authority')

    async def build(self, operation, body):
        memo = await GovernanceMemoRepository().get(operation.user_id, body.memo_id)
        if memo is None:
            raise EnrollmentConflict('Read your complete saved memo before making its release choice')
        LabExecutionRepository.check_operation(operation, memo)
        validate_memo(body, memo)
        raw = await self.records.find_one({'uuid': memo['uuid'], 'user_id': operation.user_id})
        if raw is None or raw.get('governance_handoff_claimed') is True:
            raise EnrollmentConflict('The memo is unavailable or its handoff was claimed; inspect the original receipt')
        return {'memo': memo, 'prompt': next(q for q in memo['case']['questions'] if q['id'] == 'release_review'),
            'previous_release_decision_id': raw.get('release_decision_id'), 'delivery_confirmed': False}

    async def after_save(self, operation, saved, *, replay):
        lease = LabExecutionRepository.check_operation(operation, saved)
        current = await self.records.find_one({'uuid': saved['memo']['uuid'], 'user_id': operation.user_id})
        if current is None:
            if replay:
                return
            raise EnrollmentConflict('The original memo is unavailable')
        if current.get('release_decision_id') == saved['uuid']:
            return
        if current.get('release_decision_id') != saved['previous_release_decision_id']:
            if replay:
                return
            raise EnrollmentConflict('A newer release decision exists; inspect the current choice')
        await LabInputRepository._check_lease(lease)
        result = await self.records.update_one({'uuid': saved['memo']['uuid'], 'user_id': operation.user_id,
            'record_sha256': saved['submission']['memo_sha256'], 'release_decision_id': saved['previous_release_decision_id'],
            'governance_handoff_claimed': {'$ne': True}},
            {'$set': {'release_decision_id': saved['uuid'], 'release_decision_sha256': encode(saved)[1]}})
        if result.modified_count != 1:
            raise EnrollmentConflict('The memo changed or its handoff was claimed before this release decision could be linked')
