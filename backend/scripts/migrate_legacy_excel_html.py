"""Repair Excel documents the legacy Flask app converted to HTML.

The pre-FastAPI app converted every uploaded .xlsx/.xls to an HTML render
for viewing, then rewrote the document record in place: `extension="html"`
and `path=<user>/<uuid>.html`. Those records were never migrated, so today
they download as an unnamed binary blob instead of opening in the viewer,
and their text was never extracted by the modern pipeline (token_count=0).

The original workbook still sits on disk next to the render
(`<user>/<uuid>.xlsx`) — the legacy upload wrote it before converting.
This script repoints each record at the original file (verified by magic
bytes), restores the real extension, and re-runs the full upload pipeline
(extraction → update → semantic ingestion).

The stale `.html` render (and per-sheet `<uuid>-<Sheet>.html` files) are
left on disk; they are harmless and no record references them.

Usage:
    cd backend
    python -m scripts.migrate_legacy_excel_html --dry-run   # preview
    python -m scripts.migrate_legacy_excel_html             # apply
    python -m scripts.migrate_legacy_excel_html --limit 5   # throttle
"""

import argparse
import asyncio
import datetime
import logging
from pathlib import PurePosixPath

from app.config import Settings
from app.database import init_db
from app.models.document import SmartDocument
from app.services.storage import get_storage
from app.utils.file_validation import is_valid_file_content

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


async def _find_original(storage, html_path: str) -> tuple[str, str] | None:
    """Locate the original workbook next to the legacy HTML render.

    Returns (relative_path, extension) or None. The extension is decided by
    the file's magic bytes, not the title — a zip container is xlsx, an OLE2
    container is xls.
    """
    stem = PurePosixPath(html_path).with_suffix("")
    for ext in ("xlsx", "xls"):
        candidate = f"{stem}.{ext}"
        if not await storage.exists(candidate):
            continue
        data = await storage.read(candidate)
        if is_valid_file_content(data, ext):
            return candidate, ext
        logger.warning("  %s exists but is not a valid .%s — skipping it", candidate, ext)
    return None


async def main(dry_run: bool, limit: int | None) -> None:
    settings = Settings()
    await init_db(settings)
    storage = get_storage(settings)

    docs = await SmartDocument.find(
        {
            "extension": "html",
            "soft_deleted": {"$ne": True},
            "title": {"$regex": r"\.xlsx?$", "$options": "i"},
        }
    ).sort("+created_at").to_list()
    if limit:
        docs = docs[:limit]
    logger.info("Found %d legacy html-extension Excel document(s)", len(docs))

    if not dry_run:
        # Import here so dry-run doesn't require Celery broker connectivity.
        from app.tasks.upload_tasks import dispatch_upload_tasks

    repaired = 0
    missing = 0
    for doc in docs:
        original = await _find_original(storage, doc.downloadpath or doc.path)
        if original is None:
            missing += 1
            logger.warning("  MISSING original workbook: %s  %s (path=%s)",
                           doc.uuid, doc.title, doc.path)
            continue

        rel_path, ext = original
        if dry_run:
            logger.info("  [dry-run] %s  %s  ->  %s (.%s)", doc.uuid, doc.title, rel_path, ext)
            repaired += 1
            continue

        doc.path = rel_path
        doc.downloadpath = rel_path
        doc.extension = ext
        doc.updated_at = datetime.datetime.now()
        await doc.save()

        dispatch_upload_tasks(
            document_uuid=doc.uuid,
            extension=ext,
            document_path=rel_path,
            user_id=doc.user_id,
        )
        repaired += 1
        logger.info("  Repaired %s  %s (.%s, pipeline re-dispatched)", doc.uuid, doc.title, ext)

    logger.info("Done. Repaired: %d, missing original: %d%s",
                repaired, missing, " (dry run — nothing written)" if dry_run else "")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Repair Excel docs the legacy Flask app rewrote to extension=html"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be repaired without writing or dispatching")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap the number of documents repaired (oldest first)")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run, args.limit))
