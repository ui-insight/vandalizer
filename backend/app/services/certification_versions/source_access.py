"""Current source reads require ownership and the application's project ACL.

The authenticated course operation supplies the learner identity. Staff/admin
privileges never substitute for that learner's access to new training evidence.
Previously captured assessment history remains a separate immutable record.
"""
from app.models.user import User
from app.services.access_control import get_authorized_document


async def owned_source(user_id, document_id, *, lab_folder_id=None):
    document = await get_authorized_document(document_id, User(user_id=user_id))
    if document is None or document.user_id != user_id or document.soft_deleted:
        return None
    if lab_folder_id is not None and document.folder != lab_folder_id:
        return None
    return document
