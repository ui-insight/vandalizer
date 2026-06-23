import logging
import re
import uuid

from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.user import User
from app.services import access_control

logger = logging.getLogger(__name__)


def _safe_component(name: str) -> str:
    """Make a folder/file title safe to use as a single zip path segment."""
    cleaned = re.sub(r'[/\\:*?"<>|]', "_", name or "").strip()
    return cleaned or "untitled"


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


async def move_folder(folder_uuid: str, new_parent_id: str, user: User) -> SmartFolder:
    """Reparent a folder under ``new_parent_id`` ("0" == top level).

    Guards against the three ways a move can corrupt the tree:
      * moving a folder into itself or one of its own descendants (cycle),
      * moving the immovable shared team root,
      * crossing the personal/team ownership boundary (use convert-to-team
        for that), which would otherwise silently re-own a whole subtree.
    """
    folder = await access_control.get_authorized_folder(folder_uuid, user, manage=True)
    if not folder:
        raise ValueError("Folder not found.")
    if folder.is_shared_team_root:
        raise ValueError("Shared team folders cannot be moved.")

    dest_team_id: str | None = None
    if new_parent_id != "0":
        parent = await access_control.get_authorized_folder(new_parent_id, user, manage=True)
        if not parent:
            raise ValueError("Destination folder not found.")
        dest_team_id = parent.team_id

        # Reject moving into self or any descendant.
        descendants = {folder_uuid}
        frontier = [folder_uuid]
        while frontier:
            children = await SmartFolder.find({"parent_id": {"$in": frontier}}).to_list()
            frontier = [child.uuid for child in children]
            descendants.update(frontier)
        if new_parent_id in descendants:
            raise ValueError("Cannot move a folder into itself or one of its subfolders.")

    if folder.team_id != dest_team_id:
        raise ValueError(
            "Cannot move a folder across personal and team ownership. "
            "Use 'Convert to team folder' instead."
        )

    old_parent_id = folder.parent_id
    folder.parent_id = new_parent_id
    await folder.save()

    # Re-sync project knowledge-base membership for every document in the moved
    # subtree (moving a folder into/out of a project changes the owning project
    # for all docs under it). Best-effort, async via Celery.
    if old_parent_id != new_parent_id:
        try:
            from app.tasks.document_tasks import sync_project_kb_on_folder_move

            sync_project_kb_on_folder_move.delay(folder_uuid, old_parent_id)
        except Exception:
            logger.warning(
                "Failed to dispatch project KB sync for moved folder %s", folder_uuid
            )

    return folder


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


async def collect_export_entries(
    folder_uuid: str, user: User
) -> tuple[str, list[tuple[str, str]]] | None:
    """Plan a zip export of a folder subtree.

    Returns ``(root_title, [(path_prefix, doc_uuid), ...])`` where each prefix
    is the document's folder path relative to the export root (e.g.
    ``"Subfolder/"`` or ``""`` for the root). Per-document authorization is
    still enforced at download time, so candidates here are filtered to the
    requested (already authorized) subtree only. Returns ``None`` if the root
    folder is missing or not viewable.
    """
    root = await access_control.get_authorized_folder(folder_uuid, user)
    if not root:
        return None

    folders_by_uuid: dict[str, SmartFolder] = {root.uuid: root}
    frontier = [root.uuid]
    while frontier:
        children = await SmartFolder.find({"parent_id": {"$in": frontier}}).to_list()
        frontier = []
        for child in children:
            folders_by_uuid[child.uuid] = child
            frontier.append(child.uuid)

    def path_prefix(folder: SmartFolder) -> str:
        parts: list[str] = []
        current = folder
        while current.uuid != root.uuid:
            parts.append(_safe_component(current.title))
            parent = folders_by_uuid.get(current.parent_id)
            if parent is None:
                break
            current = parent
        return "/".join(reversed(parts)) + "/" if parts else ""

    docs = await SmartDocument.find(
        {"folder": {"$in": list(folders_by_uuid)}}
    ).to_list()
    entries = [
        (path_prefix(folders_by_uuid[d.folder]), d.uuid)
        for d in docs
        if d.folder in folders_by_uuid
    ]
    return root.title, entries


async def expand_folders_to_document_uuids(
    folder_uuids: list[str], user: User
) -> list[str]:
    """Resolve a set of folders to the UUIDs of all viewable documents within
    them, recursing through subfolders.

    Each root folder must be viewable by the user (raises ValueError otherwise);
    documents are additionally filtered by per-document view access. Returns a
    de-duplicated, order-preserving list. Used by "Run workflow on folder" and
    "Add folder to knowledge base".
    """
    team_access = await access_control.get_team_access_context(user)

    folder_uuid_set: list[str] = []
    seen_folders: set[str] = set()
    for root_uuid in folder_uuids:
        root = await access_control.get_authorized_folder(
            root_uuid, user, team_access=team_access, allow_admin=True
        )
        if not root:
            raise ValueError(f"Folder not found: {root_uuid}")
        # Walk the subtree rooted here; descendants share the root's ownership.
        frontier = [root.uuid]
        while frontier:
            for fid in frontier:
                if fid not in seen_folders:
                    seen_folders.add(fid)
                    folder_uuid_set.append(fid)
            children = await SmartFolder.find(
                {"parent_id": {"$in": frontier}}
            ).to_list()
            frontier = [c.uuid for c in children if c.uuid not in seen_folders]

    docs = await SmartDocument.find(
        {"folder": {"$in": folder_uuid_set}}
    ).to_list()
    result: list[str] = []
    seen_docs: set[str] = set()
    for doc in docs:
        if doc.uuid in seen_docs:
            continue
        if access_control.can_view_document(doc, user, team_access, allow_admin=True):
            result.append(doc.uuid)
            seen_docs.add(doc.uuid)
    return result


async def convert_to_personal_folder(
    folder_uuid: str, user: User, *, owner_user_id: str | None = None
) -> SmartFolder:
    """Convert a team folder (and all its descendants) back to personal ownership.

    Inverse of ``convert_to_team_folder``. ``owner_user_id`` is who the folder
    and its documents revert to (defaults to the acting user) — the project flow
    passes the project owner so an admin acting on their behalf doesn't claim it.
    """
    folder = await access_control.get_authorized_folder(folder_uuid, user, manage=True)
    if not folder:
        raise ValueError("Folder not found.")
    if not folder.team_id:
        raise ValueError("Folder is already personal.")
    target_user_id = owner_user_id or user.user_id

    # Collect this folder and all descendants
    folder_uuids = [folder_uuid]
    frontier = [folder_uuid]
    while frontier:
        children = await SmartFolder.find({"parent_id": {"$in": frontier}}).to_list()
        frontier = [child.uuid for child in children]
        folder_uuids.extend(frontier)

    await SmartFolder.find({"uuid": {"$in": folder_uuids}}).update(
        {"$set": {"team_id": None, "user_id": target_user_id}}
    )
    await SmartDocument.find({"folder": {"$in": folder_uuids}}).update(
        {"$set": {"team_id": None, "user_id": target_user_id}}
    )

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
