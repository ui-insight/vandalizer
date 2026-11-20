"""Pin one enrollment across nested service/tool calls for a single operation."""
from collections.abc import Awaitable, Callable
from typing import Literal, ParamSpec, TypeVar, TypedDict, overload

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


P = ParamSpec('P')
R = TypeVar('R')


class CourseToolError(TypedDict):
    error: str
    hint: str


@overload
def course_operation(
    *, write: bool = False, http: bool = False, tool: Literal[False] = False,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]: ...


@overload
def course_operation(
    *, write: bool = False, http: bool = False, tool: Literal[True],
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R | CourseToolError]]]: ...


def course_operation(
    *, write: bool = False, http: bool = False, tool: bool = False,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R | CourseToolError]]]:
    """Bind at the outer boundary; nested calls cannot change user or course.

    Disabled by default until rollout verification. The enrollment_id argument
    is optional for initial reads and required by clients submitting old cards
    once upgrades are exposed; a supplied stale identity always fails closed.
    """
    def decorate(function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | CourseToolError]]:
        signature = inspect.signature(function)

        @wraps(function)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R | CourseToolError:
            try:
                bound = signature.bind(*args, **kwargs).arguments
                principal = bound.get('context') or bound.get('user') or bound.get('user_id')
                if isinstance(principal, str):
                    principal_user_id: object = principal
                else:
                    principal_user_id = getattr(getattr(principal, 'deps', principal), 'user_id', None)
                if not isinstance(principal_user_id, str) or not principal_user_id:
                    raise EnrollmentConflict('A course operation requires an authenticated learner')
                user_id = principal_user_id
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

                async def run(progress: CertificationProgress) -> R:
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
