"""Stable lab-folder creation without a process lock or expiring ownership lease."""
import hashlib
import json

from bson import ObjectId
from pymongo import ReturnDocument

from app.models.certification import CertificationProgress
from app.models.folder import SmartFolder
from app.models.user import User
from .enrollments import EnrollmentConflict


async def ensure_lab_folder(user: User, progress: CertificationProgress, title: str) -> SmartFolder:
    """Reuse the same creation identity after a race or an unknown insert result.

    Existing assigned folders are resolved by the caller first. This only governs
    new personal root labs; document upload/queue idempotency is a separate gate.
    """
    if not progress.id or progress.user_id != user.user_id:
        raise EnrollmentConflict('Lab creation requires its original learner progress')
    identity = hashlib.sha256(json.dumps([
        'vandalizer:certification-lab-folder:v1', user.user_id, str(progress.id),
        progress.enrollment_id or 'unversioned',
    ], separators=(',', ':')).encode()).hexdigest()
    folder = SmartFolder(id=ObjectId(identity[:24]), uuid=identity[:32], title=title,
                         parent_id='0', user_id=user.user_id, created_by=user.user_id)
    values = folder.model_dump(mode='python', by_alias=True, exclude={'revision_id'})
    values['_certification_lab_identity'] = identity
    # Mongo's built-in _id uniqueness arbitrates competing workers. Replaying
    # only inserts if absent; it never renames, moves or transfers an existing lab.
    raw = await SmartFolder.get_motor_collection().find_one_and_update(
        {'_id': folder.id}, {'$setOnInsert': values}, upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if (raw is None or raw.get('_certification_lab_identity') != identity
            or raw.get('uuid') != folder.uuid or raw.get('user_id') != user.user_id
            or raw.get('team_id') is not None or raw.get('created_by') != user.user_id):
        raise EnrollmentConflict('The original lab creation identity is no longer available')
    return SmartFolder.model_validate(raw)
