"""Support ticket API endpoints."""

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.system_config import SystemConfig
from app.models.user import User
from app.services import support_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AddMessageRequest(BaseModel):
    content: str


class UpdateTicketRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: str | None = None
    tags: list[str] | None = None


def _strip_tags(payload: dict) -> dict:
    """Remove the internal-only tags field — non-support callers must not see it."""
    payload.pop("tags", None)
    return payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _is_support_user(user: User) -> bool:
    """Check if user is a support contact or admin."""
    if user.is_admin:
        return True
    config = await SystemConfig.get_config()
    contacts = config.support_contacts or []
    return any(c.get("user_id") == user.user_id for c in contacts)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/tickets")
async def create_ticket(
    subject: str = Form(...),
    message: str = Form(...),
    priority: str = Form("normal"),
    files: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
):
    # Validate all file sizes up-front so we don't create a ticket and then fail
    file_payloads: list[tuple[str, str | None, bytes]] = []
    for f in files:
        data = await f.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"File '{f.filename}' must be under 10MB",
            )
        file_payloads.append((f.filename or "attachment", f.content_type, data))

    team_id = str(user.current_team) if user.current_team else None
    ticket = await support_service.create_ticket(
        user=user,
        subject=subject,
        message=message,
        priority=priority,
        team_id=team_id,
    )

    is_support = await _is_support_user(user)

    if not file_payloads:
        return ticket if is_support else _strip_tags(ticket)

    initial_message_uuid = ticket["messages"][0]["uuid"] if ticket.get("messages") else None
    for filename, content_type, data in file_payloads:
        result = await support_service.add_attachment(
            ticket_uuid=ticket["uuid"],
            user=user,
            filename=filename,
            file_type=content_type,
            file_bytes=data,
            message_uuid=initial_message_uuid,
        )
        if result is not None:
            ticket = result

    return ticket if is_support else _strip_tags(ticket)


@router.get("/tickets")
async def list_tickets(
    status: str | None = None,
    tag: str | None = None,
    limit: int = 50,
    offset: int = 0,
    scope: str | None = None,
    user: User = Depends(get_current_user),
):
    """List tickets.

    - Default: support users see all tickets, regular users see their own.
    - ``scope=mine``: always return only the caller's own tickets, even for
      support users. Used by the Support Center page (where agents file QA
      tickets) so they see their personal queue, not the global one.
    - ``tag``: filter to tickets carrying this tag. Tags are support-internal,
      so this filter is ignored for non-support callers.
    """
    is_support = await _is_support_user(user)
    effective_tag = tag if is_support else None
    if scope == "mine" or not is_support:
        tickets = await support_service.list_tickets(
            user_id=user.user_id, status=status, tag=effective_tag, limit=limit, offset=offset
        )
    else:
        tickets = await support_service.list_all_tickets(
            status=status, tag=effective_tag, limit=limit, offset=offset
        )
    if not is_support:
        tickets = [_strip_tags(t) for t in tickets]
    return {"tickets": tickets}


@router.get("/tickets/{ticket_uuid}")
async def get_ticket(
    ticket_uuid: str,
    user: User = Depends(get_current_user),
):
    ticket = await support_service.get_ticket(ticket_uuid)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Only allow the ticket owner or support users to view
    is_support = await _is_support_user(user)
    if ticket["user_id"] != user.user_id and not is_support:
        raise HTTPException(status_code=403, detail="Not authorized")

    if not is_support:
        _strip_tags(ticket)
    return ticket


@router.post("/tickets/{ticket_uuid}/read")
async def mark_ticket_read(
    ticket_uuid: str,
    user: User = Depends(get_current_user),
):
    """Mark a ticket as read by the current user."""
    ok = await support_service.mark_ticket_read(ticket_uuid, user.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ok": True}


@router.post("/tickets/{ticket_uuid}/messages")
async def add_message(
    ticket_uuid: str,
    body: AddMessageRequest,
    user: User = Depends(get_current_user),
):
    # Check access
    ticket_data = await support_service.get_ticket(ticket_uuid)
    if not ticket_data:
        raise HTTPException(status_code=404, detail="Ticket not found")

    is_support = await _is_support_user(user)
    if ticket_data["user_id"] != user.user_id and not is_support:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await support_service.add_message(
        ticket_uuid=ticket_uuid,
        user=user,
        content=body.content,
        is_support_reply=is_support and ticket_data["user_id"] != user.user_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return result if is_support else _strip_tags(result)


@router.post("/tickets/{ticket_uuid}/attachments")
async def add_attachment(
    ticket_uuid: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    ticket_data = await support_service.get_ticket(ticket_uuid)
    if not ticket_data:
        raise HTTPException(status_code=404, detail="Ticket not found")

    is_support = await _is_support_user(user)
    if ticket_data["user_id"] != user.user_id and not is_support:
        raise HTTPException(status_code=403, detail="Not authorized")

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File must be under 10MB")

    result = await support_service.add_attachment(
        ticket_uuid=ticket_uuid,
        user=user,
        filename=file.filename or "attachment",
        file_type=file.content_type,
        file_bytes=file_bytes,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return result if is_support else _strip_tags(result)


@router.get("/tickets/{ticket_uuid}/attachments/{attachment_uuid}")
async def download_attachment(
    ticket_uuid: str,
    attachment_uuid: str,
    user: User = Depends(get_current_user),
):
    ticket_data = await support_service.get_ticket(ticket_uuid)
    if not ticket_data:
        raise HTTPException(status_code=404, detail="Ticket not found")

    is_support = await _is_support_user(user)
    if ticket_data["user_id"] != user.user_id and not is_support:
        raise HTTPException(status_code=403, detail="Not authorized")

    data = await support_service.get_attachment_data(ticket_uuid, attachment_uuid)
    if not data:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_bytes = base64.b64decode(data["file_data"])
    content_type = data.get("file_type") or "application/octet-stream"
    filename = data.get("filename", "attachment")

    # Images and PDFs can display inline; everything else should download
    inline_types = ("image/", "application/pdf")
    disposition = "inline" if any(content_type.startswith(t) for t in inline_types) else "attachment"

    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.patch("/tickets/{ticket_uuid}")
async def update_ticket(
    ticket_uuid: str,
    body: UpdateTicketRequest,
    user: User = Depends(get_current_user),
):
    """Update ticket status/priority/assignment. Support users only."""
    is_support = await _is_support_user(user)
    if not is_support:
        raise HTTPException(status_code=403, detail="Only support staff can update tickets")

    result = await support_service.update_ticket(
        ticket_uuid=ticket_uuid,
        status=body.status,
        priority=body.priority,
        assigned_to=body.assigned_to,
        tags=body.tags,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return result


@router.get("/stats")
async def get_ticket_stats(user: User = Depends(get_current_user)):
    """Aggregate ticket counts by status. Support users / admins only."""
    is_support = await _is_support_user(user)
    if not is_support:
        raise HTTPException(status_code=403, detail="Not authorized")
    return await support_service.get_ticket_stats()


@router.get("/tags")
async def list_tags(user: User = Depends(get_current_user)):
    """Return distinct tags currently in use across tickets. Support users only."""
    is_support = await _is_support_user(user)
    if not is_support:
        raise HTTPException(status_code=403, detail="Not authorized")
    return {"tags": await support_service.list_all_tags()}


@router.get("/contacts")
async def get_support_contacts(user: User = Depends(get_current_user)):
    """Get list of support contacts (for admin config UI)."""
    is_support = await _is_support_user(user)
    if not is_support:
        raise HTTPException(status_code=403, detail="Not authorized")
    return {"contacts": await support_service.get_support_contacts()}
