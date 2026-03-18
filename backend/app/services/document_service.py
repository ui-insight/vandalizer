from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.user import User
from app.services import access_control


async def list_contents(
    *,
    user: User,
    folder: str | None = None,
    team_uuid: str | None = None,
) -> dict:
    folder_id = folder or "0"
    team_access = await access_control.get_team_access_context(user)

    folders: list[SmartFolder] = []
    documents: list[SmartDocument] = []

    if folder_id != "0":
        current_folder = await access_control.get_authorized_folder(
            folder_id, user, team_access=team_access
        )
        if not current_folder:
            return {"folders": [], "documents": []}

        if current_folder.team_id:
            folders = await SmartFolder.find(
                SmartFolder.parent_id == current_folder.uuid,
                SmartFolder.team_id == current_folder.team_id,
            ).to_list()
            documents = await SmartDocument.find(
                {
                    "folder": current_folder.uuid,
                    "team_id": current_folder.team_id,
                    "soft_deleted": {"$ne": True},
                }
            ).to_list()
        else:
            folders = await SmartFolder.find(
                SmartFolder.parent_id == current_folder.uuid,
                SmartFolder.user_id == user.user_id,
            ).to_list()
            documents = await SmartDocument.find(
                {
                    "folder": current_folder.uuid,
                    "user_id": user.user_id,
                    "soft_deleted": {"$ne": True},
                }
            ).to_list()
    else:
        folders = await SmartFolder.find(
            SmartFolder.parent_id == "0",
            SmartFolder.user_id == user.user_id,
        ).to_list()
        if team_uuid and (team_uuid in team_access.team_uuids or user.is_admin):
            team_folders = await SmartFolder.find(
                SmartFolder.parent_id == "0",
                SmartFolder.team_id == team_uuid,
            ).to_list()
            existing_uuids = {f.uuid for f in folders}
            for folder_doc in team_folders:
                if folder_doc.uuid not in existing_uuids:
                    folders.append(folder_doc)

        documents = await SmartDocument.find(
            {
                "folder": "0",
                "user_id": user.user_id,
                "soft_deleted": {"$ne": True},
            }
        ).to_list()

    return {
        "folders": [
            {
                "id": str(f.id),
                "title": f.title,
                "uuid": f.uuid,
                "parent_id": f.parent_id,
                "is_shared_team_root": f.is_shared_team_root,
                "team_id": f.team_id,
            }
            for f in folders
        ],
        "documents": [
            {
                "id": str(d.id),
                "title": d.title,
                "uuid": d.uuid,
                "extension": d.extension,
                "processing": d.processing,
                "valid": d.valid,
                "task_status": d.task_status,
                "folder": d.folder,
                "created_at": d.created_at.isoformat() if d.created_at else "",
                "updated_at": d.updated_at.isoformat() if d.updated_at else "",
                "token_count": d.token_count,
                "num_pages": d.num_pages,
                "classification": d.classification,
                "classification_confidence": d.classification_confidence,
                "classified_at": d.classified_at.isoformat() if d.classified_at else None,
                "classified_by": d.classified_by,
                "retention_hold": d.retention_hold,
                "soft_deleted": d.soft_deleted,
            }
            for d in documents
        ],
    }

async def poll_status(doc_uuid: str, user: User) -> dict | None:
    doc = await access_control.get_authorized_document(doc_uuid, user)
    if not doc:
        return None

    status_messages = []
    if doc.task_status == "readying":
        status_messages.append("Getting ready...")
        if doc.valid:
            status_messages.append("Document passed validation checks...")
        else:
            status_messages.append("Document failed validation checks...")

    complete = doc.task_status in ("complete", "error")

    return {
        "status": doc.task_status,
        "status_messages": status_messages,
        "complete": complete,
        "raw_text": doc.raw_text if not doc.processing else "",
        "validation_feedback": doc.validation_feedback,
        "valid": doc.valid,
        "path": doc.path,
    }
