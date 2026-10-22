"""Explicit learner execution of an owned plan with its exact saved approval."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import practical_preparation as preparation
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .lab_execution import LabExecutionRepository, execution_plan
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository
from .runtime import CourseOperation


class ExecutionUnavailable(ValueError):
    pass


class ExecutionSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    plan_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    scope_decision_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    scope_decision_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['execute_saved_inputs']

    def expected_approval(self):
        return self.model_dump(exclude={'consent'})


class PracticalExecution:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.runs = LabExecutionRepository()

    async def owned(self, user_id, enrollment_id, run_id):
        run = await self.runs.get(user_id, run_id)
        if run is None:
            raise ExecutionUnavailable('This saved practical run is unavailable')
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        expected = {'user_id': user_id, 'enrollment_id': enrollment_id,
                    'course_version': enrollment.course_version, 'manifest_sha256': enrollment.manifest_sha256}
        if any(run['plan'].get(key) != value for key, value in expected.items()):
            raise EnrollmentConflict('This saved run belongs to a different course')
        package = self.repository.catalog.load(enrollment.course_version)
        preparation.PracticalPreparation.eligible(package, run['plan']['module_id'])
        return run, package

    @staticmethod
    def public(run, *, can_execute=False, blocked_reason=None):
        result = run.get('result') or {}
        return {
            **{key: run['plan'][key] for key in ('enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'input_snapshot_id')},
            **{key: run[key] for key in ('run_id', 'state', 'plan_sha256', 'scope_decision_id', 'scope_decision_sha256')},
            'model_names': run['plan']['model_names'], 'can_execute': can_execute, 'blocked_reason': blocked_reason,
            'started_at': result.get('started_at'), 'finished_at': result.get('finished_at'),
            'documents_executed': len(result.get('documents_executed', [])) if run['state'] == 'completed' else None,
            'result_available': run['state'] == 'completed',
            'credit_awarded': False, 'module_completion_eligible': False,
        }

    async def get(self, user_id, enrollment_id, run_id, *, delivery_enabled=False):
        run, package = await self.owned(user_id, enrollment_id, run_id)
        if run['state'] != 'prepared':
            return self.public(run)
        # A read may explain readiness, but never initialize, claim or dispatch.
        selection = await self.repository.selections.find_one({'user_id': user_id})
        if not delivery_enabled or not selection or selection.get('active_enrollment_id') != enrollment_id:
            return self.public(run, blocked_reason='Select this course while practical delivery is available before running it.')
        try:
            await LearnerDecisionRepository().inspect_authorization(user_id, enrollment_id, package, run)
            snapshot = await LabInputRepository().get(user_id, run['plan']['input_snapshot_id'])
            if snapshot is None:
                raise EnrollmentConflict('The original saved inputs are unavailable.')
            current = execution_plan(snapshot, await preparation.configured_runtime())
            if any(current[key] != run['plan'][key] for key in current):
                raise EnrollmentConflict('Execution settings or implementation changed; prepare and review a new run.')
        except EnrollmentConflict as exc:
            return self.public(run, blocked_reason=str(exc))
        except CourseCatalogError:
            return self.public(run, blocked_reason='Execution settings are unavailable. Your saved work is preserved.')
        return self.public(run, can_execute=True)

    async def execute(self, user_id, enrollment_id, run_id, submission):
        source = await self.repository.current(user_id)
        if source is None or source.uuid != enrollment_id:
            raise EnrollmentConflict('Select your existing course before executing an assessed run')
        run, package = await self.owned(user_id, enrollment_id, run_id)
        expected = submission.expected_approval()
        if any(run.get(key) != value for key, value in expected.items()):
            raise EnrollmentConflict('The saved plan or scope approval changed; review this run again before execution')
        if run['state'] != 'prepared':
            # Lost responses can be read or explicitly replayed without settings
            # lookup, a new lease, provider dispatch or a second attempt.
            return self.public(run)
        async with self.repository.write_boundary(user_id, enrollment_id, operation='execute_practical_run') as progress:
            result = await self.runs.execute(CourseOperation(user_id, package, progress, True), run_id,
                await preparation.configured_runtime(), expected_approval=expected)
            return self.public(result)
