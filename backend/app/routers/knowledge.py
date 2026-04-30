"""Knowledge Base API routes."""

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user
from app.rate_limit import limiter
from app.models.user import User
from app.services import organization_service
from app.schemas.knowledge import (
    AddDocumentsRequest,
    AddUrlsRequest,
    AdoptKBRequest,
    CreateKBRequest,
    ImportKBRequest,
    ImportKBResponse,
    KBDetailResponse,
    KBListResponse,
    KBReferenceResponse,
    KBResponse,
    KBSourceResponse,
    KBStatusResponse,
    UpdateKBRequest,
)
from app.services import knowledge_service as svc

router = APIRouter()


async def _get_kb_or_404(uuid: str, user: User, *, manage: bool = False):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid,
        user,
        manage=manage,
        user_org_ancestry=user_org_ancestry,
        allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


async def _get_kb_suggestion_or_404(kb_uuid: str, suggestion_uuid: str):
    from app.models.kb_suggestion import KBSuggestion

    suggestion = await KBSuggestion.find_one(
        {"uuid": suggestion_uuid, "knowledge_base_uuid": kb_uuid},
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return suggestion


def _kb_response(kb, *, scope: str | None = None) -> KBResponse:
    return KBResponse(
        uuid=kb.uuid,
        title=kb.title,
        description=kb.description or "",
        status=kb.status,
        shared_with_team=kb.shared_with_team,
        verified=kb.verified,
        organization_ids=kb.organization_ids,
        total_sources=kb.total_sources,
        sources_ready=kb.sources_ready,
        sources_failed=kb.sources_failed,
        total_chunks=kb.total_chunks,
        created_at=kb.created_at.isoformat() if kb.created_at else None,
        updated_at=kb.updated_at.isoformat() if kb.updated_at else None,
        user_id=kb.user_id,
        scope=scope,
    )


def _source_response(s) -> KBSourceResponse:
    return KBSourceResponse(
        uuid=s.uuid,
        source_type=s.source_type,
        document_uuid=s.document_uuid,
        url=s.url,
        url_title=s.url_title or "",
        status=s.status,
        error_message=s.error_message or "",
        chunk_count=s.chunk_count,
        created_at=s.created_at.isoformat() if s.created_at else None,
    )


@router.get("/list", response_model=list[KBResponse])
async def list_knowledge_bases_legacy(user: User = Depends(get_current_user)):
    """Legacy flat list — returns all visible KBs without scope/pagination."""
    team_id = str(user.current_team) if user.current_team else None
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kbs = await svc.list_knowledge_bases_flat(
        user.user_id, team_id=team_id, user_org_ancestry=user_org_ancestry,
    )
    return [_kb_response(kb) for kb in kbs]


def _classify_scope(kb, user_id: str, team_id: str | None) -> str:
    """Determine the display scope for a KB relative to the requesting user."""
    if kb.user_id == user_id:
        return "mine"
    if kb.verified:
        return "verified"
    if kb.shared_with_team and kb.team_id == team_id:
        return "team"
    return "mine"


@router.get("/list/v2", response_model=KBListResponse)
async def list_knowledge_bases_v2(
    scope: str | None = Query(None, pattern="^(mine|team|verified)$"),
    search: str | None = Query(None, max_length=200),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    """Scoped knowledge base listing with search and pagination."""
    team_id = str(user.current_team) if user.current_team else None
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)

    kbs, total = await svc.list_knowledge_bases(
        user.user_id,
        team_id=team_id,
        user_org_ancestry=user_org_ancestry,
        scope=scope,
        search=search,
        skip=skip,
        limit=limit,
    )

    items: list[KBResponse] = []
    for kb in kbs:
        kb_scope = scope or _classify_scope(kb, user.user_id, team_id)
        items.append(_kb_response(kb, scope=kb_scope))

    # If scope is "mine", also include bookmarked references
    if scope in (None, "mine"):
        refs = await svc.list_references(user.user_id, team_id=team_id)
        for ref in refs:
            source_kb = await svc.resolve_reference(
                ref.uuid, user, user_org_ancestry=user_org_ancestry,
            )
            if not source_kb:
                continue  # stale reference — source KB deleted or access revoked
            resp = _kb_response(source_kb, scope="reference")
            resp.is_reference = True
            resp.source_kb_uuid = ref.source_kb_uuid
            resp.reference_uuid = ref.uuid
            items.append(resp)

    return KBListResponse(items=items, total=total + len([i for i in items if i.is_reference]))


@router.delete("/reference/{ref_uuid}")
async def remove_reference(ref_uuid: str, user: User = Depends(get_current_user)):
    """Remove a KB bookmark."""
    ok = await svc.remove_reference(ref_uuid, user)
    if not ok:
        raise HTTPException(status_code=404, detail="Reference not found")
    return {"ok": True}


@router.post("/create", response_model=KBResponse)
async def create_knowledge_base(req: CreateKBRequest, user: User = Depends(get_current_user)):
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    team_id = str(user.current_team) if user.current_team else None
    kb = await svc.create_knowledge_base(
        title=req.title, user_id=user.user_id,
        team_id=team_id, description=req.description,
    )
    return _kb_response(kb)


@router.post("/import", response_model=ImportKBResponse)
async def import_knowledge_base(req: ImportKBRequest, user: User = Depends(get_current_user)):
    """Import a knowledge base from a previously exported payload.

    Creates a new KB owned by the importing user and re-ingests all sources
    (regenerating embeddings). The importer's team becomes the KB's team.
    """
    try:
        kb = await svc.import_knowledge_base(
            req.payload.model_dump(),
            user,
            title_override=req.title,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ImportKBResponse(
        uuid=kb.uuid,
        title=kb.title,
        imported_sources=kb.total_sources,
    )


@router.get("/{uuid}/export")
async def export_knowledge_base(uuid: str, user: User = Depends(get_current_user)):
    """Download a JSON export of a knowledge base (metadata + source content).

    Embeddings are not included — they are regenerated when the file is imported.
    """
    kb = await _get_kb_or_404(uuid, user)
    payload = await svc.export_knowledge_base(kb)
    safe_title = re.sub(r"[^A-Za-z0-9_.-]+", "_", kb.title or "knowledge_base").strip("_")
    filename = f"{safe_title or 'knowledge_base'}.kb.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{uuid}", response_model=KBDetailResponse)
async def get_knowledge_base(uuid: str, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid,
        user,
        user_org_ancestry=user_org_ancestry,
        allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    sources = await svc.get_kb_sources(kb.uuid)
    return KBDetailResponse(
        **_kb_response(kb).model_dump(),
        sources=[_source_response(s) for s in sources],
    )


@router.post("/{uuid}/update")
async def update_knowledge_base(uuid: str, req: UpdateKBRequest, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.update_knowledge_base(
        uuid,
        user,
        title=req.title,
        description=req.description,
        shared_with_team=req.shared_with_team,
        organization_ids=req.organization_ids,
        user_org_ancestry=user_org_ancestry,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"ok": True}


@router.post("/{uuid}/share")
async def share_knowledge_base(uuid: str, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.share_with_team(uuid, user, user_org_ancestry=user_org_ancestry)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"ok": True, "shared_with_team": kb.shared_with_team}


@router.delete("/{uuid}")
async def delete_knowledge_base(uuid: str, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    ok = await svc.delete_knowledge_base(uuid, user, user_org_ancestry=user_org_ancestry)
    if not ok:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"ok": True}


@router.post("/{uuid}/add_documents")
async def add_documents(uuid: str, req: AddDocumentsRequest, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid,
        user,
        manage=True,
        user_org_ancestry=user_org_ancestry,
        allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if not req.document_uuids:
        raise HTTPException(status_code=400, detail="No documents provided")
    kb.status = "building"
    await kb.save()
    try:
        added = await svc.add_documents(kb, req.document_uuids, user)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, "added": added}


@router.post("/{uuid}/add_urls")
@limiter.limit("10/minute")
async def add_urls(request: Request, uuid: str, req: AddUrlsRequest, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid,
        user,
        manage=True,
        user_org_ancestry=user_org_ancestry,
        allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if not req.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")
    kb.status = "building"
    await kb.save()
    added = await svc.add_urls(
        kb, req.urls,
        crawl_enabled=req.crawl_enabled,
        max_crawl_pages=req.max_crawl_pages,
        allowed_domains=req.allowed_domains,
    )
    return {"ok": True, "added": added}


@router.delete("/{uuid}/source/{source_uuid}")
async def remove_source(uuid: str, source_uuid: str, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid,
        user,
        manage=True,
        user_org_ancestry=user_org_ancestry,
        allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    ok = await svc.remove_source(kb, source_uuid)
    if not ok:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@router.post("/{uuid}/validate")
async def validate_knowledge_base(uuid: str, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    from app.services import kb_validation_service
    result = await kb_validation_service.run_kb_validation(kb.uuid, user.user_id)
    return result


@router.get("/{uuid}/source-health")
async def get_source_health(uuid: str, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    from app.services import kb_validation_service
    return await kb_validation_service.check_source_health(kb.uuid)


@router.get("/{uuid}/quality")
async def get_kb_quality(uuid: str, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    from app.services import quality_service
    history = await quality_service.get_quality_history("knowledge_base", kb.uuid)
    contract = await quality_service.get_quality_contract_status("knowledge_base", kb.uuid)
    return {"history": history, "contract": contract}


# ---------------------------------------------------------------------------
# Test Queries
# ---------------------------------------------------------------------------


@router.get("/{uuid}/test-queries")
async def list_test_queries(uuid: str, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    from app.models.kb_test_query import KBTestQuery
    queries = await KBTestQuery.find(
        KBTestQuery.knowledge_base_uuid == kb.uuid,
    ).sort("-created_at").to_list()
    return {"test_queries": [
        {
            "uuid": q.uuid,
            "query": q.query,
            "expected_source_labels": q.expected_source_labels,
            "expected_answer_contains": q.expected_answer_contains,
            "created_at": q.created_at.isoformat() if q.created_at else None,
        }
        for q in queries
    ]}


@router.post("/{uuid}/test-queries")
async def create_test_query(uuid: str, request: Request, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, manage=True, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    body = await request.json()
    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
    from app.models.kb_test_query import KBTestQuery
    tq = KBTestQuery(
        knowledge_base_uuid=kb.uuid,
        query=query,
        expected_source_labels=body.get("expected_source_labels", []),
        expected_answer_contains=body.get("expected_answer_contains"),
        user_id=user.user_id,
    )
    await tq.insert()
    return {
        "uuid": tq.uuid,
        "query": tq.query,
        "expected_source_labels": tq.expected_source_labels,
        "expected_answer_contains": tq.expected_answer_contains,
        "created_at": tq.created_at.isoformat() if tq.created_at else None,
    }


@router.delete("/{uuid}/test-queries/{query_uuid}")
async def delete_test_query(uuid: str, query_uuid: str, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, manage=True, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    from app.models.kb_test_query import KBTestQuery
    tq = await KBTestQuery.find_one(
        KBTestQuery.uuid == query_uuid,
        KBTestQuery.knowledge_base_uuid == kb.uuid,
    )
    if not tq:
        raise HTTPException(status_code=404, detail="Test query not found")
    await tq.delete()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------


@router.post("/{uuid}/clone")
async def clone_knowledge_base(uuid: str, request: Request, user: User = Depends(get_current_user)):
    kb = await _get_kb_or_404(uuid, user)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    new_title = body.get("title")
    try:
        clone = await svc.clone_knowledge_base(kb, user, new_title=new_title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _kb_response(clone)


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------


@router.post("/{uuid}/suggestions")
async def create_suggestion(uuid: str, request: Request, user: User = Depends(get_current_user)):
    kb = await _get_kb_or_404(uuid, user)
    body = await request.json()
    suggestion_type = body.get("suggestion_type", "general")
    try:
        suggestion = await svc.create_suggestion(
            kb_uuid=kb.uuid,
            user=user,
            suggestion_type=suggestion_type,
            url=body.get("url"),
            document_uuid=body.get("document_uuid"),
            note=body.get("note"),
        )
    except ValueError as e:
        status_code = 404 if str(e) == "Knowledge base not found" else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    return {
        "uuid": suggestion.uuid,
        "suggestion_type": suggestion.suggestion_type,
        "status": suggestion.status,
        "note": suggestion.note,
        "url": suggestion.url,
        "document_uuid": suggestion.document_uuid,
        "created_at": suggestion.created_at.isoformat() if suggestion.created_at else None,
    }


@router.get("/{uuid}/suggestions")
async def list_suggestions(uuid: str, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    suggestions = await svc.list_suggestions(kb.uuid)
    return {"suggestions": [
        {
            "uuid": s.uuid,
            "suggestion_type": s.suggestion_type,
            "url": s.url,
            "document_uuid": s.document_uuid,
            "note": s.note,
            "status": s.status,
            "suggested_by_name": s.suggested_by_name,
            "suggested_by_user_id": s.suggested_by_user_id,
            "reviewed_by_user_id": s.reviewed_by_user_id,
            "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in suggestions
    ]}


@router.patch("/{uuid}/suggestions/{suggestion_uuid}")
async def review_suggestion(uuid: str, suggestion_uuid: str, request: Request, user: User = Depends(get_current_user)):
    kb = await _get_kb_or_404(uuid, user, manage=True)
    suggestion = await _get_kb_suggestion_or_404(kb.uuid, suggestion_uuid)
    body = await request.json()
    accept = body.get("accept", False)
    try:
        suggestion = await svc.review_suggestion(kb, suggestion, user, accept)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "uuid": suggestion.uuid,
        "status": suggestion.status,
        "reviewed_at": suggestion.reviewed_at.isoformat() if suggestion.reviewed_at else None,
    }


# ---------------------------------------------------------------------------
# References (bookmarks)
# ---------------------------------------------------------------------------


@router.post("/{uuid}/adopt", response_model=KBReferenceResponse)
async def adopt_knowledge_base(uuid: str, req: AdoptKBRequest, user: User = Depends(get_current_user)):
    """Create a lightweight bookmark to a verified/shared KB."""
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    team_id = req.team_id or (str(user.current_team) if user.current_team else None)
    try:
        ref = await svc.adopt_knowledge_base(
            uuid, user,
            note=req.note,
            team_id=team_id,
            user_org_ancestry=user_org_ancestry,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return KBReferenceResponse(
        uuid=ref.uuid,
        source_kb_uuid=ref.source_kb_uuid,
        user_id=ref.user_id,
        team_id=ref.team_id,
        note=ref.note,
        pinned=ref.pinned,
        created_at=ref.created_at.isoformat() if ref.created_at else None,
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("/{uuid}/status", response_model=KBStatusResponse)
async def get_status(uuid: str, user: User = Depends(get_current_user)):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid,
        user,
        user_org_ancestry=user_org_ancestry,
        allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    sources = await svc.get_kb_sources(kb.uuid)
    return KBStatusResponse(
        uuid=kb.uuid,
        status=kb.status,
        total_sources=kb.total_sources,
        sources_ready=kb.sources_ready,
        sources_failed=kb.sources_failed,
        total_chunks=kb.total_chunks,
        sources=[
            {"uuid": s.uuid, "status": s.status, "error_message": s.error_message or "", "chunk_count": s.chunk_count}
            for s in sources
        ],
    )
