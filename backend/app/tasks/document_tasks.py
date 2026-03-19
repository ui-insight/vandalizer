"""Celery tasks for document extraction, update, cleanup, and semantic ingestion.

Ported from Flask app/utilities/document_manager.py.
Uses pymongo (sync) for DB access — same pattern as workflow_tasks.py.
"""

import logging
import os
import re
from pathlib import Path

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)


def _get_db():
    """Get sync pymongo database handle."""
    from pymongo import MongoClient

    from app.config import Settings
    settings = Settings()
    client = MongoClient(settings.mongo_host)
    return client[settings.mongo_db]


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
        extract_text_from_file,
        remove_images_from_markdown,
    )

    db = _get_db()
    doc = db.smart_document.find_one({"uuid": document_uuid})
    if not doc:
        logger.warning("Document %s not found", document_uuid)
        return ""

    upload_dir = os.environ.get("UPLOAD_DIR", "../app/static/uploads")
    doc_path = os.path.join(upload_dir, doc.get("path", ""))
    absolute_path = Path(doc_path)

    extension = (extension or "").lower().lstrip(".")

    try:
        db.smart_document.update_one(
            {"uuid": document_uuid},
            {"$set": {"processing": True, "task_status": "extracting"}},
        )

        raw_text = ""

        if extension in ("xlsx", "xls"):
            raw_text = convert_to_markdown(str(absolute_path))

        elif extension in ("docx", "doc"):
            try:
                import pypandoc

                raw_text = pypandoc.convert_file(str(absolute_path), "markdown")
                raw_text = remove_images_from_markdown(raw_text)
            except Exception:
                raw_text = convert_to_markdown(str(absolute_path), keep_data_uris=False)

        else:
            raw_text = extract_text_from_file(str(absolute_path), extension)

        # Count tokens (rough estimate: ~4 chars per token)
        token_count = len(raw_text) // 4 if raw_text else 0

        db.smart_document.update_one(
            {"uuid": document_uuid},
            {
                "$set": {
                    "raw_text": raw_text,
                    "processing": False,
                    "token_count": token_count,
                }
            },
        )

        return raw_text

    except Exception as e:
        logger.error("Error extracting text from document %s: %s", document_uuid, e)
        db.smart_document.update_one(
            {"uuid": document_uuid},
            {"$set": {"raw_text": "", "processing": False}},
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
    """Mark document extraction as complete, then check folder watch automations."""
    db = _get_db()
    result = db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": {"task_id": None, "task_status": "complete"}},
    )
    if result.matched_count == 0:
        logger.warning("Document %s not found for update", document_uuid)
        return

    # Check for folder watch automations targeting this document's folder
    try:
        _check_folder_watch_automations(db, document_uuid)
    except Exception as e:
        logger.error("Error checking folder watch automations for %s: %s", document_uuid, e)


def _check_folder_watch_automations(db, document_uuid: str) -> None:
    """Check if any folder watch automations match this document's folder."""
    from datetime import datetime, timezone
    from uuid import uuid4
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

    now = datetime.now(timezone.utc)

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
            # Create a WorkflowTriggerEvent and queue execution
            event = {
                "uuid": uuid4().hex,
                "workflow": ObjectId(action_id),
                "trigger_type": "folder_watch",
                "status": "queued",
                "documents": [doc["_id"]],
                "document_count": 1,
                "trigger_context": {
                    "folder_id": folder_uuid,
                    "automation_id": str(auto["_id"]),
                    "automation_name": auto.get("name", ""),
                },
                "created_at": now,
                "process_after": now,
                "queued_at": now,
                "attempt_number": 1,
                "max_attempts": 3,
                "output_delivery": {
                    "storage_status": None,
                    "notifications_sent": [],
                    "webhooks_called": [],
                    "chains_triggered": [],
                },
            }
            result = db.workflow_trigger_event.insert_one(event)
            logger.info(
                "Created folder watch trigger %s for automation '%s' (workflow %s)",
                result.inserted_id, auto.get("name"), action_id,
            )

            from app.tasks.passive_tasks import execute_workflow_passive
            execute_workflow_passive.delay(str(result.inserted_id))

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

        # Load search set config
        ss_doc = db.search_set.find_one({"uuid": search_set_uuid})
        extraction_config = (ss_doc or {}).get("extraction_config") or {}

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
    from datetime import datetime, timezone

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
    """Error handler — mark document as errored with details."""
    db = _get_db()
    result = db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": {
            "task_id": None,
            "task_status": "error",
            "processing": False,
            "error_message": "Document extraction failed. Please try re-uploading.",
        }},
    )
    if result.matched_count == 0:
        logger.warning("Document %s not found for cleanup", document_uuid)


@celery_app.task(
    bind=True,
    name="tasks.document.semantic_ingestion",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=5,
)
def perform_semantic_ingestion(self, raw_text: str, document_uuid: str, user_id: str) -> str:
    """Chunk text and embed into ChromaDB for RAG search."""
    import os

    from app.services.document_manager import DocumentManager

    db = _get_db()
    doc = db.smart_document.find_one({"uuid": document_uuid})
    if not doc:
        logger.warning("Document %s not found for semantic ingestion", document_uuid)
        return ""

    db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": {"task_status": "readying"}},
    )

    persist_dir = os.environ.get("CHROMADB_PERSIST_DIR", "../app/static/db")
    dm = DocumentManager(persist_directory=persist_dir)
    dm.add_document(
        user_id=user_id,
        document_name=doc.get("title", ""),
        document_id=document_uuid,
        doc_path=doc.get("path", ""),
        raw_text=raw_text,
    )

    db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": {"task_status": "complete"}},
    )

    return document_uuid
