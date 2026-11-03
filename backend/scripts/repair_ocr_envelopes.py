"""Repair documents whose stored text is a raw OCR ``ocr.result`` JSON envelope.

The API queues this repair itself at startup until a sweep finishes clean
(see app/services/ocr_envelope_repair.py). Run it by hand to see what is
affected, or to repair now without waiting for a restart.

The text is decoded in place — no OCR call, no folder-watch automations —
and the document and its knowledge-base sources are queued for re-indexing,
so a Celery worker on the ``documents`` queue must be running for search to
catch up.

Usage:
    cd backend
    uv run python -m scripts.repair_ocr_envelopes --dry-run
    uv run python -m scripts.repair_ocr_envelopes [--limit N]
"""

import argparse
import logging

from app.services.ocr_envelope_repair import repair_all
from app.tasks import get_sync_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def main(dry_run: bool, limit: int | None) -> None:
    rows = repair_all(get_sync_db(), dry_run=dry_run, limit=limit)
    for row in rows:
        logger.info(
            "  %-12s %s  %s  envelopes=%s chars %s -> %s  kb_sources=%s",
            row["status"], row["uuid"], row.get("title"), row.get("envelopes", "-"),
            row.get("chars_before", "-"), row.get("chars_after", "-"),
            row.get("kb_sources_queued", "-"),
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    logger.info("%s: %s", "Dry run" if dry_run else "Done", counts or "nothing to repair")
    if counts.get("undecodable") or counts.get("empty"):
        logger.info("Undecodable/empty documents need Retry extraction in Files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="List affected documents without changing them")
    parser.add_argument("--limit", type=int, default=None, help="Repair at most N documents")
    args = parser.parse_args()
    main(args.dry_run, args.limit)
