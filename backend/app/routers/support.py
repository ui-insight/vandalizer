"""Support ticket API endpoints."""

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException
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

class CreateTicketRequest(BaseModel):
    subject: str
    message: str
    priority: str = "normal"


class AddMessageRequest(BaseModel):
    content: str


class AddAttachmentRequest(BaseModel):
    filename: str
    file_type: str | None = None
    file_data: str  # base64
    message_uuid: str | None = None


class UpdateTicketRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: str | None = None


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
    body: CreateTicketRequest,
    user: User = Depends(get_current_user),
):
    team_id = str(user.current_team) if user.current_team else None
    ticket = await support_service.create_ticket(
        user=user,
        subject=body.subject,
        message=body.message,
        priority=body.priority,
        team_id=team_id,
    )
    return ticket


@router.get("/tickets")
async def list_tickets(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
):
    """List tickets. Support users see all; regular users see only their own."""
    is_support = await _is_support_user(user)
    if is_support:
        tickets = await support_service.list_all_tickets(
            status=status, limit=limit, offset=offset
        )
    else:
        tickets = await support_service.list_tickets(
            user_id=user.user_id, status=status, limit=limit, offset=offset
        )
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

    return ticket


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
    return result


@router.post("/tickets/{ticket_uuid}/attachments")
async def add_attachment(
    ticket_uuid: str,
    body: AddAttachmentRequest,
    user: User = Depends(get_current_user),
):
    ticket_data = await support_service.get_ticket(ticket_uuid)
    if not ticket_data:
        raise HTTPException(status_code=404, detail="Ticket not found")

    is_support = await _is_support_user(user)
    if ticket_data["user_id"] != user.user_id and not is_support:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await support_service.add_attachment(
        ticket_uuid=ticket_uuid,
        user=user,
        filename=body.filename,
        file_type=body.file_type,
        file_data=body.file_data,
        message_uuid=body.message_uuid,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return result


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
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return result


@router.get("/contacts")
async def get_support_contacts(user: User = Depends(get_current_user)):
    """Get list of support contacts (for admin config UI)."""
    is_support = await _is_support_user(user)
    if not is_support:
        raise HTTPException(status_code=403, detail="Not authorized")
    return {"contacts": await support_service.get_support_contacts()}
