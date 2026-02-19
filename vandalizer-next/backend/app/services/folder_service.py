import uuid

from app.models.document import SmartDocument
from app.models.folder import SmartFolder


async def create_folder(
    name: str,
    parent_id: str,
    space: str,
    user_id: str,
    team_id: str | None = None,
) -> SmartFolder:
    folder = SmartFolder(
        title=name,
        parent_id=parent_id,
        space=space,
        user_id=user_id if not team_id else None,
        team_id=team_id,
        uuid=uuid.uuid4().hex,
    )
    await folder.insert()
    return folder


async def rename_folder(folder_uuid: str, new_title: str) -> bool:
    folder = await SmartFolder.find_one(SmartFolder.uuid == folder_uuid)
    if not folder:
        return False
    folder.title = new_title
    await folder.save()
    return True


async def delete_folder(folder_uuid: str) -> bool:
    folder = await SmartFolder.find_one(SmartFolder.uuid == folder_uuid)
    if not folder:
        return False
    if folder.is_shared_team_root:
        raise ValueError("Shared team folders cannot be deleted.")

    # Delete folder, subfolders, and documents
    await SmartFolder.find(SmartFolder.uuid == folder_uuid).delete()
    await SmartFolder.find(SmartFolder.parent_id == folder_uuid).delete()
    await SmartDocument.find(SmartDocument.folder == folder_uuid).delete()
    return True


async def get_breadcrumbs(folder_uuid: str) -> list[dict]:
    crumbs = []
    current_id = folder_uuid
    while current_id and current_id != "0":
        folder = await SmartFolder.find_one(SmartFolder.uuid == current_id)
        if not folder:
            break
        crumbs.append({"uuid": folder.uuid, "title": folder.title})
        current_id = folder.parent_id
    crumbs.reverse()
    return crumbs
