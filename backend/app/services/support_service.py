"""Support ticket service."""

import datetime
import logging
from pathlib import Path

import redis.asyncio as aioredis

from app.config import Settings
from app.services.email_service import _BASE_STYLE
from app.models.support import (
    SupportAttachment,
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


def _ticket_to_dict(t: SupportTicket) -> dict:
    return {
        "uuid": t.uuid,
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
                "created_at": m.created_at.isoformat() if m.created_at else None,
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
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in t.attachments
        ],
        "message_count": len(t.messages),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        "category": t.category,
    }


def _ticket_summary(t: SupportTicket) -> dict:
    """Lightweight dict for list views (no messages/attachments)."""
    last_message = t.messages[-1] if t.messages else None
    return {
        "uuid": t.uuid,
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
        "last_message_at": (
            last_message.created_at.isoformat() if last_message and last_message.created_at else None
        ),
        "last_message_is_support_reply": (
            last_message.is_support_reply if last_message else None
        ),
        "last_message_user_id": (
            last_message.user_id if last_message else None
        ),
        "read_by": t.read_by,
        "category": t.category,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
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

    return _ticket_to_dict(ticket)


async def get_ticket_stats() -> dict:
    """Return aggregate ticket counts by status."""
    open_count = await SupportTicket.find({"status": "open"}).count()
    in_progress_count = await SupportTicket.find({"status": "in_progress"}).count()
    closed_count = await SupportTicket.find({"status": "closed"}).count()
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
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    query: dict = {}
    if user_id:
        query["user_id"] = user_id
    if status:
        query["status"] = status
    if assigned_to:
        query["assigned_to"] = assigned_to

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
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    query: dict = {}
    if status:
        query["status"] = status
    tickets = (
        await SupportTicket.find(query)
        .sort("-updated_at")
        .skip(offset)
        .limit(limit)
        .to_list()
    )
    return [_ticket_summary(t) for t in tickets]


async def get_ticket(ticket_uuid: str) -> dict | None:
    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return None
    return _ticket_to_dict(ticket)


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

    return _ticket_to_dict(ticket)


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
    return _ticket_to_dict(ticket)


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

    return _ticket_to_dict(ticket)


async def get_support_contacts() -> list[dict]:
    """Return the list of support contacts from system config."""
    config = await SystemConfig.get_config()
    return config.support_contacts or []


async def _get_all_support_user_ids() -> list[dict]:
    """Return deduplicated list of support contacts + admins as {user_id, email, name}."""
    config = await SystemConfig.get_config()
    contacts = list(config.support_contacts or [])
    seen_ids = {c.get("user_id") for c in contacts if c.get("user_id")}

    # Include admins who aren't already in the contacts list
    admins = await User.find(User.is_admin == True).to_list()  # noqa: E712
    for admin in admins:
        if admin.user_id not in seen_ids:
            contacts.append({
                "user_id": admin.user_id,
                "email": admin.email,
                "name": admin.name or admin.user_id,
            })
            seen_ids.add(admin.user_id)

    return contacts


async def _notify_support_contacts_new_ticket(ticket: SupportTicket) -> None:
    """Email and notify all support contacts and admins about a new ticket."""
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
            subject = f"New Support Ticket: {ticket.subject}"
            html = _new_ticket_email(
                support_name=name,
                ticket_subject=ticket.subject,
                ticket_user=ticket.user_name or ticket.user_id,
                message=ticket.messages[0].content if ticket.messages else "",
                ticket_uuid=ticket.uuid,
                frontend_url=settings.frontend_url,
            )
            await send_email(email, subject, html, settings)


async def _notify_support_contacts_new_message(
    ticket: SupportTicket, msg: SupportMessage
) -> None:
    """Notify support contacts and admins about a new message on an existing ticket."""
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
                )
                await send_email(email, subject, html, settings)


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
    )
    await send_email(owner.email, subject, html, settings)


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
    )
    await send_email(owner.email, subject, html, settings)


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
) -> str:
    return f"""<!DOCTYPE html><html><head>{_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer Support</div>
      <h1>New Support Ticket</h1>
      <p>Hi {support_name}, a new support ticket has been created.</p>
      <p><strong style="color:#fff">From:</strong> {ticket_user}<br/>
         <strong style="color:#fff">Subject:</strong> <span class="highlight">{ticket_subject}</span></p>
      <div class="message-box"><p style="margin:0">{message[:500]}</p></div>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/support?ticket={ticket_uuid}">View Ticket</a></p>
      <div class="footer">Vandalizer Support System</div>
    </div></div></body></html>"""
