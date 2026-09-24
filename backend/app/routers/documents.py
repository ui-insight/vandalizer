import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional

from app.dependencies import get_current_user
from app.models.document import SmartDocument
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.rate_limit import limiter
from app.services import access_control, audit_service, document_service
from app.services.extraction_staleness import EXTRACTION_STALE_AFTER, extraction_is_stale

router = APIRouter()


@router.get("/list")
async def list_documents(
    folder: str | None = None,
    team_uuid: str | None = None,
    user: User = Depends(get_current_user),
):
    # Use provided team_uuid, or fall back to user's current team
    if not team_uuid and user.current_team:
        team = await Team.get(user.current_team)
        if team:
            team_uuid = team.uuid

    # Validate that the user is a member of the requested team
    if team_uuid:
        team = await Team.find_one(Team.uuid == team_uuid)
        if team:
            membership = await TeamMembership.find_one(
                TeamMembership.team == team.id,
                TeamMembership.user_id == user.user_id,
            )
            if not membership:
                raise HTTPException(status_code=403, detail="Not a member of this team")

    return await document_service.list_contents(user=user, folder=folder, team_uuid=team_uuid)


@router.get("/search")
async def search_documents(
    q: str = Query(default="", min_length=0),
    limit: int = Query(default=20, ge=1, le=100),
    folder: str | None = Query(default=None),
    user: User = Depends(get_current_user),
):
    """Search documents by title or content text. Returns recent docs when q is empty.

    When `folder` is provided, results are restricted to that folder value.
    Pass folder="__root__" to match documents with no folder assigned.
    """
    # Include user's own docs and team-scoped docs
    team_access = await access_control.get_team_access_context(user)
    owner_conditions: list[dict] = [{"user_id": user.user_id}]
    if team_access.team_uuids:
        owner_conditions.append({"team_id": {"$in": list(team_access.team_uuids)}})
    if team_access.team_object_ids:
        owner_conditions.append({"team_id": {"$in": list(team_access.team_object_ids)}})
    owner_filter: dict = {"$or": owner_conditions}

    base_conditions: list[dict] = [owner_filter]
    if folder is not None:
        if folder == "__root__":
            base_conditions.append({"$or": [{"folder": None}, {"folder": ""}, {"folder": "0"}]})
        else:
            base_conditions.append({"folder": folder})

    if not q.strip():
        query: dict = {"$and": base_conditions} if len(base_conditions) > 1 else owner_filter
        results = await SmartDocument.find(query).sort(-SmartDocument.created_at).limit(limit).to_list()
    else:
        regex = re.compile(re.escape(q), re.IGNORECASE)
        results = await SmartDocument.find(
            {
                "$and": base_conditions + [
                    {
                        "$or": [
                            {"title": {"$regex": regex.pattern, "$options": "i"}},
                            {"raw_text": {"$regex": regex.pattern, "$options": "i"}},
                        ],
                    },
                ],
            }
        ).sort(-SmartDocument.created_at).limit(limit).to_list()

    items = []
    for doc in results:
        # Extract snippet around match in raw_text
        snippet = ""
        if q.strip() and doc.raw_text:
            rgx = re.compile(re.escape(q), re.IGNORECASE)
            match = rgx.search(doc.raw_text)
            if match:
                start = max(0, match.start() - 80)
                end = min(len(doc.raw_text), match.end() + 80)
                snippet = ("..." if start > 0 else "") + doc.raw_text[start:end] + ("..." if end < len(doc.raw_text) else "")

        items.append({
            "uuid": doc.uuid,
            "title": doc.title,
            "extension": doc.extension,
            "snippet": snippet,
            "num_pages": doc.num_pages,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            "processing": doc.processing,
            "valid": doc.valid,
            "validation_feedback": doc.validation_feedback,
            "task_status": doc.task_status,
            "folder": doc.folder,
            "token_count": doc.token_count,
            "extraction_low_quality": document_service.is_extraction_low_quality(doc),
            "ingestion_warnings": document_service.ingestion_warnings(doc),
            # The human sentence, composed by the same registry that owns the
            # codes. Serving it keeps the words in one place — a second copy
            # of the map in TypeScript is exactly the drift the registry's
            # own comment warns about (#803).
            "ingestion_warning_text": document_service.ingestion_warning_text(doc),
        })

    return {"items": items, "total": len(items)}


@router.get("/poll_status")
async def poll_status(
    docid: str,
    user: User = Depends(get_current_user),
):
    result = await document_service.poll_status(docid, user)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


class TitlesRequest(BaseModel):
    document_uuids: list[str] = []
    folder_uuids: list[str] = []


# A chat setup link attaches at most 3 knowledge bases, but its documents and
# folders are whatever the sender had selected; this bounds the lookup.
_MAX_TITLE_LOOKUPS = 100


@router.post("/titles")
async def resolve_titles(
    body: TitlesRequest,
    user: User = Depends(get_current_user),
):
    """Titles for the documents and folders the caller can view.

    Opening a chat setup link re-attaches the sender's documents and folders
    as chips, which need titles. ``poll_status`` would ship each document's
    full text to get one. Anything the caller cannot view is left out, not
    reported, so the response says nothing about what exists; the caller
    counts what came back to tell the user some of the link was not shared
    with them. Authorization matches the chat route's, so what resolves here
    is what the chat will accept.
    """
    if len(body.document_uuids) + len(body.folder_uuids) > _MAX_TITLE_LOOKUPS:
        raise HTTPException(status_code=400, detail=f"At most {_MAX_TITLE_LOOKUPS} items per request")
    team_access = await access_control.get_team_access_context(user)
    documents = []
    for uuid in dict.fromkeys(body.document_uuids):
        doc = await access_control.get_authorized_document(
            uuid, user, team_access=team_access, allow_admin=True,
        )
        if doc:
            documents.append({"uuid": doc.uuid, "title": doc.title or doc.uuid})
    folders = []
    for uuid in dict.fromkeys(body.folder_uuids):
        folder = await access_control.get_authorized_folder(
            uuid, user, team_access=team_access, allow_admin=True,
        )
        if folder:
            folders.append({"uuid": folder.uuid, "title": folder.title})
    return {"documents": documents, "folders": folders}


# How long an in-progress extraction may go without a status write before a
# retry is allowed to replace it. The in-flight guard below is the only thing
# standing between a document and a second dispatch, and the shape this route
# itself writes — processing=True, task_status="extracting", raw_text="" — is
# what a worker that dies after that write leaves behind. The window is the
# same one the reap_stuck sweep uses to mark such a document failed, imported
# from a single definition so the route can never allow a retry while the
# sweep still considers the lock live (or vice versa).
_EXTRACTION_STALE_AFTER = EXTRACTION_STALE_AFTER


def _extraction_is_stale(doc: SmartDocument) -> bool:
    return extraction_is_stale(doc.updated_at, doc.created_at)


@router.post("/{doc_uuid}/retry-extraction")
@limiter.limit("30/minute")
async def retry_extraction(
    request: Request,
    doc_uuid: str,
    user: User = Depends(get_current_user),
):
    """Re-run text extraction (and downstream ingestion) for a document.

    Useful when the original extraction silently produced no text — for example
    because the OCR endpoint was temporarily down. Clears any prior error state
    and re-dispatches the same Celery chain that ran at upload time.

    A retry re-reads the pages with OCR when the previous extraction failed or
    produced unreadable text; a healthy document is re-read the ordinary way,
    so a retry on a working document does not spend an OCR round-trip to get
    back what it already had. When the reason is unreadable text, or the
    document's text layer was refused before, the re-read also *requires*
    OCR: rather than fall back to the local reading it is replacing, it fails
    and is retried once OCR is back.
    """
    doc = await access_control.get_authorized_document(
        doc_uuid, user, manage=True, allow_admin=True
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if document_service.extraction_in_flight(doc) and not _extraction_is_stale(doc):
        raise HTTPException(
            status_code=409,
            detail="Extraction is already in progress for this document",
        )

    restart = await document_service.restart_extraction(doc, user.user_id)
    task_id = restart["task_id"]
    force_ocr = restart["force_ocr"]
    ocr_required = restart["ocr_required"]
    previous_task_status = restart["previous_task_status"]

    await audit_service.log_event(
        action="document.retry_extraction",
        actor_user_id=user.user_id,
        resource_type="document",
        resource_id=doc_uuid,
        resource_name=doc.title,
        detail={
            "force_ocr": force_ocr,
            "ocr_required": ocr_required,
            "previous_task_status": previous_task_status,
        },
    )

    return {"uuid": doc_uuid, "task_id": task_id, "status": "extracting"}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class ReclassifyRequest(BaseModel):
    classification: str
    reason: Optional[str] = None


@router.patch("/{doc_uuid}/classify")
async def reclassify_document(
    doc_uuid: str,
    body: ReclassifyRequest,
    user: User = Depends(get_current_user),
):
    """Manually reclassify a document."""
    valid_levels = {"unrestricted", "internal", "ferpa", "cui", "itar"}
    if body.classification not in valid_levels:
        raise HTTPException(status_code=400, detail=f"Classification must be one of {valid_levels}")

    doc = await access_control.get_authorized_document(
        doc_uuid, user, manage=True, allow_admin=True
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    old_classification = doc.classification

    from app.services.classification_service import apply_classification
    await apply_classification(doc, body.classification, confidence=1.0, classified_by=user.user_id)

    await audit_service.log_event(
        action="document.classify",
        actor_user_id=user.user_id,
        resource_type="document",
        resource_id=doc_uuid,
        resource_name=doc.title,
        detail={"old": old_classification, "new": body.classification, "reason": body.reason},
    )

    return {
        "uuid": doc_uuid,
        "classification": doc.classification,
        "classification_confidence": doc.classification_confidence,
        "classified_at": doc.classified_at.isoformat() if doc.classified_at else None,
        "classified_by": doc.classified_by,
    }


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

@router.post("/{doc_uuid}/retention-hold")
async def set_retention_hold(
    doc_uuid: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Place a legal hold on a document. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    doc = await access_control.get_authorized_document(
        doc_uuid, user, manage=True, allow_admin=True
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    body = await request.json()
    reason = body.get("reason", "Legal hold")

    doc.retention_hold = True
    doc.retention_hold_reason = reason
    doc.scheduled_deletion_at = None  # cancel any pending deletion
    await doc.save()

    await audit_service.log_event(
        action="document.retention_hold",
        actor_user_id=user.user_id,
        resource_type="document",
        resource_id=doc_uuid,
        resource_name=doc.title,
        detail={"reason": reason},
    )

    return {"detail": "Retention hold applied", "retention_hold": True}


@router.delete("/{doc_uuid}/retention-hold")
async def remove_retention_hold(
    doc_uuid: str,
    user: User = Depends(get_current_user),
):
    """Remove a legal hold from a document. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    doc = await access_control.get_authorized_document(
        doc_uuid, user, manage=True, allow_admin=True
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.retention_hold = False
    doc.retention_hold_reason = None
    await doc.save()

    await audit_service.log_event(
        action="document.retention_hold_removed",
        actor_user_id=user.user_id,
        resource_type="document",
        resource_id=doc_uuid,
        resource_name=doc.title,
    )

    return {"detail": "Retention hold removed", "retention_hold": False}
