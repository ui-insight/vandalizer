"""Library CRUD service  - libraries, items, folders, clone/fork, search."""

from __future__ import annotations

import datetime
import uuid as uuid_mod
from typing import TYPE_CHECKING, Optional

from beanie import PydanticObjectId
from bson import ObjectId as BsonObjectId

from app.models.library import (
    Library,
    LibraryFolder,
    LibraryItem,
    LibraryItemKind,
    LibraryScope,
)
from app.models.search_set import SearchSet, SearchSetItem
from app.models.system_config import SystemConfig
from app.models.team import Team
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask
from app.services import access_control

if TYPE_CHECKING:
    from app.models.user import User


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


async def get_or_create_verified_library() -> Library:
    """Return the global verified library, creating and backfilling if needed."""
    lib = await Library.find_one(Library.scope == LibraryScope.VERIFIED)
    if not lib:
        now = datetime.datetime.now(datetime.timezone.utc)
        lib = Library(
            scope=LibraryScope.VERIFIED,
            title="Verified Library",
            owner_user_id="system",
            created_at=now,
            updated_at=now,
        )
        await lib.insert()

    # Backfill: if the library is empty, populate from all verified LibraryItems
    if not lib.items:
        await _backfill_verified_library(lib)

    return lib


async def _backfill_verified_library(lib: Library) -> None:
    """Populate the verified library from all existing verified LibraryItems."""
    verified_items = await LibraryItem.find(LibraryItem.verified == True).to_list()  # noqa: E712
    if not verified_items:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    seen: set[tuple[str, str]] = set()
    for item in verified_items:
        key = (str(item.item_id), item.kind.value)
        if key in seen:
            continue
        seen.add(key)
        new_item = LibraryItem(
            item_id=item.item_id,
            kind=item.kind,
            added_by_user_id="system",
            verified=True,
            tags=[],
            created_at=now,
        )
        await new_item.insert()
        lib.items.append(new_item.id)

    if lib.items:
        lib.updated_at = now
        await lib.save()


async def list_libraries(user: User, team_id: str | None = None) -> list[dict]:
    personal = await get_or_create_personal_library(user.user_id)
    results = [_library_to_dict(personal)]

    if team_id:
        try:
            team_oid = await _resolve_team_oid(team_id)
        except ValueError:
            team_oid = None
        if team_oid:
            team_access = await access_control.get_team_access_context(user)
            if access_control.can_view_team(str(team_oid), team_access):
                team_lib = await get_or_create_team_library(user.user_id, team_id)
                results.append(_library_to_dict(team_lib))

    verified = await get_or_create_verified_library()
    results.append(_library_to_dict(verified))

    return results


async def get_library(library_id: str, user: User) -> dict | None:
    lib = await access_control.get_authorized_library(library_id, user)
    if not lib:
        return None
    return _library_to_dict(lib)


async def update_library(
    library_id: str,
    user: User,
    title: str | None = None,
    description: str | None = None,
) -> dict | None:
    lib = await access_control.get_authorized_library(library_id, user, manage=True)
    if not lib:
        return None
    if title is not None:
        lib.title = title
    if description is not None:
        lib.description = description
    lib.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await lib.save()
    return _library_to_dict(lib)


async def delete_library(library_id: str, user: User) -> bool:
    lib = await access_control.get_authorized_library(library_id, user, manage=True)
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
    user: User,
    item_id: str,
    kind: str,
    note: str | None = None,
    tags: list[str] | None = None,
    folder: str | None = None,
) -> dict | None:
    lib = await access_control.get_authorized_library(library_id, user, manage=True)
    if not lib:
        return None
    if kind == LibraryItemKind.WORKFLOW.value:
        if not await access_control.get_authorized_workflow(item_id, user):
            return None
    elif kind == LibraryItemKind.SEARCH_SET.value:
        try:
            search_set = await SearchSet.get(PydanticObjectId(item_id))
        except Exception:
            search_set = None
        if not search_set or not await access_control.get_authorized_search_set(search_set.uuid, user):
            return None
    else:
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    li = LibraryItem(
        item_id=PydanticObjectId(item_id),
        kind=LibraryItemKind(kind),
        added_by_user_id=user.user_id,
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


async def remove_item(library_id: str, item_id: str, user: User) -> bool:
    lib = await access_control.get_authorized_library(library_id, user, manage=True)
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
    user: User,
    note: str | None = None,
    tags: list[str] | None = None,
    pinned: bool | None = None,
    favorited: bool | None = None,
) -> dict | None:
    item = await access_control.get_authorized_library_item(item_id, user, manage=True)
    if not item:
        return None
    # Use targeted $set to avoid overwriting fields on old documents
    # that Pydantic filled with defaults (e.g. created_at → "now").
    updates: dict = {}
    if note is not None:
        updates[LibraryItem.note] = note
        item.note = note
    if tags is not None:
        updates[LibraryItem.tags] = tags
        item.tags = tags
    if pinned is not None:
        updates[LibraryItem.pinned] = pinned
        item.pinned = pinned
    if favorited is not None:
        updates[LibraryItem.favorited] = favorited
        item.favorited = favorited
    if updates:
        await item.set(updates)
    return await _dereference_item(item)


async def touch_item(item_id: str, user: User) -> bool:
    """Update the last_used_at timestamp for a library item."""
    item = await access_control.get_authorized_library_item(item_id, user)
    if not item:
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    await item.set({LibraryItem.last_used_at: now})
    return True


async def get_library_items(
    library_id: str,
    user: User,
    kind: str | None = None,
    folder: str | None = None,
    search: str | None = None,
    user_org_ancestry: list[str] | None = None,
) -> list[dict]:
    lib = await access_control.get_authorized_library(library_id, user)
    if not lib:
        return []

    items = await LibraryItem.find({"_id": {"$in": lib.items}}).to_list()

    if kind:
        items = [i for i in items if i.kind.value == kind]
    if folder is not None:
        items = [i for i in items if i.folder == folder]

    # Import metadata for org visibility filtering and quality data
    from app.models.verification import VerifiedItemMetadata
    from app.services.quality_service import get_latest_validation, compute_quality_tier

    results = []
    for item in items:
        deref = await _dereference_item(item)
        if deref:
            if search:
                name_lower = deref.get("name", "").lower()
                tags_str = " ".join(deref.get("tags", [])).lower()
                if search.lower() not in name_lower and search.lower() not in tags_str:
                    continue

            # Look up quality metadata for all scopes
            # Validation stores item_id as the UUID for search sets,
            # so use item_uuid when available.
            quality_lookup_id = deref.get("item_uuid") or str(item.item_id)
            meta = await VerifiedItemMetadata.find_one(
                VerifiedItemMetadata.item_kind == item.kind.value,
                VerifiedItemMetadata.item_id == quality_lookup_id,
            )

            # Org visibility filtering for verified-scope libraries
            if lib.scope == LibraryScope.VERIFIED and item.verified:
                if user_org_ancestry is not None and meta and meta.organization_ids and not (set(meta.organization_ids) & set(user_org_ancestry)):
                    continue

            # Attach quality metadata for all scopes
            if meta:
                deref["quality_tier"] = meta.quality_tier
                deref["quality_score"] = meta.quality_score
                deref["last_validated_at"] = meta.last_validated_at.isoformat() if meta.last_validated_at else None
            else:
                # Fall back to latest ValidationRun
                latest = await get_latest_validation(item.kind.value, quality_lookup_id)
                if latest:
                    score = latest.get("score")
                    deref["quality_score"] = score
                    sys_cfg = await SystemConfig.get_config()
                    deref["quality_tier"] = compute_quality_tier(score, sys_cfg.get_quality_config())
                    deref["last_validated_at"] = latest.get("created_at")

            results.append(deref)

    return results


# ---------------------------------------------------------------------------
# Clone / fork / share
# ---------------------------------------------------------------------------


async def clone_to_personal(item_id: str, user: User) -> dict | None:
    item = await access_control.get_authorized_library_item(item_id, user)
    if not item:
        return None

    new_obj_id = await _clone_underlying_object(item, user.user_id, team_id=None)
    if not new_obj_id:
        return None

    personal_lib = await get_or_create_personal_library(user.user_id)
    return await add_item(
        library_id=str(personal_lib.id),
        user=user,
        item_id=str(new_obj_id),
        kind=item.kind.value,
        note=f"Cloned from library item",
        tags=list(item.tags),
    )


async def share_to_team(item_id: str, user: User, team_id: str) -> dict | None:
    item = await access_control.get_authorized_library_item(item_id, user)
    if not item:
        return None

    team_access = await access_control.get_team_access_context(user)
    try:
        team_oid = await _resolve_team_oid(team_id)
    except ValueError:
        return None
    if not access_control.can_manage_team(str(team_oid), team_access):
        return None

    new_obj_id = await _clone_underlying_object(item, user.user_id, team_id=team_id)
    if not new_obj_id:
        return None

    team_lib = await get_or_create_team_library(user.user_id, team_id)
    return await add_item(
        library_id=str(team_lib.id),
        user=user,
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
    user: User,
    name: str,
    parent_id: str | None = None,
    team_id: str | None = None,
) -> dict:
    team_oid = None
    if scope == LibraryScope.TEAM.value:
        if not team_id:
            raise ValueError("team_id is required for team folders")
        team_oid = await _resolve_team_oid(team_id)
        team_access = await access_control.get_team_access_context(user)
        if not access_control.can_manage_team(str(team_oid), team_access):
            raise ValueError("Team not accessible")

    if parent_id:
        parent = await access_control.get_authorized_library_folder(parent_id, user)
        if not parent or parent.scope.value != scope:
            raise ValueError("Parent folder not found")

    folder = LibraryFolder(
        uuid=str(uuid_mod.uuid4()),
        name=name,
        parent_id=parent_id,
        scope=LibraryScope(scope),
        owner_user_id=user.user_id,
        team=team_oid,
    )
    await folder.insert()
    return _folder_to_dict(folder)


async def rename_folder(folder_uuid: str, user: User, new_name: str) -> dict | None:
    folder = await access_control.get_authorized_library_folder(folder_uuid, user, manage=True)
    if not folder:
        return None
    folder.name = new_name
    await folder.save()
    item_count = await LibraryItem.find(LibraryItem.folder == folder_uuid).count()
    return _folder_to_dict(folder, item_count=item_count)


async def delete_folder(folder_uuid: str, user: User) -> bool:
    folder = await access_control.get_authorized_library_folder(folder_uuid, user, manage=True)
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


async def move_items(item_ids: list[str], folder_uuid: str | None, user: User) -> bool:
    target_folder = None
    if folder_uuid:
        target_folder = await access_control.get_authorized_library_folder(
            folder_uuid,
            user,
            manage=True,
        )
        if not target_folder:
            return False
    for iid in item_ids:
        item = await access_control.get_authorized_library_item(iid, user, manage=True)
        if item:
            if target_folder and item.folder == folder_uuid:
                continue
            item.folder = folder_uuid
            await item.save()
    return True


async def list_folders(
    scope: str,
    user: User,
    team_id: str | None = None,
) -> list[dict]:
    query: dict = {"scope": scope}
    if scope == LibraryScope.TEAM.value:
        if not team_id:
            return []
        try:
            team_oid = await _resolve_team_oid(team_id)
        except ValueError:
            return []
        team_access = await access_control.get_team_access_context(user)
        if not access_control.can_view_team(str(team_oid), team_access):
            return []
        query["team"] = team_oid
    else:
        query["owner_user_id"] = user.user_id
    folders = await LibraryFolder.find(query).to_list()

    # Count items per folder
    folder_uuids = [f.uuid for f in folders]
    counts: dict[str, int] = {}
    if folder_uuids:
        pipeline = [
            {"$match": {"folder": {"$in": folder_uuids}}},
            {"$group": {"_id": "$folder", "count": {"$sum": 1}}},
        ]
        collection = LibraryItem.get_motor_collection()
        results = await collection.aggregate(pipeline).to_list(length=None)
        counts = {r["_id"]: r["count"] for r in results}

    return [_folder_to_dict(f, item_count=counts.get(f.uuid, 0)) for f in folders]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def search_libraries(
    user: User,
    query: str,
    team_id: str | None = None,
    kind: str | None = None,
) -> list[dict]:
    results: list[dict] = []
    seen_item_ids: set[str] = set()
    libs = await list_libraries(user, team_id=team_id)
    for lib in libs:
        user_org_ancestry = None
        if lib["scope"] == LibraryScope.VERIFIED.value:
            from app.services import organization_service

            user_org_ancestry = await organization_service.get_user_org_ancestry(user)
        items = await get_library_items(
            lib["id"],
            user,
            kind=kind,
            user_org_ancestry=user_org_ancestry,
        )
        for item in items:
            if item["id"] in seen_item_ids:
                continue
            name_lower = item.get("name", "").lower()
            tags_str = " ".join(item.get("tags", [])).lower()
            note_str = (item.get("note") or "").lower()
            if query.lower() in name_lower or query.lower() in tags_str or query.lower() in note_str:
                seen_item_ids.add(item["id"])
                results.append(item)

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item_created_at(item: LibraryItem) -> str | None:
    """Return a reliable ISO creation timestamp for a library item.

    Old documents (created by the Flask/MongoEngine backend) store their
    creation time in ``added_at`` instead of ``created_at``.  When Beanie
    loads these, the ``default_factory`` on ``created_at`` fires and produces
    "now", which is wrong.  The MongoDB ObjectId always embeds the true
    insertion timestamp, so we use that as the canonical source.
    """
    if item.id:
        try:
            return BsonObjectId(str(item.id)).generation_time.isoformat()
        except Exception:
            pass
    return item.created_at.isoformat() if item.created_at else None


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
        "created_at": _item_created_at(item),
        "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None,
    }


async def _clone_underlying_object(item: LibraryItem, user_id: str, *, team_id: str | None = None) -> PydanticObjectId | None:
    """Clone the underlying workflow or search set. Returns new object ID."""
    if item.kind == LibraryItemKind.WORKFLOW:
        original = await Workflow.get(item.item_id)
        if not original:
            return None
        new_wf = Workflow(
            name=f"{original.name} (Copy)",
            description=original.description,
            user_id=user_id,
            team_id=team_id,
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


def _folder_to_dict(folder: LibraryFolder, item_count: int = 0) -> dict:
    return {
        "uuid": folder.uuid,
        "name": folder.name,
        "parent_id": folder.parent_id,
        "scope": folder.scope.value,
        "item_count": item_count,
    }
