"""Verification queue API routes."""

import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.user import User
from app.services import verification_service as svc
from app.services import organization_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SubmitRequest(BaseModel):
    item_kind: str  # "workflow", "search_set", or "knowledge_base"
    item_id: str
    submitter_name: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    submitter_org: Optional[str] = None
    submitter_role: Optional[str] = None
    item_version_hash: Optional[str] = None
    run_instructions: Optional[str] = None
    evaluation_notes: Optional[str] = None
    known_limitations: Optional[str] = None
    example_inputs: Optional[list[str]] = None
    expected_outputs: Optional[list[str]] = None
    dependencies: Optional[list[str]] = None
    intended_use_tags: Optional[list[str]] = None
    test_files: Optional[list[dict]] = None


class UpdateStatusRequest(BaseModel):
    status: str  # "approved", "rejected", "in_review"
    reviewer_notes: Optional[str] = None
    organization_ids: Optional[list[str]] = None
    collection_ids: Optional[list[str]] = None


class MetadataUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    markdown: Optional[str] = None
    organization_ids: Optional[list[str]] = None


class CreateCollectionRequest(BaseModel):
    title: str
    description: Optional[str] = None


class UpdateCollectionRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class AddToCollectionRequest(BaseModel):
    item_id: str


class SetExaminerRequest(BaseModel):
    user_id: str
    is_examiner: bool


# ---------------------------------------------------------------------------
# Submission & Queue
# ---------------------------------------------------------------------------


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
            submitter_org=req.submitter_org,
            submitter_role=req.submitter_role,
            item_version_hash=req.item_version_hash,
            run_instructions=req.run_instructions,
            evaluation_notes=req.evaluation_notes,
            known_limitations=req.known_limitations,
            example_inputs=req.example_inputs,
            expected_outputs=req.expected_outputs,
            dependencies=req.dependencies,
            intended_use_tags=req.intended_use_tags,
            test_files=req.test_files,
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


# ---------------------------------------------------------------------------
# Verified Catalog
# ---------------------------------------------------------------------------


@router.get("/verified")
async def list_verified_items(
    kind: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    items = await svc.list_verified_items(
        kind_filter=kind, search=search, user_org_ancestry=user_org_ancestry,
    )
    return {"items": items}


@router.get("/verified/{item_kind}/{item_id}/metadata")
async def get_item_metadata(
    item_kind: str,
    item_id: str,
    user: User = Depends(get_current_user),
):
    meta = await svc.get_item_metadata(item_kind, item_id)
    return meta or {}


@router.put("/verified/{item_kind}/{item_id}/metadata")
async def update_item_metadata(
    item_kind: str,
    item_id: str,
    req: MetadataUpdateRequest,
    user: User = Depends(get_current_user),
):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    result = await svc.update_item_metadata(
        item_kind=item_kind,
        item_id=item_id,
        user_id=user.user_id,
        display_name=req.display_name,
        description=req.description,
        markdown=req.markdown,
        organization_ids=req.organization_ids,
    )
    return result


# ---------------------------------------------------------------------------
# Upload test files for verification submission
# ---------------------------------------------------------------------------


@router.post("/upload-test-file")
async def upload_test_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Upload a test file for a verification submission. Returns metadata."""
    import os
    import uuid

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    stored_name = f"{uuid.uuid4().hex}_{file.filename}"
    upload_dir = os.path.join("uploads", "test_files")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, stored_name)
    with open(file_path, "wb") as f:
        f.write(content)

    return {
        "original_name": file.filename,
        "stored_name": stored_name,
        "path": file_path,
    }


@router.get("/download-test-file/{stored_name}")
async def download_test_file(
    stored_name: str,
    user: User = Depends(get_current_user),
):
    """Download a test file by stored name."""
    import os

    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")

    file_path = os.path.join("uploads", "test_files", stored_name)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Extract original name from stored_name (uuid_originalname)
    parts = stored_name.split("_", 1)
    original_name = parts[1] if len(parts) > 1 else stored_name

    with open(file_path, "rb") as f:
        content = f.read()

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{original_name}"'},
    )


# ---------------------------------------------------------------------------
# Verification request status updates
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Unverify
# ---------------------------------------------------------------------------


@router.delete("/verified/{item_kind}/{item_id}")
async def unverify_item(
    item_kind: str,
    item_id: str,
    user: User = Depends(get_current_user),
):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    result = await svc.unverify_item(item_id, item_kind)
    return result


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


@router.get("/collections")
async def list_collections(user: User = Depends(get_current_user)):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    return {"collections": await svc.list_collections()}


@router.post("/collections")
async def create_collection(
    req: CreateCollectionRequest,
    user: User = Depends(get_current_user),
):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    result = await svc.create_collection(title=req.title, user_id=user.user_id, description=req.description)
    return result


@router.patch("/collections/{collection_id}")
async def update_collection(
    collection_id: str,
    req: UpdateCollectionRequest,
    user: User = Depends(get_current_user),
):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    result = await svc.update_collection(collection_id, title=req.title, description=req.description)
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return result


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
    user: User = Depends(get_current_user),
):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    ok = await svc.delete_collection(collection_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"ok": True}


@router.post("/collections/{collection_id}/items")
async def add_to_collection(
    collection_id: str,
    req: AddToCollectionRequest,
    user: User = Depends(get_current_user),
):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    result = await svc.add_to_collection(collection_id, req.item_id)
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return result


@router.delete("/collections/{collection_id}/items/{item_id}")
async def remove_from_collection(
    collection_id: str,
    item_id: str,
    user: User = Depends(get_current_user),
):
    result = await svc.remove_from_collection(collection_id, item_id)
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return result


# ---------------------------------------------------------------------------
# Examiner management (admin only)
# ---------------------------------------------------------------------------


@router.get("/examiners")
async def list_examiners(
    user: User = Depends(get_current_user),
):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    examiners = await svc.list_examiners()
    return {"examiners": examiners}


@router.post("/examiners")
async def set_examiner(
    req: SetExaminerRequest,
    user: User = Depends(get_current_user),
):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        result = await svc.set_examiner(req.user_id, req.is_examiner)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Catch-all request routes (must be last to avoid shadowing named routes)
# ---------------------------------------------------------------------------


@router.get("/{request_uuid}")
async def get_request(
    request_uuid: str,
    user: User = Depends(get_current_user),
):
    result = await svc.get_request(request_uuid)
    if not result:
        raise HTTPException(status_code=404, detail="Request not found")
    return result


@router.patch("/{request_uuid}/status")
async def update_status(
    request_uuid: str,
    req: UpdateStatusRequest,
    user: User = Depends(get_current_user),
):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")

    result = await svc.update_status(
        request_uuid=request_uuid,
        new_status=req.status,
        reviewer_user_id=user.user_id,
        reviewer_notes=req.reviewer_notes,
        organization_ids=req.organization_ids,
        collection_ids=req.collection_ids,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Request not found")
    return result
