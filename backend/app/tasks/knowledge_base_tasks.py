"""Celery tasks for Knowledge Base ingestion.

Ported from Flask app/utilities/knowledge_base_tasks.py.
Uses pymongo (sync) for DB access.
"""

import datetime
import logging

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)


def _get_db():
    """Get sync pymongo database handle."""
    from pymongo import MongoClient

    from app.config import Settings
    settings = Settings()
    client = MongoClient(settings.mongo_host)
    return client[settings.mongo_db]


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
        chunk_count = dm.add_to_kb(
            kb_uuid=kb_uuid,
            source_id=source_uuid,
            source_name=doc.get("title", ""),
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

        # Fetch URL content
        import httpx
        from bs4 import BeautifulSoup
        from app.utils.url_validation import validate_outbound_url

        validate_outbound_url(url)  # raises ValueError for internal/private URLs
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove non-content elements
        for tag in soup(["script", "style", "nav", "footer", "header", "form"]):
            tag.decompose()

        raw_text = soup.get_text(separator="\n", strip=True)
        url_title = soup.title.string if soup.title else ""

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

    except Exception as e:
        logger.error("Error ingesting URL source %s: %s", source_uuid, e)
        db.knowledge_base_sources.update_one(
            {"uuid": source_uuid},
            {"$set": {"status": "error", "error_message": str(e)[:2000]}},
        )
        raise

    finally:
        _recalculate_kb(db, kb_uuid)
