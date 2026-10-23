"""Re-chunk knowledge-base sources indexed by an older chunker.

A source keeps the chunks it was ingested with until something rewrites
them, so a knowledge base built before structure-aware chunking
(:mod:`app.services.kb_chunking`) still answers from 1,000-character windows
that cut across sections. This rebuilds each such source from the text it
already stores — a URL source's snapshot, a document source's extracted text
and page markers — with nothing fetched again.

Each source is swapped with :meth:`DocumentManager.replace_kb_source`: the new
chunks are written beside the old ones and the old ones removed only once
the new set is in, so a source answers throughout and a failure leaves it
as it was. ``kb_reingest``'s delete-then-add is not used for that reason.

Safe to run again: a source whose chunks were all cut by the current chunker
(one set of them — two sets left by a race are rebuilt) is left alone. Only
"ready" sources are touched; a source whose stored text no longer matches
what was indexed (``content_hash``) is reported and skipped, because
rebuilding it would change what it says, not just how it is cut — refresh
or reprocess it instead.

What it does not touch: a knowledge base's Autovalidate-tuned settings
(``rag_config_override``). Re-embedding moves every similarity a tuned
``min_similarity`` floor was set on; measured on two catalog bases, on-target
similarities rose about 0.03 on average while the best match for questions
the base cannot answer stayed where it was, so an old floor blocks what it
blocked before and keeps slightly more of the right passages. It is kept, and
``KnowledgeBase.rechunked_at`` marks the Optimized badge stale
(:mod:`app.services.kb_optimization_status`) so the owner re-runs Validate &
improve.

Sync (pymongo), like the Celery ingest tasks it sits beside; run it with
``scripts/rechunk_knowledge_bases.py``.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import asdict, dataclass, field
from typing import Optional

from app.services import kb_chunking
from app.utils import kb_source_currency as currency

logger = logging.getLogger(__name__)

REBUILT = "rechunked"
WOULD_REBUILD = "would_rechunk"
CURRENT = "current"
SKIPPED = "skipped"
FAILED = "failed"


@dataclass
class SourceOutcome:
    source_uuid: str
    name: str
    action: str
    reason: Optional[str] = None
    chunks_before: int = 0
    chunks_after: Optional[int] = None


@dataclass
class KbReport:
    kb_uuid: str
    title: str
    dry_run: bool
    sources: list[SourceOutcome] = field(default_factory=list)
    # The KB's Autovalidate-tuned settings, reported as they stand (never
    # changed here); the badge reads stale once the KB is re-chunked.
    tuned_settings: Optional[dict] = None

    def count(self, action: str) -> int:
        return sum(1 for s in self.sources if s.action == action)

    @property
    def chunks_before(self) -> int:
        return sum(s.chunks_before for s in self.sources if s.action in (REBUILT, WOULD_REBUILD))

    @property
    def chunks_after(self) -> int:
        return sum(s.chunks_after or 0 for s in self.sources if s.action in (REBUILT, WOULD_REBUILD))

    def as_dict(self) -> dict:
        out = asdict(self)
        out["counts"] = {a: self.count(a) for a in (REBUILT, WOULD_REBUILD, CURRENT, SKIPPED, FAILED)}
        out["chunks_before"], out["chunks_after"] = self.chunks_before, self.chunks_after
        return out


def _indexed(dm, kb_uuid: str, source_id: str) -> Optional[list[dict]]:
    """The metadata of a source's indexed chunks; None when the base has no
    collection."""
    collection = dm.get_kb_collection_readonly(kb_uuid)
    if collection is None:
        return None
    got = collection.get(where={"source_id": source_id}, include=["metadatas"])
    return [m or {} for m in (got.get("metadatas") or [])]


def _is_current(metas: list[dict]) -> bool:
    """Every chunk cut by the current chunker, and only one set of them (two
    writers racing on one source can leave two)."""
    indexes = [m.get("chunk_index") for m in metas]
    return (
        all(m.get("chunker_version") == kb_chunking.CHUNKER_VERSION for m in metas)
        and len(indexes) == len(set(indexes))
    )


def _stored_text(db, source: dict) -> tuple[str, list, Optional[str]]:
    """(text, page markers, document title) a source was indexed from."""
    if source.get("source_type") == "url":
        return source.get("content") or "", [], None
    uuid = source.get("document_uuid")
    doc = db.smart_document.find_one({"uuid": uuid}) if uuid else None
    doc = doc or {}
    return doc.get("raw_text") or "", doc.get("text_markers") or [], doc.get("title") or None


def _rechunk_source(db, dm, kb: dict, source: dict, *, dry_run: bool, force: bool) -> SourceOutcome:
    kb_uuid = kb["uuid"]
    document_uuid = source.get("document_uuid")
    # Project (implicit) KBs key chunks by document; explicit ones by source.
    source_id = document_uuid if kb.get("implicit") is True and document_uuid else source["uuid"]
    label = (source.get("custom_name") or source.get("document_title") or source.get("url_title")
             or source.get("url") or source["uuid"])
    out = SourceOutcome(source_uuid=source["uuid"], name=str(label), action=SKIPPED)

    status = source.get("status")
    if status != "ready":
        # Pending, processing, failed or held for review: nothing indexed to
        # re-cut, or a worker is writing it now.
        out.reason = f"status is {status}"
        return out
    metas = _indexed(dm, kb_uuid, source_id)
    if metas is None:
        out.reason = "the knowledge base has no index"
        return out
    out.chunks_before = len(metas)
    if not metas:
        out.reason = "no indexed chunks"
        return out
    if _is_current(metas) and not force:
        out.action = CURRENT
        if source.get("chunker_version") != kb_chunking.CHUNKER_VERSION and not dry_run:
            db.knowledge_base_sources.update_one(
                {"uuid": source["uuid"]}, {"$set": {"chunker_version": kb_chunking.CHUNKER_VERSION}},
            )
        return out

    text, markers, document_title = _stored_text(db, source)
    if not text.strip():
        out.reason = "no stored text to re-chunk from"
        return out
    recorded = source.get("content_hash")
    if recorded and recorded != currency.content_fingerprint(text) and not force:
        out.reason = "stored text differs from the indexed text; refresh or reprocess the source instead"
        return out
    # The name the chunks were indexed under is the one citations show.
    name = next((str(m["source_name"]) for m in metas if m.get("source_name")), None) \
        or source.get("custom_name") or document_title or source.get("url_title") or source.get("url") or ""

    if dry_run:
        out.action = WOULD_REBUILD
        out.chunks_after = len(kb_chunking.chunk_source(text, name, max_chars=dm.chunk_size))
        return out
    try:
        count = dm.replace_kb_source(kb_uuid, source_id, name, text, text_markers=markers)
    except Exception as e:  # noqa: BLE001 — the swap left the old chunks answering
        logger.error("Re-chunking KB %s source %s failed: %s", kb_uuid, source["uuid"], e)
        out.action, out.reason = FAILED, f"{type(e).__name__}: {e}"[:500]
        return out
    db.knowledge_base_sources.update_one(
        {"uuid": source["uuid"]},
        {"$set": {
            "chunk_count": count,
            # The stored text re-cut: only the ingestion date moves.
            **currency.ingestion_stamp(
                text, retrieved=False,
                retrieved_at=source.get("content_retrieved_at") or source.get("processed_at"),
            ),
        }},
    )
    out.action, out.chunks_after = REBUILT, count
    return out


def rechunk_kb(db, dm, kb_uuid: str, *, dry_run: bool = False, force: bool = False) -> Optional[KbReport]:
    """Re-chunk one knowledge base's sources. None when it does not exist.
    ``force`` rebuilds current sources too, and ones whose stored text no
    longer matches what was indexed."""
    kb = db.knowledge_bases.find_one({"uuid": kb_uuid})
    if not kb:
        return None
    override = kb.get("rag_config_override")
    report = KbReport(
        kb_uuid=kb_uuid, title=str(kb.get("title") or kb_uuid), dry_run=dry_run,
        tuned_settings=dict(override) if isinstance(override, dict) and override else None,
    )
    for source in db.knowledge_base_sources.find({"knowledge_base_uuid": kb_uuid}).sort("created_at", 1):
        report.sources.append(_rechunk_source(db, dm, kb, source, dry_run=dry_run, force=force))
    if report.count(REBUILT):
        from app.tasks.knowledge_base_tasks import _recalculate_kb

        _recalculate_kb(db, kb_uuid)
        db.knowledge_bases.update_one(
            {"uuid": kb_uuid},
            {"$set": {"rechunked_at": datetime.datetime.now(tz=datetime.timezone.utc)}},
        )
    return report


def rechunk_all(db, dm, *, kb_uuids: Optional[list[str]] = None, dry_run: bool = False,
                force: bool = False) -> list[KbReport]:
    """Re-chunk every knowledge base (or those named), oldest first."""
    if kb_uuids:
        uuids = list(kb_uuids)
    else:
        uuids = [k["uuid"] for k in db.knowledge_bases.find({}, {"uuid": 1}).sort("created_at", 1)]
    reports = []
    for uuid in uuids:
        report = rechunk_kb(db, dm, uuid, dry_run=dry_run, force=force)
        if report is None:
            logger.warning("Knowledge base %s not found", uuid)
            continue
        reports.append(report)
    return reports
