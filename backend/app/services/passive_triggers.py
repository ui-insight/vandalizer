"""Passive trigger management for workflows.

Ported from Flask app/utilities/passive_triggers.py.
Uses pymongo (sync) for DB access.
"""

import fnmatch
import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from bson import ObjectId

from app.tasks import get_sync_db

logger = logging.getLogger(__name__)

MAX_CHAIN_DEPTH = 5


def _base_event(now: datetime) -> dict:
    """Return common fields for all trigger events."""
    return {
        "uuid": uuid4().hex,
        "created_at": now,
        "attempt_number": 1,
        "max_attempts": 3,
        "output_delivery": {
            "storage_status": None,
            "notifications_sent": [],
            "webhooks_called": [],
            "chains_triggered": [],
        },
    }


def create_folder_watch_trigger(
    workflow_doc: dict,
    document_doc: dict,
    *,
    automation_id: str | None = None,
    automation_name: str | None = None,
) -> dict:
    """Create a pending trigger event for a folder-watched document.

    Returns the inserted trigger event dict.
    """
    db = get_sync_db()
    folder_watch_config = (workflow_doc.get("input_config") or {}).get("folder_watch", {})
    delay_seconds = folder_watch_config.get("delay_seconds", 300)
    now = datetime.now(timezone.utc)

    event = {
        **_base_event(now),
        "workflow": workflow_doc["_id"],
        "trigger_type": "folder_watch",
        "status": "pending",
        "documents": [document_doc["_id"]],
        "document_count": 1,
        "trigger_context": {
            "folder_id": document_doc.get("folder", ""),
            "automation_id": automation_id,
            "automation_name": automation_name,
        },
        "process_after": now + timedelta(seconds=delay_seconds),
    }
    result = db.workflow_trigger_event.insert_one(event)
    event["_id"] = result.inserted_id
    return event


def create_m365_trigger(workflow_doc: dict, work_item_doc: dict) -> dict:
    """Create a pending trigger event for an M365-ingested work item.

    Returns the inserted trigger event dict.
    """
    db = get_sync_db()
    now = datetime.now(timezone.utc)

    event = {
        **_base_event(now),
        "workflow": workflow_doc["_id"],
        "trigger_type": "m365_intake",
        "status": "pending",
        "documents": work_item_doc.get("attachments", []),
        "document_count": work_item_doc.get("attachment_count", 0),
        "work_item": work_item_doc["_id"],
        "trigger_context": {
            "work_item_uuid": work_item_doc.get("uuid", ""),
            "source": work_item_doc.get("source", ""),
            "intake_config_id": str(work_item_doc.get("intake_config")) if work_item_doc.get("intake_config") else None,
        },
        "process_after": now,  # Process immediately (no delay for M365)
    }
    result = db.workflow_trigger_event.insert_one(event)
    event["_id"] = result.inserted_id
    return event


def create_api_trigger(
    automation_doc: dict,
    workflow_id: str,
    document_oids: list,
) -> dict:
    """Create a trigger event for an API-initiated automation.

    Bypasses the pending→queued beat cycle and goes straight to queued
    so the caller can dispatch execution immediately.
    """
    db = get_sync_db()
    now = datetime.now(timezone.utc)

    event = {
        **_base_event(now),
        "workflow": ObjectId(workflow_id),
        "trigger_type": "api",
        "status": "queued",
        "documents": document_oids,
        "document_count": len(document_oids),
        "trigger_context": {
            "automation_id": str(automation_doc.get("_id", "")),
            "automation_name": automation_doc.get("name", ""),
        },
        "process_after": now,
        "queued_at": now,
    }
    result = db.workflow_trigger_event.insert_one(event)
    event["_id"] = result.inserted_id
    return event


def create_chain_trigger(
    source_event: dict,
    target_workflow_id,
    document_oids: list,
    *,
    automation_id: str | None = None,
    automation_name: str | None = None,
) -> dict | None:
    """Create a trigger event that chains from a completed trigger.

    Returns None if max chain depth is reached.
    """
    source_context = source_event.get("trigger_context") or {}
    depth = source_context.get("chain_depth", 0) + 1
    if depth > MAX_CHAIN_DEPTH:
        logger.warning(
            "Chain depth %d exceeds max %d for source event %s",
            depth, MAX_CHAIN_DEPTH, source_event.get("uuid"),
        )
        return None

    db = get_sync_db()
    now = datetime.now(timezone.utc)

    event = {
        **_base_event(now),
        "workflow": ObjectId(target_workflow_id) if isinstance(target_workflow_id, str) else target_workflow_id,
        "trigger_type": "chain",
        "status": "pending",
        "documents": document_oids,
        "document_count": len(document_oids),
        "trigger_context": {
            "source_event_uuid": source_event.get("uuid"),
            "source_workflow": str(source_event.get("workflow", "")),
            "chain_depth": depth,
            "automation_id": automation_id,
            "automation_name": automation_name,
        },
        "process_after": now,
    }
    result = db.workflow_trigger_event.insert_one(event)
    event["_id"] = result.inserted_id
    return event


def apply_file_filters(documents: list[dict], file_filters: dict) -> list[dict]:
    """Filter documents based on type, name patterns, size."""
    if not file_filters:
        return documents

    filtered = []
    for doc in documents:
        allowed_types = file_filters.get("types", [])
        if allowed_types and doc.get("extension") not in allowed_types:
            continue

        exclude_patterns = file_filters.get("exclude_patterns", [])
        if any(fnmatch.fnmatch(doc.get("title", ""), pattern) for pattern in exclude_patterns):
            continue

        filtered.append(doc)

    return filtered


def evaluate_conditions(documents: list[dict], conditions: list) -> bool:
    """Evaluate whether documents meet workflow conditions."""
    if not conditions:
        return True

    for condition in conditions:
        field = condition.get("field")
        operator = condition.get("operator")
        value = condition.get("value")

        if field == "file_size":
            for doc in documents:
                try:
                    upload_dir = os.environ.get("UPLOAD_DIR", "../app/static/uploads")
                    doc_path = os.path.join(upload_dir, doc.get("path", ""))
                    doc_size = os.path.getsize(doc_path)
                    if operator == "less_than" and doc_size >= value:
                        return False
                    elif operator == "greater_than" and doc_size <= value:
                        return False
                except Exception:
                    pass

    return True


def check_workflow_budget(workflow_doc: dict) -> tuple[bool, str | None]:
    """Check if workflow has budget remaining for today."""
    budget_config = (workflow_doc.get("resource_config") or {}).get("budget", {})

    daily_limit = budget_config.get("daily_token_limit")
    if not daily_limit:
        return True, None

    # Aggregate actual token usage from today's completed trigger events
    db = get_sync_db()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    pipeline = [
        {
            "$match": {
                "workflow": workflow_doc["_id"],
                "status": "completed",
                "completed_at": {"$gte": today_start},
            }
        },
        {
            "$group": {
                "_id": None,
                "total_tokens": {"$sum": "$total_tokens"},
            }
        },
    ]
    results = list(db.workflow_trigger_event.aggregate(pipeline))
    tokens_today = results[0]["total_tokens"] if results else 0

    if tokens_today >= daily_limit:
        return False, f"Daily token limit reached ({tokens_today}/{daily_limit})"

    return True, None


def check_throttling(workflow_doc: dict) -> tuple[bool, str | None]:
    """Check if workflow can run based on throttling configuration."""
    db = get_sync_db()
    throttle_config = (workflow_doc.get("resource_config") or {}).get("throttling", {})
    stats = workflow_doc.get("stats") or {}

    min_delay = throttle_config.get("min_delay_between_runs", 60)
    last_run_at = stats.get("last_passive_run_at")

    if last_run_at:
        if isinstance(last_run_at, str):
            from dateutil import parser
            last_run_at = parser.parse(last_run_at)
        now = datetime.now(timezone.utc)
        if last_run_at.tzinfo is None:
            last_run_at = last_run_at.replace(tzinfo=timezone.utc)
        seconds_since = (now - last_run_at).total_seconds()
        if seconds_since < min_delay:
            return False, f"Throttled: {int(min_delay - seconds_since)}s remaining"

    max_concurrent = throttle_config.get("max_concurrent", 3)
    running_count = db.workflow_trigger_event.count_documents({
        "workflow": workflow_doc["_id"],
        "status": {"$in": ["queued", "running"]},
    })

    if running_count >= max_concurrent:
        return False, f"Max concurrent runs ({max_concurrent}) reached"

    return True, None
