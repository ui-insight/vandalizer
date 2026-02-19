"""Activity API routes."""

import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.models.user import User
from app.services import activity_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{activity_id}")
async def get_activity(
    activity_id: str,
    user: User = Depends(get_current_user),
):
    """Get a single activity event."""
    ev = await activity_service.get_activity(
        PydanticObjectId(activity_id), user.user_id
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
        PydanticObjectId(activity_id), user.user_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Activity not found")
    return {"status": "success", "message": f"Activity {activity_id} deleted."}


@router.get("/streams/")
async def activity_streams(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    """List recent activity events for the current user."""
    events = await activity_service.list_activities(user.user_id, limit=limit)
    return {"events": [ev.to_dict() for ev in events]}
