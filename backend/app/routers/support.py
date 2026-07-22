"""Support ticket API endpoints."""

import base64
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.support import TicketClassification, TicketPriority
from app.models.user import User
from app.services import support_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AddMessageRequest(BaseModel):
    content: str
    # Support agents may flag a message as an internal note — visible only to
    # other support agents. Ignored (forced False) for non-support callers.
    is_internal_note: bool = False


class EditMessageRequest(BaseModel):
    content: str


class UpdateTicketRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    # Empty string clears the classification (same convention as assigned_to).
    classification: str | None = None
    assigned_to: str | None = None
    tags: list[str] | None = None
    subject: str | None = None


class AddWatcherRequest(BaseModel):
    email: str


def _strip_tags(payload: dict) -> dict:
    """Remove the internal-only tags field — non-support callers must not see it."""
    payload.pop("tags", None)
    return payload


# Summary fields used purely as scaffolding for stripping internal notes —
# the router consumes them and never returns them to any caller.
_VISIBLE_HELPER_FIELDS = (
    "last_visible_message_preview",
    "last_visible_message_at",
    "last_visible_message_is_support_reply",
    "last_visible_message_user_id",
    "visible_message_count",
)


def _drop_visible_helpers(payload: dict) -> dict:
    """Remove the ``last_visible_*`` helper fields from a summary."""
    for k in _VISIBLE_HELPER_FIELDS:
        payload.pop(k, None)
    return payload


def _strip_internal_notes(payload: dict) -> dict:
    """Hide internal notes from non-support callers.

    Operates on both full ticket dicts (filters ``messages``) and list
    summaries (swaps in the ``last_visible_message_*`` fields so the list
    view doesn't show a phantom "just now" timestamp pointing at an
    invisible note). Mutates and returns ``payload`` for chaining.
    """
    if "messages" in payload:
        payload["messages"] = [
            m for m in payload["messages"] if not m.get("is_internal_note")
        ]
        payload["message_count"] = len(payload["messages"])

    if payload.get("last_message_is_internal_note"):
        payload["last_message_preview"] = payload.get("last_visible_message_preview")
        payload["last_message_at"] = payload.get("last_visible_message_at")
        payload["last_message_is_support_reply"] = payload.get(
            "last_visible_message_is_support_reply"
        )
        payload["last_message_user_id"] = payload.get("last_visible_message_user_id")
    if "visible_message_count" in payload:
        payload["message_count"] = payload["visible_message_count"]
    payload.pop("last_message_is_internal_note", None)
    return _drop_visible_helpers(payload)


def _strip_for_non_support(payload: dict) -> dict:
    """Compose the support-only filters: drop tags and internal notes."""
    _strip_tags(payload)
    _strip_internal_notes(payload)
    return payload


def _view(payload: dict, is_support: bool) -> dict:
    """Final pass on a response payload: support callers see everything (with
    the internal-only scaffolding fields dropped); non-support callers also
    get tags and internal notes stripped."""
    if is_support:
        return _drop_visible_helpers(payload)
    return _strip_for_non_support(payload)


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


def _can_delete_attachment(attachment: dict, user: User, is_support: bool) -> bool:
    """Support agents can delete any attachment; otherwise only the uploader."""
    if is_support:
        return True
    return attachment.get("uploaded_by") == user.user_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _is_support_user(user: User) -> bool:
    """Check if user is a support contact or admin."""
    return await support_service.is_support_user(user)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/tickets")
async def create_ticket(
    subject: str = Form(...),
    message: str = Form(...),
    priority: str = Form("normal"),
    classification: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
):
    # Normalize/validate the classification up-front so a bad value returns a
    # clean 400 rather than a 500 from the enum conversion in the service.
    classification = (classification or "").strip() or None
    if classification is not None:
        valid = {c.value for c in TicketClassification}
        if classification not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid classification. Must be one of: {', '.join(sorted(valid))}",
            )

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
        classification=classification,
        team_id=team_id,
    )

    is_support = await _is_support_user(user)

    if not file_payloads:
        return _view(ticket, is_support)

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

    return _view(ticket, is_support)


@router.get("/tickets")
async def list_tickets(
    status: str | None = None,
    priority: str | None = None,
    classification: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    search: str | None = None,
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
    - ``search``: case-insensitive match across ticket number, subject,
      requester name/email, and message body.
    - ``priority``: filter to a specific priority (low/normal/high).
    - ``classification``: filter to a request type (bug/enhancement/feature_request).
    """
    is_support = await _is_support_user(user)
    effective_tag = tag if is_support else None
    effective_category = category if is_support else None
    if scope == "mine" or not is_support:
        tickets = await support_service.list_tickets(
            user_id=user.user_id, status=status, priority=priority,
            classification=classification, tag=effective_tag,
            category=effective_category,
            search=search, limit=limit, offset=offset,
        )
    else:
        tickets = await support_service.list_all_tickets(
            status=status, priority=priority, classification=classification,
            tag=effective_tag, category=effective_category, search=search,
            limit=limit, offset=offset,
        )
    tickets = [_view(t, is_support) for t in tickets]
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

    return _view(ticket, is_support)


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

    # Internal notes are agent-only. Silently force False for non-agents and
    # for an agent writing on their own ticket (where they're acting as the
    # requester).
    is_owner = ticket_data["user_id"] == user.user_id
    is_internal_note = body.is_internal_note and is_support and not is_owner

    result = await support_service.add_message(
        ticket_uuid=ticket_uuid,
        user=user,
        content=body.content,
        is_support_reply=is_support and not is_owner,
        is_internal_note=is_internal_note,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _view(result, is_support)


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
    return _view(result, is_support)


@router.post("/tickets/{ticket_uuid}/attachments")
async def add_attachment(
    ticket_uuid: str,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
):
    """Upload one or more attachments to an existing ticket.

    Accepts the ``files`` form field repeated per file (matches the
    multi-file create_ticket flow). Validates every file's size up-front so
    a partial upload doesn't half-mutate the ticket.
    """
    ticket_data = await support_service.get_ticket(ticket_uuid)
    if not ticket_data:
        raise HTTPException(status_code=404, detail="Ticket not found")

    is_support = await _is_support_user(user)
    if not _can_view_ticket(ticket_data, user, is_support):
        raise HTTPException(status_code=403, detail="Not authorized")

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    payloads: list[tuple[str, str | None, bytes]] = []
    for f in files:
        data = await f.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"File '{f.filename}' must be under 10MB",
            )
        payloads.append((f.filename or "attachment", f.content_type, data))

    result: dict | None = None
    for filename, content_type, data in payloads:
        result = await support_service.add_attachment(
            ticket_uuid=ticket_uuid,
            user=user,
            filename=filename,
            file_type=content_type,
            file_bytes=data,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Ticket not found")
    assert result is not None  # `files` is non-empty by the check above
    return _view(result, is_support)


@router.delete("/tickets/{ticket_uuid}/attachments/{attachment_uuid}")
async def delete_attachment(
    ticket_uuid: str,
    attachment_uuid: str,
    user: User = Depends(get_current_user),
):
    """Remove an attachment. Uploader can delete their own; support agents
    can delete any. Returns the updated ticket payload."""
    ticket_data = await support_service.get_ticket(ticket_uuid)
    if not ticket_data:
        raise HTTPException(status_code=404, detail="Ticket not found")

    is_support = await _is_support_user(user)
    if not _can_view_ticket(ticket_data, user, is_support):
        raise HTTPException(status_code=403, detail="Not authorized")

    target = next(
        (a for a in ticket_data.get("attachments", []) if a["uuid"] == attachment_uuid),
        None,
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if not _can_delete_attachment(target, user, is_support):
        raise HTTPException(
            status_code=403,
            detail="You can only delete attachments you uploaded",
        )

    result, removed = await support_service.delete_attachment(
        ticket_uuid=ticket_uuid,
        attachment_uuid=attachment_uuid,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if removed is None:
        # Race: attachment was already gone between the check and delete.
        raise HTTPException(status_code=404, detail="Attachment not found")
    return _view(result, is_support)


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
    """Update a ticket.

    Status, priority, classification, assignment, and tags are support-staff
    only. The ``subject`` (title) can also be edited by the ticket's own
    author, so users can fix a title after filing.
    """
    ticket = await support_service.get_ticket(ticket_uuid)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    is_support = await _is_support_user(user)
    is_owner = ticket.get("user_id") == user.user_id

    support_only = any(
        v is not None
        for v in (
            body.status, body.priority, body.classification,
            body.assigned_to, body.tags,
        )
    )
    if support_only and not is_support:
        raise HTTPException(
            status_code=403,
            detail="Only support staff can change status, priority, type, assignment, or tags",
        )

    # Validate enum-backed fields up-front so a bad value returns a clean 400
    # rather than a 500 from the enum conversion in the service.
    if body.priority is not None:
        valid = {p.value for p in TicketPriority}
        if body.priority not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid priority. Must be one of: {', '.join(sorted(valid))}",
            )
    if body.classification:  # empty string clears, so only non-empty is checked
        valid = {c.value for c in TicketClassification}
        if body.classification not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid classification. Must be one of: {', '.join(sorted(valid))}",
            )

    if body.subject is not None:
        if not (is_support or is_owner):
            raise HTTPException(
                status_code=403, detail="You can only edit your own ticket's subject"
            )
        if not body.subject.strip():
            raise HTTPException(status_code=400, detail="Subject cannot be empty")

    result = await support_service.update_ticket(
        ticket_uuid=ticket_uuid,
        status=body.status,
        priority=body.priority,
        classification=body.classification,
        assigned_to=body.assigned_to,
        tags=body.tags,
        subject=body.subject,
        actor=user,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _view(result, is_support)


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
    return _view(result, is_support)


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
    return _view(result, is_support)


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
