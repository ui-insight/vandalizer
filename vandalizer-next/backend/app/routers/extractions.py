"""Extraction API routes  - SearchSet CRUD and extraction execution."""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.dependencies import get_api_key_user, get_current_user
from app.models.activity import ActivityStatus, ActivityType
from app.models.user import User
from app.services import activity_service
from app.schemas.extractions import (
    BuildFromDocumentRequest,
    CreateSearchSetRequest,
    CreateTestCaseRequest,
    ExtractionStatusResponse,
    ReorderItemsRequest,
    RunExtractionSyncRequest,
    RunValidationRequest,
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
# SearchSet CRUD
# ---------------------------------------------------------------------------

@router.post("/search-sets", response_model=SearchSetResponse)
async def create_search_set(req: CreateSearchSetRequest, user: User = Depends(get_current_user)):
    ss = await svc.create_search_set(req.title, req.space, req.set_type, user.user_id, extraction_config=req.extraction_config)
    count = await ss.item_count()
    return SearchSetResponse(
        id=str(ss.id), title=ss.title, uuid=ss.uuid, space=ss.space,
        status=ss.status, set_type=ss.set_type, user_id=ss.user_id,
        is_global=ss.is_global, verified=ss.verified, item_count=count,
        extraction_config=ss.extraction_config,
    )


@router.get("/search-sets", response_model=list[SearchSetResponse])
async def list_search_sets(space: str | None = None, user: User = Depends(get_current_user)):
    sets = await svc.list_search_sets(space=space)
    results = []
    for ss in sets:
        count = await ss.item_count()
        results.append(SearchSetResponse(
            id=str(ss.id), title=ss.title, uuid=ss.uuid, space=ss.space,
            status=ss.status, set_type=ss.set_type, user_id=ss.user_id,
            is_global=ss.is_global, verified=ss.verified, item_count=count,
            extraction_config=ss.extraction_config,
        ))
    return results


@router.get("/search-sets/{uuid}", response_model=SearchSetResponse)
async def get_search_set(uuid: str, user: User = Depends(get_current_user)):
    ss = await svc.get_search_set(uuid)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    count = await ss.item_count()
    return SearchSetResponse(
        id=str(ss.id), title=ss.title, uuid=ss.uuid, space=ss.space,
        status=ss.status, set_type=ss.set_type, user_id=ss.user_id,
        is_global=ss.is_global, verified=ss.verified, item_count=count,
        extraction_config=ss.extraction_config,
    )


@router.patch("/search-sets/{uuid}", response_model=SearchSetResponse)
async def update_search_set(uuid: str, req: UpdateSearchSetRequest, user: User = Depends(get_current_user)):
    ss = await svc.update_search_set(uuid, title=req.title, extraction_config=req.extraction_config)
    if not ss:
        raise HTTPException(status_code=404, detail="SearchSet not found")
    count = await ss.item_count()
    return SearchSetResponse(
        id=str(ss.id), title=ss.title, uuid=ss.uuid, space=ss.space,
        status=ss.status, set_type=ss.set_type, user_id=ss.user_id,
        is_global=ss.is_global, verified=ss.verified, item_count=count,
        extraction_config=ss.extraction_config,
    )


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
    count = await ss.item_count()
    return SearchSetResponse(
        id=str(ss.id), title=ss.title, uuid=ss.uuid, space=ss.space,
        status=ss.status, set_type=ss.set_type, user_id=ss.user_id,
        is_global=ss.is_global, verified=ss.verified, item_count=count,
        extraction_config=ss.extraction_config,
    )


# ---------------------------------------------------------------------------
# SearchSetItem CRUD
# ---------------------------------------------------------------------------

@router.post("/search-sets/{uuid}/items", response_model=SearchSetItemResponse)
async def add_item(uuid: str, req: SearchSetItemRequest, user: User = Depends(get_current_user)):
    item = await svc.add_item(uuid, req.searchphrase, req.searchtype, req.title, user.user_id)
    return SearchSetItemResponse(
        id=str(item.id), searchphrase=item.searchphrase, searchset=item.searchset,
        searchtype=item.searchtype, title=item.title,
    )


@router.get("/search-sets/{uuid}/items", response_model=list[SearchSetItemResponse])
async def list_items(uuid: str, user: User = Depends(get_current_user)):
    items = await svc.list_items(uuid)
    return [
        SearchSetItemResponse(
            id=str(item.id), searchphrase=item.searchphrase, searchset=item.searchset,
            searchtype=item.searchtype, title=item.title,
        )
        for item in items
    ]


@router.patch("/items/{item_id}", response_model=SearchSetItemResponse)
async def update_item(item_id: str, req: UpdateSearchSetItemRequest, user: User = Depends(get_current_user)):
    item = await svc.update_item(item_id, searchphrase=req.searchphrase, title=req.title)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return SearchSetItemResponse(
        id=str(item.id), searchphrase=item.searchphrase, searchset=item.searchset,
        searchtype=item.searchtype, title=item.title,
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
