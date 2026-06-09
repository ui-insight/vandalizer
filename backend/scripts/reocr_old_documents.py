"""Re-OCR (re-extract text from) SmartDocuments older than N days.

Dispatches the existing `tasks.document.extraction` Celery task for each
matching document. For PDFs this routes through the UIPDF OCR endpoint
(see app/services/document_readers.py:ocr_extract_text_from_pdf); other
extensions just re-run their normal text extraction.

Usage:
    cd backend
    python -m scripts.reocr_old_documents [--days 30] [--dry-run] [--limit N] [--all-types]

    # Preview what would be re-processed (default: PDFs older than 30 days)
    python -m scripts.reocr_old_documents --dry-run

    # Actually dispatch
    python -m scripts.reocr_old_documents

    # Wider net: every document type, not just PDFs
    python -m scripts.reocr_old_documents --all-types

    # Throttle: only the oldest 100
    python -m scripts.reocr_old_documents --limit 100
"""

import argparse
import asyncio
import datetime
import logging

from app.config import Settings
from app.database import init_db
from app.models.document import SmartDocument

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


async def main(days: int, dry_run: bool, limit: int | None, all_types: bool) -> None:
    settings = Settings()
    await init_db(settings)

    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    logger.info("Cutoff: %s (older than %d days)", cutoff.isoformat(), days)

    query = {
        "created_at": {"$lt": cutoff},
        "soft_deleted": {"$ne": True},
        "processing": {"$ne": True},
    }
    if not all_types:
        query["extension"] = {"$in": ["pdf", "PDF"]}

    cursor = SmartDocument.find(query).sort("+created_at")
    if limit:
        cursor = cursor.limit(limit)

    docs = await cursor.to_list()
    logger.info("Found %d candidate document(s)", len(docs))

    if dry_run:
        for doc in docs[:20]:
            logger.info("  [dry-run] %s  %s  %s  %s",
                        doc.uuid, doc.extension, doc.created_at.isoformat(), doc.title)
        if len(docs) > 20:
            logger.info("  ... and %d more", len(docs) - 20)
        logger.info("Dry run complete — no tasks dispatched.")
        return

    # Import here so dry-run doesn't require Celery broker connectivity.
    from app.tasks.upload_tasks import dispatch_upload_tasks

    dispatched = 0
    failed = 0
    for doc in docs:
        try:
            # Use the full pipeline (extraction | update, plus semantic
            # ingestion / classification / validation) — calling extraction
            # alone strands docs in task_status="extracting".
            dispatch_upload_tasks(
                document_uuid=doc.uuid,
                extension=doc.extension or "",
                document_path=doc.path,
                user_id=doc.user_id,
            )
            dispatched += 1
            if dispatched % 50 == 0:
                logger.info("  Dispatched %d/%d...", dispatched, len(docs))
        except Exception as e:
            failed += 1
            logger.error("  Failed to dispatch %s: %s", doc.uuid, e)

    logger.info("Done. Dispatched: %d, Failed: %d", dispatched, failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-OCR SmartDocuments older than N days")
    parser.add_argument("--days", type=int, default=30,
                        help="Re-OCR documents whose created_at is older than this many days (default: 30)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be re-processed without dispatching tasks")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap the number of documents dispatched (oldest first)")
    parser.add_argument("--all-types", action="store_true",
                        help="Re-process every extension, not just PDFs")
    args = parser.parse_args()
    asyncio.run(main(args.days, args.dry_run, args.limit, args.all_types))
