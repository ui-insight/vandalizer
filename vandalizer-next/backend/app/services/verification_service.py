"""Verification queue service — submit, review, approve, reject."""

import datetime
from typing import Optional

from beanie import PydanticObjectId

from app.models.library import Library, LibraryItem, LibraryItemKind, LibraryScope
from app.models.verification import VerificationRequest, VerificationStatus
from app.models.workflow import Workflow
from app.models.search_set import SearchSet


async def submit_for_verification(
    item_kind: str,
    item_id: str,
    user_id: str,
    submitter_name: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    category: str | None = None,
) -> dict:
    """Create a verification request for a library item."""
    obj_id = PydanticObjectId(item_id)

    # Verify the item exists
    if item_kind == "workflow":
        obj = await Workflow.get(obj_id)
    else:
        obj = await SearchSet.get(obj_id)
    if not obj:
        raise ValueError("Item not found")

    # Check for existing pending request
    existing = await VerificationRequest.find_one(
        VerificationRequest.item_id == obj_id,
        VerificationRequest.status.is_in([  # type: ignore[attr-defined]
            VerificationStatus.SUBMITTED.value,
            VerificationStatus.IN_REVIEW.value,
        ]),
    )
    if existing:
        raise ValueError("A verification request is already pending for this item")

    req = VerificationRequest(
        item_kind=item_kind,
        item_id=obj_id,
        submitter_user_id=user_id,
        submitter_name=submitter_name,
        summary=summary,
        description=description,
        category=category,
    )
    await req.insert()
    return _request_to_dict(req)


async def list_queue(
    status_filter: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List verification requests (for reviewers)."""
    query: dict = {}
    if status_filter:
        query["status"] = status_filter
    else:
        query["status"] = {"$in": [
            VerificationStatus.SUBMITTED.value,
            VerificationStatus.IN_REVIEW.value,
        ]}

    requests = await VerificationRequest.find(query).sort("-submitted_at").limit(limit).to_list()
    results = []
    for req in requests:
        d = _request_to_dict(req)
        # Attach item name
        d["item_name"] = await _get_item_name(req.item_kind, req.item_id)
        results.append(d)
    return results


async def get_request(request_uuid: str) -> dict | None:
    """Get a single verification request by UUID."""
    req = await VerificationRequest.find_one(VerificationRequest.uuid == request_uuid)
    if not req:
        return None
    d = _request_to_dict(req)
    d["item_name"] = await _get_item_name(req.item_kind, req.item_id)
    return d


async def update_status(
    request_uuid: str,
    new_status: str,
    reviewer_user_id: str,
    reviewer_notes: str | None = None,
) -> dict | None:
    """Approve or reject a verification request."""
    req = await VerificationRequest.find_one(VerificationRequest.uuid == request_uuid)
    if not req:
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    req.status = new_status
    req.reviewer_user_id = reviewer_user_id
    req.reviewer_notes = reviewer_notes
    req.reviewed_at = now
    await req.save()

    # If approved, mark the library item as verified
    if new_status == VerificationStatus.APPROVED.value:
        await _mark_item_verified(req.item_id, req.item_kind)

    return _request_to_dict(req)


async def my_requests(user_id: str, limit: int = 50) -> list[dict]:
    """List a user's own verification requests."""
    requests = (
        await VerificationRequest.find(VerificationRequest.submitter_user_id == user_id)
        .sort("-submitted_at")
        .limit(limit)
        .to_list()
    )
    results = []
    for req in requests:
        d = _request_to_dict(req)
        d["item_name"] = await _get_item_name(req.item_kind, req.item_id)
        results.append(d)
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _mark_item_verified(item_id: PydanticObjectId, item_kind: str) -> None:
    """Set verified=True on all LibraryItem records pointing to this object."""
    items = await LibraryItem.find(
        LibraryItem.item_id == item_id,
        LibraryItem.kind == LibraryItemKind(item_kind),
    ).to_list()
    for item in items:
        item.verified = True
        await item.save()


async def _get_item_name(item_kind: str, item_id: PydanticObjectId) -> str:
    if item_kind == "workflow":
        wf = await Workflow.get(item_id)
        return wf.name if wf else "Unknown workflow"
    else:
        ss = await SearchSet.get(item_id)
        return ss.title if ss else "Unknown extraction"


def _request_to_dict(req: VerificationRequest) -> dict:
    return {
        "id": str(req.id),
        "uuid": req.uuid,
        "item_kind": req.item_kind,
        "item_id": str(req.item_id),
        "status": req.status,
        "submitter_user_id": req.submitter_user_id,
        "submitter_name": req.submitter_name,
        "summary": req.summary,
        "description": req.description,
        "category": req.category,
        "reviewer_user_id": req.reviewer_user_id,
        "reviewer_notes": req.reviewer_notes,
        "submitted_at": req.submitted_at.isoformat() if req.submitted_at else None,
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
    }
