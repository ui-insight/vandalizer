"""Celery tasks for passive workflow trigger processing.

Ported from Flask app/utilities/passive_tasks.py.
Uses pymongo (sync) for DB access.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from bson import ObjectId

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_db():
    from pymongo import MongoClient

    mongo_host = os.environ.get("MONGO_HOST", "mongodb://localhost:27017/")
    mongo_db = os.environ.get("MONGO_DB", "osp")
    return MongoClient(mongo_host)[mongo_db]


# ---------------------------------------------------------------------------
# Beat task: process pending triggers (every 60s)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.process_pending_triggers",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=10,
)
def process_pending_triggers(self) -> dict:
    """Evaluate pending WorkflowTriggerEvents and dispatch execution.

    Runs every minute via Celery Beat.
    """
    from app.services.passive_triggers import (
        apply_file_filters,
        check_throttling,
        check_workflow_budget,
        evaluate_conditions,
    )

    db = _get_db()
    now = datetime.now(timezone.utc)

    pending = list(
        db.workflow_trigger_event.find({
            "status": "pending",
            "process_after": {"$lte": now},
        }).limit(100)
    )

    processed = 0

    for event in pending:
        try:
            workflow = db.workflow.find_one({"_id": event.get("workflow")})
            if not workflow:
                db.workflow_trigger_event.update_one(
                    {"_id": event["_id"]},
                    {"$set": {"status": "failed", "error": "Workflow not found"}},
                )
                continue

            # Check folder watch enabled (for folder_watch triggers)
            if event.get("trigger_type") == "folder_watch":
                fw_cfg = (workflow.get("input_config") or {}).get("folder_watch", {})
                if not fw_cfg.get("enabled"):
                    db.workflow_trigger_event.update_one(
                        {"_id": event["_id"]},
                        {"$set": {"status": "skipped", "error": "Folder watch disabled"}},
                    )
                    continue

                # Apply file filters
                file_filters = fw_cfg.get("file_filters", {})
                doc_ids = event.get("documents", [])
                docs = list(db.smart_document.find({"_id": {"$in": doc_ids}}))
                filtered = apply_file_filters(docs, file_filters)

                if not filtered:
                    db.workflow_trigger_event.update_one(
                        {"_id": event["_id"]},
                        {"$set": {"status": "skipped", "error": "No documents passed file filters"}},
                    )
                    continue

                # Evaluate conditions
                conditions = (workflow.get("input_config") or {}).get("conditions", [])
                if not evaluate_conditions(filtered, conditions):
                    db.workflow_trigger_event.update_one(
                        {"_id": event["_id"]},
                        {"$set": {"status": "skipped", "error": "Documents did not meet conditions"}},
                    )
                    continue

                # Update filtered docs on event
                db.workflow_trigger_event.update_one(
                    {"_id": event["_id"]},
                    {"$set": {
                        "documents": [d["_id"] for d in filtered],
                        "document_count": len(filtered),
                    }},
                )

            # Check budget
            can_run, budget_reason = check_workflow_budget(workflow)
            if not can_run:
                db.workflow_trigger_event.update_one(
                    {"_id": event["_id"]},
                    {"$set": {"status": "skipped", "error": budget_reason}},
                )
                continue

            # Check throttling
            can_run, throttle_reason = check_throttling(workflow)
            if not can_run:
                db.workflow_trigger_event.update_one(
                    {"_id": event["_id"]},
                    {"$set": {"process_after": now + timedelta(seconds=60)}},
                )
                continue

            # Queue for execution
            db.workflow_trigger_event.update_one(
                {"_id": event["_id"]},
                {"$set": {"status": "queued", "queued_at": now}},
            )

            execute_workflow_passive.delay(str(event["_id"]))
            processed += 1

        except Exception as e:
            logger.error("Error processing trigger event %s: %s", event.get("uuid"), e)
            db.workflow_trigger_event.update_one(
                {"_id": event["_id"]},
                {"$set": {"status": "failed", "error": f"Processing error: {e}"}},
            )

    return {"processed": processed, "timestamp": now.isoformat()}


# ---------------------------------------------------------------------------
# Execute a workflow for a passive trigger
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.execute_workflow_passive",
)
def execute_workflow_passive(self, trigger_event_id: str) -> dict:
    """Execute a workflow for a passive trigger event."""
    from app.services.workflow_engine import build_workflow_engine

    db = _get_db()
    event = db.workflow_trigger_event.find_one({"_id": ObjectId(trigger_event_id)})
    if not event:
        return {"error": "Trigger event not found"}

    workflow = db.workflow.find_one({"_id": event.get("workflow")})
    if not workflow:
        db.workflow_trigger_event.update_one(
            {"_id": event["_id"]},
            {"$set": {"status": "failed", "error": "Workflow not found"}},
        )
        return {"error": "Workflow not found"}

    now = datetime.now(timezone.utc)
    sys_config = db.system_config.find_one() or {}

    try:
        # Mark running
        db.workflow_trigger_event.update_one(
            {"_id": event["_id"]},
            {"$set": {"status": "running", "started_at": now}},
        )

        # Create WorkflowResult
        result_doc = {
            "workflow": workflow["_id"],
            "session_id": uuid4().hex,
            "status": "running",
            "trigger_type": event.get("trigger_type"),
            "is_passive": True,
            "input_context": event.get("trigger_context") or {},
            "created_at": now,
        }
        result_id = db.workflow_result.insert_one(result_doc).inserted_id

        # Gather documents
        doc_ids = event.get("documents", [])
        docs = list(db.smart_document.find({"_id": {"$in": doc_ids}}))
        doc_uuids = [d.get("uuid", "") for d in docs]

        # Merge fixed documents from input_config
        fixed_doc_config = (workflow.get("input_config") or {}).get("fixed_documents", [])
        for fd in fixed_doc_config:
            fd_uuid = fd.get("uuid") if isinstance(fd, dict) else str(fd)
            if fd_uuid and fd_uuid not in doc_uuids:
                doc_uuids.append(fd_uuid)

        # Build trigger step data
        trigger_step_data = {"doc_uuids": doc_uuids, "user_id": workflow.get("user_id")}

        # Build steps data
        steps_data = [{"name": "Document", "data": trigger_step_data, "tasks": []}]

        for step_id in workflow.get("steps", []):
            step_doc = db.workflow_step.find_one({"_id": step_id})
            if not step_doc:
                continue

            tasks = []
            for task_id in step_doc.get("tasks", []):
                task_doc = db.workflow_step_task.find_one({"_id": task_id})
                if task_doc:
                    task_data = dict(task_doc.get("data", {}))

                    # Resolve extraction keys from search set
                    if task_doc.get("name") == "Extraction" and task_data.get("search_set_uuid"):
                        ss_items = list(db.search_set_item.find({
                            "searchset": task_data["search_set_uuid"],
                            "searchtype": "extraction",
                        }))
                        task_data["keys"] = [item["searchphrase"] for item in ss_items]

                    # Pre-load doc texts
                    if doc_uuids:
                        doc_texts = []
                        for uuid_val in doc_uuids:
                            doc = db.smart_document.find_one({"uuid": uuid_val})
                            if doc and doc.get("raw_text"):
                                doc_texts.append(doc["raw_text"])
                        task_data["doc_texts"] = doc_texts

                    tasks.append({"name": task_doc.get("name", ""), "data": task_data})

            steps_data.append({
                "name": step_doc.get("name", ""),
                "data": step_doc.get("data", {}),
                "tasks": tasks,
            })

        # Resolve model
        models = sys_config.get("available_models", [])
        model = models[0]["name"] if models else "gpt-4o-mini"

        engine = build_workflow_engine(
            steps_data=steps_data,
            model=model,
            user_id=workflow.get("user_id"),
            system_config_doc=sys_config,
        )

        final_output, data = engine.execute()

        # Update result
        completed_at = datetime.now(timezone.utc)
        db.workflow_result.update_one(
            {"_id": result_id},
            {"$set": {
                "status": "completed",
                "final_output": {"output": final_output, "data": data},
            }},
        )

        # Update event
        started_at = event.get("started_at") or now
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        db.workflow_trigger_event.update_one(
            {"_id": event["_id"]},
            {"$set": {
                "status": "completed",
                "completed_at": completed_at,
                "duration_ms": duration_ms,
                "result": result_id,
                "documents_succeeded": len(doc_ids),
            }},
        )

        # Update workflow stats
        db.workflow.update_one(
            {"_id": workflow["_id"]},
            {"$inc": {
                "stats.total_runs": 1,
                "stats.passive_runs": 1,
                "stats.successful_runs": 1,
                "stats.documents_processed": len(doc_ids),
                "num_executions": 1,
            }, "$set": {
                "stats.last_run_at": completed_at,
                "stats.last_passive_run_at": completed_at,
            }},
        )

        # Dispatch output processing
        process_outputs.delay(str(result_id))

        return {
            "status": "completed",
            "workflow_result_id": str(result_id),
            "event_id": str(event["_id"]),
        }

    except Exception as e:
        logger.error("Passive execution failed for event %s: %s", event.get("uuid"), e)

        completed_at = datetime.now(timezone.utc)
        started_at = event.get("started_at") or now
        duration_ms = int((completed_at - started_at).total_seconds() * 1000) if started_at else 0

        db.workflow_trigger_event.update_one(
            {"_id": event["_id"]},
            {"$set": {
                "status": "failed",
                "completed_at": completed_at,
                "duration_ms": duration_ms,
                "error": str(e),
            }},
        )

        # Update workflow failure stats
        db.workflow.update_one(
            {"_id": workflow["_id"]},
            {"$inc": {
                "stats.total_runs": 1,
                "stats.passive_runs": 1,
                "stats.failed_runs": 1,
            }},
        )

        # Check retry
        retry_cfg = (workflow.get("resource_config") or {}).get("retry", {})
        max_retries = retry_cfg.get("max_retries", 3)
        attempt = event.get("attempt_number", 1)

        if attempt < max_retries:
            retry_delay = retry_cfg.get("retry_delay_seconds", 300)
            next_retry = datetime.now(timezone.utc) + timedelta(seconds=retry_delay)
            db.workflow_trigger_event.update_one(
                {"_id": event["_id"]},
                {"$set": {
                    "status": "pending",
                    "attempt_number": attempt + 1,
                    "process_after": next_retry,
                    "next_retry_at": next_retry,
                }},
            )
            return {"status": "retry_scheduled", "attempt": attempt + 1}

        return {"status": "failed", "error": str(e)}


# ---------------------------------------------------------------------------
# Process outputs (storage, notifications, webhooks)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.process_outputs",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=10,
)
def process_outputs(self, workflow_result_id: str) -> dict:
    """Process output configuration after workflow completes."""
    from app.services.output_handlers import (
        call_webhook,
        save_results_to_folder,
        save_results_to_onedrive_channel,
        send_workflow_notification,
        should_send_notification,
    )

    db = _get_db()
    result_doc = db.workflow_result.find_one({"_id": ObjectId(workflow_result_id)})
    if not result_doc:
        return {"error": "WorkflowResult not found"}

    workflow = db.workflow.find_one({"_id": result_doc.get("workflow")})
    if not workflow:
        return {"error": "Workflow not found"}

    output_config = workflow.get("output_config") or {}

    # Override with automation output_config if an enabled automation targets this workflow
    automation = db.automation.find_one({
        "action_type": "workflow",
        "action_id": str(workflow["_id"]),
        "enabled": True,
    })
    if automation and automation.get("output_config"):
        output_config = automation["output_config"]

    # Find associated work item (if any)
    work_item = None
    trigger_event = None
    if result_doc.get("trigger_type") in ("m365_intake", "folder_watch"):
        trigger_event = db.workflow_trigger_event.find_one({"result": result_doc["_id"]})
        if trigger_event:
            work_item = db.work_items.find_one({"trigger_event": trigger_event["_id"]})

    outputs = {"storage": None, "onedrive": None, "notifications": [], "webhooks": []}

    # 1. Local storage
    storage_cfg = output_config.get("storage", {})
    if storage_cfg.get("enabled"):
        try:
            path = save_results_to_folder(result_doc, storage_cfg)
            outputs["storage"] = {"status": "completed", "path": path}
            if trigger_event:
                db.workflow_trigger_event.update_one(
                    {"_id": trigger_event["_id"]},
                    {"$set": {
                        "output_delivery.storage_status": "completed",
                        "output_delivery.storage_path": path,
                    }},
                )
        except Exception as e:
            outputs["storage"] = {"status": "failed", "error": str(e)}
            if trigger_event:
                db.workflow_trigger_event.update_one(
                    {"_id": trigger_event["_id"]},
                    {"$set": {
                        "output_delivery.storage_status": "failed",
                        "output_delivery.storage_error": str(e),
                    }},
                )

    # 2. OneDrive case folder
    onedrive_cfg = output_config.get("onedrive", {})
    if onedrive_cfg.get("enabled"):
        try:
            folder_path = save_results_to_onedrive_channel(result_doc, onedrive_cfg, work_item)
            outputs["onedrive"] = {"status": "completed", "path": folder_path}
            if trigger_event:
                db.workflow_trigger_event.update_one(
                    {"_id": trigger_event["_id"]},
                    {"$set": {
                        "output_delivery.onedrive_status": "completed",
                        "output_delivery.onedrive_path": folder_path,
                    }},
                )
        except Exception as e:
            outputs["onedrive"] = {"status": "failed", "error": str(e)}
            if trigger_event:
                db.workflow_trigger_event.update_one(
                    {"_id": trigger_event["_id"]},
                    {"$set": {
                        "output_delivery.onedrive_status": "failed",
                        "output_delivery.onedrive_error": str(e),
                    }},
                )

    # 3. Notifications (email + Teams)
    for notification in output_config.get("notifications", []):
        try:
            if should_send_notification(result_doc, notification):
                send_workflow_notification(result_doc, notification, work_item_doc=work_item)
                nr = {
                    "channel": notification.get("channel"),
                    "recipients": notification.get("recipients"),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "status": "sent",
                }
                outputs["notifications"].append(nr)
                if trigger_event:
                    db.workflow_trigger_event.update_one(
                        {"_id": trigger_event["_id"]},
                        {"$push": {"output_delivery.notifications_sent": nr}},
                    )
        except Exception as e:
            nr = {"channel": notification.get("channel"), "status": "failed", "error": str(e)}
            outputs["notifications"].append(nr)
            if trigger_event:
                db.workflow_trigger_event.update_one(
                    {"_id": trigger_event["_id"]},
                    {"$push": {"output_delivery.notifications_sent": nr}},
                )

    # 4. Webhooks
    for webhook_cfg in output_config.get("webhooks", []):
        try:
            call_webhook(result_doc, webhook_cfg)
            wr = {"url": webhook_cfg.get("url"), "status": "sent"}
            outputs["webhooks"].append(wr)
            if trigger_event:
                db.workflow_trigger_event.update_one(
                    {"_id": trigger_event["_id"]},
                    {"$push": {"output_delivery.webhooks_called": wr}},
                )
        except Exception as e:
            wr = {"url": webhook_cfg.get("url"), "status": "failed", "error": str(e)}
            outputs["webhooks"].append(wr)

    # 5. Update work item status
    if work_item:
        new_status = "completed" if result_doc.get("status") == "completed" else "failed"
        db.work_items.update_one(
            {"_id": work_item["_id"]},
            {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc)}},
        )

    return outputs


# ---------------------------------------------------------------------------
# Beat task: cleanup old trigger events (daily)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.cleanup_old_trigger_events",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=10,
)
def cleanup_old_trigger_events(self) -> dict:
    """Delete completed/failed/skipped trigger events older than 30 days."""
    db = _get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    result = db.workflow_trigger_event.delete_many({
        "status": {"$in": ["completed", "failed", "skipped"]},
        "created_at": {"$lt": cutoff},
    })

    return {
        "deleted_count": result.deleted_count,
        "cutoff_date": cutoff.isoformat(),
    }
