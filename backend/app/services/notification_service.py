"""Notification service for verification and support events."""

import datetime

from app.models.notification import Notification

# Notification kinds that should coalesce: if an unread notification already
# exists for the same (user, item_kind, item_id), update it instead of
# creating a duplicate.  This prevents the bell from filling up with one
# entry per chat message in an active support conversation.
_COALESCE_KINDS = frozenset({
    "support_reply",
    "support_new_message",
    "support_new_ticket",
})


async def create_notification(
    user_id: str,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    item_kind: str | None = None,
    item_id: str | None = None,
    item_name: str | None = None,
    request_uuid: str | None = None,
) -> dict:
    # Coalesce: update existing unread notification for the same item
    if kind in _COALESCE_KINDS and item_kind and item_id:
        existing = await Notification.find_one(
            Notification.user_id == user_id,
            Notification.item_kind == item_kind,
            Notification.item_id == item_id,
            Notification.read == False,  # noqa: E712
        )
        if existing:
            existing.title = title
            existing.body = body
            existing.kind = kind
            existing.link = link
            existing.created_at = datetime.datetime.now(datetime.timezone.utc)
            await existing.save()
            return _to_dict(existing)

    n = Notification(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        link=link,
        item_kind=item_kind,
        item_id=item_id,
        item_name=item_name,
        request_uuid=request_uuid,
    )
    await n.insert()
    return _to_dict(n)


async def list_notifications(user_id: str, unread_only: bool = False, limit: int = 50) -> list[dict]:
    query: dict = {"user_id": user_id}
    if unread_only:
        query["read"] = False
    notifications = (
        await Notification.find(query)
        .sort("-created_at")
        .limit(limit)
        .to_list()
    )
    return [_to_dict(n) for n in notifications]


async def unread_count(user_id: str) -> int:
    return await Notification.find(
        Notification.user_id == user_id,
        Notification.read == False,  # noqa: E712
    ).count()


async def mark_read(user_id: str, notification_uuid: str) -> bool:
    n = await Notification.find_one(
        Notification.uuid == notification_uuid,
        Notification.user_id == user_id,
    )
    if not n:
        return False
    n.read = True
    await n.save()
    return True


async def mark_read_for_item(user_id: str, item_kind: str, item_id: str) -> int:
    """Mark all unread notifications for a specific item as read."""
    result = await Notification.find(
        Notification.user_id == user_id,
        Notification.item_kind == item_kind,
        Notification.item_id == item_id,
        Notification.read == False,  # noqa: E712
    ).update_many({"$set": {"read": True}})
    return result.modified_count if result else 0


async def mark_all_read(user_id: str) -> int:
    result = await Notification.find(
        Notification.user_id == user_id,
        Notification.read == False,  # noqa: E712
    ).update_many({"$set": {"read": True}})
    return result.modified_count if result else 0


def _to_dict(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "uuid": n.uuid,
        "kind": n.kind,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "item_kind": n.item_kind,
        "item_id": n.item_id,
        "item_name": n.item_name,
        "request_uuid": n.request_uuid,
        "read": n.read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }
