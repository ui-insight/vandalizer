from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.spaces import CreateSpaceRequest, UpdateSpaceRequest
from app.services import space_service

router = APIRouter()


@router.get("/")
async def list_spaces(user: User = Depends(get_current_user)):
    return await space_service.list_spaces(user)


@router.post("/create")
async def create_space(
    body: CreateSpaceRequest,
    user: User = Depends(get_current_user),
):
    space = await space_service.create_space(body.title, user.user_id)
    return {"id": str(space.id), "uuid": space.uuid, "title": space.title}


@router.patch("/{space_uuid}")
async def update_space(
    space_uuid: str,
    body: UpdateSpaceRequest,
    user: User = Depends(get_current_user),
):
    space = await space_service.update_space(space_uuid, user=user, title=body.title)
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    return {"id": str(space.id), "uuid": space.uuid, "title": space.title}


@router.delete("/{space_uuid}")
async def delete_space(
    space_uuid: str,
    user: User = Depends(get_current_user),
):
    ok = await space_service.delete_space(space_uuid, user=user)
    if not ok:
        raise HTTPException(status_code=404, detail="Space not found")
    return {"ok": True}
