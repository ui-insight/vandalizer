"""Knowledge Base CRUD and source management routes."""

import datetime
from uuid import uuid4

from devtools import debug
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.models import KnowledgeBase, KnowledgeBaseSource, SmartDocument
from app.utilities.document_manager import DocumentManager
from app.utilities.knowledge_base_tasks import kb_ingest_document, kb_ingest_url

knowledge = Blueprint("knowledge", __name__, url_prefix="/knowledge")


def _get_user_id():
    return current_user.get_id()


def _get_team_id():
    team = current_user.ensure_current_team()
    return team.uuid if team else None


@knowledge.route("/list", methods=["GET"])
@login_required
def list_knowledge_bases():
    """List knowledge bases for the current user."""
    user_id = _get_user_id()
    team_id = _get_team_id()

    kbs = KnowledgeBase.objects(user_id=user_id).order_by("-created_at")
    return jsonify([
        {
            "uuid": kb.uuid,
            "title": kb.title,
            "description": kb.description or "",
            "status": kb.status,
            "total_sources": kb.total_sources,
            "sources_ready": kb.sources_ready,
            "sources_failed": kb.sources_failed,
            "total_chunks": kb.total_chunks,
            "created_at": kb.created_at.isoformat() if kb.created_at else None,
            "updated_at": kb.updated_at.isoformat() if kb.updated_at else None,
        }
        for kb in kbs
    ])


@knowledge.route("/create", methods=["POST"])
@login_required
def create_knowledge_base():
    """Create a new knowledge base."""
    data = request.get_json()
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400

    user_id = _get_user_id()
    team_id = _get_team_id()

    kb = KnowledgeBase(
        title=title[:300],
        description=(data.get("description") or "")[:5000],
        user_id=user_id,
        team_id=team_id,
    )
    kb.save()

    return jsonify({
        "uuid": kb.uuid,
        "title": kb.title,
        "description": kb.description or "",
        "status": kb.status,
        "total_sources": 0,
        "sources_ready": 0,
        "sources_failed": 0,
        "total_chunks": 0,
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
        "updated_at": kb.updated_at.isoformat() if kb.updated_at else None,
    })


@knowledge.route("/<uuid>", methods=["GET"])
@login_required
def get_knowledge_base(uuid):
    """Get KB details including sources."""
    kb = KnowledgeBase.objects(uuid=uuid, user_id=_get_user_id()).first()
    if not kb:
        return jsonify({"error": "Knowledge base not found"}), 404

    sources = KnowledgeBaseSource.objects(knowledge_base=kb).order_by("-created_at")
    return jsonify({
        "uuid": kb.uuid,
        "title": kb.title,
        "description": kb.description or "",
        "status": kb.status,
        "total_sources": kb.total_sources,
        "sources_ready": kb.sources_ready,
        "sources_failed": kb.sources_failed,
        "total_chunks": kb.total_chunks,
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
        "updated_at": kb.updated_at.isoformat() if kb.updated_at else None,
        "sources": [
            {
                "uuid": s.uuid,
                "source_type": s.source_type,
                "document_uuid": s.document_uuid,
                "url": s.url,
                "url_title": s.url_title or "",
                "status": s.status,
                "error_message": s.error_message or "",
                "chunk_count": s.chunk_count,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sources
        ],
    })


@knowledge.route("/<uuid>/update", methods=["POST"])
@login_required
def update_knowledge_base(uuid):
    """Update KB title/description."""
    kb = KnowledgeBase.objects(uuid=uuid, user_id=_get_user_id()).first()
    if not kb:
        return jsonify({"error": "Knowledge base not found"}), 404

    data = request.get_json()
    if "title" in data:
        title = (data["title"] or "").strip()
        if title:
            kb.title = title[:300]
    if "description" in data:
        kb.description = (data["description"] or "")[:5000]

    kb.save()
    return jsonify({"ok": True})


@knowledge.route("/<uuid>", methods=["DELETE"])
@login_required
def delete_knowledge_base(uuid):
    """Delete KB and its ChromaDB collection."""
    kb = KnowledgeBase.objects(uuid=uuid, user_id=_get_user_id()).first()
    if not kb:
        return jsonify({"error": "Knowledge base not found"}), 404

    # Delete ChromaDB collection
    try:
        dm = DocumentManager()
        dm.delete_kb_collection(kb.uuid)
    except Exception as e:
        debug(f"Error deleting KB collection: {e}")

    # Delete all sources
    KnowledgeBaseSource.objects(knowledge_base=kb).delete()
    kb.delete()

    return jsonify({"ok": True})


@knowledge.route("/<uuid>/add_documents", methods=["POST"])
@login_required
def add_documents(uuid):
    """Add SmartDocuments to a KB and dispatch ingestion tasks."""
    kb = KnowledgeBase.objects(uuid=uuid, user_id=_get_user_id()).first()
    if not kb:
        return jsonify({"error": "Knowledge base not found"}), 404

    data = request.get_json()
    doc_uuids = data.get("document_uuids", [])
    if not doc_uuids:
        return jsonify({"error": "No documents provided"}), 400

    added = []
    for doc_uuid in doc_uuids:
        doc = SmartDocument.objects(uuid=doc_uuid).first()
        if not doc:
            continue

        # Skip if already added
        existing = KnowledgeBaseSource.objects(
            knowledge_base=kb, document_uuid=doc_uuid
        ).first()
        if existing:
            continue

        source = KnowledgeBaseSource(
            knowledge_base=kb,
            source_type="document",
            document=doc,
            document_uuid=doc.uuid,
        )
        source.save()
        kb.sources.append(source)
        added.append(source.uuid)

        # Dispatch Celery task
        kb_ingest_document.delay(source.uuid)

    if added:
        kb.status = "building"
        kb.save()
        kb.recalculate_stats()

    return jsonify({"ok": True, "added": len(added)})


@knowledge.route("/<uuid>/add_urls", methods=["POST"])
@login_required
def add_urls(uuid):
    """Add URLs to a KB and dispatch ingestion tasks."""
    kb = KnowledgeBase.objects(uuid=uuid, user_id=_get_user_id()).first()
    if not kb:
        return jsonify({"error": "Knowledge base not found"}), 404

    data = request.get_json()
    urls = data.get("urls", [])
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    added = []
    for url in urls:
        url = (url or "").strip()
        if not url:
            continue

        # Skip duplicates
        existing = KnowledgeBaseSource.objects(
            knowledge_base=kb, url=url
        ).first()
        if existing:
            continue

        source = KnowledgeBaseSource(
            knowledge_base=kb,
            source_type="url",
            url=url[:2000],
        )
        source.save()
        kb.sources.append(source)
        added.append(source.uuid)

        # Dispatch Celery task
        kb_ingest_url.delay(source.uuid)

    if added:
        kb.status = "building"
        kb.save()
        kb.recalculate_stats()

    return jsonify({"ok": True, "added": len(added)})


@knowledge.route("/<uuid>/source/<source_uuid>", methods=["DELETE"])
@login_required
def remove_source(uuid, source_uuid):
    """Remove a single source from a KB."""
    kb = KnowledgeBase.objects(uuid=uuid, user_id=_get_user_id()).first()
    if not kb:
        return jsonify({"error": "Knowledge base not found"}), 404

    source = KnowledgeBaseSource.objects(uuid=source_uuid, knowledge_base=kb).first()
    if not source:
        return jsonify({"error": "Source not found"}), 404

    # Remove from ChromaDB
    try:
        dm = DocumentManager()
        dm.delete_kb_source(kb.uuid, source.uuid)
    except Exception as e:
        debug(f"Error deleting KB source from ChromaDB: {e}")

    source.delete()
    kb.recalculate_stats()

    return jsonify({"ok": True})


@knowledge.route("/<uuid>/status", methods=["GET"])
@login_required
def get_status(uuid):
    """Poll build progress for a KB."""
    kb = KnowledgeBase.objects(uuid=uuid, user_id=_get_user_id()).first()
    if not kb:
        return jsonify({"error": "Knowledge base not found"}), 404

    sources = KnowledgeBaseSource.objects(knowledge_base=kb)
    return jsonify({
        "uuid": kb.uuid,
        "status": kb.status,
        "total_sources": kb.total_sources,
        "sources_ready": kb.sources_ready,
        "sources_failed": kb.sources_failed,
        "total_chunks": kb.total_chunks,
        "sources": [
            {
                "uuid": s.uuid,
                "status": s.status,
                "error_message": s.error_message or "",
                "chunk_count": s.chunk_count,
            }
            for s in sources
        ],
    })
