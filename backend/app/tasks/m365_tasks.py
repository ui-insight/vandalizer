"""Celery tasks for M365 passive intake: email ingestion, drive-item
ingestion, Graph subscription renewal, triage, and daily digest.

Ported from Flask app/utilities/m365_tasks.py.
Uses pymongo (sync) for DB access.
"""

from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)


def _get_db():
    from pymongo import MongoClient

    from app.config import Settings
    settings = Settings()
    return MongoClient(settings.mongo_host)[settings.mongo_db]


def _audit(db, action: str, **kwargs) -> None:
    """Write an immutable audit entry."""
    db.m365_audit_entry.insert_one({
        "uuid": uuid4().hex,
        "action": action,
        "created_at": datetime.now(timezone.utc),
        **kwargs,
    })


def _save_attachment_as_document(
    db,
    content_bytes: bytes,
    filename: str,
    user_id: str,
) -> dict:
    """Persist raw bytes to disk and create a SmartDocument."""
    ext = Path(filename).suffix.lstrip(".").lower() or "bin"
    doc_uuid = uuid4().hex

    from app.config import Settings
    upload_dir = Settings().upload_dir
    user_dir = Path(upload_dir) / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_dir / f"{doc_uuid}.{ext}"
    file_path.write_bytes(content_bytes)

    rel_path = f"{user_id}/{doc_uuid}.{ext}"
    doc = {
        "title": filename,
        "path": rel_path,
        "downloadpath": rel_path,
        "extension": ext,
        "uuid": doc_uuid,
        "user_id": user_id,
        "folder": "",
        "raw_text": "",
        "processing": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = db.smart_document.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def _trigger_text_extraction(doc: dict) -> None:
    """Kick off the document extraction pipeline."""
    try:
        from app.tasks.document_tasks import perform_extraction_and_update
        perform_extraction_and_update.delay(doc["uuid"], doc.get("extension", ""))
    except Exception:
        logger.warning("Could not queue text extraction for doc %s", doc.get("uuid"))


# ---------------------------------------------------------------------------
# Email ingestion
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.ingest_email_message",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=10,
)
def ingest_email_message(
    self,
    user_id: str,
    message_resource: str,
    intake_config_id: str,
) -> dict:
    """Fetch an email via Graph, download attachments, create a WorkItem."""
    from app.services.graph_client import GraphAPIError, GraphClient

    db = _get_db()
    intake = db.intake_configs.find_one({"uuid": intake_config_id})
    if not intake:
        return {"error": "IntakeConfig not found"}

    client = GraphClient(user_id)

    msg_id_match = re.search(r"messages/([^/]+)", message_resource)
    if not msg_id_match:
        return {"error": f"Could not parse message ID from {message_resource}"}
    message_id = msg_id_match.group(1)

    try:
        mailbox = intake.get("mailbox_address") if intake.get("intake_type") == "outlook_shared" else None
        msg = client.get_message(message_id, mailbox=mailbox)
    except GraphAPIError as e:
        logger.error("Failed to fetch message %s: %s", message_id, e)
        return {"error": str(e)}

    # Duplicate check
    if db.work_items.find_one({"graph_message_id": message_id}):
        logger.info("Duplicate message %s — skipping", message_id)
        return {"status": "duplicate"}

    # Download attachments
    attachment_ids = []
    if msg.get("hasAttachments"):
        try:
            raw_attachments = client.get_message_attachments(message_id, mailbox=mailbox)
            for att in raw_attachments:
                if att.get("@odata.type") == "#microsoft.graph.fileAttachment":
                    content = base64.b64decode(att.get("contentBytes", ""))
                    doc = _save_attachment_as_document(db, content, att.get("name", "attachment"), user_id)
                    _trigger_text_extraction(doc)
                    attachment_ids.append(doc["_id"])
        except GraphAPIError as e:
            logger.warning("Failed to fetch attachments for %s: %s", message_id, e)

    # Extract body text
    body_obj = msg.get("body", {})
    body_text = body_obj.get("content", "") if body_obj.get("contentType") == "text" else ""
    body_html = body_obj.get("content", "") if body_obj.get("contentType") == "html" else ""
    if body_html and not body_text:
        try:
            from markdownify import markdownify
            body_text = markdownify(body_html)
        except ImportError:
            body_text = body_html

    from_obj = msg.get("from", {}).get("emailAddress", {})

    work_item = {
        "uuid": uuid4().hex,
        "source": intake.get("intake_type", "outlook"),
        "status": "received",
        "graph_message_id": message_id,
        "subject": msg.get("subject", "(no subject)"),
        "sender_email": from_obj.get("address", ""),
        "sender_name": from_obj.get("name", ""),
        "received_at": msg.get("receivedDateTime"),
        "body_text": body_text[:100_000],
        "attachments": attachment_ids,
        "attachment_count": len(attachment_ids),
        "intake_config": intake["_id"],
        "owner_user_id": user_id,
        "team_id": intake.get("team_id"),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = db.work_items.insert_one(work_item)
    work_item["_id"] = result.inserted_id

    _audit(db, "ingest", actor_type="graph_webhook", work_item_id=work_item["uuid"],
           intake_config_id=intake.get("uuid"), detail={"source": "email", "message_id": message_id})

    triage_work_item.delay(str(work_item["_id"]))
    return {"status": "ingested", "work_item_uuid": work_item["uuid"]}


# ---------------------------------------------------------------------------
# OneDrive file ingestion
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.ingest_drive_item",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=10,
)
def ingest_drive_item(
    self,
    user_id: str,
    item_resource: str,
    intake_config_id: str,
) -> dict:
    """Fetch a OneDrive file via Graph, create SmartDocument + WorkItem."""
    from app.services.graph_client import GraphAPIError, GraphClient

    db = _get_db()
    intake = db.intake_configs.find_one({"uuid": intake_config_id})
    if not intake:
        return {"error": "IntakeConfig not found"}

    client = GraphClient(user_id)

    item_id_match = re.search(r"items/([^/]+)", item_resource)
    if not item_id_match:
        return {"error": f"Could not parse item ID from {item_resource}"}
    item_id = item_id_match.group(1)

    if db.work_items.find_one({"graph_drive_item_id": item_id}):
        logger.info("Duplicate drive item %s — skipping", item_id)
        return {"status": "duplicate"}

    try:
        item_meta = client.get_drive_item(item_id, drive_id=intake.get("drive_id"))
    except GraphAPIError as e:
        logger.error("Failed to fetch drive item %s: %s", item_id, e)
        return {"error": str(e)}

    if "folder" in item_meta:
        return {"status": "skipped_folder"}

    filename = item_meta.get("name", "file")
    ext = Path(filename).suffix.lstrip(".").lower()

    # File filters
    file_filters = intake.get("file_filters") or {}
    allowed_types = file_filters.get("types", [])
    if allowed_types and ext not in allowed_types:
        return {"status": "filtered_out", "reason": f"Extension .{ext} not in allowed types"}

    max_size = file_filters.get("max_size_bytes", 50_000_000)
    file_size = item_meta.get("size", 0)
    if max_size and file_size > max_size:
        return {"status": "filtered_out", "reason": f"File size {file_size} exceeds limit"}

    try:
        content = client.download_file(item_id, drive_id=intake.get("drive_id"))
    except GraphAPIError as e:
        logger.error("Failed to download drive item %s: %s", item_id, e)
        return {"error": str(e)}

    doc = _save_attachment_as_document(db, content, filename, user_id)
    _trigger_text_extraction(doc)

    work_item = {
        "uuid": uuid4().hex,
        "source": "onedrive_drop",
        "status": "received",
        "graph_drive_item_id": item_id,
        "subject": filename,
        "attachments": [doc["_id"]],
        "attachment_count": 1,
        "intake_config": intake["_id"],
        "owner_user_id": user_id,
        "team_id": intake.get("team_id"),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = db.work_items.insert_one(work_item)
    work_item["_id"] = result.inserted_id

    _audit(db, "ingest", actor_type="graph_webhook", work_item_id=work_item["uuid"],
           intake_config_id=intake.get("uuid"), detail={"source": "onedrive", "item_id": item_id, "filename": filename})

    triage_work_item.delay(str(work_item["_id"]))
    return {"status": "ingested", "work_item_uuid": work_item["uuid"]}


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.triage_work_item",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=10,
)
def triage_work_item(self, work_item_id: str) -> dict:
    """Classify a work item and route it to the right workflow."""
    from bson import ObjectId

    from app.services.triage_agent import triage_work_item_sync

    db = _get_db()
    work_item = db.work_items.find_one({"_id": ObjectId(work_item_id)})
    if not work_item:
        return {"error": "WorkItem not found"}

    intake = db.intake_configs.find_one({"_id": work_item.get("intake_config")})
    if not intake:
        db.work_items.update_one({"_id": work_item["_id"]}, {"$set": {"status": "failed"}})
        return {"error": "No IntakeConfig linked"}

    try:
        result = triage_work_item_sync(work_item)

        db.work_items.update_one(
            {"_id": work_item["_id"]},
            {"$set": {
                "triage_category": result.category,
                "triage_confidence": result.confidence,
                "triage_tags": result.tags,
                "sensitivity_flags": result.sensitivity_flags,
                "triage_summary": result.summary,
                "status": "triaged",
                "updated_at": datetime.now(timezone.utc),
            }},
        )

        _audit(db, "triage", actor_type="system", work_item_id=work_item["uuid"], detail={
            "category": result.category,
            "confidence": result.confidence,
            "sensitivity": result.sensitivity_flags,
            "suggested_action": result.suggested_action,
        })

        if result.sensitivity_flags and result.suggested_action == "review":
            db.work_items.update_one({"_id": work_item["_id"]}, {"$set": {"status": "awaiting_review"}})
            return {"status": "awaiting_review", "reason": f"Sensitivity flags: {result.sensitivity_flags}"}

    except Exception as e:
        logger.error("Triage failed for work item %s: %s", work_item.get("uuid"), e)
        db.work_items.update_one(
            {"_id": work_item["_id"]},
            {"$set": {"triage_summary": f"Triage error: {e}", "status": "triage_failed"}},
        )
        return {"status": "triage_failed", "error": str(e)}

    # Route to workflow
    workflow = _match_workflow(db, work_item, intake)
    if not workflow:
        db.work_items.update_one({"_id": work_item["_id"]}, {"$set": {"status": "failed"}})
        return {"error": "No matching workflow found"}

    db.work_items.update_one(
        {"_id": work_item["_id"]},
        {"$set": {"matched_workflow": workflow["_id"], "status": "processing"}},
    )

    # Create trigger event
    from app.services.passive_triggers import create_m365_trigger
    # Reload to get updated fields
    work_item = db.work_items.find_one({"_id": work_item["_id"]})
    event = create_m365_trigger(workflow, work_item)

    db.work_items.update_one(
        {"_id": work_item["_id"]},
        {"$set": {"trigger_event": event["_id"]}},
    )

    from app.tasks.passive_tasks import execute_workflow_passive
    execute_workflow_passive.delay(str(event["_id"]))

    return {"status": "dispatched", "workflow": workflow.get("name"), "trigger_event": event["uuid"]}


def _match_workflow(db, work_item: dict, intake: dict):
    """Match a work item to a workflow using triage rules or the default."""
    if intake.get("triage_enabled") and intake.get("triage_rules"):
        category = (work_item.get("triage_category") or "").lower()
        for rule in intake["triage_rules"]:
            pattern = (rule.get("pattern", "") or "").lower()
            if pattern and pattern in category:
                wf_id = rule.get("workflow_id")
                if wf_id:
                    from bson import ObjectId
                    wf = db.workflow.find_one({"_id": ObjectId(wf_id)})
                    if wf:
                        return wf

    if intake.get("default_workflow"):
        from bson import ObjectId
        return db.workflow.find_one({"_id": ObjectId(str(intake["default_workflow"]))})
    return None


# ---------------------------------------------------------------------------
# Graph subscription renewal (beat task)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.renew_graph_subscriptions",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=10,
)
def renew_graph_subscriptions(self) -> dict:
    """Renew Graph subscriptions expiring within 24 hours."""
    from app.services.graph_client import GraphClient

    db = _get_db()
    cutoff = datetime.now(timezone.utc) + timedelta(hours=24)
    expiring = db.graph_subscription.find({"active": True, "expiration": {"$lte": cutoff}})

    renewed = 0
    failed = 0

    for sub in expiring:
        try:
            client = GraphClient(sub["owner_user_id"])
            new_expiration = datetime.now(timezone.utc) + timedelta(days=2)
            client.renew_subscription(sub["subscription_id"], new_expiration)
            db.graph_subscription.update_one({"_id": sub["_id"]}, {"$set": {"expiration": new_expiration}})
            renewed += 1
        except Exception as e:
            logger.error("Failed to renew subscription %s: %s", sub.get("subscription_id"), e)
            failed += 1

    return {"renewed": renewed, "failed": failed}


# ---------------------------------------------------------------------------
# Daily digest (beat task)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.send_daily_digest",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=10,
)
def send_daily_digest(self) -> dict:
    """Send daily summary to Teams channels."""
    from app.services.graph_client import GraphClient
    from app.services.teams_cards import build_daily_digest_card

    db = _get_db()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    active_intakes = db.intake_configs.find({"enabled": True})
    digests_sent = 0

    for intake in active_intakes:
        teams_cfg = intake.get("teams_config") or {}
        if not teams_cfg.get("enabled") or not teams_cfg.get("daily_digest"):
            continue

        team_id = teams_cfg.get("team_id")
        channel_id = teams_cfg.get("channel_id")
        if not team_id or not channel_id:
            continue

        items = list(db.work_items.find({
            "intake_config": intake["_id"],
            "created_at": {"$gte": today_start},
        }).limit(10))

        if not items:
            continue

        all_items = db.work_items.find({"intake_config": intake["_id"], "created_at": {"$gte": today_start}})
        all_items_list = list(all_items)
        stats = {
            "total": len(all_items_list),
            "completed": sum(1 for i in all_items_list if i.get("status") == "completed"),
            "failed": sum(1 for i in all_items_list if i.get("status") == "failed"),
            "awaiting_review": sum(1 for i in all_items_list if i.get("status") == "awaiting_review"),
        }

        try:
            card = build_daily_digest_card(items, stats)
            client = GraphClient(intake.get("owner_user_id", ""))
            client.send_channel_message(team_id, channel_id, card_json=card)
            digests_sent += 1
        except Exception as e:
            logger.error("Failed to send digest for intake %s: %s", intake.get("name"), e)

    return {"digests_sent": digests_sent}
