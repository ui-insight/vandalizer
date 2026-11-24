"""Repair documents whose stored text is a raw OCR ``ocr.result`` envelope.

Before ``ocr_client.parse_raw_response`` existed, a raw OCR endpoint that
answered with a JSON envelope (``{"id": "ocr-…", "object": "ocr.result",
"model": "dots.MOCR", "content": "…"}``) had that whole body stored as the
document's text: the wrapper at the start, and every line break as a literal
``\\n``. Re-uploading fixed a file; nothing fixed the copies already stored,
and those kept feeding search, citations and knowledge bases (support ticket).

The envelope still holds the text the fixed reader would have stored, so the
repair decodes it in place rather than re-reading the file. Re-reading would
mean a fresh OCR bill per document, and re-extraction re-fires its folder's
watch automations, which a background repair must never do.

Each envelope found in the text is replaced with what ``parse_raw_response``
returns for it — the exact path new uploads take, layout cleanup included.
A document can hold several: the per-page OCR path stores one per page it
sent to OCR, between pages read locally. Page markers are carried across:
interpolated (approximate) markers are spread again over the repaired text,
and measured ones are moved by how much the text before them shrank.

Then the document is re-indexed: its own chunks (and its project's KB mirror,
which that ingestion refreshes), and every other knowledge-base source built
from it, swapped in place so a failed embed keeps the previous chunks.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pymongo.database import Database

logger = logging.getLogger(__name__)

# What a stored envelope contains, as a Mongo regex and as Python. Only the
# discriminator ``parse_raw_response`` itself requires: a JSON example quoted
# in a document is not an OCR envelope and is left alone.
ENVELOPE_PATTERN = r'"object"\s*:\s*"ocr\.result"'
_ENVELOPE_RE = re.compile(ENVELOPE_PATTERN)

# How far before the discriminator the envelope's opening brace may sit. The
# fields ahead of it are an id and nothing else in every envelope seen; this
# leaves room for a long id or a reordered ``created`` without scanning the
# whole document for braces.
_MAX_LEAD = 512


@dataclass
class UnwrapResult:
    text: str
    envelopes: int
    # One (old_start, old_end, new_start, new_end) per replaced span, in order.
    spans: list[tuple[int, int, int, int]] = field(default_factory=list)
    # Discriminators found that did not decode as an envelope.
    undecodable: int = 0
    # Leading whitespace stripped off the joined text; span offsets already
    # account for it, untouched text before the first span does not.
    lead: int = 0

    def map_offset(self, old: int) -> int:
        """Where character ``old`` of the stored text lands in the repaired text.

        An offset inside a replaced envelope maps to the start of its content:
        a page boundary there marks where that page's text begins.
        """
        starts = [s[0] for s in self.spans]
        i = bisect_right(starts, old) - 1
        if i < 0:
            return max(0, old - self.lead)
        old_start, old_end, new_start, new_end = self.spans[i]
        if old < old_end:
            return new_start
        return max(0, old + (new_end - old_end))


def _decode_envelope_at(
    text: str, hit: int, decoder: json.JSONDecoder,
) -> tuple[int, int, str] | None:
    """The envelope containing the discriminator at ``hit``: (start, end, body)."""
    lo = max(0, hit - _MAX_LEAD)
    brace = text.rfind("{", lo, hit)
    while brace != -1:
        try:
            value, end = decoder.raw_decode(text, brace)
        except ValueError:
            value, end = None, brace
        if (
            isinstance(value, dict)
            and value.get("object") == "ocr.result"
            and end > hit
        ):
            return brace, end, text[brace:end]
        brace = text.rfind("{", lo, brace)
    return None


def unwrap_ocr_envelopes(text: str) -> UnwrapResult | None:
    """Replace every ``ocr.result`` envelope in ``text`` with its decoded text.

    Returns None when ``text`` contains no envelope that decodes. An envelope
    whose content is not a string is counted as undecodable and left in place:
    there is no text in it to recover, and the document needs re-reading.
    """
    if not text or "ocr.result" not in text:
        return None
    from app.services.ocr_client import OcrRequestError, parse_raw_response

    decoder = json.JSONDecoder()
    out: list[str] = []
    spans: list[tuple[int, int, int, int]] = []
    undecodable = 0
    kept_from = 0
    new_len = 0
    for match in _ENVELOPE_RE.finditer(text):
        if match.start() < kept_from:
            continue  # inside an envelope already replaced
        found = _decode_envelope_at(text, match.start(), decoder)
        if found is None:
            undecodable += 1
            continue
        start, end, body = found
        try:
            content = parse_raw_response(body)
        except OcrRequestError:
            undecodable += 1
            continue
        before = text[kept_from:start]
        out.append(before)
        new_len += len(before)
        out.append(content)
        spans.append((start, end, new_len, new_len + len(content)))
        new_len += len(content)
        kept_from = end
    if not spans:
        return None
    out.append(text[kept_from:])
    repaired = "".join(out)
    # parse_raw_response strips its result; a document that was one envelope
    # padded with whitespace should not keep the padding.
    lead = len(repaired) - len(repaired.lstrip())
    repaired = repaired.strip()
    if lead:
        spans = [(a, b, max(0, c - lead), max(0, d - lead)) for a, b, c, d in spans]
    return UnwrapResult(
        text=repaired, envelopes=len(spans), spans=spans,
        undecodable=undecodable, lead=lead,
    )


def repair_markers(markers: list[dict], result: UnwrapResult) -> list[dict]:
    """Page/sheet markers for the repaired text.

    Interpolated markers only ever meant "the text spread evenly over N
    pages", so they are spread again over the new length — moving them would
    keep the old, wrapper-inflated spacing. Measured markers are moved.
    """
    if not markers:
        return []
    from app.services.document_readers import _interpolate_page_markers

    if all(m.get("kind") == "page" and m.get("approximate") for m in markers):
        return _interpolate_page_markers(result.text, len(markers))
    last = max(0, len(result.text) - 1)
    repaired = []
    for marker in markers:
        offset = marker.get("char_offset")
        moved = dict(marker)
        if isinstance(offset, int):
            moved["char_offset"] = min(last, result.map_offset(offset))
        repaired.append(moved)
    return repaired


def repaired_fields(doc: dict, result: UnwrapResult) -> dict:
    """The document fields that derive from its text, recomputed for ``result``."""
    from app.services.context_budget import count_raw_tokens
    from app.utils.extraction_quality import is_sparse_extraction, nonletter_ratio

    text = result.text
    fields: dict = {
        "raw_text": text,
        "text_markers": repair_markers(doc.get("text_markers") or [], result),
        "token_count": count_raw_tokens(text) if text else 0,
        "extraction_nonletter_ratio": nonletter_ratio(text) if text else None,
        "ocr_envelope_repaired_at": datetime.datetime.now(tz=datetime.timezone.utc),
    }
    # The density check judged the wrapped text; judge the real text instead.
    # Other warnings (partial OCR, unread pages) describe the reading, not the
    # wrapper, and stand.
    warnings = [w for w in (doc.get("ingestion_warnings") or []) if w != "sparse_text"]
    extension = (doc.get("extension") or "").lower()
    if extension == "pdf" and text and is_sparse_extraction(text, doc.get("num_pages") or None):
        warnings.append("sparse_text")
    fields["ingestion_warnings"] = warnings
    return fields


def _reindex(db: Database[Any], doc: dict) -> int:
    """Queue the re-index of a repaired document; returns KB sources queued."""
    from app.celery_app import celery_app

    revision = doc.get("_extraction_restart_revision")
    celery_app.send_task(
        "tasks.document.semantic_ingestion",
        args=["", doc["uuid"], doc.get("user_id", "")],
        kwargs={"extraction_revision": revision if type(revision) is int else 0},
        queue="documents",
    )
    # Project (implicit) KBs are refreshed by that ingestion's project mirror,
    # which sees the changed text; queueing them here too would race it.
    implicit = {
        kb["uuid"]
        for kb in db.knowledge_bases.find({"implicit": True}, {"uuid": 1})
    }
    queued = 0
    for source in db.knowledge_base_sources.find(
        {"document_uuid": doc["uuid"], "source_type": "document", "status": "ready"},
        {"uuid": 1, "knowledge_base_uuid": 1},
    ):
        if source.get("knowledge_base_uuid") in implicit:
            continue
        celery_app.send_task(
            "tasks.documents.kb_ingest_document",
            args=[source["uuid"]],
            # Not re-read: the source's retrieval dates stay, the chunks swap.
            kwargs={"retrieved": False},
            queue="documents",
        )
        queued += 1
    return queued


def candidate_query() -> dict:
    return {
        "raw_text": {"$regex": ENVELOPE_PATTERN},
        "soft_deleted": {"$ne": True},
    }


def repair_document(db: Database[Any], doc: dict, *, dry_run: bool = False) -> dict:
    """Repair one document. Returns a summary row for logs and the script."""
    row = {"uuid": doc.get("uuid"), "title": doc.get("title"), "status": "skipped"}
    if doc.get("processing"):
        # An extraction in flight will store fresh text of its own.
        row["status"] = "extracting"
        return row
    old_text = doc.get("raw_text") or ""
    result = unwrap_ocr_envelopes(old_text)
    if result is None:
        row["status"] = "undecodable"
        return row
    row.update(
        envelopes=result.envelopes, undecodable=result.undecodable,
        chars_before=len(old_text), chars_after=len(result.text),
    )
    if not result.text.strip():
        row["status"] = "empty"
        return row
    if dry_run:
        row["status"] = "would_repair"
        return row
    fields = repaired_fields(doc, result)
    # Compare-and-set on the text read: a retry or re-upload that stored new
    # text in the meantime wins, and a second sweep never repairs (or
    # re-indexes) the same document twice.
    updated = db.smart_document.update_one(
        {"uuid": doc["uuid"], "raw_text": old_text, "processing": {"$ne": True}},
        {"$set": fields},
    )
    if not updated.matched_count:
        row["status"] = "changed"
        return row
    row["kb_sources_queued"] = _reindex(db, doc)
    row["status"] = "repaired"
    logger.info(
        "Repaired OCR envelope text on document %s (%d envelope(s), %d -> %d chars, "
        "%d KB source(s) re-indexing)",
        doc["uuid"], result.envelopes, len(old_text), len(result.text),
        row["kb_sources_queued"],
    )
    return row


def repair_all(db: Database[Any], *, dry_run: bool = False, limit: int | None = None) -> list[dict]:
    """Repair every affected document. Idempotent: repaired text has no envelope."""
    cursor = db.smart_document.find(
        candidate_query(),
        {
            "uuid": 1, "title": 1, "raw_text": 1, "text_markers": 1, "user_id": 1,
            "processing": 1, "extension": 1, "num_pages": 1, "ingestion_warnings": 1,
            "_extraction_restart_revision": 1,
        },
    )
    if limit:
        cursor = cursor.limit(limit)
    rows = []
    for doc in cursor:
        try:
            rows.append(repair_document(db, doc, dry_run=dry_run))
        except Exception as e:  # noqa: BLE001 — one bad document must not stop the sweep
            logger.exception("OCR envelope repair failed for document %s", doc.get("uuid"))
            rows.append({"uuid": doc.get("uuid"), "title": doc.get("title"), "status": "failed", "error": str(e)})
    return rows
