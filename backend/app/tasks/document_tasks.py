"""Celery tasks for document extraction, update, cleanup, and semantic ingestion.

Ported from Flask app/utilities/document_manager.py.
Uses pymongo (sync) for DB access — same pattern as workflow_tasks.py.
"""

import datetime
import logging
import os
import re
import uuid
from pathlib import Path

from app.celery_app import celery_app
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


def _ingest_into_project_kb(db, dm, doc: dict, text: str) -> None:
    """Best-effort: add a freshly-ingested document to its Project's implicit KB.

    Walks the document's folder ancestry to find the owning project, then mirrors
    the chunks into the project's KB collection (the same path KBs use) so
    "chat with this project" sees the file. Sync — runs inside the Celery task.
    """
    project = _find_project_for_folder(db, doc.get("folder"))
    if not project or not project.get("kb_uuid"):
        return

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
                    _ingest_into_project_kb(db, dm, doc, text)
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


def _remove_images_from_markdown(markdown_text: str) -> str:
    """Remove all image references from markdown text."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", "", markdown_text)
    text = re.sub(r"!\[([^\]]*)\]\[[^\]]*\]", "", text)
    text = re.sub(r'\{[^}]*(?:width|height)\s*=\s*"[^"]*"[^}]*\}', "", text)
    text = re.sub(r'\{[^{}]*="[^"]*"[^{}]*\}', "", text)
    text = re.sub(r"^\s*\[[^\]]+\]:\s*[^\s]+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)
    text = re.sub(r"^\s+$", "", text, flags=re.MULTILINE)
    return text.strip()


@celery_app.task(
    bind=True,
    name="tasks.document.extraction",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=5,
)
def perform_extraction_and_update(self, document_uuid: str, extension: str) -> str:
    """Extract text from a document file (PDF, DOCX, XLSX, etc.).

    Updates SmartDocument.raw_text and processing flags.
    """
    from app.services.document_readers import (
        convert_to_markdown,
        extract_docx_extras,
        extract_text_from_file,
        remove_images_from_markdown,
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

        if extension == "xlsx":
            from app.services.document_readers import extract_text_with_markers
            raw_text, text_markers = extract_text_with_markers(str(absolute_path), extension)

        elif extension == "xls":
            raw_text = convert_to_markdown(str(absolute_path))

        elif extension in ("docx", "doc"):
            try:
                import pypandoc

                raw_text = pypandoc.convert_file(str(absolute_path), "markdown")
                raw_text = remove_images_from_markdown(raw_text)
            except Exception:
                raw_text = convert_to_markdown(str(absolute_path), keep_data_uris=False)

            if extension == "docx":
                extras = extract_docx_extras(str(absolute_path))
                if extras:
                    raw_text = (raw_text or "").rstrip() + "\n\n" + extras

        elif extension == "pdf":
            from app.services.document_readers import extract_text_with_markers
            raw_text, text_markers = extract_text_with_markers(str(absolute_path), extension)

        else:
            raw_text = extract_text_from_file(str(absolute_path), extension)

        # Count tokens using the same tokenizer the budget planner uses so the
        # pre-flight oversize check is accurate.
        from app.services.context_budget import count_tokens
        token_count = count_tokens(raw_text) if raw_text else 0

        # An "extracted successfully but got zero text" outcome is almost always
        # a silent OCR/extraction failure (image-only PDF, OCR endpoint down,
        # encrypted file). Mark it as error so the UI can surface it and offer
        # a retry, rather than presenting an empty document.
        if not raw_text or not raw_text.strip():
            logger.warning(
                "Document %s produced empty extracted text (ext=%s) — marking as error",
                document_uuid, extension,
            )
            db.smart_document.update_one(
                {"uuid": document_uuid},
                {
                    "$set": {
                        "raw_text": "",
                        "processing": False,
                        "token_count": 0,
                        "text_markers": [],
                        "task_status": "error",
                        "error_message": (
                            "We couldn't extract any text from this document. "
                            "It may be image-only, encrypted, or our OCR service "
                            "may be temporarily unavailable. Try retrying — if "
                            "it keeps failing, re-upload or contact support."
                        ),
                    }
                },
            )
            return ""

        db.smart_document.update_one(
            {"uuid": document_uuid},
            {
                "$set": {
                    "raw_text": raw_text,
                    "processing": False,
                    "token_count": token_count,
                    "text_markers": text_markers,
                    "error_message": None,
                }
            },
        )

        return raw_text

    except Exception as e:
        logger.exception("Error extracting text from document %s", document_uuid)
        db.smart_document.update_one(
            {"uuid": document_uuid},
            {
                "$set": {
                    "raw_text": "",
                    "processing": False,
                    "task_status": "error",
                    "error_message": f"Text extraction failed: {str(e)[:300]}",
                }
            },
        )
        return ""


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
        return

    db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": {"task_id": None, "task_status": "complete"}},
    )

    # Check for folder watch automations targeting this document's folder
    try:
        _check_folder_watch_automations(db, document_uuid)
    except Exception as e:
        logger.error("Error checking folder watch automations for %s: %s", document_uuid, e)


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

        # Check file type filters from trigger_config
        trigger_config = auto.get("trigger_config") or {}
        allowed_types = trigger_config.get("file_types", [])
        if allowed_types and doc.get("extension") not in allowed_types:
            logger.info(
                "Skipping automation %s: doc type '%s' not in %s",
                auto.get("name"), doc.get("extension"), allowed_types,
            )
            continue

        # Check exclude patterns
        exclude_patterns = trigger_config.get("exclude_patterns", "")
        if exclude_patterns:
            import fnmatch
            patterns = [p.strip() for p in exclude_patterns.split(",") if p.strip()]
            if any(fnmatch.fnmatch(doc.get("title", ""), pat) for pat in patterns):
                logger.info("Skipping automation %s: doc matches exclude pattern", auto.get("name"))
                continue

        if action_type == "workflow":
            # Create a pending WorkflowTriggerEvent — the beat task
            # (process_pending_triggers) will apply budget/throttle checks
            # and dispatch execution.
            workflow_doc = db.workflow.find_one({"_id": ObjectId(action_id)})
            if not workflow_doc:
                logger.warning("Workflow %s not found for automation '%s'", action_id, auto.get("name"))
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

    # 1. Storage
    storage_cfg = output_config.get("storage", {})
    if storage_cfg.get("enabled"):
        try:
            path = save_extraction_results_to_folder(results, automation, storage_cfg)
            logger.info("Extraction results saved to %s", path)
        except Exception as e:
            logger.error("Failed to save extraction results: %s", e)

    # 2. Notifications
    for notification in output_config.get("notifications", []):
        try:
            if should_send_notification(result_doc, notification):
                send_workflow_notification(result_doc, notification)
        except Exception as e:
            logger.error("Failed to send extraction notification: %s", e)

    # 3. Webhooks
    for webhook_cfg in output_config.get("webhooks", []):
        try:
            call_webhook(result_doc, webhook_cfg)
        except Exception as e:
            logger.error("Failed to call extraction webhook: %s", e)


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

    db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": {"task_status": "readying"}},
    )

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
        db.smart_document.update_one(
            {"uuid": document_uuid},
            {
                "$set": {
                    "task_status": "complete",
                    "chromadb_ready": False,
                    "chunk_count": 0,
                    "ingest_error": str(e)[:500],
                }
            },
        )
        raise

    db.smart_document.update_one(
        {"uuid": document_uuid},
        {
            "$set": {
                "task_status": "complete",
                "chromadb_ready": chunk_count > 0,
                "chunk_count": chunk_count,
                "ingest_error": None,
            }
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
