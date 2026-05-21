"""Support ticket service."""

import asyncio
import datetime
import logging
from pathlib import Path

import redis.asyncio as aioredis
from pymongo import ReturnDocument

from app.config import Settings
from app.services.email_service import _BASE_STYLE
from app.models.support import (
    SupportAttachment,
    SupportCounter,
    SupportMessage,
    SupportTicket,
    TicketPriority,
    TicketStatus,
)
from app.models.system_config import SystemConfig
from app.models.user import User
from app.services.email_service import send_email
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

# Cooldown in seconds — skip email if we already emailed this person about
# this ticket within this window (avoids spam during live chat).
_EMAIL_COOLDOWN_SECONDS = 600  # 10 minutes

# Sequential ticket numbers start at this base — "#1001" reads better than
# "#1" and makes it obvious it isn't an internal db id.
_TICKET_NUMBER_BASE = 1000

_counter_init_lock = asyncio.Lock()
_counter_initialized = False


async def _ensure_counter_initialized() -> None:
    """First-call backfill: assign ticket_number to legacy tickets and seed
    the counter. Idempotent; the asyncio lock guards concurrent inserts on
    process start.
    """
    global _counter_initialized
    if _counter_initialized:
        return
    async with _counter_init_lock:
        if _counter_initialized:
            return
        coll = SupportCounter.get_motor_collection()
        existing = await coll.find_one({"name": "support_ticket"})
        if existing is None:
            # Chronological backfill so older tickets get smaller numbers.
            legacy = (
                await SupportTicket.find({"ticket_number": None})
                .sort("+created_at")
                .to_list()
            )
            next_num = 0
            for t in legacy:
                next_num += 1
                t.ticket_number = _TICKET_NUMBER_BASE + next_num
                await t.save()
            await coll.update_one(
                {"name": "support_ticket"},
                {"$set": {"name": "support_ticket", "value": next_num}},
                upsert=True,
            )
        _counter_initialized = True


async def _next_ticket_number() -> int:
    """Atomically reserve the next ticket number."""
    await _ensure_counter_initialized()
    coll = SupportCounter.get_motor_collection()
    res = await coll.find_one_and_update(
        {"name": "support_ticket"},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return _TICKET_NUMBER_BASE + int(res["value"])


def _iso_utc(dt: datetime.datetime | None) -> str | None:
    """Serialize a datetime as an ISO string with a timezone suffix.

    Why: MongoDB returns BSON Dates as naive UTC datetimes, so a plain
    .isoformat() emits no offset and browsers parse it as local time.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.isoformat()


async def _check_email_cooldown(ticket_uuid: str, recipient: str) -> bool:
    """Return True if we should send (cooldown expired), False if throttled."""
    settings = Settings()
    key = f"support_email_cd:{ticket_uuid}:{recipient}"
    try:
        r = aioredis.from_url(f"redis://{settings.redis_host}:6379")
        try:
            existing = await r.get(key)
            if existing:
                return False
            await r.set(key, "1", ex=_EMAIL_COOLDOWN_SECONDS)
            return True
        finally:
            await r.aclose()
    except Exception:
        # Redis down — allow the email rather than silently dropping it
        return True


async def _hydrate_watchers(user_ids: list[str]) -> list[dict]:
    """Look up watcher user_ids and return [{user_id, name, email}] dicts.

    Users that no longer exist are returned with just their user_id so the
    UI can still render and unfollow them.
    """
    if not user_ids:
        return []
    users = await User.find({"user_id": {"$in": list(user_ids)}}).to_list()
    by_id = {u.user_id: u for u in users}
    result: list[dict] = []
    for uid in user_ids:
        u = by_id.get(uid)
        result.append({
            "user_id": uid,
            "name": (u.name if u else None) or uid,
            "email": u.email if u else None,
        })
    return result


async def _ticket_to_dict(t: SupportTicket) -> dict:
    watcher_ids = list(getattr(t, "watchers", []) or [])
    return {
        "uuid": t.uuid,
        "ticket_number": getattr(t, "ticket_number", None),
        "subject": t.subject,
        "status": t.status.value,
        "priority": t.priority.value,
        "user_id": t.user_id,
        "user_name": t.user_name,
        "user_email": t.user_email,
        "team_id": t.team_id,
        "assigned_to": t.assigned_to,
        "messages": [
            {
                "uuid": m.uuid,
                "user_id": m.user_id,
                "user_name": m.user_name,
                "content": m.content,
                "is_support_reply": m.is_support_reply,
                "created_at": _iso_utc(m.created_at),
                "edited_at": _iso_utc(getattr(m, "edited_at", None)),
            }
            for m in t.messages
        ],
        "attachments": [
            {
                "uuid": a.uuid,
                "filename": a.filename,
                "file_type": a.file_type,
                "uploaded_by": a.uploaded_by,
                "message_uuid": a.message_uuid,
                "created_at": _iso_utc(a.created_at),
            }
            for a in t.attachments
        ],
        "message_count": len(t.messages),
        "created_at": _iso_utc(t.created_at),
        "updated_at": _iso_utc(t.updated_at),
        "closed_at": _iso_utc(t.closed_at),
        "category": t.category,
        "tags": list(getattr(t, "tags", []) or []),
        "watchers": await _hydrate_watchers(watcher_ids),
    }


def _ticket_summary(t: SupportTicket) -> dict:
    """Lightweight dict for list views (no messages/attachments)."""
    last_message = t.messages[-1] if t.messages else None
    return {
        "uuid": t.uuid,
        "ticket_number": getattr(t, "ticket_number", None),
        "subject": t.subject,
        "status": t.status.value,
        "priority": t.priority.value,
        "user_id": t.user_id,
        "user_name": t.user_name,
        "assigned_to": t.assigned_to,
        "message_count": len(t.messages),
        "last_message_preview": (
            last_message.content[:120] if last_message else None
        ),
        "last_message_at": _iso_utc(last_message.created_at) if last_message else None,
        "last_message_is_support_reply": (
            last_message.is_support_reply if last_message else None
        ),
        "last_message_user_id": (
            last_message.user_id if last_message else None
        ),
        "read_by": t.read_by,
        "category": t.category,
        "tags": list(getattr(t, "tags", []) or []),
        # List view only needs the user_ids — the full name/email lookup is
        # done in the ticket detail view. We surface them here so the UI can
        # show a "Watching" badge for the current user without an extra fetch.
        "watcher_ids": list(getattr(t, "watchers", []) or []),
        "created_at": _iso_utc(t.created_at),
        "updated_at": _iso_utc(t.updated_at),
        "closed_at": _iso_utc(t.closed_at),
    }


async def create_ticket(
    user: User,
    subject: str,
    message: str,
    priority: str = "normal",
    team_id: str | None = None,
) -> dict:
    msg = SupportMessage(
        user_id=user.user_id,
        user_name=user.name or user.user_id,
        content=message,
        is_support_reply=False,
    )
    ticket = SupportTicket(
        ticket_number=await _next_ticket_number(),
        subject=subject,
        priority=TicketPriority(priority),
        user_id=user.user_id,
        user_name=user.name or user.user_id,
        user_email=user.email,
        team_id=team_id,
        messages=[msg],
    )
    await ticket.insert()

    # Notify support contacts
    await _notify_support_contacts_new_ticket(ticket)

    return await _ticket_to_dict(ticket)


# Trial check-in prompts are stored as support tickets with this category.
# They are surfaced in the admin Demo tab, not the Support Center, so the
# default list/stats queries exclude them.
_CHECK_IN_CATEGORY = "feedback_prompt"
_EXCLUDE_CHECK_INS = {"$ne": _CHECK_IN_CATEGORY}


async def get_ticket_stats() -> dict:
    """Return aggregate ticket counts by status (excludes trial check-ins)."""
    base = {"category": _EXCLUDE_CHECK_INS}
    open_count = await SupportTicket.find({**base, "status": "open"}).count()
    in_progress_count = await SupportTicket.find({**base, "status": "in_progress"}).count()
    closed_count = await SupportTicket.find({**base, "status": "closed"}).count()
    total = open_count + in_progress_count + closed_count
    return {
        "total": total,
        "open": open_count,
        "in_progress": in_progress_count,
        "closed": closed_count,
    }


async def list_tickets(
    user_id: str | None = None,
    status: str | None = None,
    assigned_to: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List tickets the given user_id owns *or* is tagged as a watcher on.

    Watched tickets are surfaced in the same list as owned ones so the
    requester sees a single unified queue — owner_tickets vs. tickets I
    follow are distinguished client-side via `user_id` vs. `watcher_ids`.
    """
    query: dict = {}
    if user_id:
        # Owner OR watcher. We $or this with the other filters via $and.
        query["$or"] = [{"user_id": user_id}, {"watchers": user_id}]
    if status:
        query["status"] = status
    if assigned_to:
        query["assigned_to"] = assigned_to
    if tag:
        query["tags"] = tag
    if category is not None:
        query["category"] = category

    tickets = (
        await SupportTicket.find(query)
        .sort("-updated_at")
        .skip(offset)
        .limit(limit)
        .to_list()
    )
    return [_ticket_summary(t) for t in tickets]


async def list_all_tickets(
    status: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List every ticket in the system. Defaults to regular tickets only —
    pass ``category="feedback_prompt"`` to fetch trial check-ins instead.
    """
    query: dict = {}
    if status:
        query["status"] = status
    if tag:
        query["tags"] = tag
    if category is not None:
        query["category"] = category
    else:
        query["category"] = _EXCLUDE_CHECK_INS
    tickets = (
        await SupportTicket.find(query)
        .sort("-updated_at")
        .skip(offset)
        .limit(limit)
        .to_list()
    )
    return [_ticket_summary(t) for t in tickets]


async def list_all_tags() -> list[str]:
    """Return every distinct tag in use across tickets, sorted."""
    raw = await SupportTicket.get_motor_collection().distinct("tags")
    return sorted({str(t) for t in raw if t})


async def get_ticket(ticket_uuid: str) -> dict | None:
    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return None
    return await _ticket_to_dict(ticket)


async def mark_ticket_read(ticket_uuid: str, user_id: str) -> bool:
    """Record that a user has read this ticket. Returns True if ticket exists."""
    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return False
    if user_id not in ticket.read_by:
        ticket.read_by.append(user_id)
        await ticket.save()
    return True


async def add_message(
    ticket_uuid: str,
    user: User,
    content: str,
    is_support_reply: bool = False,
) -> dict | None:
    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return None

    msg = SupportMessage(
        user_id=user.user_id,
        user_name=user.name or user.user_id,
        content=content,
        is_support_reply=is_support_reply,
    )
    ticket.messages.append(msg)
    ticket.updated_at = datetime.datetime.now(datetime.timezone.utc)
    # Reset read tracking — only the sender has "read" this state
    ticket.read_by = [user.user_id]

    # Re-open if closed and user replies
    if ticket.status == TicketStatus.CLOSED and not is_support_reply:
        ticket.status = TicketStatus.OPEN

    await ticket.save()

    # If the user (not support) replied to a feedback prompt ticket,
    # mark the corresponding prompt as responded.
    if not is_support_reply and ticket.category == "feedback_prompt":
        from app.services.feedback_prompt_service import mark_responded
        await mark_responded(ticket.uuid)

    # Notify the other party
    if is_support_reply:
        await create_notification(
            user_id=ticket.user_id,
            kind="support_reply",
            title="New reply on your support ticket",
            body=f"Re: {ticket.subject}",
            link=f"/support?ticket={ticket.uuid}",
            item_kind="support_ticket",
            item_id=ticket.uuid,
            item_name=ticket.subject,
        )
        # Email the ticket owner (with cooldown to avoid spam during live chat)
        await _email_ticket_owner_reply(ticket, msg)
    else:
        await _notify_support_contacts_new_message(ticket, msg)
        # Watchers can reply too — when they do, the owner needs to know
        # (the support-contacts branch above covers support staff).
        if user.user_id != ticket.user_id:
            await create_notification(
                user_id=ticket.user_id,
                kind="support_new_message",
                title=f"New message on ticket: {ticket.subject}",
                body=msg.content[:120],
                link=f"/support?ticket={ticket.uuid}",
                item_kind="support_ticket",
                item_id=ticket.uuid,
                item_name=ticket.subject,
            )

    # Notify watchers on every new message (they followed the ticket precisely
    # to stay in the loop). Skip the sender — they obviously know.
    await _notify_watchers_new_message(ticket, msg)

    return await _ticket_to_dict(ticket)


async def edit_message(
    ticket_uuid: str,
    message_uuid: str,
    user: User,
    content: str,
) -> tuple[dict | None, str | None]:
    """Edit an existing message's content. Only the author can edit.

    Returns (ticket_dict, error). ``error`` is set on permission/validation
    failures so the router can map it to a 4xx response.
    """
    cleaned = (content or "").strip()
    if not cleaned:
        return None, "Message content is required"

    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return None, "Ticket not found"

    target: SupportMessage | None = None
    for m in ticket.messages:
        if m.uuid == message_uuid:
            target = m
            break
    if target is None:
        return None, "Message not found"

    if target.user_id != user.user_id:
        return None, "You can only edit your own messages"

    target.content = cleaned
    target.edited_at = datetime.datetime.now(datetime.timezone.utc)
    ticket.updated_at = target.edited_at
    await ticket.save()
    return await _ticket_to_dict(ticket), None


def _support_attachments_dir() -> Path:
    """Return (and create) the directory for support ticket attachments."""
    from app.dependencies import get_settings
    base = Path(get_settings().upload_dir) / "support_attachments"
    base.mkdir(parents=True, exist_ok=True)
    return base


async def add_attachment(
    ticket_uuid: str,
    user: User,
    filename: str,
    file_type: str | None,
    file_bytes: bytes,
    message_uuid: str | None = None,
) -> dict | None:
    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return None

    att = SupportAttachment(
        filename=filename,
        file_type=file_type,
        file_data="",  # don't store in DB
        uploaded_by=user.user_id,
        message_uuid=message_uuid,
    )
    dest_dir = _support_attachments_dir() / ticket_uuid
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / att.uuid
    dest_file.write_bytes(file_bytes)
    att.file_path = str(dest_file)

    ticket.attachments.append(att)
    ticket.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await ticket.save()
    return await _ticket_to_dict(ticket)


async def get_attachment_data(ticket_uuid: str, attachment_uuid: str) -> dict | None:
    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return None
    for a in ticket.attachments:
        if a.uuid == attachment_uuid:
            # Read from disk if file_path exists, fall back to legacy base64
            if a.file_path:
                p = Path(a.file_path)
                if p.exists():
                    import base64 as b64
                    return {
                        "uuid": a.uuid,
                        "filename": a.filename,
                        "file_type": a.file_type,
                        "file_data": b64.b64encode(p.read_bytes()).decode(),
                    }
            # Legacy: base64 stored in document
            if a.file_data:
                return {
                    "uuid": a.uuid,
                    "filename": a.filename,
                    "file_type": a.file_type,
                    "file_data": a.file_data,
                }
    return None


async def update_ticket(
    ticket_uuid: str,
    status: str | None = None,
    priority: str | None = None,
    assigned_to: str | None = None,
    tags: list[str] | None = None,
    actor: User | None = None,
) -> dict | None:
    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return None

    if status:
        ticket.status = TicketStatus(status)
        if status == "closed":
            ticket.closed_at = datetime.datetime.now(datetime.timezone.utc)
        elif ticket.closed_at:
            ticket.closed_at = None
    if priority:
        ticket.priority = TicketPriority(priority)
    if assigned_to is not None:
        ticket.assigned_to = assigned_to or None
    added_tags: list[str] = []
    if tags is not None:
        # Normalize: strip whitespace, drop empties, dedupe (preserve order)
        seen: set[str] = set()
        cleaned: list[str] = []
        for raw in tags:
            t = raw.strip()
            if t and t not in seen:
                seen.add(t)
                cleaned.append(t)
        prev = set(ticket.tags or [])
        added_tags = [t for t in cleaned if t not in prev]
        ticket.tags = cleaned

    ticket.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await ticket.save()

    # Notify ticket owner of status changes
    if status:
        await create_notification(
            user_id=ticket.user_id,
            kind="support_status",
            title=f"Ticket {status.replace('_', ' ')}",
            body=f"Your ticket \"{ticket.subject}\" has been marked as {status.replace('_', ' ')}.",
            link=f"/support?ticket={ticket.uuid}",
            item_kind="support_ticket",
            item_id=ticket.uuid,
            item_name=ticket.subject,
        )
        # Email the ticket owner about status change
        await _email_ticket_owner_status(ticket, status)
        # Watchers asked to follow the ticket — keep them in the loop on
        # status changes too (in-app notification only; no email blast).
        await _notify_watchers_status(ticket, status, actor)

    # Email the other support agents when tags are added.
    if added_tags:
        await _notify_support_contacts_tag_added(ticket, added_tags, actor)

    return await _ticket_to_dict(ticket)


# ---------------------------------------------------------------------------
# Watchers — users tagged on a ticket to follow its progress
# ---------------------------------------------------------------------------

async def add_watcher(
    ticket_uuid: str,
    actor: User,
    email: str,
) -> tuple[dict | None, str | None]:
    """Tag a user (by email) as a watcher on the ticket.

    Returns (ticket_dict, error). ``error`` is set if the email doesn't map
    to a real account, or the user is the ticket owner (already participant).
    """
    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return None, "Ticket not found"

    normalized = (email or "").strip().lower()
    if not normalized:
        return None, "Email is required"

    target = await User.find_one(User.email == normalized)
    if not target:
        return None, f"No Vandalizer account found for {email}"

    if target.user_id == ticket.user_id:
        return None, "That user already owns this ticket"

    if target.user_id in (ticket.watchers or []):
        # Idempotent — return the ticket without re-notifying.
        return await _ticket_to_dict(ticket), None

    ticket.watchers = list(ticket.watchers or []) + [target.user_id]
    ticket.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await ticket.save()

    await _notify_watcher_added(ticket, target, actor)

    return await _ticket_to_dict(ticket), None


async def remove_watcher(
    ticket_uuid: str,
    watcher_user_id: str,
) -> dict | None:
    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return None
    current = list(ticket.watchers or [])
    if watcher_user_id not in current:
        return await _ticket_to_dict(ticket)
    ticket.watchers = [w for w in current if w != watcher_user_id]
    ticket.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await ticket.save()
    return await _ticket_to_dict(ticket)


async def _notify_watcher_added(
    ticket: SupportTicket, watcher: User, actor: User,
) -> None:
    """Notify a user that they've been tagged on a ticket — in-app + email."""
    actor_name = (actor.name or actor.user_id) if actor else "Someone"
    first_message = ticket.messages[0].content if ticket.messages else ""
    await create_notification(
        user_id=watcher.user_id,
        kind="support_watcher_added",
        title=f"{actor_name} added you to a support ticket",
        body=ticket.subject,
        link=f"/support?ticket={ticket.uuid}",
        item_kind="support_ticket",
        item_id=ticket.uuid,
        item_name=ticket.subject,
    )
    if not watcher.email:
        return
    settings = Settings()
    from app.services.email_service import support_watcher_added_email
    subject, html = support_watcher_added_email(
        watcher_name=watcher.name or watcher.user_id,
        ticket_subject=ticket.subject,
        ticket_user=ticket.user_name or ticket.user_id,
        actor_name=actor_name,
        first_message=first_message,
        ticket_uuid=ticket.uuid,
        frontend_url=settings.frontend_url,
        ticket_number=ticket.ticket_number,
    )
    await send_email(
        watcher.email, subject, html, settings, email_type="support_watcher_added",
    )


async def _notify_watchers_new_message(
    ticket: SupportTicket, msg: SupportMessage,
) -> None:
    """In-app notification (and cooldown-respecting email) to each watcher."""
    if not ticket.watchers:
        return
    watchers = await User.find({"user_id": {"$in": list(ticket.watchers)}}).to_list()
    settings = Settings()
    for w in watchers:
        if w.user_id == msg.user_id:
            continue  # sender already knows
        await create_notification(
            user_id=w.user_id,
            kind="support_new_message",
            title=f"New message on ticket: {ticket.subject}",
            body=msg.content[:120],
            link=f"/support?ticket={ticket.uuid}",
            item_kind="support_ticket",
            item_id=ticket.uuid,
            item_name=ticket.subject,
        )
        if w.email and await _check_email_cooldown(ticket.uuid, w.user_id):
            from app.services.email_service import support_new_message_email
            subject, html = support_new_message_email(
                support_name=w.name or w.user_id,
                ticket_subject=ticket.subject,
                ticket_user=msg.user_name or msg.user_id,
                message=msg.content,
                ticket_uuid=ticket.uuid,
                frontend_url=settings.frontend_url,
                ticket_number=ticket.ticket_number,
            )
            await send_email(
                w.email, subject, html, settings,
                email_type="support_new_message",
            )


async def _notify_watchers_status(
    ticket: SupportTicket, new_status: str, actor: User | None,
) -> None:
    """In-app only — watchers see status flips alongside the ticket owner."""
    if not ticket.watchers:
        return
    actor_id = actor.user_id if actor else None
    pretty = new_status.replace("_", " ")
    for watcher_id in ticket.watchers:
        if watcher_id == actor_id:
            continue
        await create_notification(
            user_id=watcher_id,
            kind="support_status",
            title=f"Ticket {pretty}",
            body=f"\"{ticket.subject}\" was marked as {pretty}.",
            link=f"/support?ticket={ticket.uuid}",
            item_kind="support_ticket",
            item_id=ticket.uuid,
            item_name=ticket.subject,
        )


async def get_support_contacts() -> list[dict]:
    """Return the list of support contacts from system config."""
    config = await SystemConfig.get_config()
    return config.support_contacts or []


async def _get_all_support_user_ids() -> list[dict]:
    """Return the configured support contacts as {user_id, email, name}."""
    config = await SystemConfig.get_config()
    return list(config.support_contacts or [])


async def _notify_support_contacts_new_ticket(ticket: SupportTicket) -> None:
    """Email and notify configured support contacts about a new ticket."""
    contacts = await _get_all_support_user_ids()
    settings = Settings()

    for contact in contacts:
        email = contact.get("email")
        user_id = contact.get("user_id")
        name = contact.get("name", "Support")

        # Don't notify the ticket creator
        if user_id == ticket.user_id:
            continue

        # In-app notification
        if user_id:
            await create_notification(
                user_id=user_id,
                kind="support_new_ticket",
                title="New support ticket",
                body=f"{ticket.user_name}: {ticket.subject}",
                link=f"/support?ticket={ticket.uuid}",
                item_kind="support_ticket",
                item_id=ticket.uuid,
                item_name=ticket.subject,
            )

        # Email notification
        if email:
            num_prefix = f"[#{ticket.ticket_number}] " if ticket.ticket_number else ""
            subject = f"{num_prefix}New Support Ticket: {ticket.subject}"
            html = _new_ticket_email(
                support_name=name,
                ticket_subject=ticket.subject,
                ticket_user=ticket.user_name or ticket.user_id,
                message=ticket.messages[0].content if ticket.messages else "",
                ticket_uuid=ticket.uuid,
                frontend_url=settings.frontend_url,
                ticket_number=ticket.ticket_number,
            )
            await send_email(email, subject, html, settings, email_type="support_new_ticket")


async def _notify_support_contacts_new_message(
    ticket: SupportTicket, msg: SupportMessage
) -> None:
    """Notify configured support contacts about a new message on an existing ticket."""
    contacts = await _get_all_support_user_ids()
    settings = Settings()

    for contact in contacts:
        user_id = contact.get("user_id")
        email = contact.get("email")
        name = contact.get("name", "Support")
        if user_id and user_id != msg.user_id:
            await create_notification(
                user_id=user_id,
                kind="support_new_message",
                title=f"New message on ticket: {ticket.subject}",
                body=msg.content[:120],
                link=f"/support?ticket={ticket.uuid}",
                item_kind="support_ticket",
                item_id=ticket.uuid,
                item_name=ticket.subject,
            )
            # Email with cooldown
            if email and await _check_email_cooldown(ticket.uuid, user_id):
                from app.services.email_service import support_new_message_email
                subject, html = support_new_message_email(
                    support_name=name,
                    ticket_subject=ticket.subject,
                    ticket_user=msg.user_name or msg.user_id,
                    message=msg.content,
                    ticket_uuid=ticket.uuid,
                    frontend_url=settings.frontend_url,
                    ticket_number=ticket.ticket_number,
                )
                await send_email(email, subject, html, settings, email_type="support_new_message")


async def _notify_support_contacts_tag_added(
    ticket: SupportTicket,
    added_tags: list[str],
    actor: User | None,
) -> None:
    """Email the other support agents when a tag is added to a ticket."""
    contacts = await _get_all_support_user_ids()
    settings = Settings()
    actor_user_id = actor.user_id if actor else None
    actor_name = (actor.name or actor.user_id) if actor else "A support agent"

    for contact in contacts:
        user_id = contact.get("user_id")
        email = contact.get("email")
        name = contact.get("name", "Support")
        # Don't email the agent who just added the tag.
        if user_id and user_id == actor_user_id:
            continue
        if not email:
            continue
        from app.services.email_service import support_tag_added_email
        subject, html = support_tag_added_email(
            support_name=name,
            ticket_subject=ticket.subject,
            ticket_user=ticket.user_name or ticket.user_id,
            added_tags=added_tags,
            actor_name=actor_name,
            ticket_uuid=ticket.uuid,
            frontend_url=settings.frontend_url,
            ticket_number=ticket.ticket_number,
        )
        await send_email(email, subject, html, settings, email_type="support_tag_added")


async def _email_ticket_owner_reply(
    ticket: SupportTicket, msg: SupportMessage
) -> None:
    """Email the ticket owner when support replies (with cooldown)."""
    if not await _check_email_cooldown(ticket.uuid, ticket.user_id):
        return
    owner = await User.find_one(User.user_id == ticket.user_id)
    if not owner or not owner.email:
        return
    settings = Settings()
    from app.services.email_service import support_reply_email
    subject, html = support_reply_email(
        user_name=owner.name or owner.user_id,
        ticket_subject=ticket.subject,
        message=msg.content,
        ticket_uuid=ticket.uuid,
        frontend_url=settings.frontend_url,
        ticket_number=ticket.ticket_number,
    )
    await send_email(owner.email, subject, html, settings, email_type="support_reply")


async def _email_ticket_owner_status(
    ticket: SupportTicket, new_status: str
) -> None:
    """Email the ticket owner when ticket status changes."""
    owner = await User.find_one(User.user_id == ticket.user_id)
    if not owner or not owner.email:
        return
    settings = Settings()
    from app.services.email_service import support_status_email
    subject, html = support_status_email(
        user_name=owner.name or owner.user_id,
        ticket_subject=ticket.subject,
        new_status=new_status.replace("_", " "),
        ticket_uuid=ticket.uuid,
        frontend_url=settings.frontend_url,
        ticket_number=ticket.ticket_number,
    )
    await send_email(owner.email, subject, html, settings, email_type="support_status")


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

_STYLE = _BASE_STYLE + """
<style>
  .message-box { background: #1f1f1f; border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 16px; margin: 16px 0; }
</style>
"""


def _new_ticket_email(
    support_name: str,
    ticket_subject: str,
    ticket_user: str,
    message: str,
    ticket_uuid: str,
    frontend_url: str,
    ticket_number: int | None = None,
) -> str:
    number_line = (
        f'<p><strong style="color:#fff">Ticket:</strong> '
        f'<span class="highlight">#{ticket_number}</span></p>'
        if ticket_number is not None
        else ""
    )
    return f"""<!DOCTYPE html><html><head>{_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer Support</div>
      <h1>New Support Ticket</h1>
      <p>Hi {support_name}, a new support ticket has been created.</p>
      {number_line}
      <p><strong style="color:#fff">From:</strong> {ticket_user}<br/>
         <strong style="color:#fff">Subject:</strong> <span class="highlight">{ticket_subject}</span></p>
      <div class="message-box"><p style="margin:0">{message[:500]}</p></div>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/support?ticket={ticket_uuid}">View Ticket</a></p>
      <div class="footer">Vandalizer Support System</div>
    </div></div></body></html>"""
