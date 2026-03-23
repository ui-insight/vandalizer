"""Activity API routes."""

import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.models.user import User
from app.services import access_control, activity_service

logger = logging.getLogger(__name__)

router = APIRouter()


async def _team_ids_for_user(user) -> list[str]:
    """Collect all team identifiers (UUID and ObjectId forms) for the user."""
    ctx = await access_control.get_team_access_context(user)
    return list(ctx.team_uuids | ctx.team_object_ids)


@router.get("/{activity_id}")
async def get_activity(
    activity_id: str,
    user: User = Depends(get_current_user),
):
    """Get a single activity event."""
    team_ids = await _team_ids_for_user(user)
    ev = await activity_service.get_activity(
        PydanticObjectId(activity_id), user.user_id, team_ids=team_ids,
    )
    if not ev:
        raise HTTPException(status_code=404, detail="Activity not found")
    return {"activity": ev.to_dict()}


@router.delete("/{activity_id}")
async def delete_activity(
    activity_id: str,
    user: User = Depends(get_current_user),
):
    """Delete an activity event with cascade."""
    deleted = await activity_service.delete_activity(
        PydanticObjectId(activity_id), user.user_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Activity not found")
    return {"status": "success", "message": f"Activity {activity_id} deleted."}


@router.get("/streams/")
async def activity_streams(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    """List recent activity events for the current user and their teams."""
    team_ids = await _team_ids_for_user(user)
    events = await activity_service.list_activities(user.user_id, limit=limit, team_ids=team_ids)
    return {"events": [ev.to_dict() for ev in events]}
