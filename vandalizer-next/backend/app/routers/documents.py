from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.user import User
from app.models.team import Team
from app.services import document_service

router = APIRouter()


@router.get("/list")
async def list_documents(
    space: str,
    folder: str | None = None,
    team_uuid: str | None = None,
    user: User = Depends(get_current_user),
):
    # Use provided team_uuid, or fall back to user's current team
    if not team_uuid and user.current_team:
        team = await Team.get(user.current_team)
        if team:
            team_uuid = team.uuid

    return await document_service.list_contents(
        space, folder, user_id=user.user_id, team_uuid=team_uuid
    )


@router.get("/poll_status")
async def poll_status(
    docid: str,
    user: User = Depends(get_current_user),
):
    result = await document_service.poll_status(docid)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result
