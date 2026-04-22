import uuid

from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.user import User
from app.services import access_control


async def create_folder(
    name: str,
    parent_id: str,
    user: User,
    requested_team_id: str | None = None,
) -> SmartFolder:
    parent_folder: SmartFolder | None = None
    if parent_id != "0":
        parent_folder = await access_control.get_authorized_folder(parent_id, user)
        if not parent_folder:
            raise ValueError("Parent folder not found.")

    effective_team_id = requested_team_id
    if parent_folder:
        if parent_folder.team_id:
            effective_team_id = parent_folder.team_id
        elif requested_team_id:
            raise ValueError("Cannot create a team folder inside a personal folder.")
    elif requested_team_id:
        access = await access_control.get_team_access_context(user)
        if requested_team_id not in access.team_uuids and not user.is_admin:
            raise ValueError("Not a member of this team.")

    folder = SmartFolder(
        title=name,
        parent_id=parent_id,
        user_id=user.user_id if not effective_team_id else None,
        team_id=effective_team_id,
        created_by=user.user_id,
        uuid=uuid.uuid4().hex,
    )
    await folder.insert()
    return folder


async def rename_folder(folder_uuid: str, new_title: str, user: User) -> bool:
    folder = await access_control.get_authorized_folder(folder_uuid, user, manage=True)
    if not folder:
        return False
    folder.title = new_title
    await folder.save()
    return True


async def delete_folder(folder_uuid: str, user: User) -> bool:
    folder = await access_control.get_authorized_folder(folder_uuid, user, manage=True)
    if not folder:
        return False
    if folder.is_shared_team_root:
        raise ValueError("Shared team folders cannot be deleted.")

    folder_uuids = [folder_uuid]
    frontier = [folder_uuid]
    while frontier:
        children = await SmartFolder.find({"parent_id": {"$in": frontier}}).to_list()
        frontier = [child.uuid for child in children]
        folder_uuids.extend(frontier)

    await SmartFolder.find({"uuid": {"$in": folder_uuids}}).delete()
    await SmartDocument.find({"folder": {"$in": folder_uuids}}).delete()
    return True


async def convert_to_team_folder(folder_uuid: str, user: User) -> SmartFolder:
    """Convert a personal folder (and all its descendants) to a team folder."""
    folder = await access_control.get_authorized_folder(folder_uuid, user, manage=True)
    if not folder:
        raise ValueError("Folder not found.")
    if folder.team_id:
        raise ValueError("Folder is already a team folder.")
    if not user.current_team:
        raise ValueError("You are not on a team.")

    from app.models.team import Team

    team = await Team.get(user.current_team)
    if not team:
        raise ValueError("Team not found.")

    team_access = await access_control.get_team_access_context(user)
    if team.uuid not in team_access.team_uuids and not user.is_admin:
        raise ValueError("Not a member of this team.")

    # Collect this folder and all descendants
    folder_uuids = [folder_uuid]
    frontier = [folder_uuid]
    while frontier:
        children = await SmartFolder.find({"parent_id": {"$in": frontier}}).to_list()
        frontier = [child.uuid for child in children]
        folder_uuids.extend(frontier)

    # Update all folders to team ownership
    await SmartFolder.find({"uuid": {"$in": folder_uuids}}).update(
        {"$set": {"team_id": team.uuid, "user_id": None}}
    )

    # Update all documents in those folders to team ownership
    await SmartDocument.find({"folder": {"$in": folder_uuids}}).update(
        {"$set": {"team_id": team.uuid}}
    )

    # Refresh and return
    folder = await SmartFolder.find_one(SmartFolder.uuid == folder_uuid)
    return folder


async def get_breadcrumbs(folder_uuid: str, user: User) -> list[dict] | None:
    current = await access_control.get_authorized_folder(folder_uuid, user)
    if not current:
        return None

    crumbs = []
    current_id = current.uuid
    while current_id and current_id != "0":
        folder = await access_control.get_authorized_folder(current_id, user)
        if not folder:
            break
        crumbs.append({"uuid": folder.uuid, "title": folder.title})
        current_id = folder.parent_id
    crumbs.reverse()
    return crumbs
