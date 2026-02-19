from app.models.document import SmartDocument
from app.models.folder import SmartFolder


async def list_contents(
    space: str,
    folder: str | None = None,
    user_id: str | None = None,
    team_uuid: str | None = None,
) -> dict:
    folder_id = folder or "0"

    # Build folder query
    folder_query = {
        "space": space,
        "parent_id": folder_id,
    }
    folders = await SmartFolder.find(folder_query).to_list()

    # Also include team folders at root level
    team_folders = []
    if folder_id == "0" and team_uuid:
        team_folders = await SmartFolder.find(
            SmartFolder.team_id == team_uuid,
            SmartFolder.parent_id == "0",
            SmartFolder.space == space,
        ).to_list()
        # Merge, avoiding duplicates
        existing_uuids = {f.uuid for f in folders}
        for tf in team_folders:
            if tf.uuid not in existing_uuids:
                folders.append(tf)

    # Check if current folder is a team folder
    is_team_folder = False
    if folder_id != "0":
        current_folder = await SmartFolder.find_one(SmartFolder.uuid == folder_id)
        if current_folder and current_folder.team_id:
            is_team_folder = True

    # Build document query — team folders show all docs, personal folders filter by user
    if is_team_folder:
        documents = await SmartDocument.find(
            SmartDocument.space == space,
            SmartDocument.folder == folder_id,
        ).to_list()
    else:
        doc_filters = {"space": space, "folder": folder_id}
        if user_id:
            doc_filters["user_id"] = user_id
        documents = await SmartDocument.find(doc_filters).to_list()

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
                "token_count": d.token_count,
                "num_pages": d.num_pages,
            }
            for d in documents
        ],
    }


async def poll_status(doc_uuid: str) -> dict | None:
    doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
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
