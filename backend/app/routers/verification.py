"""Verification queue API routes."""

import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.user import User
from app.rate_limit import limiter
from app.services import access_control
from app.services import verification_service as svc
from app.services import organization_service

router = APIRouter()


def _require_examiner_access(user: User) -> None:
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")


async def _authorize_submission_target(item_kind: str, item_id: str, user: User) -> None:
    if item_kind == "workflow":
        obj = await access_control.get_authorized_workflow(item_id, user)
    elif item_kind == "search_set":
        obj = await access_control.get_authorized_search_set_by_id(item_id, user)
    elif item_kind == "knowledge_base":
        obj = await access_control.get_authorized_knowledge_base(item_id, user)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported item_kind: {item_kind}")

    if not obj:
        raise HTTPException(status_code=404, detail="Item not found")


async def _authorize_visible_verified_item(item_kind: str, item_id: str, user: User):
    if item_kind == "workflow":
        obj = await access_control.get_authorized_workflow(item_id, user)
    elif item_kind == "search_set":
        obj = await access_control.get_authorized_search_set_by_id(item_id, user)
    elif item_kind == "knowledge_base":
        obj = await access_control.get_authorized_knowledge_base_by_id(item_id, user)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported item_kind: {item_kind}")

    if not obj or not getattr(obj, "verified", False):
        raise HTTPException(status_code=404, detail="Verified item not found")
    return obj


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
    await _authorize_submission_target(req.item_kind, req.item_id, user)
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
    _require_examiner_access(user)
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
    await _authorize_visible_verified_item(item_kind, item_id, user)
    meta = await svc.get_item_metadata(item_kind, item_id)
    return meta or {}


@router.put("/verified/{item_kind}/{item_id}/metadata")
async def update_item_metadata(
    item_kind: str,
    item_id: str,
    req: MetadataUpdateRequest,
    user: User = Depends(get_current_user),
):
    _require_examiner_access(user)
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

    _require_examiner_access(user)

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
    _require_examiner_access(user)
    result = await svc.unverify_item(item_id, item_kind)
    return result


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


@router.get("/collections")
async def list_collections(user: User = Depends(get_current_user)):
    _require_examiner_access(user)
    return {"collections": await svc.list_collections()}


@router.post("/collections")
async def create_collection(
    req: CreateCollectionRequest,
    user: User = Depends(get_current_user),
):
    _require_examiner_access(user)
    result = await svc.create_collection(title=req.title, user_id=user.user_id, description=req.description)
    return result


@router.patch("/collections/{collection_id}")
async def update_collection(
    collection_id: str,
    req: UpdateCollectionRequest,
    user: User = Depends(get_current_user),
):
    _require_examiner_access(user)
    result = await svc.update_collection(collection_id, title=req.title, description=req.description)
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return result


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
    user: User = Depends(get_current_user),
):
    _require_examiner_access(user)
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
    _require_examiner_access(user)
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
    _require_examiner_access(user)
    result = await svc.remove_from_collection(collection_id, item_id)
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return result


# ---------------------------------------------------------------------------
# Catalog export / import
# ---------------------------------------------------------------------------


@router.get("/catalog/export")
async def export_catalog(user: User = Depends(get_current_user)):
    _require_examiner_access(user)

    from app.services import export_import_service as eis

    data = await eis.export_catalog(user.email or user.user_id)
    json_bytes = json.dumps(data, indent=2, default=str).encode()
    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="verified-catalog.vandalizer.json"'},
    )


@router.post("/catalog/preview-import")
async def preview_catalog_import(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    _require_examiner_access(user)

    from app.services import export_import_service as eis

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    try:
        items = eis.preview_catalog_import(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"items": items}


@router.post("/catalog/import")
async def import_catalog_items(
    file: UploadFile = File(...),
    selected_indices: str = Form(...),
    space: str | None = Form(None),
    user: User = Depends(get_current_user),
):
    _require_examiner_access(user)

    from app.services import export_import_service as eis

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    try:
        parsed_indices = json.loads(selected_indices)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="selected_indices must be valid JSON")

    if not isinstance(parsed_indices, list) or any(type(idx) is not int for idx in parsed_indices):
        raise HTTPException(status_code=400, detail="selected_indices must be a JSON array of integers")

    try:
        imported = await eis.import_catalog_items(
            data,
            parsed_indices,
            user.user_id,
            space=space,
            team_id=str(user.current_team) if user.current_team else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"imported": imported}


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
# Try a verified extraction on your own document
# ---------------------------------------------------------------------------


@router.post("/try/{item_kind}/{item_id}")
@limiter.limit("10/minute")
async def try_verified_item(
    request: Request,
    item_kind: str,
    item_id: str,
    user: User = Depends(get_current_user),
):
    """Run a trial extraction using a verified search set against user's own document.

    Lets users 'try before adopting' from the verified catalog.
    """
    if item_kind != "search_set":
        raise HTTPException(status_code=400, detail="Only search_set items can be tried")

    body = await request.json()
    document_uuid = body.get("document_uuid")
    source_text = body.get("source_text")

    if not document_uuid and not source_text:
        raise HTTPException(status_code=400, detail="Provide document_uuid or source_text")

    from app.models.search_set import SearchSet
    from app.models.verification import VerifiedItemMetadata
    from app.services.search_set_service import get_extraction_keys, get_extraction_field_metadata
    from app.services.extraction_engine import ExtractionEngine
    from app.models.system_config import SystemConfig
    from app.services.config_service import get_user_model_name
    import asyncio

    # Verify the item is actually verified
    ss = await SearchSet.find_one(SearchSet.uuid == item_id)
    if not ss or not ss.verified:
        raise HTTPException(status_code=404, detail="Verified item not found")

    meta = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == "search_set",
        VerifiedItemMetadata.item_id == str(ss.id),
    )
    if meta and meta.organization_ids:
        user_org_ancestry = await organization_service.get_user_org_ancestry(user) or []
        if not set(meta.organization_ids) & set(user_org_ancestry):
            raise HTTPException(status_code=404, detail="Verified item not found")

    # Resolve text
    text = source_text
    if document_uuid and not text:
        team_access = await access_control.get_team_access_context(user)
        doc = await access_control.get_authorized_document(
            document_uuid,
            user,
            team_access=team_access,
        )
        if not doc or not doc.raw_text:
            raise HTTPException(status_code=400, detail="Document not found or has no text")
        text = doc.raw_text

    keys = await get_extraction_keys(item_id)
    if not keys:
        raise HTTPException(status_code=400, detail="No extraction fields defined")

    field_metadata = await get_extraction_field_metadata(item_id)
    model = await get_user_model_name(user.user_id)
    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}
    extraction_config = ss.extraction_config if ss.extraction_config else None

    engine = ExtractionEngine(system_config_doc=sys_config_doc)
    result = await asyncio.to_thread(
        engine.extract,
        extract_keys=keys,
        model=model,
        doc_texts=[text],
        extraction_config_override=extraction_config,
        field_metadata=field_metadata,
    )

    flat: dict = {}
    if result and isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                flat.update(item)

    return {
        "search_set_uuid": item_id,
        "search_set_title": ss.title,
        "fields": keys,
        "extraction_result": flat,
    }


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
    if not (user.is_admin or user.is_examiner) and result.get("submitter_user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Request not found")
    return result


@router.patch("/{request_uuid}/status")
async def update_status(
    request_uuid: str,
    req: UpdateStatusRequest,
    user: User = Depends(get_current_user),
):
    _require_examiner_access(user)

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
