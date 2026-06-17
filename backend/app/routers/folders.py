import io
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models.folder import SmartFolder
from app.models.user import User
from app.schemas.documents import (
    CreateFolderRequest,
    MoveFolderRequest,
    RenameFolderRequest,
)
from app.services import file_service, folder_service

router = APIRouter()


@router.post("/create")
async def create(
    body: CreateFolderRequest,
    user: User = Depends(get_current_user),
):
    team_id: str | None = None
    if body.folder_type == "team" and user.current_team:
        from app.models.team import Team

        team = await Team.get(user.current_team)
        if team:
            team_id = team.uuid

    try:
        folder = await folder_service.create_folder(
            name=body.name,
            parent_id=body.parent_id,
            user=user,
            requested_team_id=team_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": str(folder.id),
        "uuid": folder.uuid,
        "title": folder.title,
        "parent_id": folder.parent_id,
        "is_shared_team_root": folder.is_shared_team_root,
        "team_id": folder.team_id,
    }


@router.patch("/rename")
async def rename(
    body: RenameFolderRequest,
    user: User = Depends(get_current_user),
):
    ok = await folder_service.rename_folder(body.uuid, body.newName, user)
    if not ok:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"ok": True}


@router.get("/{folder_uuid}/export")
async def export(
    folder_uuid: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Stream a zip of every document in the folder subtree, preserving structure."""
    manifest = await folder_service.collect_export_entries(folder_uuid, user)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    root_title, entries = manifest

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for prefix, doc_uuid in entries:
            result = await file_service.download_document(doc_uuid, settings, user=user)
            if not result:
                continue
            name = result.title
            ext = (result.extension or "").lower()
            if ext and not name.lower().endswith(f".{ext}"):
                name = f"{name}.{ext}"
            zf.writestr(f"{prefix}{name}", result.data)

    buf.seek(0)
    filename = folder_service._safe_component(root_title)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}.zip"'},
    )


@router.patch("/{folder_uuid}/move")
async def move(
    folder_uuid: str,
    body: MoveFolderRequest,
    user: User = Depends(get_current_user),
):
    try:
        folder = await folder_service.move_folder(folder_uuid, body.parent_id, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": str(folder.id),
        "uuid": folder.uuid,
        "title": folder.title,
        "parent_id": folder.parent_id,
        "is_shared_team_root": folder.is_shared_team_root,
        "team_id": folder.team_id,
    }


@router.delete("/{folder_uuid}")
async def delete(
    folder_uuid: str,
    user: User = Depends(get_current_user),
):
    try:
        ok = await folder_service.delete_folder(folder_uuid, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"ok": True}


@router.patch("/{folder_uuid}/convert-to-team")
async def convert_to_team(
    folder_uuid: str,
    user: User = Depends(get_current_user),
):
    try:
        folder = await folder_service.convert_to_team_folder(folder_uuid, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": str(folder.id),
        "uuid": folder.uuid,
        "title": folder.title,
        "parent_id": folder.parent_id,
        "is_shared_team_root": folder.is_shared_team_root,
        "team_id": folder.team_id,
    }


@router.get("/all")
async def list_all_folders(
    user: User = Depends(get_current_user),
):
    """Return all folders for the current user, including subfolders."""
    from app.services.access_control import get_team_access_context

    folders = await SmartFolder.find(SmartFolder.user_id == user.user_id).to_list()
    team_access = await get_team_access_context(user)
    if team_access.team_uuids:
        team_folders = await SmartFolder.find(
            {"team_id": {"$in": list(team_access.team_uuids)}}
        ).to_list()
        existing = {f.uuid for f in folders}
        for tf in team_folders:
            if tf.uuid not in existing:
                folders.append(tf)

    # Build path labels by resolving parent chains
    by_uuid = {f.uuid: f for f in folders}

    def get_path(f: SmartFolder) -> str:
        parts = [f.title]
        current = f
        while current.parent_id != "0" and current.parent_id in by_uuid:
            current = by_uuid[current.parent_id]
            parts.append(current.title)
        return " / ".join(reversed(parts))

    return [
        {
            "uuid": f.uuid,
            "title": f.title,
            "path": get_path(f),
            "parent_id": f.parent_id,
            "is_shared_team_root": f.is_shared_team_root,
            "team_id": f.team_id,
        }
        for f in folders
    ]


@router.get("/breadcrumbs/{folder_uuid}")
async def breadcrumbs(
    folder_uuid: str,
    user: User = Depends(get_current_user),
):
    crumbs = await folder_service.get_breadcrumbs(folder_uuid, user)
    if crumbs is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return crumbs
