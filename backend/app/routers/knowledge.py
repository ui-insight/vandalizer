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
    ShareKBRequest,
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
    import datetime as _dt
    override = getattr(kb, "rag_config_override", None)
    # Only consider this a real applied override if the value is dict-shaped.
    # Mocks/legacy KBs without the field shouldn't masquerade as optimized.
    has_override = isinstance(override, dict) and bool(override)
    override_at = getattr(kb, "rag_config_override_set_at", None)
    override_at_str = (
        override_at.isoformat() if isinstance(override_at, _dt.datetime) else None
    )
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
        has_optimized_config=has_override,
        optimized_config_set_at=override_at_str,
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
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "created": len(created),
        "test_queries": [_serialize_test_query(q) for q in created],
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
# Autovalidate (optimizer)
# ---------------------------------------------------------------------------


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
        "data_source_suggestions": run.data_source_suggestions,
        "options": run.options,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "cancel_requested": run.cancel_requested,
    }


@router.post("/{uuid}/optimize")
async def start_kb_optimization(uuid: str, request: Request, user: User = Depends(get_current_user)):
    """Kick off a KB Autovalidate optimization run.

    Body:
      - token_budget: int (required)
      - include_indexing_track: bool (v1 ignores this — cheap track only)
      - apply_on_finish: bool
      - autogen_coverage: "quick" | "standard" | "exhaustive" (used only when KB has no test queries)
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

    run = KBOptimizationRun(
        kb_uuid=kb.uuid,
        user_id=user.user_id,
        status="queued",
        token_budget=token_budget,
        options={
            "include_indexing_track": include_indexing_track,
            "apply_on_finish": apply_on_finish,
            "autogen_coverage": autogen_coverage,
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
    return {
        "uuid": run.uuid,
        "kb_uuid": run.kb_uuid,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
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
    kb.rag_config_override = dict(run.best_config)
    kb.rag_config_override_set_at = _dt.datetime.now(tz=_dt.timezone.utc)
    kb.rag_config_override_run_uuid = run.uuid
    await kb.save()
    return {"ok": True, "applied_config": kb.rag_config_override}


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
