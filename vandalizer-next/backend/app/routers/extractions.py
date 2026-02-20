"""Extraction API routes  - SearchSet CRUD and extraction execution."""

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.extractions import (
    BuildFromDocumentRequest,
    CreateSearchSetRequest,
    ExtractionStatusResponse,
    RunExtractionSyncRequest,
    SearchSetItemRequest,
    SearchSetItemResponse,
    SearchSetResponse,
    UpdateSearchSetRequest,
    UpdateSearchSetItemRequest,
)
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
    results = await svc.run_extraction_sync(
        search_set_uuid=req.search_set_uuid,
        document_uuids=req.document_uuids,
        user_id=user.user_id,
        model=req.model,
        extraction_config_override=req.extraction_config_override,
    )
    return {"results": results}
