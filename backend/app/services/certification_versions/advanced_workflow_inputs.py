"""Bind a learner's saved workflow and method decision to exact calculations.

This capture preserves evidence only. A separate approved plan is required for
execution; neither the learner's method claim nor source addition earns credit.
"""
import datetime
from typing import Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .advanced_calculation_records import AdvancedCalculationRepository
from .advanced_case import load_advanced_case
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository, MAX_SNAPSHOT_BYTES
from .outcomes import ContractModel
from .workflow_design_inputs import WorkflowDesignInputRepository


class AdvancedWorkflowCapture(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    workflow_id: str = Field(pattern=r'^[a-f0-9]{24}$')
    calculation_snapshot_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    calculation_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    method_choice: str = Field(min_length=30, max_length=8000)
    consent: Literal['capture_budget_workflow_and_method']

    @model_validator(mode='after')
    def explained_choice(self):
        if len(self.method_choice.strip()) < 30:
            raise ValueError('Explain the interpretation method, arithmetic evidence and available alternative')
        return self


class AdvancedWorkflowInputRepository(WorkflowDesignInputRepository):
    @staticmethod
    def decode(raw):
        saved = LabInputRepository.decode(raw)
        try:
            body = AdvancedWorkflowCapture.model_validate(saved['request'])
            calculation = saved['calculation_snapshot']
            serialized, digest = encode(calculation)
            AdvancedCalculationRepository.decode({**calculation, 'record_json': serialized, 'record_sha256': digest})
            shared = ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'rubric_id', 'exercise_sha256')
            if (saved['record_kind'] != 'advanced_workflow_input' or saved['schema_version'] != 1
                    or saved['module_id'] != 'advanced_nodes' or body.request_id != saved['uuid']
                    or body.workflow_id != saved['artifact_id']
                    or body.calculation_snapshot_id != calculation['uuid'] or body.calculation_snapshot_sha256 != digest
                    or any(saved[key] != calculation[key] for key in shared)
                    or saved['case'] != calculation['case'] or body.case_sha256 != saved['case']['case_sha256']
                    or encode(body.model_dump(mode='json'))[1] != saved['request_sha256']
                    or encode(saved['artifact'])[1] != saved['artifact_sha256']
                    or saved['artifact']['workflow']['id'] != saved['artifact_id']
                    or saved['artifact']['workflow']['user_id'] != saved['user_id']
                    or saved['artifact']['capture_scope'] != 'saved_workflow_step_task_configuration_only'
                    or saved['method_choice_provenance'] != 'authenticated_learner_before_execution'
                    or saved['execution_status'] != 'not_started' or saved['execution_authorized'] is not False
                    or saved['credit_awarded'] is not False or saved['module_completion_eligible'] is not False
                    or saved['outcomes_awarded'] != []):
                raise ValueError('Saved workflow, method or original calculation binding changed')
            return saved
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise CourseCatalogError('Saved budget workflow evidence failed integrity verification') from exc

    async def capture(self, operation, body, *, actor_user_id):
        body = AdvancedWorkflowCapture.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Budget workflow capture requires the authenticated learner')
        package = operation.package
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': 'advanced_nodes', 'course_version': package.manifest.release_id,
                    'manifest_sha256': package.manifest_sha256, 'artifact_id': body.workflow_id}
        lease = LabExecutionRepository.check_operation(operation, identity)
        case = load_advanced_case(package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('Select the pinned budget case before capturing the workflow')
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            saved = self.decode(raw)
            if any(saved[key] != value for key, value in identity.items()) or saved['request_sha256'] != request_hash:
                raise EnrollmentConflict('This capture request belongs to another workflow or method decision')
            return saved

        await self._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        calculation = await AdvancedCalculationRepository().get(actor_user_id, body.calculation_snapshot_id)
        if (calculation is None or any(calculation[key] != identity[key] for key in
                ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                or encode(calculation)[1] != body.calculation_snapshot_sha256
                or calculation['case'] != case.public_definition()
                or calculation['rubric_id'] != package.manifest.rubric_id
                or calculation['exercise_sha256'] != package.manifest.artifacts['exercises.json']):
            raise EnrollmentConflict('Select the exact owned calculation record from this course and source')
        artifact = await self._read_artifact(actor_user_id, body.workflow_id)
        if await self._read_artifact(actor_user_id, body.workflow_id) != artifact:
            raise EnrollmentConflict('The workflow changed during capture; inspect its current revision')
        saved = {**identity, 'schema_version': 1, 'record_kind': 'advanced_workflow_input',
                 'rubric_id': package.manifest.rubric_id, 'exercise_sha256': package.manifest.artifacts['exercises.json'],
                 'request': request, 'request_sha256': request_hash, 'case': case.public_definition(),
                 'artifact': artifact, 'artifact_sha256': encode(artifact)[1], 'calculation_snapshot': calculation,
                 'method_choice_provenance': 'authenticated_learner_before_execution',
                 'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'execution_status': 'not_started', 'execution_authorized': False, 'outcomes_awarded': [],
                 'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > MAX_SNAPSHOT_BYTES:
            raise EnrollmentConflict('The complete budget workflow evidence exceeds the immutable storage budget')
        await self._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'record_kind': saved['record_kind'], 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('This workflow reference was claimed by another operation')
            return replay(existing)
        await self._check_lease(lease)
        return saved
