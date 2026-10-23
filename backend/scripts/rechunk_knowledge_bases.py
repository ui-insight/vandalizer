"""Re-chunk knowledge bases indexed before structure-aware chunking.

Rebuilds every ready source whose chunks were cut by an older chunker from
the text it already stores — nothing is fetched — swapping old chunks for new
ones source by source, so each source answers throughout. Idempotent: a
second run finds every source current and writes nothing. See
``app/services/kb_rechunk.py`` for what is skipped and why, and for why
Autovalidate-tuned settings are left as they are (the KB's Optimized badge
reads stale until it is re-tuned).

Before a real run: back up MongoDB and the ChromaDB volume, and run it when
no ingestion is in flight (two writers on one source can leave it with two
sets of chunks; a later run repairs that). Afterwards restart the api and
celery containers, or allow ten minutes: each process caches its knowledge-
base index and rebuilds it once the chunk count has changed.

Usage (inside the backend container, from /app, or from backend/)::

    python -m scripts.rechunk_knowledge_bases --dry-run          # report only
    python -m scripts.rechunk_knowledge_bases                    # every KB
    python -m scripts.rechunk_knowledge_bases --kb <uuid> --kb <uuid>
    python -m scripts.rechunk_knowledge_bases --json report.json

``--force`` rebuilds current sources too, and sources whose stored text no
longer matches what was indexed.
"""

import argparse
import json
import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rechunk_knowledge_bases")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--kb", action="append", default=[], help="knowledge base uuid (repeatable); default all")
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    parser.add_argument("--force", action="store_true", help="rebuild current and changed-text sources too")
    parser.add_argument("--json", help="also write the full report to this file")
    args = parser.parse_args(argv)

    from app.services import kb_chunking
    from app.services.document_manager import get_document_manager
    from app.services.kb_rechunk import FAILED, REBUILT, WOULD_REBUILD, rechunk_all
    from app.tasks import get_sync_db

    db, dm = get_sync_db(), get_document_manager()
    started = time.time()
    logger.info("Chunker version %d%s", kb_chunking.CHUNKER_VERSION, " — dry run, nothing written" if args.dry_run else "")
    reports = rechunk_all(db, dm, kb_uuids=args.kb or None, dry_run=args.dry_run, force=args.force)

    changed = REBUILT if not args.dry_run else WOULD_REBUILD
    for r in reports:
        counts = r.as_dict()["counts"]
        logger.info(
            "%s  %-40s %s %d, current %d, skipped %d, failed %d; chunks %d -> %d%s",
            r.kb_uuid, r.title[:40], changed, counts[changed], counts["current"], counts["skipped"],
            counts[FAILED], r.chunks_before, r.chunks_after,
            "  [tuned settings kept; Optimized badge will read stale]" if r.tuned_settings and counts[changed] else "",
        )
        for s in r.sources:
            if s.action in ("skipped", FAILED):
                logger.info("    %-8s %s (%s): %s", s.action, s.name[:60], s.source_uuid, s.reason)
    total = sum(r.count(changed) for r in reports)
    failed = sum(r.count(FAILED) for r in reports)
    logger.info(
        "%d knowledge bases, %d sources %s, %d failed, chunks %d -> %d, %.0fs",
        len(reports), total, changed.replace("_", " "), failed,
        sum(r.chunks_before for r in reports), sum(r.chunks_after for r in reports), time.time() - started,
    )
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([r.as_dict() for r in reports], f, indent=2, default=str)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
