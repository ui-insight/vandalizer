"""Extraction API routes  - SearchSet CRUD and extraction execution."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models.extraction_test_case import ExtractionTestCase

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse

from app.dependencies import get_api_key_user, get_current_user
from app.rate_limit import limiter
from app.models.activity import ActivityStatus, ActivityType
from app.models.user import User
from app.services import access_control, activity_service
from app.schemas.extractions import (
    BuildFromDocumentRequest,
    CreateSearchSetRequest,
    CreateTestCaseRequest,
    ExportPDFRequest,
    ReorderItemsRequest,
    RunExtractionSyncRequest,
    RunValidationRequest,
    RunValidationV2Request,
    SearchSetItemRequest,
    SearchSetItemResponse,
    SearchSetResponse,
    TestCaseResponse,
    UpdateSearchSetRequest,
    UpdateSearchSetItemRequest,
    UpdateTestCaseRequest,
)
from app.services import extraction_validation_service as val_svc
from app.services import search_set_service as svc

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _attach_quality(ss) -> dict:
    """Query quality data for a SearchSet from VerifiedItemMetadata or latest ValidationRun."""
    from app.models.verification import VerifiedItemMetadata
    from app.services.quality_service import get_latest_validation

    meta = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == "search_set",
        VerifiedItemMetadata.item_id == ss.uuid,
    )
    if meta:
        return {
            "quality_score": meta.quality_score,
            "quality_tier": meta.quality_tier,
            "last_validated_at": meta.last_validated_at.isoformat() if meta.last_validated_at else None,
            "validation_run_count": meta.validation_run_count or 0,
        }

    latest = await get_latest_validation("search_set", ss.uuid)
    if latest:
        return {
            "quality_score": latest.get("score"),
            "quality_tier": None,
            "last_validated_at": latest.get("created_at"),
            "validation_run_count": 1,
        }

    return {"quality_score": None, "quality_tier": None, "last_validated_at": None, "validation_run_count": 0}


async def _ss_response(ss) -> SearchSetResponse:
    """Build a SearchSetResponse with quality data attached."""
    count = await ss.item_count()
    quality = await _attach_quality(ss)
    return SearchSetResponse(
        id=str(ss.id), title=ss.title, uuid=ss.uuid,
        status=ss.status, set_type=ss.set_type, user_id=ss.user_id,
        team_id=ss.team_id, is_global=ss.is_global, verified=ss.verified, item_count=count,
        extraction_config=ss.extraction_config,
        fillable_pdf_url=ss.fillable_pdf_url,
        **quality,
    )


async def _get_search_set_or_404(uuid: str, user: User, *, manage: bool = False):
    ss = await access_control.get_authorized_search_set(
        uuid,
        user,
        manage=manage,
        allow_admin=True,
    )
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    return ss


async def _get_search_set_item_or_404(item_id: str, user: User):
    item = await svc.get_search_set_item(item_id)
    if not item or not item.searchset:
        raise HTTPException(status_code=404, detail="Item not found")
    await _get_search_set_or_404(item.searchset, user, manage=True)
    return item


async def _authorize_documents(document_uuids: list[str], user: User) -> list[str]:
    team_access = await access_control.get_team_access_context(user)
    authorized: list[str] = []
    for doc_uuid in document_uuids:
        doc = await access_control.get_authorized_document(
            doc_uuid,
            user,
            team_access=team_access,
            allow_admin=True,
        )
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_uuid}")
        authorized.append(doc.uuid)
    return authorized


# ---------------------------------------------------------------------------
# SearchSet CRUD
# ---------------------------------------------------------------------------

@router.post("/search-sets", response_model=SearchSetResponse)
async def create_search_set(req: CreateSearchSetRequest, user: User = Depends(get_current_user)):
    team_id = str(user.current_team) if user.current_team else None
    ss = await svc.create_search_set(
        req.title,
        user.user_id,
        req.set_type,
        extraction_config=req.extraction_config,
        team_id=team_id,
    )
    return await _ss_response(ss)


@router.get("/search-sets", response_model=list[SearchSetResponse])
async def list_search_sets(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    scope: str | None = Query(default=None),
    search: str | None = Query(default=None),
    user: User = Depends(get_current_user),
):
    sets = await svc.list_search_sets(user=user, skip=skip, limit=limit, scope=scope, search=search)
    return [await _ss_response(ss) for ss in sets]


@router.get("/search-sets/{uuid}", response_model=SearchSetResponse)
async def get_search_set(uuid: str, user: User = Depends(get_current_user)):
    ss = await _get_search_set_or_404(uuid, user)
    return await _ss_response(ss)


@router.patch("/search-sets/{uuid}", response_model=SearchSetResponse)
async def update_search_set(uuid: str, req: UpdateSearchSetRequest, user: User = Depends(get_current_user)):
    await _get_search_set_or_404(uuid, user, manage=True)
    ss = await svc.update_search_set(uuid, title=req.title, extraction_config=req.extraction_config)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    # Flag stale verification if this search set was verified
    from app.services.verification_service import check_and_flag_stale_verification
    await check_and_flag_stale_verification("search_set", str(ss.id))
    return await _ss_response(ss)


@router.delete("/search-sets/{uuid}")
async def delete_search_set(uuid: str, user: User = Depends(get_current_user)):
    await _get_search_set_or_404(uuid, user, manage=True)
    ok = await svc.delete_search_set(uuid)
    if not ok:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    return {"ok": True}


@router.post("/search-sets/{uuid}/clone", response_model=SearchSetResponse)
async def clone_search_set(uuid: str, user: User = Depends(get_current_user)):
    await _get_search_set_or_404(uuid, user)
    ss = await svc.clone_search_set(uuid, user.user_id)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    return await _ss_response(ss)


@router.get("/search-sets/{uuid}/export")
async def export_search_set(uuid: str, user: User = Depends(get_current_user)):
    """Download extraction definition as a shareable JSON file."""
    import io
    from app.services import export_import_service as eis

    await _get_search_set_or_404(uuid, user)
    try:
        data = await eis.export_search_set(uuid, user.email or user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    json_bytes = json.dumps(data, indent=2, default=str).encode()
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in (data["items"][0]["title"] or "extraction")).strip() or "extraction"
    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.vandalizer.json"'},
    )


@router.post("/search-sets/import", response_model=SearchSetResponse)
async def import_search_set(
    file: UploadFile = File(...),
    target_uuid: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
):
    """Import an extraction from an exported JSON file.

    If *target_uuid* is provided, items are appended to that existing SearchSet
    and its extraction_config is replaced. Otherwise a new SearchSet is created.
    """
    from app.services import export_import_service as eis

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    target = None
    if target_uuid:
        target = await _get_search_set_or_404(target_uuid, user, manage=True)

    team_id = str(user.current_team) if user.current_team else None
    try:
        ss = await eis.import_search_set(data, user.user_id, team_id=team_id, target=target)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await _ss_response(ss)


@router.post("/search-sets/{uuid}/upload-template", response_model=SearchSetResponse)
@limiter.limit("10/minute")
async def upload_pdf_template(
    request: Request,
    uuid: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Attach a fillable PDF template; auto-generate extraction items from its form fields."""
    from pathlib import Path
    from pydantic import BaseModel as PydanticBase
    from PyPDF2 import PdfReader
    from app.config import Settings
    from app.models.search_set import SearchSetItem
    from app.services.llm_service import create_chat_agent
    from app.services.config_service import get_default_model_name

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    ss = await _get_search_set_or_404(uuid, user, manage=True)

    settings = Settings()
    file_bytes = await file.read()

    # Save template file
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    template_filename = f"{uuid}_template.pdf"
    template_path = upload_dir / template_filename
    template_path.write_bytes(file_bytes)

    # Extract form field names
    import io
    reader = PdfReader(io.BytesIO(file_bytes))
    raw_fields = reader.get_fields() or {}
    if not raw_fields:
        raise HTTPException(status_code=422, detail="No form fields found in PDF")

    # Build field info dict: {field_name: value_or_options}
    field_info: dict[str, object] = {}
    for name, field_obj in raw_fields.items():
        if hasattr(field_obj, "get"):
            options = field_obj.get("/Opt")
            field_info[name] = options if options else None
        else:
            field_info[name] = None

    # Use LLM to map field names to human-readable extraction prompts
    class FieldMapping(PydanticBase):
        mappings: dict[str, str]  # {pdf_field_name: human_readable_prompt}

    from app.models.system_config import SystemConfig
    sys_cfg = await SystemConfig.get_config()
    sys_config_doc = sys_cfg.model_dump() if sys_cfg else {}

    model_name = await get_default_model_name()
    if not model_name:
        model_name = "gpt-4o-mini"
    agent = create_chat_agent(
        model_name,
        system_prompt=(
            "You are a document intelligence assistant. Given PDF form field names and their "
            "possible values, produce a JSON object with a 'mappings' key whose value maps each "
            "field name to a short, clear English extraction prompt (what to extract from a document "
            "to fill that field). Return only valid JSON."
        ),
        system_config_doc=sys_config_doc,
    )
    prompt = (
        f"PDF form fields and their options:\n{field_info}\n\n"
        "Return a JSON object with key 'mappings' mapping each field name to a human-readable "
        "extraction prompt."
    )
    result = await agent.run(prompt, output_type=FieldMapping)
    mappings: dict[str, str] = result.output.mappings

    # Replace all existing items with new ones from the mapping
    existing = await SearchSetItem.find(SearchSetItem.searchset == uuid).to_list()
    for item in existing:
        await item.delete()

    new_items = []
    for field_name, human_prompt in mappings.items():
        item = SearchSetItem(
            searchphrase=human_prompt,
            searchset=uuid,
            searchtype="extraction",
            pdf_binding=field_name,
            user_id=user.user_id,
        )
        await item.insert()
        new_items.append(item)

    # Update search set
    ss.fillable_pdf_url = template_filename
    ss.item_order = [str(i.id) for i in new_items]
    await ss.save()

    return await _ss_response(ss)


@router.post("/search-sets/{uuid}/generate-template")
@limiter.limit("10/minute")
async def generate_pdf_template(
    request: Request,
    uuid: str,
    user: User = Depends(get_current_user),
):
    """Generate an example fillable PDF from the current extraction items and attach it as the template."""
    from pathlib import Path
    from app.config import Settings
    from app.models.search_set import SearchSetItem
    from app.services.pdf_service import generate_fillable_template

    ss = await _get_search_set_or_404(uuid, user, manage=True)

    items = await SearchSetItem.find(SearchSetItem.searchset == uuid).to_list()
    if ss.item_order:
        order_map = {oid: idx for idx, oid in enumerate(ss.item_order)}
        items = sorted(items, key=lambda i: order_map.get(str(i.id), 9999))

    if not items:
        raise HTTPException(status_code=400, detail="No items to generate template from")

    pdf_bytes, field_names = generate_fillable_template(ss.title or "Extraction Template", items)

    settings = Settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    template_filename = f"{uuid}_template.pdf"
    (upload_dir / template_filename).write_bytes(pdf_bytes)

    for i, item in enumerate(items):
        item.pdf_binding = field_names[i]
        await item.save()

    ss.fillable_pdf_url = template_filename
    await ss.save()

    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in (ss.title or "template")).strip() or "template"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}_template.pdf"'},
    )


@router.post("/search-sets/{uuid}/export-pdf")
async def export_pdf(
    uuid: str,
    req: ExportPDFRequest,
    user: User = Depends(get_current_user),
):
    """Download a filled PDF template or a clean report PDF with extraction results."""
    from pathlib import Path
    from app.config import Settings
    from app.models.search_set import SearchSetItem
    from app.services.pdf_service import generate_extraction_pdf

    ss = await _get_search_set_or_404(uuid, user)

    items = await SearchSetItem.find(SearchSetItem.searchset == uuid).to_list()
    # Respect item_order if present
    if ss.item_order:
        order_map = {oid: idx for idx, oid in enumerate(ss.item_order)}
        items = sorted(items, key=lambda i: order_map.get(str(i.id), 9999))

    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in ss.title).strip() or "extraction"

    if ss.fillable_pdf_url:
        # Fill the PDF template
        from io import BytesIO
        from PyPDF2 import PdfReader, PdfWriter

        settings = Settings()
        template_path = Path(settings.upload_dir) / ss.fillable_pdf_url
        if not template_path.exists():
            raise HTTPException(status_code=404, detail="Template file not found on server")

        bindings: dict[str, str] = {}
        for item in items:
            if item.pdf_binding and item.searchphrase in req.results:
                bindings[item.pdf_binding] = req.results[item.searchphrase]

        reader = PdfReader(str(template_path))
        writer = PdfWriter()
        writer.append(reader)
        if bindings:
            writer.update_page_form_field_values(writer.pages[0], bindings, auto_regenerate=False)

        buf = BytesIO()
        writer.write(buf)
        pdf_bytes = buf.getvalue()
    else:
        pdf_bytes = generate_extraction_pdf(
            title=ss.title,
            items=items,
            results=req.results,
            document_names=req.document_names,
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.pdf"'},
    )


# ---------------------------------------------------------------------------
# SearchSetItem CRUD
# ---------------------------------------------------------------------------

@router.post("/search-sets/{uuid}/items", response_model=SearchSetItemResponse)
async def add_item(uuid: str, req: SearchSetItemRequest, user: User = Depends(get_current_user)):
    await _get_search_set_or_404(uuid, user, manage=True)
    item = await svc.add_item(
        uuid, req.searchphrase, req.searchtype, req.title, user.user_id,
        is_optional=req.is_optional, enum_values=req.enum_values or [],
    )
    return SearchSetItemResponse(
        id=str(item.id), searchphrase=item.searchphrase, searchset=item.searchset,
        searchtype=item.searchtype, title=item.title,
        is_optional=item.is_optional, enum_values=item.enum_values,
    )


@router.get("/search-sets/{uuid}/items", response_model=list[SearchSetItemResponse])
async def list_items(uuid: str, user: User = Depends(get_current_user)):
    await _get_search_set_or_404(uuid, user)
    items = await svc.list_items(uuid)
    return [
        SearchSetItemResponse(
            id=str(item.id), searchphrase=item.searchphrase, searchset=item.searchset,
            searchtype=item.searchtype, title=item.title,
            is_optional=item.is_optional, enum_values=item.enum_values,
            pdf_binding=item.pdf_binding,
        )
        for item in items
    ]


@router.patch("/items/{item_id}", response_model=SearchSetItemResponse)
async def update_item(item_id: str, req: UpdateSearchSetItemRequest, user: User = Depends(get_current_user)):
    await _get_search_set_item_or_404(item_id, user)
    item = await svc.update_item(
        item_id, searchphrase=req.searchphrase, title=req.title,
        is_optional=req.is_optional, enum_values=req.enum_values,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    # Flag stale verification on parent search set
    if item.searchset:
        from app.models.search_set import SearchSet
        from app.services.verification_service import check_and_flag_stale_verification
        parent_ss = await SearchSet.find_one(SearchSet.uuid == item.searchset)
        if parent_ss:
            await check_and_flag_stale_verification("search_set", str(parent_ss.id))
    return SearchSetItemResponse(
        id=str(item.id), searchphrase=item.searchphrase, searchset=item.searchset,
        searchtype=item.searchtype, title=item.title,
        is_optional=item.is_optional, enum_values=item.enum_values,
    )


@router.post("/search-sets/{uuid}/reorder-items")
async def reorder_items(uuid: str, req: ReorderItemsRequest, user: User = Depends(get_current_user)):
    await _get_search_set_or_404(uuid, user, manage=True)
    ok = await svc.reorder_items(uuid, req.item_ids)
    if not ok:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    return {"ok": True}


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, user: User = Depends(get_current_user)):
    await _get_search_set_item_or_404(item_id, user)
    ok = await svc.delete_item(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Extraction execution
# ---------------------------------------------------------------------------

@router.post("/search-sets/{uuid}/build-from-document")
@limiter.limit("10/minute")
async def build_from_document(request: Request, uuid: str, req: BuildFromDocumentRequest, user: User = Depends(get_current_user)):
    """Use AI to analyze selected documents and generate extraction fields."""
    await _get_search_set_or_404(uuid, user)
    document_uuids = await _authorize_documents(req.document_uuids, user)
    try:
        entities = await svc.build_from_documents(
            search_set_uuid=uuid,
            document_uuids=document_uuids,
            user_id=user.user_id,
            model=req.model,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"entities": entities}


@router.post("/run-sync")
@limiter.limit("30/minute")
async def run_extraction_sync(request: Request, req: RunExtractionSyncRequest, user: User = Depends(get_current_user)) -> dict:
    # Look up the search set for the activity title
    ss = await _get_search_set_or_404(req.search_set_uuid, user)
    document_uuids = await _authorize_documents(req.document_uuids, user)
    title = ss.title

    # Create activity event
    activity = await activity_service.activity_start(
        type=ActivityType.SEARCH_SET_RUN,
        title=title,
        user_id=user.user_id,
        team_id=str(user.current_team) if user.current_team else None,
        search_set_uuid=req.search_set_uuid,
    )
    assert activity.id is not None

    try:
        results = await svc.run_extraction_sync(
            search_set_uuid=req.search_set_uuid,
            document_uuids=document_uuids,
            user_id=user.user_id,
            model=req.model,
            extraction_config_override=req.extraction_config_override,
            combined_context=req.combined_context,
        )
        await activity_service.activity_finish(activity.id, ActivityStatus.COMPLETED)
        # Merge all result entities into a single normalized map so the
        # activity rail can restore results when the user reopens the run.
        normalized: dict = {}
        for entity in results:
            if isinstance(entity, dict):
                normalized.update(entity)
        await activity_service.activity_update(
            activity.id,
            documents_touched=len(document_uuids),
            result_snapshot={
                "normalized": normalized,
                "document_uuids": document_uuids,
                "search_set_uuid": req.search_set_uuid,
            },
        )

        # Fire-and-forget auto-validation if test cases exist
        from app.tasks.quality_tasks import auto_validate_extraction
        auto_validate_extraction.delay(req.search_set_uuid, user.user_id, req.model)

        return {"results": results}
    except Exception as e:
        await activity_service.activity_finish(
            activity.id, ActivityStatus.FAILED, error=str(e),
        )
        raise


# ---------------------------------------------------------------------------
# External API integration endpoints (x-api-key auth)
# ---------------------------------------------------------------------------


@router.post("/run-integrated")
@limiter.limit("10/minute")
async def run_extraction_integrated(
    request: Request,
    search_set_uuid: str = Form(...),
    document_uuids: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
    user: User = Depends(get_api_key_user),
) -> dict:
    """Run extraction via external API. Accepts optional file uploads and/or existing document UUIDs."""
    import uuid as _uuid
    from pathlib import Path
    from app.config import Settings
    from app.models.document import SmartDocument
    from app.tasks.upload_tasks import dispatch_upload_tasks

    settings = Settings()
    all_doc_uuids: list[str] = []

    # Parse existing document UUIDs
    if document_uuids:
        all_doc_uuids.extend(u.strip() for u in document_uuids.split(",") if u.strip())

    # Handle file uploads
    for upload in files:
        if not upload.filename:
            continue
        uid = _uuid.uuid4().hex.upper()
        ext = (upload.filename.rsplit(".", 1)[-1] if "." in upload.filename else "pdf").lower()
        relative_path = Path(user.user_id) / f"{uid}.{ext}"
        upload_dir = Path(settings.upload_dir) / user.user_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{uid}.{ext}"
        file_data = await upload.read()
        file_path.write_bytes(file_data)

        doc = SmartDocument(
            title=upload.filename,
            processing=True,
            valid=True,
            raw_text="",
            downloadpath=str(relative_path),
            path=str(relative_path),
            extension=ext,
            uuid=uid,
            user_id=user.user_id,
            folder="0",
        )
        await doc.insert()

        task_id = dispatch_upload_tasks(
            document_uuid=uid, extension=ext, document_path=str(file_path),
            user_id=user.user_id,
        )
        doc.task_id = task_id
        await doc.save()
        all_doc_uuids.append(uid)

    if not all_doc_uuids:
        raise HTTPException(status_code=400, detail="No documents or files provided")

    # Look up the search set
    ss = await _get_search_set_or_404(search_set_uuid, user)
    existing_doc_uuids = await _authorize_documents(all_doc_uuids, user)
    new_doc_uuids = [doc_uuid for doc_uuid in all_doc_uuids if doc_uuid not in existing_doc_uuids]
    all_doc_uuids = existing_doc_uuids + new_doc_uuids

    # Create activity
    activity = await activity_service.activity_start(
        type=ActivityType.SEARCH_SET_RUN,
        title=ss.title,
        user_id=user.user_id,
        search_set_uuid=search_set_uuid,
    )
    assert activity.id is not None

    try:
        results = await svc.run_extraction_sync(
            search_set_uuid=search_set_uuid,
            document_uuids=all_doc_uuids,
            user_id=user.user_id,
        )
        await activity_service.activity_finish(activity.id, ActivityStatus.COMPLETED)
        await activity_service.activity_update(activity.id, documents_touched=len(all_doc_uuids))
        return {"status": "completed", "activity_id": str(activity.id), "results": results}
    except Exception as e:
        await activity_service.activity_finish(activity.id, ActivityStatus.FAILED, error=str(e))
        raise


@router.get("/status/{activity_id}")
async def get_extraction_status(
    activity_id: str,
    user: User = Depends(get_api_key_user),
) -> dict:
    """Check extraction status by activity ID."""
    try:
        activity_oid = PydanticObjectId(activity_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Activity not found") from exc

    activity = await activity_service.get_activity(activity_oid, user.user_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return {
        "status": activity.status,
        "title": activity.title,
        "started_at": activity.started_at.isoformat() if activity.started_at else None,
        "finished_at": activity.finished_at.isoformat() if activity.finished_at else None,
        "error": activity.error,
        "documents_touched": activity.documents_touched,
        "result_snapshot": activity.result_snapshot,
    }


# ---------------------------------------------------------------------------
# Extraction test cases & validation
# ---------------------------------------------------------------------------

def _tc_response(tc: "ExtractionTestCase") -> TestCaseResponse:
    return TestCaseResponse(
        id=str(tc.id),
        uuid=tc.uuid,
        search_set_uuid=tc.search_set_uuid,
        label=tc.label,
        source_type=tc.source_type,
        source_text=tc.source_text,
        document_uuid=tc.document_uuid,
        expected_values=tc.expected_values,
        user_id=tc.user_id,
        created_at=tc.created_at.isoformat(),
    )


@router.post("/test-cases", response_model=TestCaseResponse)
async def create_test_case(req: CreateTestCaseRequest, user: User = Depends(get_current_user)) -> TestCaseResponse:
    await _get_search_set_or_404(req.search_set_uuid, user, manage=True)
    if req.document_uuid:
        await _authorize_documents([req.document_uuid], user)
    tc = await val_svc.create_test_case(
        search_set_uuid=req.search_set_uuid,
        label=req.label,
        source_type=req.source_type,
        user_id=user.user_id,
        source_text=req.source_text,
        document_uuid=req.document_uuid,
        expected_values=req.expected_values,
    )
    return _tc_response(tc)


@router.get("/test-cases", response_model=list[TestCaseResponse])
async def list_test_cases(search_set_uuid: str, user: User = Depends(get_current_user)) -> list[TestCaseResponse]:
    await _get_search_set_or_404(search_set_uuid, user, manage=True)
    tcs = await val_svc.list_test_cases(search_set_uuid)
    return [_tc_response(tc) for tc in tcs]


@router.patch("/test-cases/{uuid}", response_model=TestCaseResponse)
async def update_test_case(uuid: str, req: UpdateTestCaseRequest, user: User = Depends(get_current_user)) -> TestCaseResponse:
    current = await val_svc.get_test_case(uuid)
    if not current:
        raise HTTPException(status_code=404, detail="Test case not found")
    await _get_search_set_or_404(current.search_set_uuid, user, manage=True)
    if req.document_uuid:
        await _authorize_documents([req.document_uuid], user)
    tc = await val_svc.update_test_case(
        uuid,
        label=req.label,
        source_type=req.source_type,
        source_text=req.source_text,
        document_uuid=req.document_uuid,
        expected_values=req.expected_values,
    )
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    return _tc_response(tc)


@router.delete("/test-cases/{uuid}")
async def delete_test_case(uuid: str, user: User = Depends(get_current_user)) -> dict:
    current = await val_svc.get_test_case(uuid)
    if not current:
        raise HTTPException(status_code=404, detail="Test case not found")
    await _get_search_set_or_404(current.search_set_uuid, user, manage=True)
    ok = await val_svc.delete_test_case(uuid)
    if not ok:
        raise HTTPException(status_code=404, detail="Test case not found")
    return {"ok": True}


@router.post("/test-cases/from-extraction")
@limiter.limit("10/minute")
async def create_test_cases_from_extraction(request: Request, user: User = Depends(get_current_user)) -> dict:
    """Run extraction on documents and auto-create test cases from results.

    The 'extract once, review, save as test case' flow. Users can then
    edit the expected_values on each test case to correct any mistakes.
    """
    body = await request.json()
    search_set_uuid = body.get("search_set_uuid")
    document_uuids = body.get("document_uuids", [])
    model = body.get("model")

    if not search_set_uuid:
        raise HTTPException(status_code=400, detail="search_set_uuid is required")
    if not document_uuids:
        raise HTTPException(status_code=400, detail="At least one document_uuid is required")

    await _get_search_set_or_404(search_set_uuid, user, manage=True)
    await _authorize_documents(document_uuids, user)

    try:
        test_cases = await val_svc.create_test_cases_from_extraction(
            search_set_uuid=search_set_uuid,
            document_uuids=document_uuids,
            user_id=user.user_id,
            model=model,
        )
        return {"test_cases": [_tc_response(tc) for tc in test_cases], "count": len(test_cases)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/search-sets/{uuid}/history")
async def get_extraction_history(
    uuid: str, limit: int = 50, user: User = Depends(get_current_user),
) -> dict:
    """List the current user's past runs of this extraction."""
    await _get_search_set_or_404(uuid, user)
    from app.models.activity import ActivityEvent
    events = (
        await ActivityEvent.find(
            ActivityEvent.search_set_uuid == uuid,
            ActivityEvent.user_id == user.user_id,
            ActivityEvent.type == "search_set_run",
        )
        .sort("-started_at")
        .limit(limit)
        .to_list()
    )
    return {
        "runs": [
            {
                "id": str(ev.id),
                "status": ev.status,
                "started_at": ev.started_at.isoformat() if ev.started_at else None,
                "finished_at": ev.finished_at.isoformat() if ev.finished_at else None,
                "duration_ms": ev.duration_ms,
                "error": ev.error or "",
                "tokens_input": ev.tokens_input,
                "tokens_output": ev.tokens_output,
                "documents_touched": ev.documents_touched,
                "result_snapshot": ev.result_snapshot or {},
            }
            for ev in events
        ],
    }


@router.get("/search-sets/{uuid}/quality-history")
async def get_extraction_quality_history(
    uuid: str, limit: int = 50, user: User = Depends(get_current_user),
) -> dict:
    await _get_search_set_or_404(uuid, user)
    from app.services.quality_service import get_quality_history
    return {"runs": await get_quality_history("search_set", uuid, limit)}


@router.get("/search-sets/{uuid}/quality-sparkline")
async def get_extraction_quality_sparkline(
    uuid: str, limit: int = 10, user: User = Depends(get_current_user),
) -> dict:
    """Return compact score history for sparkline visualization."""
    await _get_search_set_or_404(uuid, user)
    from app.services.quality_service import get_quality_history
    runs = await get_quality_history("search_set", uuid, limit)
    scores = [{"score": r["score"], "created_at": r["created_at"]} for r in reversed(runs)]
    return {"scores": scores}


@router.get("/search-sets/{uuid}/quality-status")
async def get_extraction_quality_status(
    uuid: str, user: User = Depends(get_current_user),
) -> dict:
    """Return quality status for Quality Pulse card."""
    import hashlib
    import json
    from app.models.verification import VerifiedItemMetadata
    from app.services.quality_service import get_latest_validation

    ss = await _get_search_set_or_404(uuid, user)

    meta = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == "search_set",
        VerifiedItemMetadata.item_id == uuid,
    )
    latest = await get_latest_validation("search_set", uuid)

    if not latest and not meta:
        return {"status": "unvalidated", "score": None, "tier": None, "config_changed": False, "stale": False}

    score = meta.quality_score if meta else latest.get("score") if latest else None
    tier = meta.quality_tier if meta else None
    last_at = (meta.last_validated_at.isoformat() if meta and meta.last_validated_at else
               latest.get("created_at") if latest else None)

    # Check if config changed since last validation
    config_changed = False
    if latest:
        last_config = latest.get("extraction_config", {})
        current_config = ss.extraction_config or {}
        current_hash = hashlib.sha256(json.dumps(current_config, sort_keys=True).encode()).hexdigest()
        last_hash = hashlib.sha256(json.dumps(last_config, sort_keys=True).encode()).hexdigest()
        config_changed = current_hash != last_hash

    # Check staleness (>14 days)
    import datetime
    stale = False
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if meta and meta.last_validated_at:
        lv = meta.last_validated_at
        if lv.tzinfo is None:
            lv = lv.replace(tzinfo=datetime.timezone.utc)
        stale = (now_utc - lv).days > 14
    elif latest and latest.get("created_at"):
        from dateutil.parser import isoparse
        created = isoparse(latest["created_at"])
        if created.tzinfo is None:
            created = created.replace(tzinfo=datetime.timezone.utc)
        stale = (now_utc - created).days > 14

    return {
        "status": "validated",
        "score": score,
        "tier": tier,
        "last_validated_at": last_at,
        "config_changed": config_changed,
        "stale": stale,
    }


@router.get("/search-sets/{uuid}/quality-contract")
async def get_extraction_quality_contract(
    uuid: str, user: User = Depends(get_current_user),
) -> dict:
    """Return quality contract status for a search set."""
    await _get_search_set_or_404(uuid, user)
    from app.services.quality_service import get_quality_contract_status
    return await get_quality_contract_status("search_set", uuid)


@router.get("/search-sets/{uuid}/verification-readiness")
async def check_verification_readiness(uuid: str, user: User = Depends(get_current_user)) -> dict:
    """Check if a search set meets minimum thresholds for verification submission."""
    await _get_search_set_or_404(uuid, user)
    from app.services.quality_service import check_verification_readiness as check_ready
    return await check_ready("search_set", uuid)


@router.post("/search-sets/{uuid}/improvement-suggestions")
@limiter.limit("5/minute")
async def get_extraction_suggestions(
    request: Request,
    uuid: str, user: User = Depends(get_current_user),
) -> dict:
    """Use LLM to suggest improvements based on validation results or field config."""
    await _get_search_set_or_404(uuid, user)
    from app.services.quality_service import get_latest_validation, generate_improvement_suggestions

    latest = await get_latest_validation("search_set", uuid)
    result_snapshot = (latest.get("result_snapshot") or {}) if latest else {}

    # If no validation run or no test cases, build a basic snapshot from field config
    if not result_snapshot.get("test_cases"):
        items = await svc.list_items(uuid)
        result_snapshot = {
            "aggregate_accuracy": None,
            "aggregate_consistency": None,
            "test_cases": [{
                "label": "Field Configuration Review",
                "overall_accuracy": None,
                "overall_consistency": None,
                "fields": [
                    {
                        "field_name": item.searchphrase,
                        "expected": "N/A",
                        "most_common_value": "not yet run",
                        "accuracy": None,
                        "consistency": None,
                        "is_optional": item.is_optional,
                        "enum_values": item.enum_values,
                    }
                    for item in items if item.searchphrase
                ],
            }],
        }

    suggestions = await generate_improvement_suggestions("search_set", uuid, result_snapshot)
    return {"suggestions": suggestions}


@router.post("/search-sets/{uuid}/find-best-settings")
@limiter.limit("3/minute")
async def find_best_settings(
    request: Request,
    uuid: str,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Try multiple extraction configurations via SSE, streaming results as each finishes."""
    await _get_search_set_or_404(uuid, user, manage=True)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    num_runs = body.get("num_runs", 2)
    max_candidates = body.get("max_candidates", 8)

    from app.services.extraction_tuning_service import find_best_settings_stream

    async def generate():
        try:
            async for event in find_best_settings_stream(
                search_set_uuid=uuid,
                user_id=user.user_id,
                num_runs=min(num_runs, 5),
                max_candidates=min(max_candidates, 12),
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'kind': 'error', 'detail': str(e)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'kind': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/search-sets/{uuid}/tuning-result")
async def get_tuning_result(uuid: str, user: User = Depends(get_current_user)) -> dict:
    """Return the persisted tuning result for a search set, or null."""
    ss = await _get_search_set_or_404(uuid, user)
    return {"tuning_result": ss.tuning_result}


@router.delete("/search-sets/{uuid}/tuning-result")
async def clear_tuning_result(uuid: str, user: User = Depends(get_current_user)) -> dict:
    """Clear the persisted tuning result."""
    ss = await _get_search_set_or_404(uuid, user, manage=True)
    ss.tuning_result = None
    await ss.save()
    return {"ok": True}


@router.post("/validate")
@limiter.limit("10/minute")
async def run_validation(request: Request, req: RunValidationRequest, user: User = Depends(get_current_user)) -> dict:
    await _get_search_set_or_404(req.search_set_uuid, user, manage=True)
    try:
        result = await val_svc.run_validation(
            search_set_uuid=req.search_set_uuid,
            user_id=user.user_id,
            test_case_uuids=req.test_case_uuids or None,
            num_runs=req.num_runs,
            model=req.model,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/validate-v2")
@limiter.limit("10/minute")
async def run_validation_v2(request: Request, req: RunValidationV2Request, user: User = Depends(get_current_user)) -> dict:
    await _get_search_set_or_404(req.search_set_uuid, user, manage=True)
    document_uuids = [source.document_uuid for source in req.sources if source.document_uuid]
    if document_uuids:
        await _authorize_documents(document_uuids, user)
    try:
        result = await val_svc.run_validation_v2(
            search_set_uuid=req.search_set_uuid,
            user_id=user.user_id,
            sources=[s.model_dump() for s in req.sources],
            num_runs=req.num_runs,
            model=req.model,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Cross-Field Validation Rules
# ---------------------------------------------------------------------------

@router.get("/search-sets/{uuid}/cross-field-rules")
async def get_cross_field_rules(uuid: str, user: User = Depends(get_current_user)) -> dict:
    """Get cross-field validation rules for a search set."""
    ss = await _get_search_set_or_404(uuid, user)
    return {"rules": ss.cross_field_rules}


@router.put("/search-sets/{uuid}/cross-field-rules")
async def update_cross_field_rules(uuid: str, request: Request, user: User = Depends(get_current_user)) -> dict:
    """Update cross-field validation rules for a search set."""
    body = await request.json()
    rules = body.get("rules", [])

    ss = await _get_search_set_or_404(uuid, user, manage=True)

    ss.cross_field_rules = rules
    await ss.save()
    return {"rules": ss.cross_field_rules}


@router.post("/search-sets/{uuid}/validate-cross-field")
async def validate_cross_field(uuid: str, request: Request, user: User = Depends(get_current_user)) -> dict:
    """Run cross-field validation rules against provided extraction data."""
    body = await request.json()
    data = body.get("data", {})

    ss = await _get_search_set_or_404(uuid, user)

    if not ss.cross_field_rules:
        return {"results": [], "message": "No cross-field rules defined"}

    from app.services.cross_field_validation import CrossFieldValidator
    validator = CrossFieldValidator()
    results = validator.validate(data, ss.cross_field_rules)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    return {
        "results": results,
        "summary": {"passed": passed, "failed": total - passed, "total": total},
    }
