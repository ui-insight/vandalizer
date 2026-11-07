from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.user import User
from app.services import space_service

router = APIRouter()


class UpdateSpaceRequest(BaseModel):
    title: str


@router.get("/", response_model=None)
async def list_spaces(user: User = Depends(get_current_user)) -> list[dict]:
    return await space_service.list_spaces(user)


@router.patch("/{space_uuid}", response_model=None)
async def update_space(
    space_uuid: str,
    body: UpdateSpaceRequest,
    user: User = Depends(get_current_user),
) -> dict:
    result = await space_service.update_space(space_uuid, body.title, user)
    if result is None:
        raise HTTPException(status_code=404, detail="Space not found")
    return result


@router.delete("/{space_uuid}", response_model=None)
async def delete_space(
    space_uuid: str,
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    ok = await space_service.delete_space(space_uuid, user)
    if not ok:
        raise HTTPException(status_code=404, detail="Space not found")
    return {"ok": True}
