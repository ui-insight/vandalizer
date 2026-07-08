"""Celery tasks for Knowledge Base ingestion.

Ported from Flask app/utilities/knowledge_base_tasks.py.
Uses pymongo (sync) for DB access.
"""

import datetime
import logging

import httpx

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)


def _get_db():
    """Get sync pymongo database handle (shared per-process client)."""
    from app.tasks import get_sync_db

    return get_sync_db()


def _recalculate_kb(db, kb_uuid: str) -> None:
    """Recalculate KB aggregate stats from its sources."""
    sources = list(db.knowledge_base_sources.find({"knowledge_base_uuid": kb_uuid}))

    total = len(sources)
    ready = sum(1 for s in sources if s.get("status") == "ready")
    failed = sum(1 for s in sources if s.get("status") == "error")
    total_chunks = sum(s.get("chunk_count", 0) for s in sources)

    if total == 0:
        status = "empty"
    elif ready == total:
        status = "ready"
    elif failed == total:
        status = "error"
    else:
        status = "building"

    db.knowledge_bases.update_one(
        {"uuid": kb_uuid},
        {
            "$set": {
                "total_sources": total,
                "sources_ready": ready,
                "sources_failed": failed,
                "total_chunks": total_chunks,
                "status": status,
                "updated_at": datetime.datetime.now(datetime.timezone.utc),
            }
        },
    )


@celery_app.task(
    name="tasks.documents.kb_ingest_document",
    bind=True,
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=10,
)
def kb_ingest_document(self, source_uuid: str) -> None:
    """Fetch a SmartDocument's raw_text, chunk and embed into the KB collection."""
    from app.services.document_manager import get_document_manager

    db = _get_db()
    source = db.knowledge_base_sources.find_one({"uuid": source_uuid})
    if not source:
        logger.warning("KB source %s not found, skipping.", source_uuid)
        return

    kb_uuid = source["knowledge_base_uuid"]

    db.knowledge_base_sources.update_one(
        {"uuid": source_uuid},
        {"$set": {"status": "processing"}},
    )

    try:
        doc = db.smart_document.find_one({"uuid": source.get("document_uuid")})
        if not doc:
            db.knowledge_base_sources.update_one(
                {"uuid": source_uuid},
                {"$set": {"status": "error", "error_message": "Document not found"}},
            )
            _recalculate_kb(db, kb_uuid)
            return

        raw_text = doc.get("raw_text", "")
        if not raw_text.strip():
            db.knowledge_base_sources.update_one(
                {"uuid": source_uuid},
                {"$set": {"status": "error", "error_message": "Document has no text content"}},
            )
            _recalculate_kb(db, kb_uuid)
            return

        dm = get_document_manager()
        # Idempotent: clear any chunks from a prior (partial) run so a Celery
        # autoretry can't double-add or collide on chunk ids.
        dm.delete_kb_source(kb_uuid, source_uuid)
        chunk_count = dm.add_to_kb(
            kb_uuid=kb_uuid,
            source_id=source_uuid,
            source_name=doc.get("title", ""),
            raw_text=raw_text,
            text_markers=doc.get("text_markers") or [],
        )

        db.knowledge_base_sources.update_one(
            {"uuid": source_uuid},
            {
                "$set": {
                    "chunk_count": chunk_count,
                    "status": "ready",
                    "processed_at": datetime.datetime.now(datetime.timezone.utc),
                }
            },
        )

    except Exception as e:
        logger.error("Error ingesting document source %s: %s", source_uuid, e)
        db.knowledge_base_sources.update_one(
            {"uuid": source_uuid},
            {"$set": {"status": "error", "error_message": str(e)[:2000]}},
        )
        raise

    finally:
        _recalculate_kb(db, kb_uuid)


@celery_app.task(
    name="tasks.documents.kb_reingest",
    bind=True,
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=10,
)
def kb_reingest(self, kb_uuid: str) -> None:
    """Re-chunk and re-embed every source in a KB from stored text.

    Used after chunking improvements (e.g. table-aware splitting) so existing
    KBs benefit without re-uploading files. Document sources re-chunk from
    ``SmartDocument.raw_text`` + ``text_markers``; URL sources re-chunk from
    their stored ``content`` snapshot (no refetch). Sources with nothing
    stored to re-chunk are left untouched.
    """
    from app.services.document_manager import get_document_manager

    db = _get_db()
    kb = db.knowledge_bases.find_one({"uuid": kb_uuid})
    if not kb:
        logger.warning("KB %s not found, skipping re-ingest.", kb_uuid)
        return
    sources = list(db.knowledge_base_sources.find({"knowledge_base_uuid": kb_uuid}))
    if not sources:
        _recalculate_kb(db, kb_uuid)
        return

    # Project (implicit) KBs key chunks by document_uuid (_ingest_into_project_kb);
    # explicit KBs key by the source's own uuid. Re-adding must preserve the
    # convention or later per-source deletes would miss the chunks.
    is_implicit = bool(kb.get("implicit"))

    dm = get_document_manager()
    for source in sources:
        source_uuid = source["uuid"]
        document_uuid = source.get("document_uuid")
        try:
            if source.get("source_type") == "url":
                raw_text = source.get("content") or ""
                source_name = (
                    source.get("custom_name")
                    or source.get("url_title")
                    or source.get("url")
                    or ""
                )
                text_markers: list = []
                source_id = source_uuid
            else:
                doc = (
                    db.smart_document.find_one({"uuid": document_uuid})
                    if document_uuid else None
                )
                raw_text = (doc or {}).get("raw_text", "")
                source_name = source.get("custom_name") or (doc or {}).get("title", "")
                text_markers = (doc or {}).get("text_markers") or []
                source_id = (
                    document_uuid if is_implicit and document_uuid else source_uuid
                )

            if not raw_text.strip():
                logger.warning(
                    "KB %s source %s has no stored text to re-chunk; skipping.",
                    kb_uuid, source_uuid,
                )
                continue

            db.knowledge_base_sources.update_one(
                {"uuid": source_uuid},
                {"$set": {"status": "processing"}},
            )
            # Clear under both id conventions — harmless no-op for the unused one.
            dm.delete_kb_source(kb_uuid, source_uuid)
            if document_uuid and document_uuid != source_uuid:
                dm.delete_kb_source(kb_uuid, document_uuid)

            chunk_count = dm.add_to_kb(
                kb_uuid=kb_uuid,
                source_id=source_id,
                source_name=source_name,
                raw_text=raw_text,
                text_markers=text_markers,
            )
            db.knowledge_base_sources.update_one(
                {"uuid": source_uuid},
                {
                    "$set": {
                        "chunk_count": chunk_count,
                        "status": "ready",
                        "error_message": None,
                        "processed_at": datetime.datetime.now(datetime.timezone.utc),
                    }
                },
            )
        except Exception as e:
            logger.error(
                "Error re-ingesting KB %s source %s: %s", kb_uuid, source_uuid, e,
            )
            db.knowledge_base_sources.update_one(
                {"uuid": source_uuid},
                {"$set": {"status": "error", "error_message": str(e)[:2000]}},
            )

    _recalculate_kb(db, kb_uuid)


@celery_app.task(
    name="tasks.documents.kb_ingest_url",
    bind=True,
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=10,
)
def kb_ingest_url(self, source_uuid: str) -> None:
    """Fetch URL content, chunk and embed into the KB collection."""
    from app.services.document_manager import get_document_manager

    db = _get_db()
    source = db.knowledge_base_sources.find_one({"uuid": source_uuid})
    if not source:
        logger.warning("KB source %s not found, skipping.", source_uuid)
        return

    kb_uuid = source["knowledge_base_uuid"]

    db.knowledge_base_sources.update_one(
        {"uuid": source_uuid},
        {"$set": {"status": "processing"}},
    )

    try:
        url = source.get("url", "")
        if not url:
            db.knowledge_base_sources.update_one(
                {"uuid": source_uuid},
                {"$set": {"status": "error", "error_message": "No URL specified"}},
            )
            _recalculate_kb(db, kb_uuid)
            return

        # Fetch URL content via the shared web_fetcher (trafilatura + Playwright
        # fallback for JS-rendered pages).
        from app.services.web_fetcher import fetch_url_sync

        result = fetch_url_sync(url)  # raises ValueError for blocked URLs
        raw_text = result.text
        url_title = result.title

        if not raw_text.strip():
            db.knowledge_base_sources.update_one(
                {"uuid": source_uuid},
                {"$set": {"status": "error", "error_message": "Failed to fetch URL content"}},
            )
            _recalculate_kb(db, kb_uuid)
            return

        # Store extracted content on source
        db.knowledge_base_sources.update_one(
            {"uuid": source_uuid},
            {
                "$set": {
                    "content": raw_text[:500000],
                    "url_title": (url_title or "")[:500],
                }
            },
        )

        dm = get_document_manager()
        # Idempotent: clear any chunks from a prior (partial) run so a Celery
        # autoretry can't double-add or collide on chunk ids.
        dm.delete_kb_source(kb_uuid, source_uuid)
        chunk_count = dm.add_to_kb(
            kb_uuid=kb_uuid,
            source_id=source_uuid,
            source_name=url_title or url,
            raw_text=raw_text,
        )

        db.knowledge_base_sources.update_one(
            {"uuid": source_uuid},
            {
                "$set": {
                    "chunk_count": chunk_count,
                    "status": "ready",
                    "processed_at": datetime.datetime.now(datetime.timezone.utc),
                }
            },
        )

    except httpx.HTTPStatusError as e:
        if 400 <= e.response.status_code < 500:
            logger.warning("URL source %s returned %d: %s", source_uuid, e.response.status_code, e.request.url)
            db.knowledge_base_sources.update_one(
                {"uuid": source_uuid},
                {"$set": {"status": "error", "error_message": str(e)[:2000]}},
            )
        else:
            logger.error("Error ingesting URL source %s: %s", source_uuid, e)
            db.knowledge_base_sources.update_one(
                {"uuid": source_uuid},
                {"$set": {"status": "error", "error_message": str(e)[:2000]}},
            )
            raise
    except (ValueError, httpx.RequestError) as e:
        logger.warning("URL source %s unreachable: %s", source_uuid, e)
        db.knowledge_base_sources.update_one(
            {"uuid": source_uuid},
            {"$set": {"status": "error", "error_message": str(e)[:2000]}},
        )
    except Exception as e:
        logger.error("Error ingesting URL source %s: %s", source_uuid, e)
        db.knowledge_base_sources.update_one(
            {"uuid": source_uuid},
            {"$set": {"status": "error", "error_message": str(e)[:2000]}},
        )
        raise

    finally:
        _recalculate_kb(db, kb_uuid)
