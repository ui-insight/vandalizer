"""Library API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.models.library import Library, LibraryScope
from app.models.user import User
from app.services import group_service
from app.schemas.library import (
    AddItemRequest,
    CloneRequest,
    CreateFolderRequest,
    LibraryItemResponse,
    LibraryResponse,
    MoveItemsRequest,
    RenameFolderRequest,
    SearchRequest,
    ShareToTeamRequest,
    UpdateItemRequest,
    UpdateLibraryRequest,
)
from app.services import library_service as svc

router = APIRouter()


# ---------------------------------------------------------------------------
# Library CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[LibraryResponse])
async def list_libraries(
    team_id: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    team = team_id or (str(user.current_team) if user.current_team else None)
    libs = await svc.list_libraries(user.user_id, team_id=team)
    return [LibraryResponse(**lib) for lib in libs]


# ---------------------------------------------------------------------------
# Items (fixed paths — must come before /{library_id})
# ---------------------------------------------------------------------------


@router.patch("/items/{item_id}", response_model=LibraryItemResponse)
async def update_item(
    item_id: str,
    req: UpdateItemRequest,
    user: User = Depends(get_current_user),
):
    item = await svc.update_item(
        item_id,
        user.user_id,
        note=req.note,
        tags=req.tags,
        pinned=req.pinned,
        favorited=req.favorited,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return LibraryItemResponse(**item)


@router.post("/items/{item_id}/touch")
async def touch_item(item_id: str, user: User = Depends(get_current_user)):
    """Record that a library item was just used."""
    await svc.touch_item(item_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Clone / Share (fixed paths — must come before /{library_id})
# ---------------------------------------------------------------------------


@router.post("/clone", response_model=LibraryItemResponse)
async def clone_to_personal(req: CloneRequest, user: User = Depends(get_current_user)):
    item = await svc.clone_to_personal(req.item_id, user.user_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return LibraryItemResponse(**item)


@router.post("/share", response_model=LibraryItemResponse)
async def share_to_team(req: ShareToTeamRequest, user: User = Depends(get_current_user)):
    item = await svc.share_to_team(req.item_id, user.user_id, req.team_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found or team not accessible")
    return LibraryItemResponse(**item)


# ---------------------------------------------------------------------------
# Folders (fixed paths — must come before /{library_id})
# ---------------------------------------------------------------------------


@router.get("/folders")
async def list_folders(
    scope: str = Query("personal"),
    team_id: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    return await svc.list_folders(scope=scope, user_id=user.user_id, team_id=team_id)


@router.post("/folders")
async def create_folder(req: CreateFolderRequest, user: User = Depends(get_current_user)):
    folder = await svc.create_folder(
        scope=req.scope,
        user_id=user.user_id,
        name=req.name,
        parent_id=req.parent_id,
        team_id=req.team_id,
    )
    return folder


@router.post("/folders/move-items")
async def move_items(req: MoveItemsRequest, user: User = Depends(get_current_user)):
    await svc.move_items(req.item_ids, req.folder_uuid, user.user_id)
    return {"ok": True}


@router.patch("/folders/{folder_uuid}")
async def rename_folder(
    folder_uuid: str,
    req: RenameFolderRequest,
    user: User = Depends(get_current_user),
):
    folder = await svc.rename_folder(folder_uuid, user.user_id, req.name)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@router.delete("/folders/{folder_uuid}")
async def delete_folder(folder_uuid: str, user: User = Depends(get_current_user)):
    ok = await svc.delete_folder(folder_uuid, user.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Search (fixed path — must come before /{library_id})
# ---------------------------------------------------------------------------


@router.post("/search", response_model=list[LibraryItemResponse])
async def search_libraries(req: SearchRequest, user: User = Depends(get_current_user)):
    items = await svc.search_libraries(
        user.user_id, req.query, team_id=req.team_id, kind=req.kind
    )
    return [LibraryItemResponse(**i) for i in items]


# ---------------------------------------------------------------------------
# Library CRUD by ID (parameterized — must come after all fixed paths)
# ---------------------------------------------------------------------------


@router.get("/{library_id}", response_model=LibraryResponse)
async def get_library(library_id: str, user: User = Depends(get_current_user)):
    lib = await svc.get_library(library_id, user.user_id)
    if not lib:
        raise HTTPException(status_code=404, detail="Library not found")
    return LibraryResponse(**lib)


@router.patch("/{library_id}", response_model=LibraryResponse)
async def update_library(
    library_id: str,
    req: UpdateLibraryRequest,
    user: User = Depends(get_current_user),
):
    lib = await svc.update_library(library_id, user.user_id, title=req.title, description=req.description)
    if not lib:
        raise HTTPException(status_code=404, detail="Library not found")
    return LibraryResponse(**lib)


@router.delete("/{library_id}")
async def delete_library(library_id: str, user: User = Depends(get_current_user)):
    ok = await svc.delete_library(library_id, user.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Library not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Items (parameterized library_id)
# ---------------------------------------------------------------------------


@router.post("/{library_id}/items", response_model=LibraryItemResponse)
async def add_item(
    library_id: str,
    req: AddItemRequest,
    user: User = Depends(get_current_user),
):
    item = await svc.add_item(
        library_id,
        user.user_id,
        item_id=req.item_id,
        kind=req.kind,
        note=req.note,
        tags=req.tags,
        folder=req.folder,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Library not found")
    return LibraryItemResponse(**item)


@router.get("/{library_id}/items", response_model=list[LibraryItemResponse])
async def list_items(
    library_id: str,
    kind: Optional[str] = Query(None),
    folder: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    # Check if this is a verified-scope library; if so, apply group filtering
    from beanie import PydanticObjectId
    user_group_uuids = None
    try:
        lib = await Library.get(PydanticObjectId(library_id))
        if lib and lib.scope == LibraryScope.VERIFIED:
            user_group_uuids = await group_service.get_user_group_uuids(user.user_id)
    except Exception:
        pass
    items = await svc.get_library_items(
        library_id, user.user_id, kind=kind, folder=folder, search=search,
        user_group_uuids=user_group_uuids,
    )
    return [LibraryItemResponse(**i) for i in items]


@router.delete("/{library_id}/items/{item_id}")
async def remove_item(
    library_id: str,
    item_id: str,
    user: User = Depends(get_current_user),
):
    ok = await svc.remove_item(library_id, item_id, user.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}
