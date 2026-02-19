from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.spaces import CreateSpaceRequest
from app.services import space_service

router = APIRouter()


@router.get("/")
async def list_spaces(user: User = Depends(get_current_user)):
    return await space_service.list_spaces()


@router.post("/create")
async def create_space(
    body: CreateSpaceRequest,
    user: User = Depends(get_current_user),
):
    space = await space_service.create_space(body.title, user.user_id)
    return {"id": str(space.id), "uuid": space.uuid, "title": space.title}
