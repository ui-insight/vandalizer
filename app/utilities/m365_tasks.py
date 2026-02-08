#!/usr/bin/env python3
"""Celery tasks for M365 passive intake: email ingestion, drive-item
ingestion, Graph subscription renewal, triage, and daily digest.
"""

from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app import app
from app.celery_worker import celery_app
from app.models import (
    GraphSubscription,
    IntakeConfig,
    M365AuditEntry,
    SmartDocument,
    WorkItem,
    Workflow,
    WorkflowTriggerEvent,
)
from app.utilities.graph_client import GraphClient, GraphAPIError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _audit(action: str, **kwargs) -> None:
    """Write an immutable audit entry."""
    M365AuditEntry(uuid=uuid4().hex, action=action, **kwargs).save()


def _save_attachment_as_document(
    content_bytes: bytes,
    filename: str,
    user_id: str,
    space: str,
    folder_uuid: str | None = None,
) -> SmartDocument:
    """Persist raw bytes to disk and create a SmartDocument."""
    ext = Path(filename).suffix.lstrip(".").lower() or "bin"
    doc_uuid = uuid4().hex

    upload_dir = Path(app.root_path) / "static" / "uploads" / user_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{doc_uuid}.{ext}"
    file_path.write_bytes(content_bytes)

    rel_path = f"{user_id}/{doc_uuid}.{ext}"
    doc = SmartDocument(
        title=filename,
        path=rel_path,
        downloadpath=rel_path,
        extension=ext,
        uuid=doc_uuid,
        user_id=user_id,
        space=space,
        folder=folder_uuid or "",
        raw_text="",  # will be populated by text extraction task
    )
    doc.save()
    return doc


def _trigger_text_extraction(doc: SmartDocument) -> None:
    """Kick off the existing document extraction pipeline."""
    try:
        from app.utilities.extraction_tasks import perform_extraction_and_update

        perform_extraction_and_update.delay(str(doc.id))
    except Exception:
        logger.warning(f"Could not queue text extraction for doc {doc.uuid}")


# ---------------------------------------------------------------------------
# Email ingestion
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.passive.ingest_email_message")
def ingest_email_message(
    user_id: str,
    message_resource: str,
    intake_config_id: str,
) -> dict:
    """Fetch an email via Graph, download attachments, create a WorkItem.

    Args:
        user_id: Graph-token owner.
        message_resource: The Graph resource path (e.g. "/users/{id}/messages/{msg_id}").
        intake_config_id: UUID of the IntakeConfig that triggered this.
    """
    intake = IntakeConfig.objects(uuid=intake_config_id).first()
    if not intake:
        return {"error": "IntakeConfig not found"}

    client = GraphClient(user_id)

    # Extract message ID from resource path
    # Resource looks like: users/{id}/messages/{message_id}
    msg_id_match = re.search(r"messages/([^/]+)", message_resource)
    if not msg_id_match:
        return {"error": f"Could not parse message ID from {message_resource}"}
    message_id = msg_id_match.group(1)

    try:
        mailbox = intake.mailbox_address if intake.intake_type == "outlook_shared" else None
        msg = client.get_message(message_id, mailbox=mailbox)
    except GraphAPIError as e:
        logger.error(f"Failed to fetch message {message_id}: {e}")
        return {"error": str(e)}

    # Check for duplicate (same Graph message ID)
    if WorkItem.objects(graph_message_id=message_id).first():
        logger.info(f"Duplicate message {message_id} — skipping")
        return {"status": "duplicate"}

    # Determine space (use user_id as fallback)
    space = user_id

    # Download attachments
    attachments: list[SmartDocument] = []
    if msg.get("hasAttachments"):
        try:
            raw_attachments = client.get_message_attachments(message_id, mailbox=mailbox)
            for att in raw_attachments:
                if att.get("@odata.type") == "#microsoft.graph.fileAttachment":
                    content = base64.b64decode(att.get("contentBytes", ""))
                    doc = _save_attachment_as_document(
                        content, att.get("name", "attachment"), user_id, space
                    )
                    _trigger_text_extraction(doc)
                    attachments.append(doc)
        except GraphAPIError as e:
            logger.warning(f"Failed to fetch attachments for {message_id}: {e}")

    # Extract body
    body_obj = msg.get("body", {})
    body_text = body_obj.get("content", "") if body_obj.get("contentType") == "text" else ""
    body_html = body_obj.get("content", "") if body_obj.get("contentType") == "html" else ""
    # If HTML only, create a basic text version
    if body_html and not body_text:
        from markdownify import markdownify

        body_text = markdownify(body_html)

    from_obj = msg.get("from", {}).get("emailAddress", {})

    work_item = WorkItem(
        uuid=uuid4().hex,
        source=intake.intake_type,
        status="received",
        graph_message_id=message_id,
        source_mailbox=intake.mailbox_address,
        subject=msg.get("subject", "(no subject)"),
        sender_email=from_obj.get("address", ""),
        sender_name=from_obj.get("name", ""),
        received_at=msg.get("receivedDateTime"),
        body_text=body_text[:100_000],  # cap at 100K chars
        body_html=body_html[:100_000],
        attachments=attachments,
        attachment_count=len(attachments),
        intake_config=intake,
        owner_user_id=user_id,
        team_id=intake.team_id,
    )
    work_item.save()

    _audit(
        "ingest",
        actor_type="graph_webhook",
        work_item_id=work_item.uuid,
        intake_config_id=intake.uuid,
        detail={"source": "email", "message_id": message_id},
    )

    # Dispatch triage
    triage_work_item.delay(str(work_item.id))

    return {"status": "ingested", "work_item_uuid": work_item.uuid}


# ---------------------------------------------------------------------------
# OneDrive file ingestion
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.passive.ingest_drive_item")
def ingest_drive_item(
    user_id: str,
    item_resource: str,
    intake_config_id: str,
) -> dict:
    """Fetch a OneDrive file via Graph, create SmartDocument + WorkItem.

    Args:
        user_id: Graph-token owner.
        item_resource: The Graph resource path (e.g. "/drives/{id}/items/{item_id}").
        intake_config_id: UUID of the IntakeConfig.
    """
    intake = IntakeConfig.objects(uuid=intake_config_id).first()
    if not intake:
        return {"error": "IntakeConfig not found"}

    client = GraphClient(user_id)

    # Extract item ID
    item_id_match = re.search(r"items/([^/]+)", item_resource)
    if not item_id_match:
        return {"error": f"Could not parse item ID from {item_resource}"}
    item_id = item_id_match.group(1)

    # Check duplicate
    if WorkItem.objects(graph_drive_item_id=item_id).first():
        logger.info(f"Duplicate drive item {item_id} — skipping")
        return {"status": "duplicate"}

    try:
        item_meta = client.get_drive_item(item_id, drive_id=intake.drive_id)
    except GraphAPIError as e:
        logger.error(f"Failed to fetch drive item {item_id}: {e}")
        return {"error": str(e)}

    # Skip folders
    if "folder" in item_meta:
        return {"status": "skipped_folder"}

    filename = item_meta.get("name", "file")
    ext = Path(filename).suffix.lstrip(".").lower()

    # Apply file filters
    allowed_types = intake.file_filters.get("types", [])
    if allowed_types and ext not in allowed_types:
        return {"status": "filtered_out", "reason": f"Extension .{ext} not in allowed types"}

    max_size = intake.file_filters.get("max_size_bytes", 50_000_000)
    file_size = item_meta.get("size", 0)
    if file_size > max_size:
        return {"status": "filtered_out", "reason": f"File size {file_size} exceeds limit"}

    # Download
    try:
        content = client.download_file(item_id, drive_id=intake.drive_id)
    except GraphAPIError as e:
        logger.error(f"Failed to download drive item {item_id}: {e}")
        return {"error": str(e)}

    space = user_id
    doc = _save_attachment_as_document(content, filename, user_id, space)
    _trigger_text_extraction(doc)

    work_item = WorkItem(
        uuid=uuid4().hex,
        source="onedrive_drop",
        status="received",
        graph_drive_item_id=item_id,
        source_folder_path=intake.folder_path,
        subject=filename,
        attachments=[doc],
        attachment_count=1,
        intake_config=intake,
        owner_user_id=user_id,
        team_id=intake.team_id,
    )
    work_item.save()

    _audit(
        "ingest",
        actor_type="graph_webhook",
        work_item_id=work_item.uuid,
        intake_config_id=intake.uuid,
        detail={"source": "onedrive", "item_id": item_id, "filename": filename},
    )

    triage_work_item.delay(str(work_item.id))

    return {"status": "ingested", "work_item_uuid": work_item.uuid}


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.passive.triage_work_item")
def triage_work_item(work_item_id: str) -> dict:
    """Classify a work item and route it to the right workflow.

    Uses the triage agent (LLM) to determine category, sensitivity,
    and suggested workflow.  If sensitive content is detected the item
    is held for human review.
    """
    work_item = WorkItem.objects(id=work_item_id).first()
    if not work_item:
        return {"error": "WorkItem not found"}

    intake = work_item.intake_config
    if not intake:
        work_item.status = "failed"
        work_item.save()
        return {"error": "No IntakeConfig linked"}

    try:
        from app.utilities.triage_agent import triage_work_item_sync

        result = triage_work_item_sync(work_item)

        work_item.triage_category = result.category
        work_item.triage_confidence = result.confidence
        work_item.triage_tags = result.tags
        work_item.sensitivity_flags = result.sensitivity_flags
        work_item.triage_summary = result.summary
        work_item.status = "triaged"
        work_item.updated_at = datetime.utcnow()
        work_item.save()

        _audit(
            "triage",
            actor_type="system",
            work_item_id=work_item.uuid,
            detail={
                "category": result.category,
                "confidence": result.confidence,
                "sensitivity": result.sensitivity_flags,
                "suggested_action": result.suggested_action,
            },
        )

        # Gate: if sensitive, hold for human review
        if result.sensitivity_flags and result.suggested_action == "review":
            work_item.status = "awaiting_review"
            work_item.save()
            # Teams notification will be sent by the notification layer
            return {
                "status": "awaiting_review",
                "reason": f"Sensitivity flags: {result.sensitivity_flags}",
            }

    except Exception as e:
        logger.error(f"Triage failed for work item {work_item.uuid}: {e}")
        # If triage fails, continue with default workflow (graceful degradation)
        work_item.triage_summary = f"Triage error: {e}"
        work_item.status = "triaged"
        work_item.save()

    # Route to workflow
    workflow = _match_workflow(work_item, intake)
    if not workflow:
        work_item.status = "failed"
        work_item.save()
        return {"error": "No matching workflow found"}

    work_item.matched_workflow = workflow
    work_item.status = "processing"
    work_item.save()

    # Create trigger event and execute
    from app.utilities.passive_triggers import create_m365_trigger

    event = create_m365_trigger(workflow, work_item)
    work_item.trigger_event = event
    work_item.save()

    from app.utilities.passive_tasks import execute_workflow_passive

    execute_workflow_passive.delay(str(event.id))

    return {
        "status": "dispatched",
        "workflow": workflow.name,
        "trigger_event": event.uuid,
    }


def _match_workflow(work_item: WorkItem, intake: IntakeConfig) -> Workflow | None:
    """Match a work item to a workflow using triage rules or the default."""
    # Check triage rules first
    if intake.triage_enabled and intake.triage_rules:
        category = (work_item.triage_category or "").lower()
        for rule in intake.triage_rules:
            pattern = (rule.get("pattern", "") or "").lower()
            if pattern and pattern in category:
                wf_id = rule.get("workflow_id")
                if wf_id:
                    wf = Workflow.objects(id=wf_id).first()
                    if wf:
                        return wf

    # Fall back to default workflow
    return intake.default_workflow


# ---------------------------------------------------------------------------
# Graph subscription renewal (beat task)
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.passive.renew_graph_subscriptions")
def renew_graph_subscriptions() -> dict:
    """Renew Graph subscriptions expiring within the next 24 hours.

    Runs every 12 hours via Celery Beat.
    """
    cutoff = datetime.utcnow() + timedelta(hours=24)
    expiring = GraphSubscription.objects(active=True, expiration__lte=cutoff)

    renewed = 0
    failed = 0

    for sub in expiring:
        try:
            client = GraphClient(sub.owner_user_id)
            new_expiration = datetime.utcnow() + timedelta(days=2)
            client.renew_subscription(sub.subscription_id, new_expiration)
            sub.expiration = new_expiration
            sub.save()
            renewed += 1
        except Exception as e:
            logger.error(f"Failed to renew subscription {sub.subscription_id}: {e}")
            failed += 1

    return {"renewed": renewed, "failed": failed}


# ---------------------------------------------------------------------------
# Daily digest (beat task)
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.passive.send_daily_digest")
def send_daily_digest() -> dict:
    """Send a daily summary to Teams channels.

    Runs once per day (configured in beat schedule).
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Group by intake config
    active_intakes = IntakeConfig.objects(enabled=True)
    digests_sent = 0

    for intake in active_intakes:
        teams_cfg = intake.teams_config or {}
        if not teams_cfg.get("enabled") or not teams_cfg.get("daily_digest"):
            continue

        team_id = teams_cfg.get("team_id")
        channel_id = teams_cfg.get("channel_id")
        if not team_id or not channel_id:
            continue

        # Get today's work items for this intake
        items = WorkItem.objects(
            intake_config=intake, created_at__gte=today_start
        )

        if items.count() == 0:
            continue

        stats = {
            "total": items.count(),
            "completed": items.filter(status="completed").count(),
            "failed": items.filter(status="failed").count(),
            "awaiting_review": items.filter(status="awaiting_review").count(),
            "processing": items.filter(status="processing").count(),
        }

        try:
            from app.utilities.teams_cards import build_daily_digest_card

            card = build_daily_digest_card(list(items[:10]), stats)
            client = GraphClient(intake.owner_user_id)
            client.send_channel_message(team_id, channel_id, card_json=card)
            digests_sent += 1
        except Exception as e:
            logger.error(f"Failed to send digest for intake {intake.name}: {e}")

    return {"digests_sent": digests_sent}
