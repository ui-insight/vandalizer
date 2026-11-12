"""The reading a document had before a re-read started, kept so Stop can put it back.

A re-read (Retry extraction, Re-run OCR, a knowledge-base Reprocess) clears the
document's text when it starts, because every later step reads the text from
the document itself. Support ticket: Re-run OCR on a PDF whose text was fine,
then Stop, left the document with no text until someone clicked Retry, and
chat and workflows read an empty document in the meantime.

The previous reading is copied here, outside the document, before it is
cleared. It lives in its own collection so a large text is not stored twice in
one record, and it is never loaded with the document.

Everything here is best effort and never raises: a re-read or a Stop must not
fail because the safety copy could not be written or read. Without a copy the
behaviour is what it was before: Stop leaves a retryable, text-less document.
"""

import datetime
import logging
from typing import Any, Optional

from app.models.document import SmartDocument

logger = logging.getLogger(__name__)

COLLECTION = "document_previous_reading"

#: What a re-read clears or replaces, and so what Stop restores.
READING_FIELDS = (
    "raw_text", "token_count", "text_markers", "extraction_nonletter_ratio",
    "ingestion_warnings", "task_status", "validating", "error_message",
    "error_retryable", "text_layer_rejected",
)

#: A copy this large is skipped rather than risk the 16 MB record limit.
MAX_TEXT_BYTES = 8 * 1024 * 1024

#: Copies clean themselves up; no extraction stays in flight this long.
KEEP_SECONDS = 7 * 24 * 60 * 60

_index_ready = False


def _collection() -> Any:
    return SmartDocument.get_motor_collection().database[COLLECTION]


async def save_previous_reading(doc: SmartDocument, revision: int) -> bool:
    """Copy *doc*'s current reading before a re-read clears it.

    ``revision`` is the restart revision the re-read is about to claim; Stop
    restores the copy only into that same run. A document with no text has
    nothing worth keeping, and any older copy is dropped.
    """
    global _index_ready
    try:
        snapshots = _collection()
        raw = await SmartDocument.get_motor_collection().find_one(
            {"_id": doc.id}, {field: 1 for field in READING_FIELDS}
        )
        raw = raw or {}
        text = raw.get("raw_text") or ""
        if not text or len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            await snapshots.delete_one({"_id": doc.uuid})
            return False
        if not _index_ready:
            await snapshots.create_index("saved_at", expireAfterSeconds=KEEP_SECONDS)
            _index_ready = True
        await snapshots.replace_one(
            {"_id": doc.uuid},
            {
                "revision": revision,
                "saved_at": datetime.datetime.now(datetime.timezone.utc),
                "fields": {field: raw[field] for field in READING_FIELDS if field in raw},
            },
            upsert=True,
        )
        return True
    except Exception:
        logger.warning("Could not keep the previous reading of document %s", doc.uuid, exc_info=True)
        return False


async def previous_reading(doc_uuid: str) -> Optional[dict]:
    """The saved copy for this document: ``{"revision", "fields"}``, or None."""
    try:
        found = await _collection().find_one({"_id": doc_uuid})
    except Exception:
        logger.warning("Could not read the previous reading of document %s", doc_uuid, exc_info=True)
        return None
    if not isinstance(found, dict) or not isinstance(found.get("fields"), dict):
        return None
    if not found["fields"].get("raw_text") or not isinstance(found.get("revision"), int):
        return None
    return {"revision": found["revision"], "fields": dict(found["fields"])}


async def discard(doc_uuid: str) -> None:
    try:
        await _collection().delete_one({"_id": doc_uuid})
    except Exception:
        logger.warning("Could not discard the previous reading of document %s", doc_uuid, exc_info=True)
