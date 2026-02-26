"""Celery tasks for Knowledge Base ingestion."""

import datetime

from devtools import debug

from app.celery_worker import celery_app
from app.models import KnowledgeBase, KnowledgeBaseSource, SmartDocument
from app.utilities.document_manager import DocumentManager
from app.utilities.web_utils import URLContentFetcher


def _recalculate_kb(kb):
    """Recalculate KB stats and update status."""
    kb.reload()
    kb.recalculate_stats()


@celery_app.task(
    name="tasks.documents.kb_ingest_document",
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=10,
)
def kb_ingest_document(self, source_uuid: str):
    """Fetch a SmartDocument's raw_text, chunk and embed into the KB collection."""
    source = KnowledgeBaseSource.objects(uuid=source_uuid).first()
    if not source:
        debug(f"KB source {source_uuid} not found, skipping.")
        return

    source.status = "processing"
    source.save()

    try:
        doc = SmartDocument.objects(uuid=source.document_uuid).first()
        if not doc:
            source.status = "error"
            source.error_message = "Document not found"
            source.save()
            _recalculate_kb(source.knowledge_base)
            return

        raw_text = doc.raw_text or ""
        if not raw_text.strip():
            source.status = "error"
            source.error_message = "Document has no text content"
            source.save()
            _recalculate_kb(source.knowledge_base)
            return

        kb = source.knowledge_base
        dm = DocumentManager()
        chunk_count = dm.add_to_kb(
            kb_uuid=kb.uuid,
            source_id=source.uuid,
            source_name=doc.title,
            raw_text=raw_text,
        )

        source.chunk_count = chunk_count
        source.status = "ready"
        source.processed_at = datetime.datetime.now()
        source.save()

    except Exception as e:
        debug(f"Error ingesting document source {source_uuid}: {e}")
        source.status = "error"
        source.error_message = str(e)[:2000]
        source.save()
        raise

    finally:
        _recalculate_kb(source.knowledge_base)


@celery_app.task(
    name="tasks.documents.kb_ingest_url",
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=10,
)
def kb_ingest_url(self, source_uuid: str):
    """Fetch URL content, chunk and embed into the KB collection."""
    source = KnowledgeBaseSource.objects(uuid=source_uuid).first()
    if not source:
        debug(f"KB source {source_uuid} not found, skipping.")
        return

    source.status = "processing"
    source.save()

    try:
        fetcher = URLContentFetcher()
        result = fetcher.fetch_url_content(source.url)

        if not result or not result.get("content"):
            source.status = "error"
            source.error_message = "Failed to fetch URL content"
            source.save()
            _recalculate_kb(source.knowledge_base)
            return

        raw_text = result["content"]
        source.content = raw_text[:500000]  # Store extracted text
        source.url_title = result.get("title", "")[:500]

        kb = source.knowledge_base
        dm = DocumentManager()
        chunk_count = dm.add_to_kb(
            kb_uuid=kb.uuid,
            source_id=source.uuid,
            source_name=source.url_title or source.url,
            raw_text=raw_text,
        )

        source.chunk_count = chunk_count
        source.status = "ready"
        source.processed_at = datetime.datetime.now()
        source.save()

    except Exception as e:
        debug(f"Error ingesting URL source {source_uuid}: {e}")
        source.status = "error"
        source.error_message = str(e)[:2000]
        source.save()
        raise

    finally:
        _recalculate_kb(source.knowledge_base)
