"""Celery tasks for document extraction, update, cleanup, and semantic ingestion.

Ported from Flask app/utilities/document_manager.py.
Uses pymongo (sync) for DB access — same pattern as workflow_tasks.py.
"""

import logging
import os
import re
from pathlib import Path

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_db():
    """Get sync pymongo database handle."""
    from pymongo import MongoClient

    mongo_host = os.environ.get("MONGO_HOST", "mongodb://localhost:27017/")
    mongo_db = os.environ.get("MONGO_DB", "osp")
    client = MongoClient(mongo_host)
    return client[mongo_db]


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
    name="tasks.document.extraction",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def perform_extraction_and_update(document_uuid: str, extension: str) -> str:
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
        # For PDFs that already have raw_text, just ensure processing is cleared
        if extension == "pdf" and doc.get("raw_text", "").strip():
            raw_text = doc["raw_text"]
            db.smart_document.update_one(
                {"uuid": document_uuid},
                {"$set": {"processing": False}},
            )
            return raw_text

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
    name="tasks.document.update",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def update_document_fields(document_uuid: str) -> None:
    """Mark document extraction as complete."""
    db = _get_db()
    result = db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": {"task_id": None, "task_status": "complete"}},
    )
    if result.matched_count == 0:
        logger.warning("Document %s not found for update", document_uuid)


@celery_app.task(
    name="tasks.document.cleanup",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def cleanup_document(document_uuid: str) -> None:
    """Error handler — mark document as errored."""
    db = _get_db()
    result = db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": {"task_id": None, "task_status": "error", "processing": False}},
    )
    if result.matched_count == 0:
        logger.warning("Document %s not found for cleanup", document_uuid)


@celery_app.task(
    name="tasks.document.semantic_ingestion",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def perform_semantic_ingestion(raw_text: str, document_uuid: str, user_id: str) -> str:
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
