"""Support ticket service."""

import datetime
import logging
from typing import Optional

from app.config import Settings
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

    # Re-open if closed and user replies
    if ticket.status == TicketStatus.CLOSED and not is_support_reply:
        ticket.status = TicketStatus.OPEN

    await ticket.save()

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
    else:
        await _notify_support_contacts_new_message(ticket, msg)

    return _ticket_to_dict(ticket)


async def add_attachment(
    ticket_uuid: str,
    user: User,
    filename: str,
    file_type: str | None,
    file_data: str,
    message_uuid: str | None = None,
) -> dict | None:
    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return None

    attachment = SupportAttachment(
        filename=filename,
        file_type=file_type,
        file_data=file_data,
        uploaded_by=user.user_id,
        message_uuid=message_uuid,
    )
    ticket.attachments.append(attachment)
    ticket.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await ticket.save()
    return _ticket_to_dict(ticket)


async def get_attachment_data(ticket_uuid: str, attachment_uuid: str) -> dict | None:
    ticket = await SupportTicket.find_one(SupportTicket.uuid == ticket_uuid)
    if not ticket:
        return None
    for a in ticket.attachments:
        if a.uuid == attachment_uuid:
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

    return _ticket_to_dict(ticket)


async def get_support_contacts() -> list[dict]:
    """Return the list of support contacts from system config."""
    config = await SystemConfig.get_config()
    return config.support_contacts or []


async def _notify_support_contacts_new_ticket(ticket: SupportTicket) -> None:
    """Email and notify all support contacts about a new ticket."""
    config = await SystemConfig.get_config()
    contacts = config.support_contacts or []
    settings = Settings()

    for contact in contacts:
        email = contact.get("email")
        user_id = contact.get("user_id")
        name = contact.get("name", "Support")

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
    """Notify support contacts about a new message on an existing ticket."""
    config = await SystemConfig.get_config()
    contacts = config.support_contacts or []

    for contact in contacts:
        user_id = contact.get("user_id")
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


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

_STYLE = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a0a; color: #e5e7eb; margin: 0; padding: 0; }
  .container { max-width: 600px; margin: 0 auto; padding: 40px 24px; }
  .card { background: #171717; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 32px; }
  .logo { font-size: 24px; font-weight: 700; color: #f1b300; margin-bottom: 24px; }
  h1 { font-size: 20px; color: #fff; margin: 0 0 16px 0; }
  p { font-size: 15px; line-height: 1.6; color: #9ca3af; margin: 0 0 16px 0; }
  .btn { display: inline-block; background: #f1b300; color: #000; font-weight: 700; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-size: 15px; }
  .footer { margin-top: 32px; font-size: 13px; color: #6b7280; text-align: center; }
  .highlight { color: #f1b300; font-weight: 600; }
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
