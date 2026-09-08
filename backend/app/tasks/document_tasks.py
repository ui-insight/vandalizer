"""Celery tasks for document extraction, update, cleanup, and semantic ingestion.

Ported from Flask app/utilities/document_manager.py.
Uses pymongo (sync) for DB access — same pattern as workflow_tasks.py.
"""

import datetime
import logging
import os
import uuid
from pathlib import Path

from app.celery_app import celery_app
from app.services.document_readers import DocumentReadError
from app.services.ocr_client import OcrUnavailableError
from app.tasks import TRANSIENT_EXCEPTIONS, get_sync_db

logger = logging.getLogger(__name__)


def _find_project_for_folder(db, folder_uuid: str | None) -> dict | None:
    """Walk a folder's ancestry and return the Project that owns its root, if any."""
    if not folder_uuid or folder_uuid == "0":
        return None

    # Collect the folder plus every ancestor up to the root.
    ancestors: list[str] = []
    cursor = folder_uuid
    seen: set[str] = set()
    while cursor and cursor != "0" and cursor not in seen:
        seen.add(cursor)
        ancestors.append(cursor)
        folder = db.smart_folder.find_one({"uuid": cursor}, {"parent_id": 1})
        if not folder:
            break
        cursor = folder.get("parent_id")

    return db.project.find_one({"root_folder_uuid": {"$in": ancestors}})


def _ingest_into_project_kb(db, dm, doc: dict, text: str) -> bool:
    """Best-effort: add a freshly-ingested document to its Project's implicit KB.

    Walks the document's folder ancestry to find the owning project, then mirrors
    the chunks into the project's KB collection (the same path KBs use) so
    "chat with this project" sees the file. Sync — runs inside the Celery task.

    Returns True when the document is (or already was) in the project's KB,
    False when the mirror failed — a failure is logged and belled here, never
    raised, so callers only need the return value for honest counting.
    """
    project = _find_project_for_folder(db, doc.get("folder"))
    if not project or not project.get("kb_uuid"):
        return True

    try:
        _mirror_into_project_kb(db, dm, doc, project, text)
        return True
    except Exception as e:
        # Best-effort by design, but never silently: the user just watched
        # this file land in the project, and "chat with this project" cannot
        # see it. Callers keep their own guards (project RESOLUTION above can
        # still raise); the bell rides here so every entry point (fresh
        # ingest, file move, folder move) discloses. Returns False so the
        # folder-move task's synced count cannot report failed mirrors as
        # successes.
        logger.exception(
            "Failed to mirror %s into project %s KB", doc.get("uuid"), project.get("uuid"),
        )
        from app.services.failure_notifications import notify_project_kb_sync_failed

        notify_project_kb_sync_failed(db, doc=doc, project=project, error=e)
        return False


def _mirror_into_project_kb(db, dm, doc: dict, project: dict, text: str) -> None:
    kb_uuid = project["kb_uuid"]
    doc_uuid = doc["uuid"]
    # Dedupe — never add the same document to a project KB twice.
    if db.knowledge_base_sources.find_one(
        {"knowledge_base_uuid": kb_uuid, "document_uuid": doc_uuid}
    ):
        return

    chunk_count = dm.add_to_kb(
        kb_uuid=kb_uuid,
        source_id=doc_uuid,
        source_name=doc.get("title", ""),
        raw_text=text,
        text_markers=doc.get("text_markers") or [],
    )

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    db.knowledge_base_sources.insert_one({
        "uuid": uuid.uuid4().hex,
        "knowledge_base_uuid": kb_uuid,
        "source_type": "document",
        "document_uuid": doc_uuid,
        "url": None,
        "url_title": None,
        "custom_name": None,
        "content": None,
        "status": "ready",
        "error_message": None,
        "chunk_count": chunk_count,
        "crawl_enabled": False,
        "max_crawl_pages": 5,
        "parent_source_uuid": None,
        "crawled_urls": None,
        "created_at": now,
        "processed_at": now,
    })
    db.knowledge_bases.update_one(
        {"uuid": kb_uuid},
        {
            "$inc": {
                "total_sources": 1,
                "sources_ready": 1,
                "total_chunks": chunk_count,
            },
            "$set": {"status": "ready", "updated_at": now},
        },
    )
    logger.info(
        "Added document %s to project %s implicit KB (%d chunks)",
        doc_uuid, project.get("uuid"), chunk_count,
    )


def _remove_from_project_kb(db, dm, doc: dict, project: dict) -> None:
    """Best-effort: drop a document's chunks from a Project's implicit KB.

    Used when a document is moved out of (or to a different) project so the old
    project's chat stops surfacing it. Sync — runs inside the Celery task.
    """
    kb_uuid = project.get("kb_uuid")
    if not kb_uuid:
        return
    doc_uuid = doc["uuid"]
    src = db.knowledge_base_sources.find_one(
        {"knowledge_base_uuid": kb_uuid, "document_uuid": doc_uuid}
    )
    if not src:
        return

    dm.delete_kb_source(kb_uuid, doc_uuid)
    db.knowledge_base_sources.delete_one({"_id": src["_id"]})

    chunk_count = src.get("chunk_count") or 0
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    db.knowledge_bases.update_one(
        {"uuid": kb_uuid},
        {
            "$inc": {
                "total_sources": -1,
                "sources_ready": -1,
                "total_chunks": -chunk_count,
            },
            "$set": {"updated_at": now},
        },
    )
    logger.info(
        "Removed document %s from project %s implicit KB",
        doc_uuid, project.get("uuid"),
    )


@celery_app.task(bind=True, name="tasks.document.sync_project_kb")
def sync_project_kb_on_move(self, document_uuid: str, old_folder_uuid: str | None) -> str:
    """Re-sync a document's project-KB membership after it is moved between folders.

    Moving a file into a project's folder tree must add it to that project's
    implicit KB (otherwise "chat with this project" can't see it and answers from
    the model's own knowledge); moving it out must remove it. Best-effort — never
    raises into the move flow.
    """
    db = get_sync_db()
    doc = db.smart_document.find_one({"uuid": document_uuid})
    if not doc:
        return ""

    from app.config import Settings
    from app.services.document_manager import DocumentManager

    settings = Settings()
    dm = DocumentManager(persist_directory=settings.chromadb_persist_dir)

    new_project = _find_project_for_folder(db, doc.get("folder"))
    old_project = _find_project_for_folder(db, old_folder_uuid)

    # Remove from the old project's KB if the project changed.
    if old_project and (
        not new_project or old_project.get("uuid") != new_project.get("uuid")
    ):
        try:
            _remove_from_project_kb(db, dm, doc, old_project)
        except Exception:
            logger.exception(
                "Failed to remove %s from old project KB on move", document_uuid
            )

    # Add to the new project's KB. _ingest_into_project_kb dedupes, so a no-op
    # move (same project) is harmless. Requires extracted text — a doc still being
    # processed will be mirrored by perform_semantic_ingestion when it finishes.
    if new_project:
        text = doc.get("raw_text", "") or ""
        if text:
            try:
                _ingest_into_project_kb(db, dm, doc, text)
            except Exception:
                logger.exception(
                    "Failed to add %s to new project KB on move", document_uuid
                )

    return document_uuid


@celery_app.task(bind=True, name="tasks.document.sync_project_kb_folder")
def sync_project_kb_on_folder_move(self, folder_uuid: str, old_parent_id: str | None) -> int:
    """Re-sync project-KB membership for every document under a moved folder.

    Moving a folder subtree into/out of a project changes the owning project for
    all of its descendant documents at once. Mirror each one into the new
    project's implicit KB and drop it from the old one. Best-effort.
    """
    db = get_sync_db()

    new_project = _find_project_for_folder(db, folder_uuid)
    old_project = _find_project_for_folder(db, old_parent_id)
    new_uuid = new_project.get("uuid") if new_project else None
    old_uuid = old_project.get("uuid") if old_project else None
    if new_uuid == old_uuid:
        return 0  # subtree stayed within the same project (or no project either side)

    # Collect the moved folder plus every descendant folder.
    folder_uuids = [folder_uuid]
    frontier = [folder_uuid]
    while frontier:
        children = list(
            db.smart_folder.find({"parent_id": {"$in": frontier}}, {"uuid": 1})
        )
        frontier = [c["uuid"] for c in children]
        folder_uuids.extend(frontier)

    from app.config import Settings
    from app.services.document_manager import DocumentManager

    settings = Settings()
    dm = DocumentManager(persist_directory=settings.chromadb_persist_dir)

    synced = 0
    for doc in db.smart_document.find({"folder": {"$in": folder_uuids}}):
        if old_project:
            try:
                _remove_from_project_kb(db, dm, doc, old_project)
            except Exception:
                logger.exception(
                    "Failed to remove %s from old project KB on folder move",
                    doc.get("uuid"),
                )
        if new_project:
            text = doc.get("raw_text", "") or ""
            if text:
                try:
                    # Counted only on success: a Chroma outage mirroring zero
                    # of 40 documents must not log "re-synced 40".
                    if _ingest_into_project_kb(db, dm, doc, text):
                        synced += 1
                except Exception:
                    logger.exception(
                        "Failed to add %s to new project KB on folder move",
                        doc.get("uuid"),
                    )
    logger.info(
        "Folder move %s re-synced %d document(s) into project %s",
        folder_uuid, synced, new_uuid,
    )
    return synced


def _notify_document_processing_failed(db, document_uuid: str, message: str) -> None:
    """Tell the uploader their document never became readable.

    Both callers swallow the exception and return "" rather than re-raising, so
    the document simply sits in the file list with an error state nobody is told
    about — the bell is the only signal the uploader gets.
    """
    from app.services.failure_notifications import notify_document_failed

    doc = db.smart_document.find_one(
        {"uuid": document_uuid}, {"uuid": 1, "title": 1, "user_id": 1},
    )
    notify_document_failed(db, doc=doc, error=message)


# An OCR outage is measured in minutes — a GPU loading a model, a service
# restarting during a deploy, a provider rate-limiting a burst. The previous
# budget (backoff from 5s, 3 retries) was exhausted inside a minute and the
# document was written off as unreadable. This spans roughly 1/2/4/8/10
# minutes, about 25 minutes in total, with jitter so a batch upload doesn't
# retry in lockstep. Permanent failures never reach here — they degrade to
# PyMuPDF inside the reader (see ocr_client.PERMANENT_STATUS_CODES).
@celery_app.task(
    bind=True,
    name="tasks.document.extraction",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=60,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
    default_retry_delay=5,
)
def perform_extraction_and_update(self, document_uuid: str, extension: str) -> str:
    """Extract text from a document file (PDF, DOCX, XLSX, etc.).

    Updates SmartDocument.raw_text and processing flags.
    """
    from app.services.document_readers import (
        convert_to_markdown,
        extract_text_from_file,
    )

    db = get_sync_db()
    doc = db.smart_document.find_one({"uuid": document_uuid})
    if not doc:
        logger.warning("Document %s not found", document_uuid)
        return ""

    from app.config import Settings

    settings = Settings()
    doc_path = os.path.join(settings.upload_dir, doc.get("path", ""))
    absolute_path = Path(doc_path)

    extension = (extension or "").lower().lstrip(".")

    try:
        db.smart_document.update_one(
            {"uuid": document_uuid},
            {"$set": {"processing": True, "task_status": "extracting"}},
        )

        raw_text = ""
        text_markers: list[dict] = []
        # Only paginated formats get a page count. Marker count is not a
        # substitute: XLSX markers are sheets, and PyMuPDF emits no marker for
        # a page that has no text layer and no form fields.
        num_pages: int | None = None

        # Filled in by the PDF reader: what the returned text cannot say about
        # itself, notably that the OCR conversion was only partial.
        ocr_report: dict = {}

        if extension == "xlsx":
            from app.services.document_readers import extract_text_with_markers
            raw_text, text_markers = extract_text_with_markers(str(absolute_path), extension)

        elif extension == "xls":
            raw_text = convert_to_markdown(str(absolute_path))

        # docx/doc deliberately have no branch here: they fall through to
        # extract_text_from_file below, whose docx branch is the ONE assembly
        # site (read_docx_markdown + extras). A local copy of that assembly
        # is exactly how upload and chat-attachment text drifted apart before.

        elif extension == "pdf":
            from app.services.document_readers import (
                extract_text_with_markers,
                pdf_page_count,
            )
            raw_text, text_markers = extract_text_with_markers(
                str(absolute_path), extension, report=ocr_report,
            )
            # Read from the PDF rather than the markers so the count is exact on
            # both the OCR and the direct-extraction path. Returns 0 if the file
            # can't be opened, which is the same as the model default.
            num_pages = pdf_page_count(str(absolute_path))

        else:
            raw_text = extract_text_from_file(str(absolute_path), extension)

        # Stored raw, on purpose. The safety margin that makes a count safe to
        # budget against depends on the model doing the reading, which is not
        # known here and is not fixed for the life of the document — so
        # find_oversize_documents applies it per-model at comparison time.
        from app.services.context_budget import count_raw_tokens
        token_count = count_raw_tokens(raw_text) if raw_text else 0

        from app.utils.extraction_quality import is_sparse_extraction, nonletter_ratio
        extraction_ratio = nonletter_ratio(raw_text) if raw_text else None

        # Ways an extraction can succeed and still not be the whole document.
        # Both used to be invisible: the partial conversion was a log line in
        # the OCR client, and the density check did not exist at all, so a
        # 400-page package whose OCR produced 150 characters was stored as
        # complete and answered questions as if it were.
        ingestion_warnings: list[str] = []
        if ocr_report.get("partial"):
            ingestion_warnings.append("partial_ocr")
        if ocr_report.get("hidden_text_unchecked"):
            # The prompt-injection scrub could not inspect this PDF, so its
            # text may include content the page never displays. Stored as a
            # warning rather than failing the document: an inspection hiccup
            # on an honest PDF must stay usable, but never silently.
            ingestion_warnings.append("hidden_text_unchecked")
        if extension == "pdf" and raw_text and is_sparse_extraction(raw_text, num_pages):
            ingestion_warnings.append("sparse_text")
        if ingestion_warnings:
            logger.warning(
                "Document %s ingested with warnings %s (pages=%s, chars=%d)",
                document_uuid, ingestion_warnings, num_pages, len(raw_text or ""),
            )

        # An "extracted successfully but got zero text" outcome is almost always
        # a silent OCR/extraction failure (image-only PDF, OCR endpoint down,
        # encrypted file). Mark it as error so the UI can surface it and offer
        # a retry, rather than presenting an empty document.
        if not raw_text or not raw_text.strip():
            logger.warning(
                "Document %s produced empty extracted text (ext=%s) — marking as error",
                document_uuid, extension,
            )
            message = (
                "We couldn't extract any text from this document. "
                "It may be blank, image-only, or encrypted, or our "
                "OCR service may be temporarily unavailable. Try "
                "retrying — if it keeps failing, re-upload or "
                "contact support."
            )
            db.smart_document.update_one(
                {"uuid": document_uuid},
                {
                    "$set": {
                        "raw_text": "",
                        "processing": False,
                        "token_count": 0,
                        "text_markers": [],
                        "extraction_nonletter_ratio": None,
                        "ingestion_warnings": [],
                        # Don't leave a stale page count beside empty text when
                        # a previously-good document is reprocessed.
                        "num_pages": 0,
                        "task_status": "error",
                        "error_message": message,
                    }
                },
            )
            # Every other terminal-error branch notifies; this one silently
            # relied on the user noticing the row state — which the file list
            # didn't render either. Same coalesced bell as the rest.
            _notify_document_processing_failed(db, document_uuid, message)
            return ""

        update_fields: dict = {
            "raw_text": raw_text,
            "processing": False,
            "token_count": token_count,
            "text_markers": text_markers,
            "extraction_nonletter_ratio": extraction_ratio,
            "ingestion_warnings": ingestion_warnings,
            "error_message": None,
        }
        if num_pages is not None:
            update_fields["num_pages"] = num_pages

        db.smart_document.update_one(
            {"uuid": document_uuid},
            {"$set": update_fields},
        )

        return raw_text

    except FileNotFoundError as e:
        # The source file vanished between upload and extraction — a document
        # deleted or reset mid-processing (common in E2E teardown and retention
        # sweeps). There is nothing to extract and nothing to fix in code, so
        # record it on the doc but log at warning rather than paging Sentry.
        logger.warning(
            "Source file missing for document %s — skipping extraction: %s",
            document_uuid, e,
        )
        message = (
            "The uploaded file is no longer available "
            "(it may have been deleted during processing)."
        )
        db.smart_document.update_one(
            {"uuid": document_uuid},
            {
                "$set": {
                    "raw_text": "",
                    "processing": False,
                    "extraction_nonletter_ratio": None,
                    "ingestion_warnings": [],
                    "task_status": "error",
                    "error_message": message,
                }
            },
        )
        _notify_document_processing_failed(db, document_uuid, message)
        return ""

    except OcrUnavailableError as e:
        # Must be re-raised, not recorded: the catch-all below would swallow it
        # before `autoretry_for` ever saw it, which is the exact shape of the
        # original defect — an outage written off as an unreadable document.
        if self.request.retries < self.max_retries:
            logger.warning(
                "OCR unavailable for document %s (attempt %d/%d) — retrying: %s",
                document_uuid, self.request.retries + 1, self.max_retries, e,
            )
            raise
        # Out of retries. Say *why* it failed — "we couldn't reach OCR" is a
        # different instruction to the user than "this file has no text in it".
        logger.warning(
            "OCR still unavailable for document %s after %d attempts",
            document_uuid, self.max_retries,
        )
        message = (
            "We couldn't reach the text-recognition service for this document, "
            "and kept trying for several minutes. The file itself looks fine — "
            "retry once the service is back, or contact your administrator if "
            "it keeps happening."
        )
        db.smart_document.update_one(
            {"uuid": document_uuid},
            {
                "$set": {
                    "raw_text": "",
                    "processing": False,
                    "extraction_nonletter_ratio": None,
                    "ingestion_warnings": [],
                    "task_status": "error",
                    "error_message": message,
                }
            },
        )
        _notify_document_processing_failed(db, document_uuid, message)
        return ""

    except DocumentReadError as e:
        # Expected, user-actionable refusal (a binary upload, an unreadable
        # file) — the same error-state writes as the generic handler below,
        # but logged at warning without a traceback: a user dragging a folder
        # of .zip/.exe files into the uploader must not page Sentry once per
        # file, the way FileNotFoundError and OCR outages already don't.
        logger.warning("Document %s is not readable text: %s", document_uuid, e)
        message = str(e)
        db.smart_document.update_one(
            {"uuid": document_uuid},
            {
                "$set": {
                    "raw_text": "",
                    "processing": False,
                    "extraction_nonletter_ratio": None,
                    "ingestion_warnings": [],
                    "task_status": "error",
                    "error_message": message,
                }
            },
        )
        _notify_document_processing_failed(db, document_uuid, message)
        return ""

    except Exception as e:
        logger.exception("Error extracting text from document %s", document_uuid)
        message = f"Text extraction failed: {str(e)[:300]}"
        db.smart_document.update_one(
            {"uuid": document_uuid},
            {
                "$set": {
                    "raw_text": "",
                    "processing": False,
                    "extraction_nonletter_ratio": None,
                    "ingestion_warnings": [],
                    "task_status": "error",
                    "error_message": message,
                }
            },
        )
        _notify_document_processing_failed(db, document_uuid, message)
        return ""


def advance_task_status(db, document_uuid: str, status: str) -> bool:
    """Move a document to ``status`` unless extraction already marked it failed.

    Applies to *every* post-extraction status write, not just the terminal
    "complete" one. An intermediate marker is just as destructive: setting
    "readying" on a document that already failed erases the error, and then the
    very next write legitimately advances the now-unmarked document to
    "complete". That is how a zero-character document ends up carrying an
    extraction error message and a green checkmark at the same time.

    The exclusion lives in the query filter, not in a preceding read. These
    tasks run concurrently on separate queues — extraction on `documents`,
    compliance on `uploads` — so a read-then-write check can be overtaken
    between the read and the update.

    Note this is deliberately one-way: it never *clears* an error. Re-running
    extraction is what resets a failed document, via the "extracting" write at
    the top of `perform_extraction_and_update`, so a retry still works.

    Returns True when the document was advanced.
    """
    result = db.smart_document.update_one(
        {"uuid": document_uuid, "task_status": {"$ne": "error"}},
        {"$set": {"task_status": status}},
    )
    if not result.matched_count:
        logger.info(
            "Leaving document %s in its failed state rather than setting %r",
            document_uuid, status,
        )
    return bool(result.matched_count)


def mark_complete_unless_errored(db, document_uuid: str) -> bool:
    """Advance a document to "complete" unless extraction already failed."""
    return advance_task_status(db, document_uuid, "complete")


def _record_ingestion_result(db, document_uuid: str, fields: dict) -> None:
    """Persist ingestion bookkeeping, then advance the status if it's allowed.

    Two writes on purpose. Chunk counts and readiness flags are true whatever
    extraction did, so they are always recorded; only the status transition is
    conditional. Folding them into one guarded write would silently drop the
    bookkeeping for documents that failed extraction.
    """
    db.smart_document.update_one({"uuid": document_uuid}, {"$set": fields})
    mark_complete_unless_errored(db, document_uuid)


@celery_app.task(
    bind=True,
    name="tasks.document.update",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=5,
)
def update_document_fields(self, document_uuid: str) -> None:
    """Mark document extraction as complete, then check folder watch automations.

    Skips the complete status if extraction already flagged the doc as errored —
    we don't want to mask a silent OCR failure with a green checkmark.
    """
    db = get_sync_db()
    doc = db.smart_document.find_one({"uuid": document_uuid}, {"task_status": 1})
    if not doc:
        logger.warning("Document %s not found for update", document_uuid)
        return

    if doc.get("task_status") == "error":
        db.smart_document.update_one(
            {"uuid": document_uuid},
            {"$set": {"task_id": None}},
        )
        _resume_pending_kb_sources(db, document_uuid, extraction_failed=True)
        return

    db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": {"task_id": None, "task_status": "complete"}},
    )

    # Now that raw_text is populated, ingest any KB sources that were added
    # before extraction finished and parked in "pending" (see
    # knowledge_service._ingest_document_source).
    _resume_pending_kb_sources(db, document_uuid, extraction_failed=False)

    # Check for folder watch automations targeting this document's folder
    try:
        _check_folder_watch_automations(db, document_uuid)
    except Exception as e:
        logger.error("Error checking folder watch automations for %s: %s", document_uuid, e)


def _resume_pending_kb_sources(db, document_uuid: str, extraction_failed: bool) -> None:
    """Settle KB document-sources that were waiting on this document's extraction.

    A KB source added before its document finished extracting is parked in
    "pending" by ``_ingest_document_source``. When extraction completes we
    re-ingest those sources; when it fails we mark them errored so they don't
    spin forever. No-op when nothing is waiting.
    """
    pending = list(
        db.knowledge_base_sources.find(
            {
                "document_uuid": document_uuid,
                "source_type": "document",
                "status": "pending",
            },
            {"uuid": 1, "knowledge_base_uuid": 1},
        )
    )
    if not pending:
        return

    if extraction_failed:
        from app.tasks.knowledge_base_tasks import _recalculate_kb

        doc = db.smart_document.find_one({"uuid": document_uuid}, {"error_message": 1})
        message = (doc or {}).get("error_message") or "Document has no extractable text"
        affected_kbs = set()
        for src in pending:
            db.knowledge_base_sources.update_one(
                {"uuid": src["uuid"]},
                {"$set": {"status": "error", "error_message": message}},
            )
            affected_kbs.add(src["knowledge_base_uuid"])
        for kb_uuid in affected_kbs:
            _recalculate_kb(db, kb_uuid)
        return

    for src in pending:
        celery_app.send_task(
            "tasks.documents.kb_ingest_document",
            args=[src["uuid"]],
            queue="documents",
        )


def _check_folder_watch_automations(db, document_uuid: str) -> None:
    """Check if any folder watch automations match this document's folder."""
    from bson import ObjectId

    doc = db.smart_document.find_one({"uuid": document_uuid})
    if not doc or not doc.get("folder") or doc["folder"] == "0":
        return

    folder_uuid = doc["folder"]

    # Find enabled automations watching this folder
    automations = list(db.automation.find({
        "enabled": True,
        "trigger_type": "folder_watch",
        "trigger_config.folder_id": folder_uuid,
    }))

    if not automations:
        return

    for auto in automations:
        action_type = auto.get("action_type")
        action_id = auto.get("action_id")
        if not action_id:
            continue

        # Filters run inside their own per-automation guard: a malformed
        # trigger_config (e.g. exclude_patterns stored as a list) used to
        # raise BEFORE the dispatch try below, aborting every remaining
        # automation for this document via the caller's silent catch-all.
        try:
            trigger_config = auto.get("trigger_config") or {}
            allowed_types = trigger_config.get("file_types", [])
            if allowed_types and doc.get("extension") not in allowed_types:
                logger.info(
                    "Skipping automation %s: doc type '%s' not in %s",
                    auto.get("name"), doc.get("extension"), allowed_types,
                )
                continue

            exclude_patterns = trigger_config.get("exclude_patterns", "")
            if isinstance(exclude_patterns, list):
                # Tolerated elsewhere (automation_run_now); normalize here too.
                exclude_patterns = ",".join(str(p) for p in exclude_patterns)
            if exclude_patterns:
                import fnmatch
                patterns = [p.strip() for p in exclude_patterns.split(",") if p.strip()]
                if any(fnmatch.fnmatch(doc.get("title", ""), pat) for pat in patterns):
                    logger.info("Skipping automation %s: doc matches exclude pattern", auto.get("name"))
                    continue
        except Exception as e:
            logger.error("Automation '%s' has a malformed trigger_config: %s", auto.get("name"), e)
            from app.services.failure_notifications import notify_automation_failed

            notify_automation_failed(
                db, automation=auto, error=e,
                detail="This automation's trigger configuration is malformed and it was skipped.",
            )
            continue

        if action_type == "workflow":
            # Create a pending WorkflowTriggerEvent — the beat task
            # (process_pending_triggers) will apply budget/throttle checks
            # and dispatch execution. Isolated per automation and belled on
            # failure, like the extraction branch below: one broken
            # automation used to abort this loop for its siblings and vanish
            # into the caller's catch-all — silent forever.
            try:
                workflow_doc = db.workflow.find_one({"_id": ObjectId(action_id)})
                if not workflow_doc:
                    # The workflow this automation runs was deleted; without a
                    # bell the automation shows enabled forever and never fires.
                    logger.warning("Workflow %s not found for automation '%s'", action_id, auto.get("name"))
                    from app.services.failure_notifications import notify_automation_failed

                    notify_automation_failed(
                        db, automation=auto,
                        error="the workflow this automation runs no longer exists",
                        detail="Disable the automation, or point it at an existing workflow.",
                    )
                    continue

                from app.services.passive_triggers import create_folder_watch_trigger
                event = create_folder_watch_trigger(
                    workflow_doc,
                    doc,
                    automation_id=str(auto["_id"]),
                    automation_name=auto.get("name", ""),
                )
                logger.info(
                    "Created folder watch trigger %s for automation '%s' (workflow %s)",
                    event["_id"], auto.get("name"), action_id,
                )
            except Exception as e:
                logger.error("Workflow automation '%s' failed to dispatch: %s", auto.get("name"), e)
                from app.services.failure_notifications import notify_automation_failed

                notify_automation_failed(
                    db,
                    automation=auto,
                    error=e,
                    detail=f'Could not start the workflow for "{doc.get("title") or "a document"}".',
                )

        elif action_type == "extraction":
            # Run extraction inline (sync) since we're in a Celery worker
            logger.info(
                "Triggering extraction for automation '%s' (search set %s) on doc %s",
                auto.get("name"), action_id, document_uuid,
            )
            try:
                _run_automation_extraction(db, auto, action_id, doc)
            except Exception as e:
                logger.error("Extraction automation '%s' failed: %s", auto.get("name"), e)
                from app.services.failure_notifications import notify_automation_failed

                notify_automation_failed(
                    db,
                    automation=auto,
                    error=e,
                    detail=f'Extraction on "{doc.get("title") or "a document"}" failed.',
                )

        else:
            logger.info("Skipping automation %s: unsupported action_type '%s'", auto.get("name"), action_type)


def _run_automation_extraction(db, automation: dict, search_set_uuid: str, doc: dict) -> None:
    """Run an extraction search set against a document (sync, for Celery workers)."""
    from datetime import datetime, timezone

    from app.services.extraction_engine import ExtractionEngine

    # Mark automation as running
    now = datetime.now(timezone.utc)
    db.automation.update_one(
        {"_id": automation["_id"]},
        {"$set": {"_running": True, "_running_since": now}},
    )

    try:
        # Get extraction keys from search set items
        ss_items = list(db.search_set_item.find({
            "searchset": search_set_uuid,
            "searchtype": "extraction",
        }))
        keys = [item["searchphrase"] for item in ss_items]
        if not keys:
            logger.warning("No extraction keys found for search set %s", search_set_uuid)
            return

        doc_text = doc.get("raw_text", "")
        if not doc_text:
            logger.warning("Document %s has no raw_text, skipping extraction", doc.get("uuid"))
            return

        # Resolve model
        sys_config = db.system_config.find_one() or {}
        models = sys_config.get("available_models", [])
        model = models[0]["name"] if models else "gpt-4o-mini"

        # Load search set config (honors optimizer override if set)
        from app.services.search_set_service import effective_extraction_config
        ss_doc = db.search_set.find_one({"uuid": search_set_uuid})
        extraction_config = effective_extraction_config(ss_doc)

        # Load field metadata
        field_metadata = {}
        for item in ss_items:
            meta = {}
            if item.get("enum_values"):
                meta["enum_values"] = item["enum_values"]
            if item.get("optional"):
                meta["optional"] = True
            if meta:
                field_metadata[item["searchphrase"]] = meta

        engine = ExtractionEngine(system_config_doc=sys_config)
        results = engine.extract(
            extract_keys=keys,
            model=model,
            doc_texts=[doc_text],
            extraction_config_override=extraction_config or None,
            field_metadata=field_metadata,
        )

        # Save results to the document's extraction_results
        db.smart_document.update_one(
            {"_id": doc["_id"]},
            {"$set": {
                f"extraction_results.{search_set_uuid}": results,
            }},
        )

        logger.info(
            "Extraction automation '%s' completed: %d keys extracted for doc %s",
            automation.get("name"), len(keys), doc.get("uuid"),
        )

        # Process output_config (storage, notifications, webhooks)
        _process_extraction_outputs(db, automation, results)

    finally:
        # Clear running flag
        db.automation.update_one(
            {"_id": automation["_id"]},
            {"$unset": {"_running": "", "_running_since": ""}},
        )


def _process_extraction_outputs(db, automation: dict, results: dict) -> None:
    """Process output_config for an extraction automation."""

    from app.services.output_handlers import (
        call_webhook,
        save_extraction_results_to_folder,
        send_workflow_notification,
        should_send_notification,
    )

    output_config = automation.get("output_config") or {}
    if not output_config:
        return

    # Build a result-like dict for notification/webhook handlers
    result_doc = {
        "status": "completed",
        "trigger_type": automation.get("trigger_type", "folder_watch"),
        "final_output": {"output": results},
    }

    # Each output is attempted independently (one failed webhook must not
    # block storage), but failures are COLLECTED, not swallowed: the
    # automation used to report success with its deliverables never leaving
    # the building (#810).
    delivery_failures: list[str] = []

    # 1. Storage
    storage_cfg = output_config.get("storage", {})
    if storage_cfg.get("enabled"):
        try:
            path = save_extraction_results_to_folder(results, automation, storage_cfg)
            logger.info("Extraction results saved to %s", path)
        except Exception as e:
            logger.error("Failed to save extraction results: %s", e)
            delivery_failures.append(f"library save failed: {str(e)[:200]}")

    # 2. Notifications
    for notification in output_config.get("notifications", []):
        try:
            if should_send_notification(result_doc, notification):
                send_workflow_notification(result_doc, notification)
        except Exception as e:
            logger.error("Failed to send extraction notification: %s", e)
            delivery_failures.append(
                f"notification ({notification.get('channel') or 'configured'}) failed: {str(e)[:200]}"
            )

    # 3. Webhooks
    for webhook_cfg in output_config.get("webhooks", []):
        try:
            call_webhook(result_doc, webhook_cfg)
        except Exception as e:
            logger.error("Failed to call extraction webhook: %s", e)
            delivery_failures.append(
                f"webhook ({webhook_cfg.get('url') or 'configured'}) failed: {str(e)[:200]}"
            )

    if delivery_failures:
        # delivery_failed, not automation_failed: the extraction RAN and its
        # results exist — and coalescing onto the automation_failed key would
        # overwrite an unread genuine dispatch failure's detail.
        from app.services.failure_notifications import notify_delivery_failed

        notify_delivery_failed(
            db,
            automation=automation,
            detail=(
                "The extraction ran, but "
                f"{len(delivery_failures)} configured output(s) failed to "
                "deliver: " + "; ".join(delivery_failures)
            ),
        )


@celery_app.task(
    bind=True,
    name="tasks.document.cleanup",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=5,
)
def cleanup_document(self, document_uuid: str) -> None:
    """Error handler — mark document as errored with details.

    If the extraction task already wrote a specific error_message before raising,
    keep it (it's more diagnostic than the generic fallback below).
    """
    db = get_sync_db()
    existing = db.smart_document.find_one(
        {"uuid": document_uuid}, {"error_message": 1}
    )
    if not existing:
        logger.warning("Document %s not found for cleanup", document_uuid)
        return

    update_fields = {
        "task_id": None,
        "task_status": "error",
        "processing": False,
    }
    if not existing.get("error_message"):
        update_fields["error_message"] = (
            "Document extraction failed. Please retry or re-upload."
        )

    db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": update_fields},
    )


@celery_app.task(
    bind=True,
    name="tasks.document.semantic_ingestion",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=5,
)
def perform_semantic_ingestion(self, raw_text: str, document_uuid: str, user_id: str) -> str:
    """Chunk text and embed into ChromaDB for RAG search.

    Writes back ``chromadb_ready`` / ``chunk_count`` / ``ingest_error`` so the
    frontend can show a meaningful retrieval state on the document.
    """

    from app.services.document_manager import DocumentManager

    db = get_sync_db()
    doc = db.smart_document.find_one({"uuid": document_uuid})
    if not doc:
        logger.warning("Document %s not found for semantic ingestion", document_uuid)
        return ""

    # Guarded: a document whose extraction just failed must not be dragged back
    # into an in-progress state, because that erases the error and lets the
    # terminal write below mark it complete.
    advance_task_status(db, document_uuid, "readying")

    # If the caller passed empty raw_text, fall back to whatever the
    # extraction task already wrote to the DB.
    text = raw_text or doc.get("raw_text", "") or ""
    markers = doc.get("text_markers") or []

    from app.config import Settings

    settings = Settings()
    try:
        dm = DocumentManager(persist_directory=settings.chromadb_persist_dir)
        chunk_count = dm.add_document(
            user_id=user_id,
            document_name=doc.get("title", ""),
            document_id=document_uuid,
            doc_path=doc.get("path", ""),
            raw_text=text,
            text_markers=markers,
        )
    except Exception as e:
        logger.exception("Semantic ingestion failed for %s", document_uuid)
        _record_ingestion_result(
            db,
            document_uuid,
            {
                "chromadb_ready": False,
                "chunk_count": 0,
                "ingest_error": str(e)[:500],
            },
        )
        # The amber icon on the file row was the only signal; the owner of a
        # 50-file upload never sees row 37's icon. Bell once retries are
        # exhausted — the document is saved, but search/chat cannot see it.
        from app.services.failure_notifications import (
            is_final_attempt,
            notify_document_not_searchable,
        )

        if is_final_attempt(self, e):
            notify_document_not_searchable(db, doc=doc, error=e)
        raise

    _record_ingestion_result(
        db,
        document_uuid,
        {
            "chromadb_ready": chunk_count > 0,
            "chunk_count": chunk_count,
            "ingest_error": None,
        },
    )

    # If this document lives in a Project, mirror it into the project's implicit
    # KB. Best-effort: a failure here must not fail document ingestion.
    if chunk_count > 0:
        try:
            _ingest_into_project_kb(db, dm, doc, text)
        except Exception:
            logger.exception(
                "Project KB ingestion failed for %s", document_uuid
            )

    return document_uuid


# In-progress task_status values. A doc with one of these stages but
# processing=False has finished extraction without the chain advancing it —
# usually because a caller dispatched extraction without chaining update.
_IN_PROGRESS_TASK_STATUSES = ["layout", "extracting", "ocr", "security", "readying"]


@celery_app.task(bind=True, name="tasks.document.reap_stuck")
def reap_stuck_documents(self) -> None:
    """Self-heal documents whose task_status is stuck in an in-progress stage.

    Failure mode this handles: extraction finished (processing=False, raw_text
    populated) but task_status never advanced to "complete" because the caller
    dispatched the extraction task without chaining update_document_fields.
    The frontend then shows these docs as "Reading text…" indefinitely.

    Acts as a backstop against pipeline-chaining bugs; the fix in the caller
    is still preferred.
    """
    db = get_sync_db()

    orphans = list(db.smart_document.find(
        {
            "processing": False,
            "task_status": {"$in": _IN_PROGRESS_TASK_STATUSES},
            "soft_deleted": {"$ne": True},
            "raw_text": {"$ne": ""},
        },
        {"uuid": 1},
    ))

    if not orphans:
        return

    for doc in orphans:
        update_document_fields.delay(doc["uuid"])

    logger.info("Reaped %d stuck document(s) — dispatched update step", len(orphans))
