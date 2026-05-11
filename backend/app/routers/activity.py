"""Activity API routes."""

import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.models.system_config import SystemConfig
from app.models.user import User
from app.services import access_control, activity_service
from app.tasks.activity_tasks import STALE_ACTIVITY_THRESHOLD_MINUTES_DEFAULT

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

    # Frontend uses this to flip stuck rail items to a "timed out" state without
    # waiting on the reaper. Keep it in sync with the backend reaper threshold.
    try:
        config = await SystemConfig.get_config()
        retention = config.get_retention_config()
        threshold = retention.get(
            "activity_stale_threshold_minutes",
            STALE_ACTIVITY_THRESHOLD_MINUTES_DEFAULT,
        )
        stale_threshold_minutes = (
            int(threshold)
            if isinstance(threshold, (int, float)) and threshold > 0
            else STALE_ACTIVITY_THRESHOLD_MINUTES_DEFAULT
        )
    except Exception:
        logger.exception("Failed to resolve stale-activity threshold")
        stale_threshold_minutes = STALE_ACTIVITY_THRESHOLD_MINUTES_DEFAULT

    return {
        "events": [ev.to_dict() for ev in events],
        "stale_threshold_minutes": stale_threshold_minutes,
    }
