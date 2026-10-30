"""Activity service  - start, finish, update, list, and delete activity events."""

import logging
from datetime import datetime, timezone
from typing import Optional

from beanie import PydanticObjectId

from app.models.activity import ActivityEvent, ActivityStatus, ActivityType
from app.models.chat import ChatConversation, ChatMessage, FileAttachment, UrlAttachment

logger = logging.getLogger(__name__)


# How many document titles a run records. The list shows the first and a count.
RUN_DOCUMENT_TITLES_MAX = 10


async def document_titles_for(document_uuids: Optional[list[str]]) -> list[str]:
    """Titles of the first documents a run reads, in the order given.

    A document that no longer exists is left out rather than failing the run.
    """
    uuids = list(dict.fromkeys(document_uuids or []))[:RUN_DOCUMENT_TITLES_MAX]
    if not uuids:
        return []
    from app.models.document import SmartDocument

    try:
        docs = await SmartDocument.find({"uuid": {"$in": uuids}}).to_list()
    except Exception:
        logger.exception("Could not look up document titles for a run")
        return []
    by_uuid = {d.uuid: (d.title or d.uuid) for d in docs}
    return [by_uuid[u] for u in uuids if u in by_uuid]


async def activity_start(
    *,
    type: ActivityType,
    user_id: str,
    title: Optional[str] = None,
    team_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    search_set_uuid: Optional[str] = None,
    workflow: Optional[PydanticObjectId] = None,
    workflow_result: Optional[PydanticObjectId] = None,
    steps_total: int = 0,
    tags: Optional[list[str]] = None,
    document_uuids: Optional[list[str]] = None,
    source_conversation_id: Optional[str] = None,
    project_uuid: Optional[str] = None,
) -> ActivityEvent:
    now = datetime.now(timezone.utc)
    ev = ActivityEvent(
        type=type.value,
        title=title,
        status=ActivityStatus.RUNNING.value,
        user_id=user_id,
        team_id=team_id,
        conversation_id=conversation_id,
        search_set_uuid=search_set_uuid,
        workflow=workflow,
        workflow_result=workflow_result,
        steps_total=steps_total,
        tags=tags or [],
        document_titles=await document_titles_for(document_uuids),
        source_conversation_id=source_conversation_id,
        project_uuid=project_uuid,
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


async def activity_update(activity_id: PydanticObjectId, **kwargs: object) -> Optional[ActivityEvent]:
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
    activity_id: PydanticObjectId, user_id: str, *, team_ids: list[str] | None = None,
) -> Optional[ActivityEvent]:
    return await ActivityEvent.find_one(
        ActivityEvent.id == activity_id, ActivityEvent.user_id == user_id,
    )


async def list_activities(
    user_id: str,
    limit: int = 50,
    team_ids: list[str] | None = None,
) -> list[ActivityEvent]:
    # Activity rail is personal — only show the current user's activities.
    # Team-level activity sharing is handled separately.
    return (
        await ActivityEvent.find({"user_id": user_id})
        .sort("-started_at")
        .limit(limit)
        .to_list()
    )


CHAT_TITLE_MAX_CHARS = 120

# How many turns may try to title a chat. A failed or empty attempt left the
# chat named by its first few words forever ("Can we assume a waiver for").
CHAT_TITLE_MAX_ATTEMPTS = 3


def should_queue_chat_title(meta_summary: Optional[dict]) -> bool:
    """Whether this turn should ask for a generated chat title.

    Until a title has been generated (``ai_description``), each turn retries,
    up to ``CHAT_TITLE_MAX_ATTEMPTS``. Never once the user has named the chat.
    """
    meta = meta_summary or {}
    if meta.get("title_user_set") or meta.get("ai_description"):
        return False
    return int(meta.get("title_attempts") or 0) < CHAT_TITLE_MAX_ATTEMPTS


async def rename_conversation_activity(
    activity_id: PydanticObjectId,
    user_id: str,
    title: str,
) -> Optional[ActivityEvent]:
    """Rename a chat in the activity list, and its conversation.

    Only the chat's owner can rename it, as with delete. The name is marked as
    the user's (``title_user_set``) so the background title generator never
    replaces it. Returns None when there is no such chat for this user.
    Raises ValueError for an empty name or an activity that isn't a chat.
    """
    name = " ".join((title or "").split())
    if not name:
        raise ValueError("A chat name can't be empty.")
    if len(name) > CHAT_TITLE_MAX_CHARS:
        raise ValueError(f"Keep chat names to {CHAT_TITLE_MAX_CHARS} characters or fewer.")

    ev = await ActivityEvent.find_one(
        ActivityEvent.id == activity_id, ActivityEvent.user_id == user_id,
    )
    if not ev:
        return None
    if ev.type != ActivityType.CONVERSATION.value:
        raise ValueError("Only chats can be renamed.")

    ev.title = name
    ev.meta_summary = {
        **(ev.meta_summary or {}),
        "title_user_set": True,
        # Stops the rail's "Generating title…" placeholder for this row.
        "description_generated": True,
    }
    await ev.save()

    if ev.conversation_id:
        conversation = await ChatConversation.find_one(
            ChatConversation.uuid == ev.conversation_id,
        )
        if conversation:
            conversation.title = name
            await conversation.save()
    return ev


async def delete_activity(
    activity_id: PydanticObjectId,
    user_id: str,
) -> bool:
    ev = await ActivityEvent.find_one(
        ActivityEvent.id == activity_id, ActivityEvent.user_id == user_id,
    )
    if not ev:
        return False

    # Cascade delete conversation and related records
    if ev.conversation_id:
        conversation = await ChatConversation.find_one(
            ChatConversation.uuid == ev.conversation_id,
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
