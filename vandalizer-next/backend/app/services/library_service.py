"""Library CRUD service  - libraries, items, folders, clone/fork, search."""

import datetime
import uuid as uuid_mod
from typing import Optional

from beanie import PydanticObjectId

from app.models.library import (
    Library,
    LibraryFolder,
    LibraryItem,
    LibraryItemKind,
    LibraryScope,
)
from app.models.search_set import SearchSet, SearchSetItem
from app.models.team import Team
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask


async def _resolve_team_oid(team_id: str) -> PydanticObjectId:
    """Resolve a team identifier (ObjectId string or UUID) to a PydanticObjectId.

    The Flask app stores team UUIDs (32-char hex) in some fields while Beanie
    expects 24-char BSON ObjectIds.  This helper tries both lookups.
    """
    # Try as a BSON ObjectId first (24-char hex)
    if len(team_id) == 24:
        try:
            oid = PydanticObjectId(team_id)
            team = await Team.get(oid)
            if team:
                return oid
        except Exception:
            pass

    # Fall back to UUID lookup
    team = await Team.find_one(Team.uuid == team_id)
    if team:
        return team.id

    raise ValueError(f"Team not found: {team_id}")


# ---------------------------------------------------------------------------
# Library CRUD
# ---------------------------------------------------------------------------


async def get_or_create_personal_library(user_id: str) -> Library:
    lib = await Library.find_one(
        Library.scope == LibraryScope.PERSONAL,
        Library.owner_user_id == user_id,
    )
    if lib:
        return lib
    now = datetime.datetime.now(datetime.timezone.utc)
    lib = Library(
        scope=LibraryScope.PERSONAL,
        title="My Library",
        owner_user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    await lib.insert()
    return lib


async def get_or_create_team_library(user_id: str, team_id: str) -> Library:
    team_oid = await _resolve_team_oid(team_id)
    lib = await Library.find_one(
        Library.scope == LibraryScope.TEAM,
        Library.team == team_oid,
    )
    if lib:
        return lib
    team = await Team.get(team_oid)
    now = datetime.datetime.now(datetime.timezone.utc)
    lib = Library(
        scope=LibraryScope.TEAM,
        title=f"{team.name} Library" if team else "Team Library",
        owner_user_id=user_id,
        team=team_oid,
        created_at=now,
        updated_at=now,
    )
    await lib.insert()
    return lib


async def list_libraries(user_id: str, team_id: str | None = None) -> list[dict]:
    personal = await get_or_create_personal_library(user_id)
    results = [_library_to_dict(personal)]

    if team_id:
        team_lib = await get_or_create_team_library(user_id, team_id)
        results.append(_library_to_dict(team_lib))

    return results


async def get_library(library_id: str, user_id: str) -> dict | None:
    lib = await Library.get(PydanticObjectId(library_id))
    if not lib:
        return None
    return _library_to_dict(lib)


async def update_library(
    library_id: str,
    user_id: str,
    title: str | None = None,
    description: str | None = None,
) -> dict | None:
    lib = await Library.get(PydanticObjectId(library_id))
    if not lib:
        return None
    if title is not None:
        lib.title = title
    if description is not None:
        lib.description = description
    lib.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await lib.save()
    return _library_to_dict(lib)


async def delete_library(library_id: str, user_id: str) -> bool:
    lib = await Library.get(PydanticObjectId(library_id))
    if not lib:
        return False
    # Cascade delete items
    for item_id in lib.items:
        item = await LibraryItem.get(item_id)
        if item:
            await item.delete()
    await lib.delete()
    return True


# ---------------------------------------------------------------------------
# Item management
# ---------------------------------------------------------------------------


async def add_item(
    library_id: str,
    user_id: str,
    item_id: str,
    kind: str,
    note: str | None = None,
    tags: list[str] | None = None,
    folder: str | None = None,
) -> dict | None:
    lib = await Library.get(PydanticObjectId(library_id))
    if not lib:
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    li = LibraryItem(
        item_id=PydanticObjectId(item_id),
        kind=LibraryItemKind(kind),
        added_by_user_id=user_id,
        note=note,
        tags=tags or [],
        folder=folder,
        created_at=now,
    )
    await li.insert()

    lib.items.append(li.id)
    lib.updated_at = now
    await lib.save()

    return await _dereference_item(li)


async def remove_item(library_id: str, item_id: str, user_id: str) -> bool:
    lib = await Library.get(PydanticObjectId(library_id))
    if not lib:
        return False
    item_oid = PydanticObjectId(item_id)
    lib.items = [i for i in lib.items if i != item_oid]
    lib.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await lib.save()

    item = await LibraryItem.get(item_oid)
    if item:
        await item.delete()
    return True


async def update_item(
    item_id: str,
    user_id: str,
    note: str | None = None,
    tags: list[str] | None = None,
    pinned: bool | None = None,
    favorited: bool | None = None,
) -> dict | None:
    item = await LibraryItem.get(PydanticObjectId(item_id))
    if not item:
        return None
    if note is not None:
        item.note = note
    if tags is not None:
        item.tags = tags
    if pinned is not None:
        item.pinned = pinned
    if favorited is not None:
        item.favorited = favorited
    await item.save()
    return await _dereference_item(item)


async def touch_item(item_id: str) -> bool:
    """Update the last_used_at timestamp for a library item."""
    item = await LibraryItem.get(PydanticObjectId(item_id))
    if not item:
        return False
    item.last_used_at = datetime.datetime.now(datetime.timezone.utc)
    await item.save()
    return True


async def get_library_items(
    library_id: str,
    user_id: str,
    kind: str | None = None,
    folder: str | None = None,
    search: str | None = None,
    user_group_uuids: list[str] | None = None,
) -> list[dict]:
    lib = await Library.get(PydanticObjectId(library_id))
    if not lib:
        return []

    items = await LibraryItem.find({"_id": {"$in": lib.items}}).to_list()

    if kind:
        items = [i for i in items if i.kind == kind]
    if folder is not None:
        items = [i for i in items if i.folder == folder]

    # For verified-scope libraries, import metadata for group filtering
    from app.models.verification import VerifiedItemMetadata

    results = []
    for item in items:
        deref = await _dereference_item(item)
        if deref:
            if search:
                name_lower = deref.get("name", "").lower()
                tags_str = " ".join(deref.get("tags", [])).lower()
                if search.lower() not in name_lower and search.lower() not in tags_str:
                    continue
            # Group filtering for verified items
            if user_group_uuids is not None and lib.scope == LibraryScope.VERIFIED and item.verified:
                meta = await VerifiedItemMetadata.find_one(
                    VerifiedItemMetadata.item_kind == item.kind.value,
                    VerifiedItemMetadata.item_id == str(item.item_id),
                )
                if meta and meta.group_ids and not (set(meta.group_ids) & set(user_group_uuids)):
                    continue
            results.append(deref)

    return results


# ---------------------------------------------------------------------------
# Clone / fork / share
# ---------------------------------------------------------------------------


async def clone_to_personal(item_id: str, user_id: str) -> dict | None:
    item = await LibraryItem.get(PydanticObjectId(item_id))
    if not item:
        return None

    new_obj_id = await _clone_underlying_object(item, user_id)
    if not new_obj_id:
        return None

    personal_lib = await get_or_create_personal_library(user_id)
    return await add_item(
        library_id=str(personal_lib.id),
        user_id=user_id,
        item_id=str(new_obj_id),
        kind=item.kind.value,
        note=f"Cloned from library item",
        tags=list(item.tags),
    )


async def share_to_team(item_id: str, user_id: str, team_id: str) -> dict | None:
    item = await LibraryItem.get(PydanticObjectId(item_id))
    if not item:
        return None

    new_obj_id = await _clone_underlying_object(item, user_id)
    if not new_obj_id:
        return None

    team_lib = await get_or_create_team_library(user_id, team_id)
    return await add_item(
        library_id=str(team_lib.id),
        user_id=user_id,
        item_id=str(new_obj_id),
        kind=item.kind.value,
        note=f"Shared to team",
        tags=list(item.tags),
    )


# ---------------------------------------------------------------------------
# Folder management
# ---------------------------------------------------------------------------


async def create_folder(
    scope: str,
    user_id: str,
    name: str,
    parent_id: str | None = None,
    team_id: str | None = None,
) -> dict:
    team_oid = await _resolve_team_oid(team_id) if team_id else None
    folder = LibraryFolder(
        uuid=str(uuid_mod.uuid4()),
        name=name,
        parent_id=parent_id,
        scope=LibraryScope(scope),
        owner_user_id=user_id,
        team=team_oid,
    )
    await folder.insert()
    return _folder_to_dict(folder)


async def rename_folder(folder_uuid: str, user_id: str, new_name: str) -> dict | None:
    folder = await LibraryFolder.find_one(LibraryFolder.uuid == folder_uuid)
    if not folder:
        return None
    folder.name = new_name
    await folder.save()
    return _folder_to_dict(folder)


async def delete_folder(folder_uuid: str, user_id: str) -> bool:
    folder = await LibraryFolder.find_one(LibraryFolder.uuid == folder_uuid)
    if not folder:
        return False
    # Move items in this folder to root
    items_in_folder = await LibraryItem.find(LibraryItem.folder == folder_uuid).to_list()
    for item in items_in_folder:
        item.folder = None
        await item.save()
    # Move child folders to root
    children = await LibraryFolder.find(LibraryFolder.parent_id == folder_uuid).to_list()
    for child in children:
        child.parent_id = None
        await child.save()
    await folder.delete()
    return True


async def move_items(item_ids: list[str], folder_uuid: str | None, user_id: str) -> bool:
    for iid in item_ids:
        item = await LibraryItem.get(PydanticObjectId(iid))
        if item:
            item.folder = folder_uuid
            await item.save()
    return True


async def list_folders(
    scope: str,
    user_id: str,
    team_id: str | None = None,
) -> list[dict]:
    query: dict = {"scope": scope, "owner_user_id": user_id}
    if team_id:
        query["team"] = await _resolve_team_oid(team_id)
    folders = await LibraryFolder.find(query).to_list()
    return [_folder_to_dict(f) for f in folders]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def search_libraries(
    user_id: str,
    query: str,
    team_id: str | None = None,
    kind: str | None = None,
) -> list[dict]:
    # Gather libraries to search
    personal = await get_or_create_personal_library(user_id)
    libs = [personal]
    if team_id:
        team_lib = await get_or_create_team_library(user_id, team_id)
        libs.append(team_lib)

    all_item_ids: list[PydanticObjectId] = []
    for lib in libs:
        all_item_ids.extend(lib.items)

    if not all_item_ids:
        return []

    items = await LibraryItem.find({"_id": {"$in": all_item_ids}}).to_list()
    if kind:
        items = [i for i in items if i.kind == kind]

    results = []
    for item in items:
        deref = await _dereference_item(item)
        if not deref:
            continue
        name_lower = deref.get("name", "").lower()
        tags_str = " ".join(deref.get("tags", [])).lower()
        note_str = (deref.get("note") or "").lower()
        if query.lower() in name_lower or query.lower() in tags_str or query.lower() in note_str:
            results.append(deref)

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _dereference_item(item: LibraryItem) -> dict | None:
    """Load the actual Workflow or SearchSet and return combined dict."""
    name = ""
    description = None

    set_type = None
    item_uuid = None

    if item.kind == LibraryItemKind.WORKFLOW:
        wf = await Workflow.get(item.item_id)
        if not wf:
            return None
        name = wf.name
        description = wf.description
    elif item.kind == LibraryItemKind.SEARCH_SET:
        ss = await SearchSet.get(item.item_id)
        if not ss:
            return None
        name = ss.title
        description = ss.extraction_config.get("content") if ss.extraction_config else None
        set_type = ss.set_type
        item_uuid = ss.uuid

    return {
        "id": str(item.id),
        "item_id": str(item.item_id),
        "item_uuid": item_uuid,
        "kind": item.kind.value,
        "name": name,
        "description": description,
        "set_type": set_type,
        "tags": item.tags,
        "note": item.note,
        "folder": item.folder,
        "pinned": item.pinned,
        "favorited": item.favorited,
        "verified": item.verified,
        "added_by_user_id": item.added_by_user_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None,
    }


async def _clone_underlying_object(item: LibraryItem, user_id: str) -> PydanticObjectId | None:
    """Clone the underlying workflow or search set. Returns new object ID."""
    if item.kind == LibraryItemKind.WORKFLOW:
        original = await Workflow.get(item.item_id)
        if not original:
            return None
        new_wf = Workflow(
            name=f"{original.name} (Copy)",
            description=original.description,
            user_id=user_id,
            created_by_user_id=user_id,
            space=original.space,
            input_config=original.input_config,
            output_config=original.output_config,
            resource_config=original.resource_config,
        )
        await new_wf.insert()

        # Clone steps and tasks
        new_step_ids = []
        for step_id in original.steps:
            step = await WorkflowStep.get(step_id)
            if not step:
                continue
            new_task_ids = []
            for task_id in step.tasks:
                task = await WorkflowStepTask.get(task_id)
                if task:
                    new_task = WorkflowStepTask(name=task.name, data=dict(task.data))
                    await new_task.insert()
                    new_task_ids.append(new_task.id)
            new_step = WorkflowStep(
                name=step.name,
                tasks=new_task_ids,
                data=dict(step.data),
                is_output=step.is_output,
            )
            await new_step.insert()
            new_step_ids.append(new_step.id)

        new_wf.steps = new_step_ids
        await new_wf.save()
        return new_wf.id

    elif item.kind == LibraryItemKind.SEARCH_SET:
        original = await SearchSet.get(item.item_id)
        if not original:
            return None
        new_uuid = str(uuid_mod.uuid4())
        new_ss = SearchSet(
            title=f"{original.title} (Copy)",
            uuid=new_uuid,
            space=original.space,
            status=original.status,
            set_type=original.set_type,
            user_id=user_id,
            extraction_config=dict(original.extraction_config),
            created_by_user_id=user_id,
        )
        await new_ss.insert()

        # Clone items
        orig_items = await original.get_items()
        for oi in orig_items:
            new_item = SearchSetItem(
                searchphrase=oi.searchphrase,
                searchset=new_uuid,
                searchtype=oi.searchtype,
                title=oi.title,
                user_id=user_id,
                space_id=oi.space_id,
            )
            await new_item.insert()

        return new_ss.id

    return None


def _library_to_dict(lib: Library) -> dict:
    return {
        "id": str(lib.id),
        "scope": lib.scope.value,
        "title": lib.title,
        "description": lib.description,
        "owner_user_id": lib.owner_user_id,
        "team_id": str(lib.team) if lib.team else None,
        "item_count": len(lib.items),
        "created_at": lib.created_at.isoformat() if lib.created_at else None,
        "updated_at": lib.updated_at.isoformat() if lib.updated_at else None,
    }


def _folder_to_dict(folder: LibraryFolder) -> dict:
    return {
        "uuid": folder.uuid,
        "name": folder.name,
        "parent_id": folder.parent_id,
        "scope": folder.scope.value,
    }
