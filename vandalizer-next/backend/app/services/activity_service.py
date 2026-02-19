"""Activity service — start, finish, update, list, and delete activity events."""

import logging
from datetime import datetime, timezone
from typing import Optional

from beanie import PydanticObjectId

from app.models.activity import ActivityEvent, ActivityStatus, ActivityType
from app.models.chat import ChatConversation, ChatMessage, FileAttachment, UrlAttachment

logger = logging.getLogger(__name__)


async def activity_start(
    *,
    type: ActivityType,
    user_id: str,
    title: Optional[str] = None,
    team_id: Optional[str] = None,
    space: Optional[str] = None,
    conversation_id: Optional[str] = None,
    search_set_uuid: Optional[str] = None,
    workflow: Optional[PydanticObjectId] = None,
    workflow_result: Optional[PydanticObjectId] = None,
    steps_total: int = 0,
    tags: Optional[list[str]] = None,
) -> ActivityEvent:
    now = datetime.now(timezone.utc)
    ev = ActivityEvent(
        type=type.value,
        title=title,
        status=ActivityStatus.RUNNING.value,
        user_id=user_id,
        team_id=team_id,
        space=space,
        conversation_id=conversation_id,
        search_set_uuid=search_set_uuid,
        workflow=workflow,
        workflow_result=workflow_result,
        steps_total=steps_total,
        tags=tags or [],
        started_at=now,
        last_updated_at=now,
    )
    await ev.insert()
    return ev


async def activity_finish(
    activity_id: PydanticObjectId,
    status: ActivityStatus = ActivityStatus.COMPLETED,
    error: Optional[str] = None,
) -> Optional[ActivityEvent]:
    ev = await ActivityEvent.get(activity_id)
    if not ev:
        return None
    ev.status = status.value
    ev.finished_at = datetime.now(timezone.utc)
    ev.last_updated_at = datetime.now(timezone.utc)
    if error:
        ev.error = error[:2000]
    await ev.save()
    return ev


async def activity_update(activity_id: PydanticObjectId, **kwargs) -> Optional[ActivityEvent]:
    ev = await ActivityEvent.get(activity_id)
    if not ev:
        return None
    for key, value in kwargs.items():
        if hasattr(ev, key):
            setattr(ev, key, value)
    ev.last_updated_at = datetime.now(timezone.utc)
    await ev.save()
    return ev


async def get_activity(
    activity_id: PydanticObjectId, user_id: str
) -> Optional[ActivityEvent]:
    return await ActivityEvent.find_one(
        ActivityEvent.id == activity_id, ActivityEvent.user_id == user_id
    )


async def list_activities(user_id: str, limit: int = 50) -> list[ActivityEvent]:
    return (
        await ActivityEvent.find(ActivityEvent.user_id == user_id)
        .sort("-started_at")
        .limit(limit)
        .to_list()
    )


async def delete_activity(activity_id: PydanticObjectId, user_id: str) -> bool:
    ev = await ActivityEvent.find_one(
        ActivityEvent.id == activity_id, ActivityEvent.user_id == user_id
    )
    if not ev:
        return False

    # Cascade delete conversation and related records
    if ev.conversation_id:
        conversation = await ChatConversation.find_one(
            ChatConversation.uuid == ev.conversation_id,
            ChatConversation.user_id == user_id,
        )
        if conversation:
            if conversation.messages:
                await ChatMessage.find(
                    {"_id": {"$in": conversation.messages}}
                ).delete()
            if conversation.file_attachments:
                await FileAttachment.find(
                    {"_id": {"$in": conversation.file_attachments}}
                ).delete()
            if conversation.url_attachments:
                await UrlAttachment.find(
                    {"_id": {"$in": conversation.url_attachments}}
                ).delete()
            await conversation.delete()

    await ev.delete()
    return True
