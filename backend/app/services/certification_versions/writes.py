"""Database-enforced ownership for staged enrollment progress writes.

The fence lives outside the public progress model. It is never removed: each
release leaves a new value, so a delayed acquisition cannot reuse an old one.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from bson import ObjectId

from app.models.certification import CertificationProgress


@dataclass(frozen=True)
class WriteLease:
    user_id: str
    enrollment_id: str
    progress_id: str
    write_id: str

    def selection_filter(self):
        return {'user_id': self.user_id, 'active_enrollment_id': self.enrollment_id,
                'in_flight_writes': 1, 'active_write.id': self.write_id}

    def progress_filter(self):
        return {'_id': ObjectId(self.progress_id), 'user_id': self.user_id,
                '_certification_write_fence': self.write_id}


lease_context: ContextVar[WriteLease | None] = ContextVar('certification_write_lease', default=None)


def closed_fence(write_id):
    return uuid5(NAMESPACE_URL, 'vandalizer:certification:closed:' + write_id).hex


def require_lease(user_id, enrollment_id):
    from .enrollments import EnrollmentConflict
    lease = lease_context.get()
    if lease is None or (lease.user_id, lease.enrollment_id) != (user_id, enrollment_id):
        raise EnrollmentConflict('This operation does not hold the enrollment write boundary')
    return lease


def progress_filter(progress):
    from .enrollments import EnrollmentConflict
    lease = require_lease(progress.user_id, progress.enrollment_id)
    if str(progress.id) != lease.progress_id:
        raise EnrollmentConflict('This progress record does not belong to the write boundary')
    return lease.progress_filter()


async def save_progress(progress):
    """All staged progress saves compare ownership in the same Mongo write."""
    from .enrollments import EnrollmentConflict
    if lease_context.get() is None and not getattr(progress, 'enrollment_id', None):
        from .legacy_writes import save_progress as save_legacy_progress
        return await save_legacy_progress(progress)
    result = await CertificationProgress.get_motor_collection().update_one(
        progress_filter(progress),
        {'$set': progress.model_dump(mode='python', by_alias=True, exclude={'id', 'revision_id'})},
    )
    if result.matched_count != 1:
        raise EnrollmentConflict('This worker no longer owns the enrollment; reload the saved result')
    return progress
