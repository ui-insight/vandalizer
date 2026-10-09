"""Explicit learner scope choices for an exact saved connected-workflow plan."""
import datetime
from typing import Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .catalog import CourseCatalogError
from .connected_workflow_preparation import ConnectedWorkflowPreparation
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository
from .outcomes import ContractModel


class ConnectedScopeRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    plan_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    choice: Literal['approve', 'hold']
    reason: str = Field(min_length=10, max_length=4000)
    consent: Literal['save_connected_workflow_scope_decision']

    @model_validator(mode='after')
    def nonempty_reason(self):
        if len(self.reason.strip()) < 10:
            raise ValueError('Explain the scope choice for this saved revision')
        return self


class ConnectedScopeRepository(LearnerDecisionRepository):
    request_model = ConnectedScopeRequest
    preparation_type = ConnectedWorkflowPreparation
    module_id = 'multi_step'
    record_kind = 'connected_workflow_scope'
    scope_prompt_id = 'scope_approval'

    @classmethod
    def decode(cls, raw):
        record = LearnerDecisionRepository.decode(raw)
        try:
            body = cls.request_model.model_validate(record['submission'])
            if (record['record_kind'] != cls.record_kind or record['module_id'] != cls.module_id
                    or record['prompt_id'] != cls.scope_prompt_id or record['prompt']['id'] != cls.scope_prompt_id
                    or record['prompt']['phase'] != 'before_execution' or record['prompt']['execution_choice'] != 'approve'
                    or record['prompt_sha256'] != encode(record['prompt'])[1]
                    or record['uuid'] != body.request_id or record['run_id'] != body.run_id
                    or record['plan_sha256'] != body.plan_sha256 or record['case_sha256'] != body.case_sha256
                    or record['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or record['run_state_at_submission'] != 'prepared'
                    or record['submission_channel'] != 'authenticated_learner_request'
                    or record['credit_awarded'] is not False):
                raise ValueError('Saved approval binding changed')
            return record
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The saved connected-workflow scope decision failed integrity verification') from exc

    async def submit(self, operation, body, *, actor_user_id):
        body = self.request_model.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can approve the saved revision')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id,
                    'enrollment_id': operation.progress.enrollment_id, 'module_id': self.module_id,
                    'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256,
                    'run_id': body.run_id, 'prompt_id': self.scope_prompt_id}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        async def replay(raw):
            record = self.decode(raw)
            if any(record[key] != value for key, value in identity.items()) or record['request_sha256'] != request_hash:
                raise EnrollmentConflict('This scope reference belongs to different answers or another learner')
            await self._link_scope(operation, record, replay=True)
            return record

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return await replay(existing)
        run = await self.preparation_type().get(actor_user_id, body.run_id)
        if run is None:
            raise EnrollmentConflict('Prepare an owned connected-workflow plan before approving it')
        LabExecutionRepository.check_operation(operation, run['plan'])
        if run['state'] != 'prepared' or run['plan_sha256'] != body.plan_sha256 or run['plan']['case_sha256'] != body.case_sha256:
            raise EnrollmentConflict('Scope approval must bind the exact prepared plan before execution')
        prompt = {**run['plan']['approval_requirement']['question'], 'execution_choice': 'approve'}
        record = {**identity, 'record_kind': self.record_kind, 'request_sha256': request_hash,
                  'submission': request, 'prompt': prompt, 'prompt_sha256': encode(prompt)[1],
                  'plan_sha256': body.plan_sha256, 'case_sha256': body.case_sha256,
                  'input_snapshot_id': run['plan']['input_snapshot_id'],
                  'input_snapshot_sha256': run['plan']['input_snapshot_sha256'],
                  'run_state_at_submission': 'prepared', 'previous_scope_decision_id': run.get('scope_decision_id'),
                  'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'submission_channel': 'authenticated_learner_request', 'credit_awarded': False}
        serialized, digest = encode(record)
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash,
                                           'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The scope reference was claimed by another operation')
            return await replay(existing)
        await self._link_scope(operation, record, replay=False)
        return record

    async def authorize(self, operation, run):
        """Validate currently linked consent; this method never dispatches."""
        LabExecutionRepository.check_operation(operation, run['plan'])
        record = await self.get(operation.user_id, run.get('scope_decision_id'))
        if record is None:
            raise EnrollmentConflict('Approve this saved connected-workflow plan before execution')
        plan = run['plan']
        LabExecutionRepository.check_operation(operation, record)
        expected_prompt = {**plan['approval_requirement']['question'], 'execution_choice': 'approve'}
        if (run['state'] != 'prepared' or record['run_id'] != run['run_id']
                or record['plan_sha256'] != run['plan_sha256'] or record['case_sha256'] != plan['case_sha256']
                or record['input_snapshot_id'] != plan['input_snapshot_id']
                or record['input_snapshot_sha256'] != plan['input_snapshot_sha256']
                or record['prompt'] != expected_prompt or encode(record)[1] != run.get('scope_decision_sha256')
                or record['submission']['choice'] != 'approve'):
            raise EnrollmentConflict('The latest scope choice does not approve this exact prepared plan')
        return {'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
                'decision': record, 'decision_sha256': encode(record)[1]}
