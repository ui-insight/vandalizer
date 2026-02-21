"""Knowledge Base API routes."""

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.knowledge import (
    AddDocumentsRequest,
    AddUrlsRequest,
    CreateKBRequest,
    KBDetailResponse,
    KBResponse,
    KBSourceResponse,
    KBStatusResponse,
    UpdateKBRequest,
)
from app.services import knowledge_service as svc

router = APIRouter()


def _kb_response(kb) -> KBResponse:
    return KBResponse(
        uuid=kb.uuid,
        title=kb.title,
        description=kb.description or "",
        status=kb.status,
        total_sources=kb.total_sources,
        sources_ready=kb.sources_ready,
        sources_failed=kb.sources_failed,
        total_chunks=kb.total_chunks,
        created_at=kb.created_at.isoformat() if kb.created_at else None,
        updated_at=kb.updated_at.isoformat() if kb.updated_at else None,
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
async def list_knowledge_bases(user: User = Depends(get_current_user)):
    kbs = await svc.list_knowledge_bases(user.user_id)
    return [_kb_response(kb) for kb in kbs]


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


@router.get("/{uuid}", response_model=KBDetailResponse)
async def get_knowledge_base(uuid: str, user: User = Depends(get_current_user)):
    kb = await svc.get_knowledge_base(uuid, user.user_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    sources = await svc.get_kb_sources(kb.uuid)
    return KBDetailResponse(
        **_kb_response(kb).model_dump(),
        sources=[_source_response(s) for s in sources],
    )


@router.post("/{uuid}/update")
async def update_knowledge_base(uuid: str, req: UpdateKBRequest, user: User = Depends(get_current_user)):
    kb = await svc.update_knowledge_base(uuid, user.user_id, title=req.title, description=req.description)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"ok": True}


@router.delete("/{uuid}")
async def delete_knowledge_base(uuid: str, user: User = Depends(get_current_user)):
    ok = await svc.delete_knowledge_base(uuid, user.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"ok": True}


@router.post("/{uuid}/add_documents")
async def add_documents(uuid: str, req: AddDocumentsRequest, user: User = Depends(get_current_user)):
    kb = await svc.get_knowledge_base(uuid, user.user_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if not req.document_uuids:
        raise HTTPException(status_code=400, detail="No documents provided")
    kb.status = "building"
    await kb.save()
    added = await svc.add_documents(kb, req.document_uuids)
    return {"ok": True, "added": added}


@router.post("/{uuid}/add_urls")
async def add_urls(uuid: str, req: AddUrlsRequest, user: User = Depends(get_current_user)):
    kb = await svc.get_knowledge_base(uuid, user.user_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if not req.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")
    kb.status = "building"
    await kb.save()
    added = await svc.add_urls(kb, req.urls)
    return {"ok": True, "added": added}


@router.delete("/{uuid}/source/{source_uuid}")
async def remove_source(uuid: str, source_uuid: str, user: User = Depends(get_current_user)):
    kb = await svc.get_knowledge_base(uuid, user.user_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    ok = await svc.remove_source(kb, source_uuid)
    if not ok:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"ok": True}


@router.get("/{uuid}/status", response_model=KBStatusResponse)
async def get_status(uuid: str, user: User = Depends(get_current_user)):
    kb = await svc.get_knowledge_base(uuid, user.user_id)
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
