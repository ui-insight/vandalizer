"""Support ticket API endpoints."""

import base64
import logging
from urllib.parse import quote

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


class EditMessageRequest(BaseModel):
    content: str


class UpdateTicketRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: str | None = None
    tags: list[str] | None = None


class AddWatcherRequest(BaseModel):
    email: str


def _strip_tags(payload: dict) -> dict:
    """Remove the internal-only tags field — non-support callers must not see it."""
    payload.pop("tags", None)
    return payload


def _can_view_ticket(ticket: dict, user: User, is_support: bool) -> bool:
    """Owner, support, or a tagged watcher can read/reply on a ticket."""
    if is_support:
        return True
    if ticket.get("user_id") == user.user_id:
        return True
    watcher_ids = {
        w.get("user_id") if isinstance(w, dict) else w
        for w in (ticket.get("watchers") or [])
    }
    return user.user_id in watcher_ids


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
    category: str | None = None,
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
    - ``category``: support-only filter. Used by the admin Demo tab to fetch
      trial check-in tickets (``category=feedback_prompt``), which the global
      Support Center listing excludes by default.
    """
    is_support = await _is_support_user(user)
    effective_tag = tag if is_support else None
    effective_category = category if is_support else None
    if scope == "mine" or not is_support:
        tickets = await support_service.list_tickets(
            user_id=user.user_id, status=status, tag=effective_tag,
            category=effective_category, limit=limit, offset=offset,
        )
    else:
        tickets = await support_service.list_all_tickets(
            status=status, tag=effective_tag, category=effective_category,
            limit=limit, offset=offset,
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

    # Owner, support, or tagged watcher may view.
    is_support = await _is_support_user(user)
    if not _can_view_ticket(ticket, user, is_support):
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
    # Check access — owner, support, or watcher may reply.
    ticket_data = await support_service.get_ticket(ticket_uuid)
    if not ticket_data:
        raise HTTPException(status_code=404, detail="Ticket not found")

    is_support = await _is_support_user(user)
    if not _can_view_ticket(ticket_data, user, is_support):
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


@router.patch("/tickets/{ticket_uuid}/messages/{message_uuid}")
async def edit_message(
    ticket_uuid: str,
    message_uuid: str,
    body: EditMessageRequest,
    user: User = Depends(get_current_user),
):
    """Edit your own message on a ticket. Authorship is required — even
    support agents can't rewrite someone else's words."""
    ticket_data = await support_service.get_ticket(ticket_uuid)
    if not ticket_data:
        raise HTTPException(status_code=404, detail="Ticket not found")

    is_support = await _is_support_user(user)
    if not _can_view_ticket(ticket_data, user, is_support):
        raise HTTPException(status_code=403, detail="Not authorized")

    result, error = await support_service.edit_message(
        ticket_uuid=ticket_uuid,
        message_uuid=message_uuid,
        user=user,
        content=body.content,
    )
    if error:
        status_code = 404 if "not found" in error.lower() else 403 if "edit your own" in error.lower() else 400
        raise HTTPException(status_code=status_code, detail=error)
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
    if not _can_view_ticket(ticket_data, user, is_support):
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
    if not _can_view_ticket(ticket_data, user, is_support):
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

    # Filenames may contain non-latin-1 characters (e.g.   narrow no-break
    # space from copy-pasted Word titles). Encode per RFC 5987 with an ASCII
    # fallback so the latin-1 header encoding doesn't blow up.
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', "")
    encoded = quote(filename, safe="")
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{encoded}"
            ),
        },
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
        actor=user,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return result


@router.post("/tickets/{ticket_uuid}/watchers")
async def add_watcher(
    ticket_uuid: str,
    body: AddWatcherRequest,
    user: User = Depends(get_current_user),
):
    """Tag a user (by email) to follow this ticket.

    Owner, support agents, and existing watchers may all add new watchers —
    if you can read the ticket, you can pull in another collaborator.
    """
    ticket_data = await support_service.get_ticket(ticket_uuid)
    if not ticket_data:
        raise HTTPException(status_code=404, detail="Ticket not found")
    is_support = await _is_support_user(user)
    if not _can_view_ticket(ticket_data, user, is_support):
        raise HTTPException(status_code=403, detail="Not authorized")

    result, error = await support_service.add_watcher(
        ticket_uuid=ticket_uuid,
        actor=user,
        email=body.email,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return result if is_support else _strip_tags(result)


@router.delete("/tickets/{ticket_uuid}/watchers/{watcher_user_id}")
async def remove_watcher(
    ticket_uuid: str,
    watcher_user_id: str,
    user: User = Depends(get_current_user),
):
    """Untag a watcher. Owner, support, or the watcher themselves may remove."""
    ticket_data = await support_service.get_ticket(ticket_uuid)
    if not ticket_data:
        raise HTTPException(status_code=404, detail="Ticket not found")
    is_support = await _is_support_user(user)
    is_owner = ticket_data["user_id"] == user.user_id
    is_self = user.user_id == watcher_user_id
    if not (is_support or is_owner or is_self):
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await support_service.remove_watcher(
        ticket_uuid=ticket_uuid,
        watcher_user_id=watcher_user_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return result if is_support else _strip_tags(result)


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
