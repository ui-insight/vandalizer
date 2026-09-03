"""Notification service for verification, support, and failure events."""

import datetime
import logging
import uuid as uuid_mod

from app.models.notification import Notification

logger = logging.getLogger(__name__)

# Notification kinds that should coalesce: if an unread notification already
# exists for the same (user, item_kind, item_id), update it instead of
# creating a duplicate.  This prevents the bell from filling up with one
# entry per chat message in an active support conversation.
_COALESCE_KINDS = frozenset({
    "support_reply",
    "support_new_message",
    "support_new_ticket",
})

# Kinds that report something went wrong. Callers may pass severity explicitly;
# this set means the failure emitters can't forget to.
FAILURE_KINDS = frozenset({
    "workflow_failed",
    "extraction_failed",
    "document_failed",
    "document_unsearchable",
    "automation_failed",
    "delivery_failed",
    "kb_source_failed",
    "project_kb_sync_failed",
})


def _resolve_severity(kind: str, severity: str | None) -> str:
    if severity:
        return severity
    return "error" if kind in FAILURE_KINDS else "info"


def _apply_group_title(group_title: str | None, fallback: str, count: int) -> str:
    """Render the repeat-count title for a coalesced notification.

    `group_title` is a format string taking {count}; a malformed one falls back
    to the single-event title rather than blowing up the calling task.
    """
    if not group_title or count < 2:
        return fallback
    try:
        return group_title.format(count=count)
    except (KeyError, IndexError, ValueError):
        return fallback


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
    severity: str | None = None,
    coalesce_key: str | None = None,
    group_title: str | None = None,
) -> dict:
    severity = _resolve_severity(kind, severity)
    now = datetime.datetime.now(datetime.timezone.utc)

    # Explicit group coalescing: repeated occurrences of the same event fold
    # into one unread row and bump its count.
    if coalesce_key:
        existing = await Notification.find_one(
            Notification.user_id == user_id,
            Notification.coalesce_key == coalesce_key,
            Notification.read == False,  # noqa: E712
        )
        if existing:
            existing.occurrences = (existing.occurrences or 1) + 1
            existing.title = _apply_group_title(group_title, title, existing.occurrences)
            existing.body = body
            existing.kind = kind
            existing.link = link
            existing.severity = severity
            existing.item_kind = item_kind
            existing.item_id = item_id
            existing.item_name = item_name
            existing.created_at = now
            await existing.save()
            return _to_dict(existing)

    # Legacy per-item coalescing for the support kinds.
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
            existing.created_at = now
            await existing.save()
            return _to_dict(existing)

    n = Notification(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        link=link,
        severity=severity,
        item_kind=item_kind,
        item_id=item_id,
        item_name=item_name,
        request_uuid=request_uuid,
        coalesce_key=coalesce_key,
    )
    await n.insert()
    return _to_dict(n)


def create_notification_sync(
    db,
    user_id: str,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    item_kind: str | None = None,
    item_id: str | None = None,
    item_name: str | None = None,
    severity: str | None = None,
    coalesce_key: str | None = None,
    group_title: str | None = None,
) -> None:
    """Create a notification from a synchronous (Celery worker) context.

    Celery tasks hold a raw pymongo handle, not a Beanie/Motor session, so they
    cannot await `create_notification`. This mirrors its coalescing semantics
    against the same collection. Never raises: a task that did real work must
    not fail because the bell entry could not be written.
    """
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        severity = _resolve_severity(kind, severity)

        if coalesce_key:
            existing = db.notification.find_one({
                "user_id": user_id,
                "coalesce_key": coalesce_key,
                "read": False,
            })
            if existing:
                occurrences = (existing.get("occurrences") or 1) + 1
                db.notification.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {
                        "occurrences": occurrences,
                        "title": _apply_group_title(group_title, title, occurrences),
                        "body": body,
                        "kind": kind,
                        "link": link,
                        "severity": severity,
                        "item_kind": item_kind,
                        "item_id": item_id,
                        "item_name": item_name,
                        "created_at": now,
                    }},
                )
                return

        db.notification.insert_one({
            "uuid": uuid_mod.uuid4().hex,
            "user_id": user_id,
            "kind": kind,
            "title": title,
            "body": body,
            "link": link,
            "severity": severity,
            "item_kind": item_kind,
            "item_id": item_id,
            "item_name": item_name,
            "request_uuid": None,
            "coalesce_key": coalesce_key,
            "occurrences": 1,
            "read": False,
            "created_at": now,
        })
    except Exception:
        logger.exception(
            "Failed to write %s notification for user %s", kind, user_id,
        )


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
        "severity": getattr(n, "severity", None) or "info",
        "occurrences": getattr(n, "occurrences", None) or 1,
        "item_kind": n.item_kind,
        "item_id": n.item_id,
        "item_name": n.item_name,
        "request_uuid": n.request_uuid,
        "read": n.read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }
