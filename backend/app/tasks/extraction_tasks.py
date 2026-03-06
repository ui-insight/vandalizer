"""Celery tasks for extraction operations.

Ported from Flask app/utilities/extraction_tasks.py.
Uses pymongo (sync) for DB access.
"""

import datetime
import logging
import os
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_db():
    """Get sync pymongo database handle."""
    from pymongo import MongoClient

    mongo_host = os.environ.get("MONGO_HOST", "mongodb://localhost:27017/")
    mongo_db = os.environ.get("MONGO_DB", "osp")
    client = MongoClient(mongo_host)
    return client[mongo_db]


def normalize_results(results, expected_keys: list[str] | None = None) -> dict[str, Any]:
    """Normalize a list of dicts into a single dict of unique values (comma-joined)."""
    normalized: dict[str, Any] = {}

    if isinstance(results, dict):
        normalized = results.copy()
    elif isinstance(results, list):
        collected: dict[str, list] = defaultdict(list)
        seen: dict[str, set] = defaultdict(set)

        for item in results:
            if not isinstance(item, dict):
                continue
            for k, v in item.items():
                if v in (None, "", [], {}):
                    continue
                if v in seen[k]:
                    continue
                seen[k].add(v)
                collected[k].append(v)

        normalized = {
            k: vals[0] if len(vals) == 1 else ", ".join(map(str, vals))
            for k, vals in collected.items()
        }
    else:
        normalized = {}

    if expected_keys:
        for key in expected_keys:
            if key not in normalized:
                normalized[key] = None

    return normalized


def _build_extraction_ingestion_text(documents: list[dict], keys: list) -> str:
    """Format text for semantic recommender ingestion."""
    ingestion_text = "# Documents selected:"
    for doc in documents:
        ingestion_text += f"\n- {doc.get('title', 'Untitled')}"
        raw_text = doc.get("raw_text", "")
        if raw_text:
            text_preview = raw_text[:500] if len(raw_text) > 500 else raw_text
            ingestion_text += f"\n{text_preview}"
    if keys:
        ingestion_text += "\n\n# Extraction performed:\n"
        for key in keys:
            ingestion_text += f"- {key}\n"
    return ingestion_text


def _get_user_model_name(user_id: str | None, db=None) -> str:
    """Resolve user's preferred model name (sync context)."""
    if db is None:
        db = _get_db()

    sys_cfg = db.system_config.find_one() or {}
    models = sys_cfg.get("available_models", [])

    def _default_model() -> str:
        for m in models:
            if isinstance(m, dict) and m.get("name"):
                return m["name"]
        return ""

    if user_id:
        user_config = db.user_model_config.find_one({"user_id": user_id})
        if user_config and user_config.get("name"):
            stored = user_config["name"]
            # Verify stored name/tag still matches a configured model
            for m in models:
                if isinstance(m, dict) and (m.get("name") == stored or m.get("tag") == stored):
                    return m.get("name", stored)
            # Stored value is stale — fall through to default

    return _default_model()


@celery_app.task(
    bind=True,
    name="tasks.extraction.run",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def perform_extraction_task(
    self,
    activity_id: str,
    searchset_uuid: str,
    document_uuids: list,
    keys: list,
    root_path: str,
    fillable_pdf_url: str | None = None,
    extraction_config_override: dict | None = None,
) -> dict:
    """Run ExtractionEngine against documents and save results to ActivityEvent."""
    from bson import ObjectId

    from app.services.extraction_engine import ExtractionEngine

    db = _get_db()
    sys_cfg = db.system_config.find_one() or {}

    # Update activity status to running
    activity = db.activity_event.find_one({"_id": ObjectId(activity_id)})
    if activity:
        db.activity_event.update_one(
            {"_id": ObjectId(activity_id)},
            {"$set": {"status": "running"}},
        )

    try:
        user_id = activity.get("user_id") if activity else None
        model_name = _get_user_model_name(user_id, db)

        # Perform extraction
        engine = ExtractionEngine(system_config_doc=sys_cfg)
        results = engine.extract(
            keys,
            document_uuids,
            model=model_name,
            extraction_config_override=extraction_config_override,
        )
        raw_results = deepcopy(results)

        result_count = (
            len(results)
            if isinstance(results, list)
            else (1 if isinstance(results, dict) else 0)
        )
        logger.info("Extraction produced %d result(s)", result_count)

        if isinstance(results, list) and len(results) == 1:
            results = results[0]

        # Handle fillable PDF if present
        if fillable_pdf_url:
            try:
                from PyPDF2 import PdfReader, PdfWriter

                bindings = {}
                result_dict = results if isinstance(results, dict) else (results[0] if isinstance(results, list) and results else {})
                for key in result_dict:
                    item = db.search_set_item.find_one({"searchphrase": key})
                    if item and item.get("pdf_binding"):
                        bindings[item["pdf_binding"]] = result_dict[key]

                if bindings:
                    pdf_path = Path(root_path) / "static" / "uploads" / fillable_pdf_url
                    reader = PdfReader(pdf_path)
                    writer = PdfWriter()
                    writer.append(reader)
                    writer.update_page_form_field_values(
                        writer.pages[0], bindings, auto_regenerate=False,
                    )
                    output_pdf_path = Path(root_path) / "static" / "fillable_form.pdf"
                    with open(output_pdf_path, "wb") as f:
                        writer.write(f)
            except Exception as e:
                logger.warning("Fillable PDF processing failed: %s", e)

        # Normalize and save results
        normalized_results = normalize_results(results, expected_keys=keys)

        # Finish activity
        now = datetime.datetime.now(datetime.timezone.utc)
        if activity:
            db.activity_event.update_one(
                {"_id": ObjectId(activity_id)},
                {
                    "$set": {
                        "status": "completed",
                        "finished_at": now,
                        "last_updated_at": now,
                        "result_snapshot": {
                            "raw": raw_results,
                            "normalized": normalized_results,
                            "document_uuids": document_uuids,
                            "search_set_uuid": searchset_uuid,
                        },
                    }
                },
            )

            # Trigger description generation
            try:
                from app.tasks.activity_tasks import generate_activity_description_task

                generate_activity_description_task.delay(
                    activity_id, activity.get("type", ""), document_uuids,
                )
            except Exception as e:
                logger.warning("Error triggering description generation: %s", e)

        # Ingest extraction recommendation asynchronously
        try:
            ingest_extraction_recommendation_task.delay(
                searchset_uuid, document_uuids, keys,
            )
        except Exception as e:
            logger.warning("Error scheduling recommendation ingestion: %s", e)

        return {
            "status": "completed",
            "activity_id": str(activity_id),
            "results": normalized_results,
        }

    except Exception as e:
        logger.error("Error in extraction task: %s", e)
        now = datetime.datetime.now(datetime.timezone.utc)
        if activity:
            db.activity_event.update_one(
                {"_id": ObjectId(activity_id)},
                {
                    "$set": {
                        "status": "failed",
                        "error": str(e),
                        "finished_at": now,
                        "last_updated_at": now,
                    }
                },
            )
        raise


@celery_app.task(
    bind=True,
    name="tasks.extraction.ingest_recommendation",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def ingest_extraction_recommendation_task(
    self,
    searchset_uuid: str,
    document_uuids: list,
    keys: list,
) -> None:
    """Build and ingest extraction recommendations into semantic recommender.

    NOTE: Recommendation storage is not yet implemented. This task currently
    only logs the ingestion text for future integration.
    """
    db = _get_db()

    search_set = db.search_set.find_one({"uuid": searchset_uuid})
    if not search_set:
        logger.info("Recommendation ingest skipped: search set %s not found", searchset_uuid)
        return

    documents = []
    for doc_uuid in document_uuids:
        doc = db.smart_document.find_one({"uuid": doc_uuid})
        if doc:
            documents.append(doc)

    if not documents:
        logger.info("Recommendation ingest skipped: no documents found for %s", searchset_uuid)
        return

    ingestion_text = _build_extraction_ingestion_text(documents, keys)
    logger.info(
        "Extraction recommendation prepared for %s (text length %d) — storage not yet implemented",
        searchset_uuid, len(ingestion_text),
    )
