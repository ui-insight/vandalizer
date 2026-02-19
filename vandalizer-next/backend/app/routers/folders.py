from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.documents import CreateFolderRequest, RenameFolderRequest
from app.services import folder_service

router = APIRouter()


@router.post("/create")
async def create(
    body: CreateFolderRequest,
    user: User = Depends(get_current_user),
):
    folder = await folder_service.create_folder(
        name=body.name,
        parent_id=body.parent_id,
        space=body.space,
        user_id=user.user_id,
    )
    return {
        "id": str(folder.id),
        "uuid": folder.uuid,
        "title": folder.title,
        "parent_id": folder.parent_id,
    }


@router.patch("/rename")
async def rename(
    body: RenameFolderRequest,
    user: User = Depends(get_current_user),
):
    ok = await folder_service.rename_folder(body.uuid, body.newName)
    if not ok:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"ok": True}


@router.delete("/{folder_uuid}")
async def delete(
    folder_uuid: str,
    user: User = Depends(get_current_user),
):
    try:
        ok = await folder_service.delete_folder(folder_uuid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"ok": True}


@router.get("/breadcrumbs/{folder_uuid}")
async def breadcrumbs(
    folder_uuid: str,
    user: User = Depends(get_current_user),
):
    return await folder_service.get_breadcrumbs(folder_uuid)
