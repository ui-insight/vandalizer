"""Authenticated correction of the flawed capstone proposal before execution."""
import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .governance_case import load_governance_case
from .governance_checks import embedded_input
from .governance_inputs import GovernanceInputRepository
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository
from .outcomes import ContractModel

Identity = Annotated[str, Field(pattern=r'^[a-f0-9]{32}$')]
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
PROMPT_ID = 'governance_scope_correction'


class GovernanceScopeCorrectionRequest(ContractModel):
    request_id: Identity
    input_snapshot_id: Identity
    input_snapshot_sha256: Digest
    case_sha256: Digest
    choice: Literal['reject_broad_proposal']
    source_document_ids: tuple[Identity, ...] = Field(min_length=2, max_length=2)
    destination_id: Literal['private_training_inbox']
    audience: Literal['enrolled_learner_only']
    ongoing_automation: Literal['keep_disabled']
    reason: str = Field(min_length=40, max_length=8000)
    consent: Literal['save_my_corrected_capstone_scope_without_execution']

    @model_validator(mode='after')
    def distinct_sources(self):
        if len(set(self.source_document_ids)) != 2 or len(self.reason.strip()) < 40:
            raise ValueError('Record two distinct original source identities and your own scope reasoning')
        return self


class GovernanceScopeCorrection(LearnerDecisionRepository):
    @staticmethod
    def decode(raw):
        saved = LearnerDecisionRepository.decode(raw)
        try:
            body = GovernanceScopeCorrectionRequest.model_validate(saved['submission'])
            snapshot = GovernanceInputRepository.decode(saved['input_snapshot'])
            question = next(q for q in snapshot['case']['questions'] if q['id'] == 'scope_correction')
            if (saved['record_kind'] != PROMPT_ID or saved['prompt_id'] != PROMPT_ID or saved['module_id'] != 'governance'
                    or saved['run_id'] != body.input_snapshot_id
                    or saved['uuid'] != body.request_id or saved['input_snapshot_id'] != body.input_snapshot_id
                    or snapshot['uuid'] != body.input_snapshot_id or encode(snapshot)[1] != body.input_snapshot_sha256
                    or saved['case'] != snapshot['case'] or body.case_sha256 != saved['case']['case_sha256']
                    or list(body.source_document_ids) != [s['document_id'] for s in snapshot['documents']]
                    or saved['prompt'] != question or saved['flawed_proposal'] != saved['case']['flawed_proposal']
                    or saved['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or any(saved[key] != snapshot[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or saved['submission_channel'] != 'authenticated_learner_governance_scope_correction'
                    or any(saved[key] is not False for key in ('execution_authorized', 'external_effects_authorized', 'credit_awarded', 'module_completion_eligible'))):
                raise ValueError('The saved learner correction changed its exact source or authority boundary')
            return saved
        except (KeyError, TypeError, ValueError, StopIteration) as exc:
            raise CourseCatalogError('The saved Governance scope correction failed integrity verification') from exc

    async def get(self, user_id, reference):
        raw = await self.records.find_one({'uuid': reference, 'user_id': user_id, 'module_id': 'governance', 'prompt_id': PROMPT_ID})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        body = GovernanceScopeCorrectionRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can record the capstone scope correction')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
            'module_id': 'governance', 'course_version': operation.package.manifest.release_id,
            'manifest_sha256': operation.package.manifest_sha256, 'input_snapshot_id': body.input_snapshot_id, 'prompt_id': PROMPT_ID,
            # The common decision journal requires a string reference. As for
            # saved Validation expectations, this pre-execution record anchors
            # its capture; its kind and false authority flags grant no run.
            'run_id': body.input_snapshot_id}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            if any(raw.get(key) != value for key, value in identity.items()) or raw.get('request_sha256') != request_hash:
                raise EnrollmentConflict('This correction identity belongs to different learner decisions or sources')
            return self.decode(raw)

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        case = load_governance_case(operation.package)
        snapshot = await GovernanceInputRepository().get(actor_user_id, body.input_snapshot_id)
        if snapshot is None or encode(snapshot)[1] != body.input_snapshot_sha256 or snapshot['case'] != case.public_definition() or body.case_sha256 != case.digest:
            raise EnrollmentConflict('Inspect the exact owned capstone capture before correcting its scope')
        LabExecutionRepository.check_operation(operation, snapshot)
        if list(body.source_document_ids) != [s['document_id'] for s in snapshot['documents']]:
            raise EnrollmentConflict('Correct the scope to both exact assigned source identities, not a workspace-wide selection')
        saved = {**identity, 'record_kind': PROMPT_ID, 'request_sha256': request_hash, 'submission': request,
            'case': case.public_definition(), 'flawed_proposal': case.flawed_proposal,
            'prompt': next(q.model_dump(mode='json') for q in case.questions if q.id == 'scope_correction'),
            'input_snapshot': embedded_input(snapshot), 'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'submission_channel': 'authenticated_learner_governance_scope_correction', 'execution_authorized': False,
            'external_effects_authorized': False, 'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > 10 * 1024 * 1024:
            raise EnrollmentConflict('The complete source-bound correction exceeds its storage limit; nothing was truncated')
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('This correction reference was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return saved
