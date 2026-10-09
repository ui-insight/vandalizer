"""Pin one enrollment across nested service/tool calls for a single operation."""
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import inspect

from fastapi import HTTPException

from app.config import Settings
from app.models.certification import CertificationProgress
from .catalog import CourseCatalogError, CoursePackage
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .legacy_writes import LegacyOperation, legacy_operation


@dataclass(frozen=True)
class CourseOperation:
    user_id: str
    package: CoursePackage
    progress: CertificationProgress
    writable: bool


_operation: ContextVar[CourseOperation | None] = ContextVar('certification_operation', default=None)


def current_operation() -> CourseOperation | None:
    return _operation.get()


def versioning_enabled() -> bool:
    return Settings().certification_versioning_enabled


def course_operation(*, write=False, http=False, tool=False):
    """Bind at the outer boundary; nested calls cannot change user or course.

    Disabled by default until rollout verification. The enrollment_id argument
    is optional for initial reads and required by clients submitting old cards
    once upgrades are exposed; a supplied stale identity always fails closed.
    """
    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        async def wrapped(*args, **kwargs):
            try:
                bound = signature.bind(*args, **kwargs).arguments
                principal = bound.get('context') or bound.get('user') or bound.get('user_id')
                if isinstance(principal, str):
                    user_id = principal
                elif hasattr(principal, 'deps'):
                    user_id = principal.deps.user_id
                else:
                    user_id = principal.user_id
                expected_id = bound.get('enrollment_id')
                operation = current_operation()
                if operation is not None:
                    if operation.user_id != user_id or (expected_id and expected_id != operation.progress.enrollment_id):
                        raise EnrollmentConflict('This request belongs to a different enrollment')
                    if write and not operation.writable:
                        raise EnrollmentConflict('A read-only course operation cannot write progress')
                    return await function(*args, **kwargs)
                legacy = legacy_operation.get()
                if legacy is not None:
                    if not legacy.active:
                        raise EnrollmentConflict('This legacy course operation has ended; start a fresh request')
                    if legacy.user_id != user_id or expected_id:
                        raise EnrollmentConflict('This request belongs to a different learner or course')
                    if write and not legacy.writable:
                        raise EnrollmentConflict('A read-only course operation cannot write progress')
                    return await function(*args, **kwargs)
                if not versioning_enabled():
                    if expected_id:
                        raise EnrollmentConflict('This saved course requires versioned certification support; try again when it is available')
                    legacy = LegacyOperation(user_id, write)
                    token = legacy_operation.set(legacy)
                    try:
                        return await function(*args, **kwargs)
                    finally:
                        legacy.active = False
                        legacy_operation.reset(token)
                if write and not expected_id:
                    raise EnrollmentConflict('Reload certification progress and submit its enrollment_id with this action')
                repository = EnrollmentRepository()
                enrollment = await repository.ensure_initial(user_id)
                if expected_id and expected_id != enrollment.uuid:
                    raise EnrollmentConflict('The selected course changed; reload before submitting')
                package = repository.catalog.load(enrollment.course_version)

                async def run(progress):
                    token = _operation.set(CourseOperation(user_id, package, progress, write))
                    try:
                        return await function(*args, **kwargs)
                    finally:
                        _operation.reset(token)

                if write:
                    async with repository.write_boundary(user_id, enrollment.uuid, operation=function.__name__) as progress:
                        return await run(progress)
                return await run(await repository.read_progress(user_id, enrollment.uuid))
            except (CourseCatalogError, EnrollmentConflict) as exc:
                if tool:
                    return {'error': str(exc), 'hint': 'Reload certification progress before continuing.'}
                if http:
                    raise HTTPException(status_code=409 if isinstance(exc, EnrollmentConflict) else 503, detail=getattr(exc, 'detail', str(exc))) from exc
                raise

        return wrapped
    return decorate
