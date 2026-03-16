import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional

from app.dependencies import get_current_user
from app.models.document import SmartDocument
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.services import audit_service, document_service

router = APIRouter()


@router.get("/list")
async def list_documents(
    space: str,
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

    return await document_service.list_contents(
        space, folder, user_id=user.user_id, team_uuid=team_uuid
    )


@router.get("/search")
async def search_documents(
    q: str = Query(default="", min_length=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """Search documents by title or content text. Returns recent docs when q is empty."""
    if not q.strip():
        results = await SmartDocument.find(
            {"user_id": user.user_id},
        ).sort(-SmartDocument.created_at).limit(limit).to_list()
    else:
        regex = re.compile(re.escape(q), re.IGNORECASE)
        results = await SmartDocument.find(
            {
                "$or": [
                    {"title": {"$regex": regex.pattern, "$options": "i"}},
                    {"raw_text": {"$regex": regex.pattern, "$options": "i"}},
                ],
                "user_id": user.user_id,
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
            "task_status": doc.task_status,
            "folder": doc.folder,
            "token_count": doc.token_count,
        })

    return {"items": items, "total": len(items)}


@router.get("/poll_status")
async def poll_status(
    docid: str,
    user: User = Depends(get_current_user),
):
    result = await document_service.poll_status(docid)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


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

    doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
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

    doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
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

    doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
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
