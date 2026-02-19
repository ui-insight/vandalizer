"""Verification queue API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.user import User
from app.services import verification_service as svc

router = APIRouter()


class SubmitRequest(BaseModel):
    item_kind: str  # "workflow" or "search_set"
    item_id: str
    submitter_name: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None


class UpdateStatusRequest(BaseModel):
    status: str  # "approved", "rejected", "in_review"
    reviewer_notes: Optional[str] = None


@router.post("/submit")
async def submit_for_verification(
    req: SubmitRequest,
    user: User = Depends(get_current_user),
):
    try:
        result = await svc.submit_for_verification(
            item_kind=req.item_kind,
            item_id=req.item_id,
            user_id=user.user_id,
            submitter_name=req.submitter_name,
            summary=req.summary,
            description=req.description,
            category=req.category,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/queue")
async def list_queue(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    requests = await svc.list_queue(status_filter=status, limit=limit)
    return {"requests": requests}


@router.get("/mine")
async def my_requests(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    requests = await svc.my_requests(user.user_id, limit=limit)
    return {"requests": requests}


@router.get("/{request_uuid}")
async def get_request(
    request_uuid: str,
    user: User = Depends(get_current_user),
):
    result = await svc.get_request(request_uuid)
    if not result:
        raise HTTPException(status_code=404, detail="Verification request not found")
    return result


@router.patch("/{request_uuid}/status")
async def update_status(
    request_uuid: str,
    req: UpdateStatusRequest,
    user: User = Depends(get_current_user),
):
    result = await svc.update_status(
        request_uuid=request_uuid,
        new_status=req.status,
        reviewer_user_id=user.user_id,
        reviewer_notes=req.reviewer_notes,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Verification request not found")
    return result
