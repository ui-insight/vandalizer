"""Save the learner's final supervision explanation with the exact complete handoff chain."""
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .enrollments import EnrollmentConflict
from .governance_handoff import GovernanceHandoffRepository
from .governance_records import GovernanceJournal, IDENTITY_KEYS, embedded_record
from .governance_scope import Digest, Identity
from .lab_execution import LabExecutionRepository
from .outcomes import ContractModel


class GovernanceReviewRequest(ContractModel):
    request_id: Identity
    run_id: Identity
    case_sha256: Digest
    handoff_id: Identity
    handoff_sha256: Digest
    final_supervision: str = Field(min_length=40, max_length=8000)
    previous_submission_id: Identity | None = None
    consent: Literal['save_my_capstone_supervision_interpretation']

    @model_validator(mode='after')
    def own_explanation(self):
        if len(self.final_supervision.strip()) < 40 or self.previous_submission_id == self.request_id:
            raise ValueError('Explain your own supervision chain; revised answers need a new request identity')
        return self


def validate_handoff(body, handoff):
    if (handoff['uuid'] != body.handoff_id or encode(handoff)[1] != body.handoff_sha256
            or handoff['run_id'] != body.run_id or handoff['case']['case_sha256'] != body.case_sha256
            or handoff['status'] != 'delivered' or handoff['destination_written'] is not True):
        raise EnrollmentConflict('The final supervision interpretation requires the exact confirmed private same-bytes handoff')


class GovernanceReviewRepository(GovernanceJournal):
    request_model = GovernanceReviewRequest
    prompt_id = 'governance_final_supervision_review'
    channel = 'authenticated_learner_governance_supervision_review'

    @classmethod
    def validate(cls, saved, body):
        handoff = GovernanceHandoffRepository.decode(embedded_record(saved['handoff']))
        validate_handoff(body, handoff)
        if (any(saved[k] != handoff[k] for k in IDENTITY_KEYS) or saved['case'] != handoff['case']
                or saved['prompt'] != next(q for q in handoff['case']['questions'] if q['id'] == 'final_supervision')):
            raise ValueError('The saved supervision changed its complete original handoff chain or question')

    async def build(self, operation, body):
        previous = await self.get(operation.user_id, body.previous_submission_id) if body.previous_submission_id else None
        if body.previous_submission_id and previous is None:
            raise EnrollmentConflict('A revision must retain an owned original supervision review')
        if previous:
            LabExecutionRepository.check_operation(operation, previous)
        handoff = (previous['handoff'] if previous and previous['submission']['handoff_id'] == body.handoff_id
            else await GovernanceHandoffRepository().get(operation.user_id, body.handoff_id))
        if handoff is None:
            raise EnrollmentConflict('Read the confirmed private handoff before saving your final supervision explanation')
        LabExecutionRepository.check_operation(operation, handoff)
        validate_handoff(body, handoff)
        return {'handoff': handoff, 'prompt': next(q for q in handoff['case']['questions'] if q['id'] == 'final_supervision')}
