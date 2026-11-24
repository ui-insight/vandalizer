"""Auditable regrades after a supported grading correction.

A correction never edits a saved result. An administrator reviews one graded
attempt, then records why it is being re-examined (for example a fixed grading
defect); the automatic reviewer reruns on the original saved evidence and
requirements as a linked child attempt. Both results remain, and the learner
chooses which attempt to use. Grading stays automatic: no one sets a verdict.
"""
from pydantic import Field

from .attempts import encode
from .automatic_review import ReviewModel
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .outcomes import ContractModel
from .review_attempts import ReviewAttemptRepository
from .runtime import CourseOperation


class GradingCorrectionRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    parent_attempt_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    parent_result_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    reason: str = Field(min_length=20, max_length=1000)
    reference: str = Field(min_length=3, max_length=200)


def correction_view(saved: dict) -> dict:
    correction = saved['record'].get('grading_correction')
    result = saved['result'] or {}
    return {'attempt_id': saved['attempt_id'], 'state': saved['state'],
            'status': result.get('assessment', {}).get('status'),
            'reason': correction['reason'], 'reference': correction['reference'],
            'actor_user_id': correction['actor_user_id'], 'prepared_at': saved['record']['prepared_at']}


class GradingCorrections:
    def __init__(self, repository: EnrollmentRepository | None = None) -> None:
        self.repository = repository or EnrollmentRepository()
        self.attempts = ReviewAttemptRepository()

    async def _graded(self, user_id: str, enrollment_id: str, attempt_id: str) -> dict:
        saved = await self.attempts.get(user_id, attempt_id)
        if saved is None or saved['record']['enrollment_id'] != enrollment_id:
            raise EnrollmentConflict('This saved assessment is unavailable for that enrollment')
        if saved['state'] != 'evaluated':
            raise EnrollmentConflict('Only a saved graded assessment can be regraded after a correction')
        return saved

    async def review(self, user_id: str, enrollment_id: str, attempt_id: str) -> dict:
        """Read-only: the exact result a correction would re-examine and earlier corrections."""
        saved = await self._graded(user_id, enrollment_id, attempt_id)
        children = []
        async for raw in self.attempts.records.find({'user_id': user_id, 'parent_attempt_id': attempt_id}).sort('_id', 1):
            child = self.attempts.decode(raw)
            if child['record'].get('grading_correction'):
                children.append(correction_view(child))
        return {'attempt_id': attempt_id, 'enrollment_id': enrollment_id, 'module_id': saved['record']['module_id'],
                'status': saved['result']['assessment']['status'], 'result_sha256': encode(saved['result'])[1],
                'reviewer_implementation_sha256': saved['record']['reviewer'].get('implementation_sha256'),
                'corrections': children}

    async def submit(self, actor_user_id: str, user_id: str, enrollment_id: str, body: object, system_config: dict, *, call_model: ReviewModel | None = None) -> dict:
        request = GradingCorrectionRequest.model_validate(body)
        await self._graded(user_id, enrollment_id, request.parent_attempt_id)
        correction = {'kind': 'supported_grading_correction', 'actor_user_id': actor_user_id,
                      'reason': request.reason.strip(), 'reference': request.reference.strip(),
                      'parent_result_sha256': request.parent_result_sha256}
        repository = self.repository
        async with repository.write_boundary(user_id, enrollment_id, operation='prepare_grading_correction') as progress:
            if progress.course_version is None:
                raise EnrollmentConflict('This operation requires a bound course version')
            package = repository.catalog.load(progress.course_version)
            prepared = await self.attempts.prepare_correction(CourseOperation(user_id, package, progress, True),
                request.parent_attempt_id, request.request_id, correction=correction, system_config=system_config)
        saved = await self.attempts.evaluate_saved(repository, user_id, enrollment_id, prepared['attempt_id'],
                                                   system_config, call_model=call_model)
        return correction_view(saved)
