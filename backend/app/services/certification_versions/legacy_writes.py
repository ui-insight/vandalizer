"""Optimistic write protection for the unversioned continuation path.

No expiring lock or staff recovery queue: a stale worker cannot overwrite a
newer record, and a fresh explicit request reads the saved state again.
"""
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationProgress


@dataclass
class LegacyOperation:
    user_id: str
    writable: bool
    active: bool = True
    progress: CertificationProgress | None = None
    snapshot: dict | None = None


legacy_operation: ContextVar[LegacyOperation | None] = ContextVar('legacy_certification_operation', default=None)


async def read_progress(user_id: str) -> CertificationProgress:
    from .enrollments import EnrollmentConflict
    operation = legacy_operation.get()
    if operation is None or not operation.active or operation.user_id != user_id:
        raise EnrollmentConflict('Legacy progress requires its original learner context')
    if operation.progress is not None:
        return operation.progress
    collection = CertificationProgress.get_motor_collection()
    records = await collection.find({'user_id': user_id}).limit(2).to_list(2)
    if not records:
        # A deterministic ID prevents parallel first reads from inserting two
        # unversioned records without imposing a user-unique index on enrollments.
        identity = ObjectId(sha256(('vandalizer:legacy-certification:' + user_id).encode()).hexdigest()[:24])
        progress = CertificationProgress(id=identity, user_id=user_id)
        try:
            await progress.insert()
        except DuplicateKeyError:
            pass
        records = await collection.find({'user_id': user_id}).limit(2).to_list(2)
    if len(records) != 1:
        raise EnrollmentConflict('Legacy progress is ambiguous or unavailable; reconcile the saved course before continuing')
    snapshot = records[0]
    if operation.writable and (snapshot.get('enrollment_id') or snapshot.get('course_version') or '_certification_write_fence' in snapshot):
        raise EnrollmentConflict('This saved course requires its enrollment write boundary; reload certification progress')
    operation.snapshot = deepcopy(snapshot)
    operation.progress = CertificationProgress.model_validate(snapshot)
    return operation.progress


async def save_progress(progress: CertificationProgress):
    from .enrollments import EnrollmentConflict
    operation = legacy_operation.get()
    if operation is None or not operation.active or not operation.writable or operation.progress is not progress or operation.snapshot is None:
        raise EnrollmentConflict('Reload legacy progress before saving this action')
    snapshot = operation.snapshot
    values = progress.model_dump(mode='python', by_alias=True, exclude={'id', 'revision_id'})
    if progress.user_id != operation.user_id or progress.id != snapshot['_id'] or progress.enrollment_id or progress.course_version:
        raise EnrollmentConflict('The original learner or course binding changed')
    revision = snapshot.get('_legacy_progress_revision', 0)
    if type(revision) is not int or revision < 0:
        raise EnrollmentConflict('The saved legacy progress revision is invalid')
    expected = {key: snapshot[key] if key in snapshot else {'$exists': False} for key in values}
    expected.update({'_id': snapshot['_id'], '_certification_write_fence': {'$exists': False},
                     '_legacy_progress_revision': snapshot.get('_legacy_progress_revision', {'$exists': False})})
    result = await CertificationProgress.get_motor_collection().update_one(
        expected, {'$set': values, '$inc': {'_legacy_progress_revision': 1}},
    )
    if result.matched_count != 1:
        raise EnrollmentConflict('Progress changed while this action was running. Refresh course progress before retrying.')
    operation.snapshot = {**snapshot, **values, '_legacy_progress_revision': revision + 1}
    return progress
