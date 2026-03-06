"""Extraction API routes  - SearchSet CRUD and extraction execution."""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from app.dependencies import get_api_key_user, get_current_user
from app.models.activity import ActivityStatus, ActivityType
from app.models.user import User
from app.services import activity_service
from app.schemas.extractions import (
    BuildFromDocumentRequest,
    CreateSearchSetRequest,
    CreateTestCaseRequest,
    ExportPDFRequest,
    ExtractionStatusResponse,
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
        id=str(ss.id), title=ss.title, uuid=ss.uuid, space=ss.space,
        status=ss.status, set_type=ss.set_type, user_id=ss.user_id,
        is_global=ss.is_global, verified=ss.verified, item_count=count,
        extraction_config=ss.extraction_config,
        fillable_pdf_url=ss.fillable_pdf_url,
        **quality,
    )


# ---------------------------------------------------------------------------
# SearchSet CRUD
# ---------------------------------------------------------------------------

@router.post("/search-sets", response_model=SearchSetResponse)
async def create_search_set(req: CreateSearchSetRequest, user: User = Depends(get_current_user)):
    ss = await svc.create_search_set(req.title, req.space, req.set_type, user.user_id, extraction_config=req.extraction_config)
    return await _ss_response(ss)


@router.get("/search-sets", response_model=list[SearchSetResponse])
async def list_search_sets(space: str | None = None, user: User = Depends(get_current_user)):
    sets = await svc.list_search_sets(space=space)
    return [await _ss_response(ss) for ss in sets]


@router.get("/search-sets/{uuid}", response_model=SearchSetResponse)
async def get_search_set(uuid: str, user: User = Depends(get_current_user)):
    ss = await svc.get_search_set(uuid)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    return await _ss_response(ss)


@router.patch("/search-sets/{uuid}", response_model=SearchSetResponse)
async def update_search_set(uuid: str, req: UpdateSearchSetRequest, user: User = Depends(get_current_user)):
    ss = await svc.update_search_set(uuid, title=req.title, extraction_config=req.extraction_config)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    return await _ss_response(ss)


@router.delete("/search-sets/{uuid}")
async def delete_search_set(uuid: str, user: User = Depends(get_current_user)):
    ok = await svc.delete_search_set(uuid)
    if not ok:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    return {"ok": True}


@router.post("/search-sets/{uuid}/clone", response_model=SearchSetResponse)
async def clone_search_set(uuid: str, user: User = Depends(get_current_user)):
    ss = await svc.clone_search_set(uuid, user.user_id)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    return await _ss_response(ss)


@router.post("/search-sets/{uuid}/upload-template", response_model=SearchSetResponse)
async def upload_pdf_template(
    uuid: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Attach a fillable PDF template; auto-generate extraction items from its form fields."""
    import re
    from pathlib import Path
    from pydantic import BaseModel as PydanticBase
    from PyPDF2 import PdfReader
    from app.config import Settings
    from app.models.search_set import SearchSetItem
    from app.services.llm_service import create_chat_agent
    from app.services.config_service import get_default_model_name

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    ss = await svc.get_search_set(uuid)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")

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

    model_name = await get_default_model_name()
    agent = create_chat_agent(
        model_name,
        system_prompt=(
            "You are a document intelligence assistant. Given PDF form field names and their "
            "possible values, produce a JSON object with a 'mappings' key whose value maps each "
            "field name to a short, clear English extraction prompt (what to extract from a document "
            "to fill that field). Return only valid JSON."
        ),
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
async def generate_pdf_template(
    uuid: str,
    user: User = Depends(get_current_user),
):
    """Generate an example fillable PDF from the current extraction items and attach it as the template."""
    from pathlib import Path
    from app.config import Settings
    from app.models.search_set import SearchSetItem
    from app.services.pdf_service import generate_fillable_template

    ss = await svc.get_search_set(uuid)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")

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

    ss = await svc.get_search_set(uuid)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")

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
    item = await svc.update_item(
        item_id, searchphrase=req.searchphrase, title=req.title,
        is_optional=req.is_optional, enum_values=req.enum_values,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return SearchSetItemResponse(
        id=str(item.id), searchphrase=item.searchphrase, searchset=item.searchset,
        searchtype=item.searchtype, title=item.title,
        is_optional=item.is_optional, enum_values=item.enum_values,
    )


@router.post("/search-sets/{uuid}/reorder-items")
async def reorder_items(uuid: str, req: ReorderItemsRequest, user: User = Depends(get_current_user)):
    ok = await svc.reorder_items(uuid, req.item_ids)
    if not ok:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    return {"ok": True}


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, user: User = Depends(get_current_user)):
    ok = await svc.delete_item(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Extraction execution
# ---------------------------------------------------------------------------

@router.post("/search-sets/{uuid}/build-from-document")
async def build_from_document(uuid: str, req: BuildFromDocumentRequest, user: User = Depends(get_current_user)):
    """Use AI to analyze selected documents and generate extraction fields."""
    try:
        entities = await svc.build_from_documents(
            search_set_uuid=uuid,
            document_uuids=req.document_uuids,
            user_id=user.user_id,
            model=req.model,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"entities": entities}


@router.post("/run-sync")
async def run_extraction_sync(req: RunExtractionSyncRequest, user: User = Depends(get_current_user)):
    # Look up the search set for the activity title
    ss = await svc.get_search_set(req.search_set_uuid)
    title = ss.title if ss else req.search_set_uuid

    # Create activity event
    activity = await activity_service.activity_start(
        type=ActivityType.SEARCH_SET_RUN,
        title=title,
        user_id=user.user_id,
        team_id=str(user.current_team) if user.current_team else None,
        search_set_uuid=req.search_set_uuid,
    )

    try:
        results = await svc.run_extraction_sync(
            search_set_uuid=req.search_set_uuid,
            document_uuids=req.document_uuids,
            user_id=user.user_id,
            model=req.model,
            extraction_config_override=req.extraction_config_override,
        )
        await activity_service.activity_finish(activity.id, ActivityStatus.COMPLETED)
        await activity_service.activity_update(
            activity.id,
            documents_touched=len(req.document_uuids),
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
async def run_extraction_integrated(
    search_set_uuid: str = Form(...),
    document_uuids: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
    user: User = Depends(get_api_key_user),
):
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
            space="default",
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
    ss = await svc.get_search_set(search_set_uuid)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")

    # Create activity
    activity = await activity_service.activity_start(
        type=ActivityType.SEARCH_SET_RUN,
        title=ss.title,
        user_id=user.user_id,
        search_set_uuid=search_set_uuid,
    )

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
):
    """Check extraction status by activity ID."""
    activity = await activity_service.get_activity(activity_id, user.user_id)
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

def _tc_response(tc) -> TestCaseResponse:
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
async def create_test_case(req: CreateTestCaseRequest, user: User = Depends(get_current_user)):
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
async def list_test_cases(search_set_uuid: str, user: User = Depends(get_current_user)):
    tcs = await val_svc.list_test_cases(search_set_uuid)
    return [_tc_response(tc) for tc in tcs]


@router.patch("/test-cases/{uuid}", response_model=TestCaseResponse)
async def update_test_case(uuid: str, req: UpdateTestCaseRequest, user: User = Depends(get_current_user)):
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
async def delete_test_case(uuid: str, user: User = Depends(get_current_user)):
    ok = await val_svc.delete_test_case(uuid)
    if not ok:
        raise HTTPException(status_code=404, detail="Test case not found")
    return {"ok": True}


@router.get("/search-sets/{uuid}/quality-history")
async def get_extraction_quality_history(
    uuid: str, limit: int = 50, user: User = Depends(get_current_user),
):
    from app.services.quality_service import get_quality_history
    return {"runs": await get_quality_history("search_set", uuid, limit)}


@router.get("/search-sets/{uuid}/quality-sparkline")
async def get_extraction_quality_sparkline(
    uuid: str, limit: int = 10, user: User = Depends(get_current_user),
):
    """Return compact score history for sparkline visualization."""
    from app.services.quality_service import get_quality_history
    runs = await get_quality_history("search_set", uuid, limit)
    scores = [{"score": r["score"], "created_at": r["created_at"]} for r in reversed(runs)]
    return {"scores": scores}


@router.get("/search-sets/{uuid}/quality-status")
async def get_extraction_quality_status(
    uuid: str, user: User = Depends(get_current_user),
):
    """Return quality status for Quality Pulse card."""
    import hashlib
    import json
    from app.models.verification import VerifiedItemMetadata
    from app.services.quality_service import get_latest_validation

    ss = await svc.get_search_set(uuid)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")

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
):
    """Return quality contract status for a search set."""
    from app.services.quality_service import get_quality_contract_status
    return await get_quality_contract_status("search_set", uuid)


@router.post("/search-sets/{uuid}/improvement-suggestions")
async def get_extraction_suggestions(
    uuid: str, user: User = Depends(get_current_user),
):
    """Use LLM to suggest improvements based on the latest validation run."""
    from app.services.quality_service import get_latest_validation, generate_improvement_suggestions

    latest = await get_latest_validation("search_set", uuid)
    if not latest:
        raise HTTPException(status_code=404, detail="No validation runs found for this search set")
    result_snapshot = latest.get("result_snapshot", latest)
    suggestions = await generate_improvement_suggestions("search_set", uuid, result_snapshot)
    return {"suggestions": suggestions}


@router.post("/validate")
async def run_validation(req: RunValidationRequest, user: User = Depends(get_current_user)):
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
async def run_validation_v2(req: RunValidationV2Request, user: User = Depends(get_current_user)):
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
