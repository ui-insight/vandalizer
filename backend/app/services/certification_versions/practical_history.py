"""Owned practical history stays readable without selecting or initializing it."""
from .enrollments import EnrollmentRepository
from .learner_decisions import LearnerDecisionRepository
from .runtime import CourseOperation


class PracticalHistory:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.decisions = LearnerDecisionRepository()

    async def operation(self, user_id, enrollment_id, delivery_enabled):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        progress = await self.repository.read_progress(user_id, enrollment_id)
        selection = await self.repository.selections.find_one({'user_id': user_id})
        reason = None
        if not delivery_enabled:
            reason = 'Practical submissions are unavailable. Your saved sources, values and decisions remain readable.'
        elif enrollment.state not in ('active', 'completed'):
            reason = 'This course is read-only. Your saved sources, values and decisions remain available.'
        elif not selection or selection.get('active_enrollment_id') != enrollment_id:
            reason = 'This is saved history from a different course. It remains available for reading; new work belongs to your selected course.'
        return CourseOperation(user_id, package, progress, False), reason

    async def runs(self, user_id, enrollment_id, module_id, *, delivery_enabled=False):
        operation, reason = await self.operation(user_id, enrollment_id, delivery_enabled)
        return {**await self.decisions.runs(operation, module_id),
                'enrollment_id': enrollment_id, 'module_id': module_id, 'read_only_reason': reason}

    async def context(self, user_id, enrollment_id, module_id, prompt_id, run_id, *, delivery_enabled=False):
        operation, reason = await self.operation(user_id, enrollment_id, delivery_enabled)
        view = await self.decisions.context(operation, module_id, prompt_id, run_id)
        return {**view, 'can_submit': view['can_submit'] and reason is None, 'read_only_reason': reason}
