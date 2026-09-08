"""Backfill ``document_title`` on knowledge base sources.

Ingestion now records the document's filename on the KB source, so a source
whose document is later deleted from Files keeps its name instead of falling
back to a UUID. Rows ingested before that change have no title stored. This
fills them in, from two places in priority order:

1. the live SmartDocument, for sources whose document still exists;
2. the ``source_name`` on the source's chunks in ChromaDB, for sources whose
   document is already gone — the chunks outlive the document, and they carry
   the name it had when it was indexed.

Idempotent: sources that already have a title are left alone. Read-only for
ChromaDB. Run from ``backend/``:

    uv run python scripts/backfill_kb_source_titles.py --dry-run
    uv run python scripts/backfill_kb_source_titles.py
"""

import argparse
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill_kb_source_titles")


def _chunk_source_name(dm, kb_uuid: str, source_id: str) -> str | None:
    """The name a source's chunks were indexed under, if any are left."""
    try:
        collection = dm.get_kb_collection_readonly(kb_uuid)
        if collection is None:
            return None
        got = collection.get(where={"source_id": source_id}, limit=1, include=["metadatas"])
    except Exception as e:
        logger.warning("  chroma read failed for %s/%s: %s", kb_uuid, source_id, e)
        return None
    for meta in (got.get("metadatas") or []):
        name = (meta or {}).get("source_name")
        if name:
            return str(name)
    return None


async def main(dry_run: bool) -> None:
    from app.database import init_db
    from app.models.document import SmartDocument
    from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
    from app.services.document_manager import get_document_manager

    await init_db()

    sources = await KnowledgeBaseSource.find(
        {"source_type": "document", "document_title": {"$in": [None, ""]}},
    ).to_list()
    if not sources:
        logger.info("Nothing to backfill.")
        return

    doc_uuids = [s.document_uuid for s in sources if s.document_uuid]
    docs = await SmartDocument.find({"uuid": {"$in": doc_uuids}}).to_list()
    live_titles = {d.uuid: d.title for d in docs if d.title}

    # Implicit (project) KBs key their chunks by document_uuid; explicit KBs by
    # the source's own uuid. Look under the right one or the read finds nothing.
    kb_uuids = {s.knowledge_base_uuid for s in sources}
    kbs = await KnowledgeBase.find({"uuid": {"$in": list(kb_uuids)}}).to_list()
    implicit = {kb.uuid for kb in kbs if kb.implicit}

    dm = get_document_manager()
    from_document = from_chunks = unresolved = 0

    for source in sources:
        title = live_titles.get(source.document_uuid or "")
        origin = "document"
        if not title:
            source_id = (
                source.document_uuid
                if source.knowledge_base_uuid in implicit and source.document_uuid
                else source.uuid
            )
            title = _chunk_source_name(dm, source.knowledge_base_uuid, source_id)
            origin = "chunks"
        if not title:
            unresolved += 1
            logger.info(
                "  no name recoverable: kb=%s source=%s document=%s",
                source.knowledge_base_uuid, source.uuid, source.document_uuid,
            )
            continue

        if origin == "document":
            from_document += 1
        else:
            from_chunks += 1
        logger.info("  %s -> %r (from %s)", source.uuid, title, origin)
        if not dry_run:
            # Write the one field, not the whole document: save() would send
            # every field this process read, so an ingest that updated
            # chunk_count/status between the find above and this write would
            # be silently rolled back. The script is re-runnable and will
            # eventually be run on a live system.
            await source.set({KnowledgeBaseSource.document_title: title})

    logger.info(
        "%s%d source(s): %d from the document, %d from indexed chunks, %d unresolved.",
        "[dry run] " if dry_run else "",
        len(sources), from_document, from_chunks, unresolved,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
