"""Reprocess one knowledge-base source in place.

Before this, the only way to rebuild a single source — after a failed
ingest, an OCR outage, or a chunking change — was to remove it and add it
again, which loses its custom name and source reference (support ticket).
Reprocess runs the same pipeline the source went through when it was added,
and the source list shows it live through the source's own status.

What runs depends on what the source has to work with:

* **Web page** — the existing Refresh: re-fetch, re-chunk, re-embed. A
  failed fetch keeps the previous text.
* **Document with readable text** — re-chunk and re-embed that text
  (``reindex``). The document is not re-read: re-extraction clears the
  document's text everywhere it is used and re-fires its folder's watch
  automations, which a KB action must not do to a document that is fine.
* **Document with no usable text** (its extraction failed or came back
  empty) — re-read the document first, then index it (``reextract``). No
  automation ever fired for such a document, so there is nothing to repeat.
  Re-reading changes the document itself, so it needs edit access to it.
* **Document already being extracted** — wait for that extraction
  (``waiting``); it indexes the source when it finishes.
"""

from __future__ import annotations

import datetime
import logging

from app.models.document import SmartDocument
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.models.user import User
from app.services import access_control, document_service, kb_url_refresh
from app.services.extraction_staleness import extraction_is_stale

logger = logging.getLogger(__name__)


class ReprocessRefused(Exception):
    """A reprocess that cannot start, with the HTTP status and reason to show."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _dispatch_reindex(source_uuid: str) -> None:
    from app.celery_app import celery_app

    celery_app.send_task(
        "tasks.documents.kb_ingest_document",
        args=[source_uuid],
        kwargs={"retrieved": False},
        queue="documents",
    )


async def reprocess_source(
    kb: KnowledgeBase, source: KnowledgeBaseSource, user: User,
) -> dict:
    """Queue a reprocess of ``source``. Raises ``ReprocessRefused``."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    if kb_url_refresh.is_in_flight(source, now):
        raise ReprocessRefused(409, "This source is already being processed")

    if source.source_type == "url":
        if not source.url:
            raise ReprocessRefused(400, "This web source has no URL to fetch")
        await kb_url_refresh.queue_refresh(kb, [source])
        mode = "refetch"
    else:
        mode = await _reprocess_document_source(source, user, now)

    kb.status = "building"
    await kb.save()
    return {"ok": True, "status": "queued", "mode": mode, "source_uuid": source.uuid}


async def _reprocess_document_source(
    source: KnowledgeBaseSource, user: User, now: datetime.datetime,
) -> str:
    doc = (
        await SmartDocument.find_one({"uuid": source.document_uuid})
        if source.document_uuid else None
    )
    if doc is None or getattr(doc, "soft_deleted", False):
        raise ReprocessRefused(
            400,
            "The document behind this source was deleted from Files, so there is "
            "nothing to read again. The source keeps answering from the text it "
            "already indexed; add the document again to rebuild it.",
        )

    extracting = document_service.extraction_in_flight(doc) and not extraction_is_stale(
        doc.updated_at, doc.created_at,
    )
    needs_read = not extracting and (
        doc.task_status == "error" or not (doc.raw_text or "").strip()
    )
    authorized_doc = None
    if needs_read:
        authorized_doc = await access_control.get_authorized_document(
            doc.uuid, user, manage=True, allow_admin=True,
        )
        if authorized_doc is None:
            raise ReprocessRefused(
                403,
                "This source's document has no readable text, and reading it again "
                "changes the document itself, which needs edit access to it in Files. "
                "Ask the document's owner to retry its extraction there, then "
                "reprocess this source.",
            )

    previous = (source.status, source.error_message, source.refresh_queued_at)
    # Parked before any extraction is dispatched: a finishing extraction
    # indexes the document's "pending" sources, and one that finished before
    # this write would leave the source waiting on nothing.
    source.status = "pending"
    source.error_message = None
    source.refresh_queued_at = now
    await source.save()

    if extracting:
        return "waiting"
    if needs_read:
        try:
            await document_service.restart_extraction(authorized_doc, user.user_id)
        except Exception:
            source.status, source.error_message, source.refresh_queued_at = previous
            await source.save()
            raise
        return "reextract"
    _dispatch_reindex(source.uuid)
    return "reindex"
