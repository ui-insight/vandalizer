"""Knowledge Base API routes."""

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user
from app.rate_limit import limiter
from app.models.user import User
from app.models.validation_run import ValidationRun
from app.models.kb_optimization_run import KBOptimizationRun
from app.services import organization_service
from app.schemas.knowledge import (
    AddDocumentsRequest,
    AddFolderRequest,
    AddUrlsRequest,
    AdoptKBRequest,
    ConvertDocumentsRequest,
    CreateKBRequest,
    ImportKBRequest,
    ImportKBResponse,
    KBDetailResponse,
    KBListResponse,
    KBReferenceResponse,
    KBResponse,
    KBSourceDetailResponse,
    KBSourceResponse,
    KBStatusResponse,
    ShareKBRequest,
    UpdateKBRequest,
    UpdateSourceRequest,
)
from app.services import knowledge_service as svc

logger = logging.getLogger(__name__)

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


class _TrustSummary:
    """Most recent AI-trust signal for a KB, unified across run sources."""

    __slots__ = ("score", "baseline", "lift", "at")

    def __init__(
        self,
        *,
        score: float | None,
        baseline: float | None,
        lift: float | None,
        at,
    ) -> None:
        self.score = score
        self.baseline = baseline
        self.lift = lift
        self.at = at


def _kb_response(kb, *, scope: str | None = None, trust: "_TrustSummary | None" = None) -> KBResponse:
    import datetime as _dt
    override = getattr(kb, "rag_config_override", None)
    # Only consider this a real applied override if the value is dict-shaped.
    # Mocks/legacy KBs without the field shouldn't masquerade as optimized.
    has_override = isinstance(override, dict) and bool(override)
    override_at = getattr(kb, "rag_config_override_set_at", None)
    override_at_str = (
        override_at.isoformat() if isinstance(override_at, _dt.datetime) else None
    )

    last_score = trust.score if trust else None
    last_baseline = trust.baseline if trust else None
    last_lift = trust.lift if trust else None
    last_validated_at_str = (
        trust.at.isoformat() if trust and isinstance(trust.at, _dt.datetime) else None
    )

    return KBResponse(
        uuid=kb.uuid,
        title=kb.title,
        description=kb.description or "",
        status=kb.status,
        shared_with_team=kb.shared_with_team,
        team_owned=kb.team_owned,
        verified=kb.verified,
        organization_ids=kb.organization_ids,
        tags=list(getattr(kb, "tags", None) or []),
        total_sources=kb.total_sources,
        sources_ready=kb.sources_ready,
        sources_failed=kb.sources_failed,
        total_chunks=kb.total_chunks,
        created_at=kb.created_at.isoformat() if kb.created_at else None,
        updated_at=kb.updated_at.isoformat() if kb.updated_at else None,
        user_id=kb.user_id,
        scope=scope,
        has_optimized_config=has_override,
        optimized_config_set_at=override_at_str,
        last_validation_score=last_score,
        last_validation_baseline_score=last_baseline,
        last_validation_lift=last_lift,
        last_validated_at=last_validated_at_str,
    )


async def _latest_runs_by_kb(kb_uuids: list[str]) -> dict[str, _TrustSummary]:
    """Return the most recent AI-trust signal per KB uuid, keyed by uuid.

    Sources are merged across two collections:

    * ``ValidationRun`` — written by the manual "Run Validation" button. Stores
      avg_judge_score / avg_baseline_score / avg_lift inside ``result_snapshot``.
    * ``KBOptimizationRun`` — written by KB Autovalidate, which doesn't go through
      persist_validation_run. Stores optimized_score / baseline_no_kb_score
      directly on the document.

    Whichever has the most recent timestamp per KB wins, so an "Optimized" KB
    never shows "Not yet validated" just because the user never clicked the
    manual button.
    """
    if not kb_uuids:
        return {}

    out: dict[str, _TrustSummary] = {}

    # Manual validation runs.
    vruns = await ValidationRun.find({
        "item_kind": "knowledge_base",
        "item_id": {"$in": kb_uuids},
    }).sort("-created_at").to_list()
    for r in vruns:
        if r.item_id in out:
            continue
        rp = (r.result_snapshot or {}).get("retrieval_precision", {}) or {}
        out[r.item_id] = _TrustSummary(
            score=rp.get("avg_judge_score"),
            baseline=rp.get("avg_baseline_score"),
            lift=rp.get("avg_lift"),
            at=r.created_at,
        )

    # KB Autovalidate runs. Only completed runs have populated scores.
    opt_runs = await KBOptimizationRun.find({
        "kb_uuid": {"$in": kb_uuids},
        "status": "completed",
    }).sort("-completed_at").to_list()
    for r in opt_runs:
        ts = r.completed_at or r.started_at
        existing = out.get(r.kb_uuid)
        if existing is not None and existing.at is not None and ts is not None and existing.at >= ts:
            continue
        # The user-facing question is "does the AI do better with the KB?".
        # Use the *applied* KB score (optimized_score when present, else the
        # default-config baseline) against the no-KB baseline so the lift
        # always reflects what the user actually gets at chat time.
        score = r.optimized_score if r.optimized_score is not None else r.baseline_default_score
        baseline = r.baseline_no_kb_score
        lift = (score - baseline) if (score is not None and baseline is not None) else None
        out[r.kb_uuid] = _TrustSummary(score=score, baseline=baseline, lift=lift, at=ts)

    return out


def _source_response(s, *, document_title: str | None = None) -> KBSourceResponse:
    return KBSourceResponse(
        uuid=s.uuid,
        source_type=s.source_type,
        document_uuid=s.document_uuid,
        document_title=document_title,
        url=s.url,
        url_title=s.url_title or "",
        custom_name=s.custom_name,
        source_reference=getattr(s, "source_reference", None),
        status=s.status,
        error_message=s.error_message or "",
        chunk_count=s.chunk_count,
        created_at=s.created_at.isoformat() if s.created_at else None,
    )


async def _resolve_document_titles(sources) -> dict[str, str]:
    """Batch-load SmartDocument titles for the given KB sources.

    Title resolution is a display nicety — a lookup failure (missing collection
    in a test, a deleted document, etc.) must not break the parent endpoint.
    """
    from app.models.document import SmartDocument

    doc_uuids = [
        s.document_uuid for s in sources
        if s.source_type == "document" and s.document_uuid
    ]
    if not doc_uuids:
        return {}
    try:
        docs = await SmartDocument.find({"uuid": {"$in": doc_uuids}}).to_list()
    except Exception:
        return {}
    return {d.uuid: d.title for d in docs if d.title}


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
    if kb.shared_with_team and kb.team_id == team_id and kb.team_owned:
        return "team"
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

    # Pre-load latest ValidationRun for every KB we'll render (including those
    # reached via references), so the AI-trust chip renders in one pass.
    ref_kbs: list = []
    if scope in (None, "mine"):
        for ref in await svc.list_references(user.user_id, team_id=team_id):
            source_kb = await svc.resolve_reference(
                ref.uuid, user, user_org_ancestry=user_org_ancestry,
            )
            if source_kb:
                ref_kbs.append((ref, source_kb))

    latest_runs = await _latest_runs_by_kb(
        [kb.uuid for kb in kbs] + [src.uuid for _, src in ref_kbs]
    )

    items: list[KBResponse] = []
    for kb in kbs:
        kb_scope = scope or _classify_scope(kb, user.user_id, team_id)
        items.append(_kb_response(kb, scope=kb_scope, trust=latest_runs.get(kb.uuid)))

    for ref, source_kb in ref_kbs:
        resp = _kb_response(source_kb, scope="reference", trust=latest_runs.get(source_kb.uuid))
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
    # Title is validated (required, length, normalized) by CreateKBRequest's EntityName field.
    team_id = str(user.current_team) if user.current_team else None
    kb = await svc.create_knowledge_base(
        title=req.title, user_id=user.user_id,
        team_id=team_id, description=req.description,
    )
    return _kb_response(kb)


@router.post("/convert_documents", response_model=KBResponse)
async def convert_documents_to_kb(
    req: ConvertDocumentsRequest, user: User = Depends(get_current_user),
):
    """One-click "Convert to Knowledge Base" for oversized documents.

    Creates a new KB with a sensible default title, then attaches the given
    SmartDocuments via the standard add_documents pipeline. The frontend uses
    this to recover from a context-over-budget error without making the user
    navigate to the KB UI.
    """
    if not req.document_uuids:
        raise HTTPException(status_code=400, detail="No documents provided")

    # Pick a default title from the first doc when the client didn't supply one.
    title = (req.title or "").strip()
    if not title:
        from app.models.document import SmartDocument

        first = await SmartDocument.find_one(SmartDocument.uuid == req.document_uuids[0])
        if first and first.title:
            title = first.title if len(req.document_uuids) == 1 else f"{first.title} (and {len(req.document_uuids) - 1} more)"
        else:
            title = "Reference documents"

    team_id = str(user.current_team) if user.current_team else None
    kb = await svc.create_knowledge_base(
        title=title, user_id=user.user_id, team_id=team_id, description=None,
    )
    kb.status = "building"
    await kb.save()
    try:
        await svc.add_documents(kb, req.document_uuids, user)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
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
    titles = await _resolve_document_titles(sources)
    latest_runs = await _latest_runs_by_kb([kb.uuid])
    return KBDetailResponse(
        **_kb_response(kb, trust=latest_runs.get(kb.uuid)).model_dump(),
        sources=[
            _source_response(s, document_title=titles.get(s.document_uuid or ""))
            for s in sources
        ],
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
        tags=req.tags,
        user_org_ancestry=user_org_ancestry,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"ok": True}


@router.post("/{uuid}/share")
async def share_knowledge_base(
    uuid: str,
    req: ShareKBRequest | None = None,
    user: User = Depends(get_current_user),
):
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    comment = req.comment if req else None
    kb = await svc.share_with_team(
        uuid,
        user,
        user_org_ancestry=user_org_ancestry,
        comment=comment,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"ok": True, "shared_with_team": kb.shared_with_team}


@router.delete("/{uuid}")
async def delete_knowledge_base(
    uuid: str,
    mode: str | None = Query(None, pattern="^unshare_and_delete$"),
    user: User = Depends(get_current_user),
):
    """Delete a knowledge base.

    For KBs that are currently shared with a team, the caller must pass
    ``mode=unshare_and_delete`` to acknowledge that the KB will disappear
    from the Team Library as well. Otherwise the request fails with 409 and
    the client should prompt the user to choose between transferring
    ownership (via POST /{uuid}/transfer-to-team) or force-deleting.
    """
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    try:
        ok = await svc.delete_knowledge_base(
            uuid,
            user,
            user_org_ancestry=user_org_ancestry,
            force_shared=(mode == "unshare_and_delete"),
        )
    except svc.SharedKBDeleteRequiresMode:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "shared_kb_delete_requires_mode",
                "message": "This knowledge base is shared with your team. Choose to move it to the Team Library only, or to unshare and delete everywhere.",
            },
        )
    if not ok:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"ok": True}


@router.post("/{uuid}/transfer-to-team")
async def transfer_to_team(uuid: str, user: User = Depends(get_current_user)):
    """Mark a shared KB as team-owned: removes it from My KBs but keeps Team Library access."""
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    try:
        kb = await svc.transfer_kb_to_team(
            uuid, user, user_org_ancestry=user_org_ancestry,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"ok": True, "team_owned": kb.team_owned}


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
    document_uuids = list(req.document_uuids)
    if req.folder_uuids:
        from app.services import folder_service

        try:
            folder_docs = await folder_service.expand_folders_to_document_uuids(
                req.folder_uuids, user
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        seen = set(document_uuids)
        for doc_uuid in folder_docs:
            if doc_uuid not in seen:
                document_uuids.append(doc_uuid)
                seen.add(doc_uuid)
    if not document_uuids:
        raise HTTPException(status_code=400, detail="No documents provided")
    kb.status = "building"
    await kb.save()
    try:
        added = await svc.add_documents(kb, document_uuids, user)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, "added": added}


@router.post("/{uuid}/add_folder")
async def add_folder(uuid: str, req: AddFolderRequest, user: User = Depends(get_current_user)):
    """Add every document in a folder (and, by default, its subfolders) to a KB."""
    from app.services import document_service

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

    doc_uuids = await document_service.collect_folder_document_uuids(
        folder_uuid=req.folder_uuid,
        user=user,
        include_subfolders=req.include_subfolders,
    )
    if doc_uuids is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    if not doc_uuids:
        return {"ok": True, "added": 0}

    kb.status = "building"
    await kb.save()
    try:
        added = await svc.add_documents(kb, doc_uuids, user)
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
    # Ingestion (fetch + optional crawl + embed) can run for minutes and would
    # blow past the proxy read timeout if awaited inline — dispatch it to a
    # worker and let the frontend poll source status. See tasks.kb.add_urls.
    from app.tasks.kb_validation_tasks import add_urls_task

    kb.status = "building"
    await kb.save()
    add_urls_task.delay(
        kb.uuid, req.urls,
        crawl_enabled=req.crawl_enabled,
        max_crawl_pages=req.max_crawl_pages,
        allowed_domains=req.allowed_domains,
    )
    return {"ok": True, "added": len(req.urls)}


@router.get("/{uuid}/source/{source_uuid}", response_model=KBSourceDetailResponse)
async def get_source_detail(uuid: str, source_uuid: str, user: User = Depends(get_current_user)):
    """Return full detail for a single source (for the inspector modal).

    Access is read-only: any user who can view the KB can inspect its sources.
    For URL sources, returns the cached extracted text. For document sources,
    returns the resolved SmartDocument title — the frontend renders the document
    itself via ``DocumentViewer`` against the document UUID.
    """
    from app.models.knowledge import KnowledgeBaseSource
    from app.models.document import SmartDocument

    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid,
        user,
        user_org_ancestry=user_org_ancestry,
        allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    source = await KnowledgeBaseSource.find_one(
        {"uuid": source_uuid, "knowledge_base_uuid": kb.uuid},
    )
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    document_title: str | None = None
    # The inspector shows the full ingested text. URL sources cache it on
    # ``source.content``; document sources don't, so fall back to the
    # SmartDocument's extracted ``raw_text`` (the same text that was chunked
    # into the KB) — mirroring what export_knowledge_base does.
    content = source.content
    if source.source_type == "document" and source.document_uuid:
        doc = await SmartDocument.find_one(SmartDocument.uuid == source.document_uuid)
        if doc:
            document_title = doc.title
            if not content:
                content = doc.raw_text or None

    # Crawled children (only meaningful when this source is itself a crawl parent)
    children = await KnowledgeBaseSource.find(
        {"knowledge_base_uuid": kb.uuid, "parent_source_uuid": source.uuid},
    ).to_list()
    child_titles = await _resolve_document_titles(children)

    return KBSourceDetailResponse(
        **_source_response(source, document_title=document_title).model_dump(),
        content=content,
        crawl_enabled=bool(source.crawl_enabled),
        max_crawl_pages=int(source.max_crawl_pages or 5),
        parent_source_uuid=source.parent_source_uuid,
        crawled_urls=source.crawled_urls,
        child_sources=[
            _source_response(c, document_title=child_titles.get(c.document_uuid or ""))
            for c in children
        ],
        processed_at=source.processed_at.isoformat() if source.processed_at else None,
    )


@router.patch("/{uuid}/source/{source_uuid}", response_model=KBSourceResponse)
async def update_source(
    uuid: str,
    source_uuid: str,
    req: UpdateSourceRequest,
    user: User = Depends(get_current_user),
):
    """Update a single source within a KB.

    Send ``custom_name`` to set a user-facing label, or ``source_reference`` to
    set the verifiable provenance shown as "Source: …". Only fields explicitly
    present in the request are applied; an empty string clears that field.
    """
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

    # Only touch fields the client actually sent — a PATCH that sets just
    # source_reference must not clear an existing custom_name (and vice versa).
    fields_set = req.model_fields_set
    source = None
    if "custom_name" in fields_set:
        source = await svc.update_source_name(kb, source_uuid, req.custom_name)
    if "source_reference" in fields_set:
        source = await svc.set_source_reference(kb, source_uuid, req.source_reference)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    titles = await _resolve_document_titles([source])
    return _source_response(source, document_title=titles.get(source.document_uuid or ""))


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
async def validate_knowledge_base(
    uuid: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Run validation on a KB.

    Optional JSON body:
      - mode: "judge" (default) or "judge+baseline" (analysis mode with lift).
      - skip_judge: bool — skip the LLM judge entirely (cheap re-run).
      - async: bool — enqueue a Celery task and return {task_id} instead of running inline.
    """
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    mode = (body.get("mode") or "judge").strip()
    if mode not in ("judge", "judge+baseline"):
        mode = "judge"
    skip_judge = bool(body.get("skip_judge", False))
    async_run = bool(body.get("async", False))

    if async_run:
        from app.tasks.kb_validation_tasks import validate_kb_task
        task = validate_kb_task.delay(kb.uuid, user.user_id, mode, skip_judge)
        return {"task_id": task.id, "status": "queued"}

    from app.services import kb_validation_service
    result = await kb_validation_service.run_kb_validation(
        kb.uuid, user.user_id, mode=mode, skip_judge=skip_judge,
    )
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


@router.get("/{uuid}/feedback-impact")
async def get_kb_feedback_impact(uuid: str, user: User = Depends(get_current_user)):
    """Thumbs-up rate on chat answers grounded in this KB, before vs after the
    most recent applied optimization. Drives the Idle hero "tuned KBs are X%
    more helpful" callout — only renders client-side once ``n_after >= 10``.

    Returns ``thumbs_up_rate_*`` as 0..1 ratios (``null`` when the window has
    no feedback) and ``applied_at`` so the UI can phrase the time delta. When
    no optimization has been applied yet (``applied_at`` null), only an
    overall thumbs-up rate is returned so the caller can still show "current
    helpfulness" if it wants to.
    """
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    from app.models.feedback import ChatFeedback
    from app.models.kb_optimization_run import KBOptimizationRun

    applied_run = None
    if kb.rag_config_override_run_uuid:
        applied_run = await KBOptimizationRun.find_one(
            {"uuid": kb.rag_config_override_run_uuid},
        )
    applied_at = applied_run.applied_at if applied_run else None

    async def _count(rating: str, after: bool | None) -> int:
        """Count thumbs of ``rating`` for this KB. ``after``: True for
        ``created_at > applied_at``, False for ``< applied_at``, None for all."""
        q: dict = {"kb_uuid": kb.uuid, "rating": rating}
        if after is True and applied_at is not None:
            q["created_at"] = {"$gt": applied_at}
        elif after is False and applied_at is not None:
            q["created_at"] = {"$lt": applied_at}
        return await ChatFeedback.find(q).count()

    if applied_at is None:
        up = await _count("up", None)
        down = await _count("down", None)
        total = up + down
        return {
            "applied_at": None,
            "thumbs_up_rate_before": None,
            "thumbs_up_rate_after": None,
            "n_before": 0,
            "n_after": 0,
            "thumbs_up_rate_overall": (up / total) if total > 0 else None,
            "n_overall": total,
        }

    up_after = await _count("up", True)
    down_after = await _count("down", True)
    up_before = await _count("up", False)
    down_before = await _count("down", False)
    n_after = up_after + down_after
    n_before = up_before + down_before

    return {
        "applied_at": applied_at.isoformat() if applied_at else None,
        "thumbs_up_rate_before": (up_before / n_before) if n_before > 0 else None,
        "thumbs_up_rate_after": (up_after / n_after) if n_after > 0 else None,
        "n_before": n_before,
        "n_after": n_after,
        "thumbs_up_rate_overall": (
            (up_before + up_after) / (n_before + n_after)
            if (n_before + n_after) > 0 else None
        ),
        "n_overall": n_before + n_after,
    }


# ---------------------------------------------------------------------------
# Test Queries
# ---------------------------------------------------------------------------


def _serialize_test_query(q) -> dict:
    return {
        "uuid": q.uuid,
        "query": q.query,
        "expected_source_labels": q.expected_source_labels,
        "expected_answer_contains": q.expected_answer_contains,
        "expected_answer": q.expected_answer,
        "category": q.category,
        "auto_generated": q.auto_generated,
        "source_chunk_ids": q.source_chunk_ids,
        "last_judged_score": q.last_judged_score,
        "last_judged_at": q.last_judged_at.isoformat() if q.last_judged_at else None,
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "updated_at": q.updated_at.isoformat() if getattr(q, "updated_at", None) else None,
    }


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
    return {"test_queries": [_serialize_test_query(q) for q in queries]}


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
        expected_answer=body.get("expected_answer"),
        category=body.get("category"),
        user_id=user.user_id,
    )
    await tq.insert()
    return _serialize_test_query(tq)


@router.post("/{uuid}/test-queries/generate")
async def generate_test_queries(
    uuid: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Auto-generate KBTestQuery records from KB content using an LLM.

    Body:
      - coverage: "quick" | "standard" | "exhaustive" (default "standard").
      - async: bool — if true, enqueue Celery task and return {task_id}.
    """
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, manage=True, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    coverage = (body.get("coverage") or "standard").strip()
    if coverage not in ("quick", "standard", "exhaustive"):
        coverage = "standard"
    async_run = bool(body.get("async", False))

    if async_run:
        from app.tasks.kb_validation_tasks import generate_test_queries_task
        task = generate_test_queries_task.delay(kb.uuid, user.user_id, coverage)
        return {"task_id": task.id, "status": "queued"}

    from app.services.kb_question_generator import KBQuestionGenerator
    try:
        created = await KBQuestionGenerator().generate(
            kb.uuid, user.user_id, coverage=coverage, persist=True,
        )
    except ValueError as e:
        # Expected, actionable conditions (empty KB, no model configured,
        # unparseable generator output) — surface the message to the user.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Unexpected failure — most often a transient LLM/provider error on the
        # inline generation call. Log with context so it's diagnosable, and
        # return a clean 502 instead of an opaque 500 with no detail.
        logger.exception(
            "Test-query generation failed for KB %s (user=%s, coverage=%s): %s",
            kb.uuid, user.user_id, coverage, e,
        )
        raise HTTPException(
            status_code=502,
            detail="Question generation failed (the language model call did not "
            "complete). Please try again; if it persists, generate in the "
            "background instead.",
        )
    return {
        "created": len(created),
        "test_queries": [_serialize_test_query(q) for q in created],
    }


@router.get("/{uuid}/test-queries/generate/status")
async def test_query_generation_status(
    uuid: str,
    task_id: str,
    user: User = Depends(get_current_user),
):
    """Poll an async test-query generation task (dispatched with async=true).

    Returns ``{status}`` while the task is pending/running, ``{status:
    "completed", created, test_queries}`` once the worker has persisted the
    queries (serialized in generation order), or ``{status: "failed", error}``
    if the task raised. Lets the frontend run generation off the request path —
    the inline LLM call could exceed the proxy's gateway timeout and surface as
    a 502 on larger KBs / slower models.
    """
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, manage=True, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    from celery.result import AsyncResult
    from app.celery_app import celery

    result = AsyncResult(task_id, app=celery)
    if not result.ready():
        return {"status": result.state}
    if result.successful():
        payload = result.result if isinstance(result.result, dict) else {}
        uuids = payload.get("uuids", [])
        from app.models.kb_test_query import KBTestQuery
        rows = await KBTestQuery.find(
            {"uuid": {"$in": uuids}, "knowledge_base_uuid": kb.uuid},
        ).to_list()
        # Preserve the generation order the task reported.
        by_uuid = {q.uuid: q for q in rows}
        ordered = [by_uuid[u] for u in uuids if u in by_uuid]
        return {
            "status": "completed",
            "created": len(ordered),
            "test_queries": [_serialize_test_query(q) for q in ordered],
        }
    err = result.result
    if isinstance(err, BaseException):
        error_text = f"{type(err).__name__}: {err}"
    else:
        error_text = str(err) if err else "Question generation failed"
    return {"status": "failed", "error": error_text}


@router.patch("/{uuid}/test-queries/{query_uuid}")
async def update_test_query(
    uuid: str, query_uuid: str, request: Request, user: User = Depends(get_current_user),
):
    """Edit a test query's user-authored fields.

    Partial update: only keys present in the body are touched, so the caller
    can send just the field(s) that changed. Judge metadata (scores, source
    chunk ids, auto_generated) is server-owned and not editable here.
    """
    import datetime as _datetime

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
    body = await request.json()
    if "query" in body:
        query = (body.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        tq.query = query
    if "expected_answer" in body:
        tq.expected_answer = body.get("expected_answer") or None
    if "expected_answer_contains" in body:
        tq.expected_answer_contains = body.get("expected_answer_contains") or None
    if "expected_source_labels" in body:
        tq.expected_source_labels = body.get("expected_source_labels") or []
    if "category" in body:
        tq.category = body.get("category") or None
    tq.updated_at = _datetime.datetime.now(tz=_datetime.timezone.utc)
    await tq.save()
    return _serialize_test_query(tq)


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
# Autovalidate (optimizer)
# ---------------------------------------------------------------------------


def _iso_utc(dt):
    """ISO-8601 string with an explicit UTC offset.

    Datetimes read back from Mongo are naive (the Motor client isn't tz_aware),
    so a bare ``.isoformat()`` emits no offset and browsers parse it as *local*
    time. For users west of UTC that pushes ``started_at`` into the future, so
    the live elapsed-time readout clamps to 0s for the whole run. Treat naive
    values as UTC so the wire format is unambiguous.
    """
    if dt is None:
        return None
    import datetime as _dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.astimezone(_dt.timezone.utc).isoformat()


def _elapsed_seconds(started_at, completed_at):
    """Server-authoritative elapsed seconds for the live run timer.

    Computed on the server so the readout can't be corrupted by client/server
    clock skew. The elapsed counter previously did ``Date.now() - started_at``
    in the browser, mixing the client wall clock with the server-set start
    timestamp; on a drifted backend (e.g. a Docker VM that fell behind the host
    after sleep) that made the counter jump by the full skew the moment polling
    replaced the optimistic client-side seed. The frontend now ticks forward
    from this base using client-clock *deltas* only.
    """
    if started_at is None:
        return None
    import datetime as _dt
    start = started_at if started_at.tzinfo else started_at.replace(tzinfo=_dt.timezone.utc)
    end = completed_at or _dt.datetime.now(tz=_dt.timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=_dt.timezone.utc)
    return max(0, int((end - start).total_seconds()))


def _serialize_optimization_run(run) -> dict:
    return {
        "uuid": run.uuid,
        "kb_uuid": run.kb_uuid,
        "status": run.status,
        "phase": run.phase,
        "progress_message": run.progress_message,
        "current_trial_index": run.current_trial_index,
        "total_trials_planned": run.total_trials_planned,
        "best_score_so_far": run.best_score_so_far,
        "best_config_so_far": run.best_config_so_far,
        "token_budget": run.token_budget,
        "tokens_used": run.tokens_used,
        "estimated_cost_usd": run.estimated_cost_usd,
        "actual_cost_usd": run.actual_cost_usd,
        "baseline_no_kb_score": run.baseline_no_kb_score,
        "baseline_default_score": run.baseline_default_score,
        "optimized_score": run.optimized_score,
        "judge_variance": run.judge_variance,
        "judge_model": run.judge_model,
        "best_config": run.best_config,
        "trials": run.trials,
        "default_per_query_results": getattr(run, "default_per_query_results", []) or [],
        "no_kb_per_query_results": getattr(run, "no_kb_per_query_results", []) or [],
        "rng_seed": getattr(run, "rng_seed", None),
        "judge_prompt_version": getattr(run, "judge_prompt_version", None),
        "judge_temperature": getattr(run, "judge_temperature", None),
        "test_query_snapshot": getattr(run, "test_query_snapshot", None),
        "judge_variance_meta": getattr(run, "judge_variance_meta", None),
        "lift_ci": getattr(run, "lift_ci", None),
        "cross_judge": getattr(run, "cross_judge", None),
        "optimized_score_train": getattr(run, "optimized_score_train", None),
        "holdout_default_score": getattr(run, "holdout_default_score", None),
        "train_query_uuids": getattr(run, "train_query_uuids", []) or [],
        "holdout_query_uuids": getattr(run, "holdout_query_uuids", []) or [],
        "overfitting_warning": getattr(run, "overfitting_warning", False),
        "stopped_reason": getattr(run, "stopped_reason", None),
        "data_source_suggestions": run.data_source_suggestions,
        "options": run.options,
        "error_message": run.error_message,
        "started_at": _iso_utc(run.started_at),
        "completed_at": _iso_utc(run.completed_at),
        "elapsed_seconds": _elapsed_seconds(run.started_at, run.completed_at),
        "cancel_requested": run.cancel_requested,
        "previous_override": getattr(run, "previous_override", None),
        "applied_at": _iso_utc(getattr(run, "applied_at", None)),
        "reverted_at": _iso_utc(getattr(run, "reverted_at", None)),
        "tied_with_baseline": getattr(run, "tied_with_baseline", False),
        "apply_preview": getattr(run, "apply_preview", None),
    }


@router.post("/{uuid}/optimize")
@limiter.limit("5/minute")
async def start_kb_optimization(uuid: str, request: Request, user: User = Depends(get_current_user)):
    """Kick off a KB Autovalidate optimization run.

    Body:
      - token_budget: int (required)
      - include_indexing_track: bool (v1 ignores this — cheap track only)
      - apply_on_finish: bool
      - autogen_coverage: "quick" | "standard" | "exhaustive" (generation tier)
      - test_set_build_mode: "existing" | "generate" | "combined" — how the
        Test-set wizard step built the eval set (audit/telemetry only).
      - test_query_uuids: list[str] — the exact reviewed test questions to grade
        against. When present this is authoritative (lets "generate only" exclude
        pre-existing saved questions, and "combine" mix both). Falls back to
        "use all saved, else auto-generate" when omitted.
    """
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, manage=True, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    body = await request.json()
    try:
        token_budget = int(body.get("token_budget", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="token_budget must be an integer")
    if token_budget <= 0:
        raise HTTPException(status_code=400, detail="token_budget must be > 0")

    include_indexing_track = bool(body.get("include_indexing_track", False))
    apply_on_finish = bool(body.get("apply_on_finish", False))
    autogen_coverage = (body.get("autogen_coverage") or "standard").strip()
    if autogen_coverage not in ("quick", "standard", "exhaustive"):
        autogen_coverage = "standard"

    # Test-set build mode chosen in the wizard. The selection is made
    # authoritative by ``test_query_uuids`` (the exact reviewed set); the mode
    # string is retained for auditing and re-run display.
    test_set_build_mode = (body.get("test_set_build_mode") or "").strip()
    if test_set_build_mode not in ("existing", "generate", "combined"):
        test_set_build_mode = ""
    raw_uuids = body.get("test_query_uuids")
    test_query_uuids = (
        [str(u) for u in raw_uuids if u] if isinstance(raw_uuids, list) else []
    )

    # Reject if a non-terminal run already exists for this KB.
    from app.models.kb_optimization_run import KBOptimizationRun
    active = await KBOptimizationRun.find_one(
        KBOptimizationRun.kb_uuid == kb.uuid,
        {"status": {"$in": ["queued", "running"]}},
    )
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"Optimization already in progress for this KB (run {active.uuid})",
        )

    # Cross-resource cost governance: per-user concurrency cap + audit trail.
    from app.services import optimization_governance
    await optimization_governance.enforce_and_record_start(
        user,
        resource_type="knowledge_base",
        resource_id=kb.uuid,
        resource_name=getattr(kb, "title", None),
        team_id=getattr(kb, "team_id", None),
        token_budget=token_budget,
    )

    run = KBOptimizationRun(
        kb_uuid=kb.uuid,
        user_id=user.user_id,
        status="queued",
        token_budget=token_budget,
        options={
            "include_indexing_track": include_indexing_track,
            "apply_on_finish": apply_on_finish,
            "autogen_coverage": autogen_coverage,
            "test_set_build_mode": test_set_build_mode,
            "test_query_uuids": test_query_uuids,
        },
    )
    await run.insert()

    from app.tasks.kb_validation_tasks import optimize_kb_task
    optimize_kb_task.delay(
        kb.uuid, user.user_id, run.uuid, token_budget,
        include_indexing_track, apply_on_finish,
    )
    return {"run_uuid": run.uuid, "status": "queued"}


@router.get("/{uuid}/optimize/active")
async def get_active_kb_optimization(uuid: str, user: User = Depends(get_current_user)):
    """Return the active (queued/running) optimization run for this KB, or null."""
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    from app.models.kb_optimization_run import KBOptimizationRun
    run = await KBOptimizationRun.find_one(
        KBOptimizationRun.kb_uuid == kb.uuid,
        {"status": {"$in": ["queued", "running"]}},
    )
    return {"run": _serialize_optimization_run(run) if run else None}


def _summarise_optimization_run(run) -> dict:
    """Compact projection of a run for list views — drops trial detail and per-query
    judge bodies that bloat the response and aren't needed for a history list."""
    # Surface the eval-set size and judge-prompt version so the history list
    # can show "12 queries · kb-judge-abc" inline without having to fetch each
    # run's full payload.
    snapshot = getattr(run, "test_query_snapshot", None) or {}
    return {
        "uuid": run.uuid,
        "kb_uuid": run.kb_uuid,
        "status": run.status,
        "started_at": _iso_utc(run.started_at),
        "completed_at": _iso_utc(run.completed_at),
        "token_budget": run.token_budget,
        "tokens_used": run.tokens_used,
        "baseline_no_kb_score": run.baseline_no_kb_score,
        "baseline_default_score": run.baseline_default_score,
        "optimized_score": run.optimized_score,
        "judge_model": run.judge_model,
        "num_trials": len(run.trials or []),
        "best_config": run.best_config,
        "options": run.options,
        "error_message": run.error_message,
        "eval_set_size": snapshot.get("total"),
        "judge_prompt_version": getattr(run, "judge_prompt_version", None),
        "lift_ci": getattr(run, "lift_ci", None),
    }


@router.get("/{uuid}/optimize")
async def list_kb_optimization_history(
    uuid: str,
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
):
    """List past optimization runs for this KB, newest first.

    Returns compact summaries (without per-trial detail) so a long history
    doesn't blow up response size. Use ``GET /{uuid}/optimize/{run_uuid}``
    to fetch the full payload for a specific run.
    """
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    from app.models.kb_optimization_run import KBOptimizationRun
    runs = await (
        KBOptimizationRun.find(KBOptimizationRun.kb_uuid == kb.uuid)
        .sort("-started_at")
        .skip(skip)
        .limit(limit)
        .to_list()
    )
    return {
        "items": [_summarise_optimization_run(r) for r in runs],
        "skip": skip,
        "limit": limit,
        "count": len(runs),
    }


@router.get("/{uuid}/optimize/{run_uuid}")
async def get_kb_optimization(uuid: str, run_uuid: str, user: User = Depends(get_current_user)):
    """Return the full state of an optimization run (for polling)."""
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    from app.models.kb_optimization_run import KBOptimizationRun
    run = await KBOptimizationRun.find_one(
        KBOptimizationRun.uuid == run_uuid,
        KBOptimizationRun.kb_uuid == kb.uuid,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    return _serialize_optimization_run(run)


@router.post("/{uuid}/optimize/{run_uuid}/cancel")
async def cancel_kb_optimization(uuid: str, run_uuid: str, user: User = Depends(get_current_user)):
    """Request cancellation. The worker checks this flag between trials and
    transitions the run to status='cancelled' on its next loop iteration."""
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, manage=True, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    from app.models.kb_optimization_run import KBOptimizationRun
    run = await KBOptimizationRun.find_one(
        KBOptimizationRun.uuid == run_uuid,
        KBOptimizationRun.kb_uuid == kb.uuid,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    if run.status not in ("queued", "running"):
        return {"ok": True, "status": run.status, "note": "not running"}
    run.cancel_requested = True
    await run.save()
    return {"ok": True, "status": "cancel_requested"}


@router.post("/{uuid}/optimize/{run_uuid}/apply")
async def apply_kb_optimization(uuid: str, run_uuid: str, user: User = Depends(get_current_user)):
    """Apply a completed optimization's best config to the KB's rag_config_override.

    This is for users who want to review trial results before applying. Runs
    started with apply_on_finish=True don't need to call this.
    """
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, manage=True, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    from app.models.kb_optimization_run import KBOptimizationRun
    run = await KBOptimizationRun.find_one(
        KBOptimizationRun.uuid == run_uuid,
        KBOptimizationRun.kb_uuid == kb.uuid,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    if run.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot apply — run status is '{run.status}', expected 'completed'",
        )
    if not run.best_config:
        raise HTTPException(status_code=400, detail="Run has no best_config to apply")

    import datetime as _dt
    now = _dt.datetime.now(tz=_dt.timezone.utc)
    # Snapshot the prior override on the run so Revert can restore it.
    run.previous_override = dict(kb.rag_config_override) if kb.rag_config_override else None
    run.applied_at = now
    run.reverted_at = None
    kb.rag_config_override = dict(run.best_config)
    kb.rag_config_override_set_at = now
    kb.rag_config_override_run_uuid = run.uuid
    await kb.save()
    await run.save()
    # Phase 4: write a corresponding ValidationRun so this apply shows up on
    # the unified quality timeline. Best-effort — never block the apply on a
    # telemetry failure.
    try:
        from app.services import quality_service as _qs
        score_pct = float((run.optimized_score or 0.0) * 100.0)
        await _qs.record_optimizer_apply(
            item_kind="knowledge_base",
            item_id=kb.uuid,
            item_name=getattr(kb, "title", "") or "",
            run_type="kb_validation",
            score=score_pct,
            user_id=user.user_id,
            source_run_uuid=run.uuid,
            applied_config=kb.rag_config_override,
            judge_model=run.judge_model,
            judge_variance=run.judge_variance,
        )
    except Exception:
        logger.warning("Failed to record optimizer-apply ValidationRun for KB %s", kb.uuid)
    return {
        "ok": True,
        "applied_config": kb.rag_config_override,
        "previous_override": run.previous_override,
        "applied_at": now.isoformat(),
    }


@router.post("/{uuid}/optimize/{run_uuid}/revert")
async def revert_kb_optimization(uuid: str, run_uuid: str, user: User = Depends(get_current_user)):
    """Revert a previously-applied optimization. Restores the prior
    ``rag_config_override`` that this run replaced (which may be None — i.e.,
    using the system defaults again).
    """
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, manage=True, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    from app.models.kb_optimization_run import KBOptimizationRun
    run = await KBOptimizationRun.find_one(
        KBOptimizationRun.uuid == run_uuid,
        KBOptimizationRun.kb_uuid == kb.uuid,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    if not run.applied_at:
        raise HTTPException(status_code=400, detail="Run has not been applied — nothing to revert")
    if run.reverted_at:
        raise HTTPException(status_code=400, detail="Run has already been reverted")
    # Refuse to revert if this run is no longer the live one — the live
    # config was set by a later apply, so reverting here would silently
    # undo someone else's change.
    if kb.rag_config_override_run_uuid and kb.rag_config_override_run_uuid != run.uuid:
        raise HTTPException(
            status_code=409,
            detail="A later optimization is currently applied; revert it first.",
        )
    import datetime as _dt
    now = _dt.datetime.now(tz=_dt.timezone.utc)
    kb.rag_config_override = dict(run.previous_override) if run.previous_override else None
    kb.rag_config_override_set_at = now if kb.rag_config_override else None
    kb.rag_config_override_run_uuid = None
    run.reverted_at = now
    await kb.save()
    await run.save()
    return {
        "ok": True,
        "restored_config": kb.rag_config_override,
        "reverted_at": now.isoformat(),
    }


@router.post("/{uuid}/baseline-probe")
async def baseline_probe(uuid: str, request: Request, user: User = Depends(get_current_user)):
    """Cheap no-KB baseline probe — runs ``judge_baselines_only`` on a small
    sample of this KB's test queries so the tuning wizard can show the floor
    *before* the user commits a budget.

    Body:
      - sample_size: int, default 5. Ignored when ``query_uuids`` is provided.
      - query_uuids: list[str], optional. When provided, runs the probe on
        exactly these queries (used by the Preview → Baseline handoff).

    Returns:
      {
        "no_kb_score": float in [0,1] or null if nothing judgeable,
        "num_queries_judged": int,
        "sample_query_ids": list[str],
        "tokens_used": int,
        "duration_ms": int,
      }
    """
    import random
    import time
    from app.models.kb_test_query import KBTestQuery
    from app.services import kb_validation_service
    from app.services.workflow_validator import _resolve_model_name as _resolve_sync

    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    kb = await svc.get_knowledge_base(
        uuid, user, manage=True, user_org_ancestry=user_org_ancestry, allow_admin=True,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        body = {}

    requested_uuids: list[str] = list(body.get("query_uuids") or [])
    try:
        sample_size = int(body.get("sample_size", 5))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="sample_size must be an integer")
    if sample_size < 1 or sample_size > 50:
        raise HTTPException(status_code=422, detail="sample_size must be between 1 and 50")

    # Load candidate test queries — only ones with expected_answer can be judged.
    # Dict-style query (rather than ``KBTestQuery.field == ...`` expression) so
    # the route is testable without Beanie's init_db wiring.
    query = KBTestQuery.find({"knowledge_base_uuid": kb.uuid})
    all_queries = await query.to_list()
    judgeable = [q for q in all_queries if getattr(q, "expected_answer", None)]
    if not judgeable:
        return {
            "no_kb_score": None,
            "num_queries_judged": 0,
            "sample_query_ids": [],
            "tokens_used": 0,
            "duration_ms": 0,
        }

    if requested_uuids:
        wanted = set(requested_uuids)
        sample = [q for q in judgeable if q.uuid in wanted]
    elif len(judgeable) <= sample_size:
        sample = list(judgeable)
    else:
        sample = random.sample(judgeable, sample_size)

    if not sample:
        return {
            "no_kb_score": None,
            "num_queries_judged": 0,
            "sample_query_ids": [],
            "tokens_used": 0,
            "duration_ms": 0,
        }

    model_name = await asyncio.to_thread(_resolve_sync, user.user_id)
    if not model_name:
        raise HTTPException(status_code=400, detail="No LLM model configured for this user")

    started = time.monotonic()
    result = await kb_validation_service.judge_baselines_only(sample, model_name)
    duration_ms = int((time.monotonic() - started) * 1000)

    return {
        "no_kb_score": result.get("avg_baseline_score"),
        "num_queries_judged": result.get("num_baselines_judged", 0),
        "sample_query_ids": [q.uuid for q in sample],
        "tokens_used": result.get("tokens_used", 0),
        "duration_ms": duration_ms,
    }


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
    """Create a lightweight bookmark to a verified/shared KB.

    ``team_id`` selects the destination: omit it (or pass null) to bookmark the
    KB privately, or pass the caller's current team to share it with that team.
    A team_id that isn't the caller's current team is rejected.
    """
    user_org_ancestry = await organization_service.get_user_org_ancestry(user)
    team_id = req.team_id
    if team_id and team_id != (str(user.current_team) if user.current_team else None):
        raise HTTPException(
            status_code=403,
            detail="You can only add a knowledge base to your current team.",
        )
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
