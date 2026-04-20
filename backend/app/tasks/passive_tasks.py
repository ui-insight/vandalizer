"""Celery tasks for passive workflow trigger processing.

Ported from Flask app/utilities/passive_tasks.py.
Uses pymongo (sync) for DB access.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from bson import ObjectId

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS, get_sync_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Beat task: process pending triggers (every 60s)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.process_pending_triggers",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
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

    db = get_sync_db()
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
# Beat task: process scheduled automations (every 60s)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.process_scheduled_automations",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=10,
)
def process_scheduled_automations(self) -> dict:
    """Evaluate schedule-based automations and create trigger events when due.

    Runs every minute via Celery Beat.
    """
    try:
        from croniter import croniter
    except ImportError:
        logger.warning("croniter not installed — schedule triggers disabled")
        return {"processed": 0, "error": "croniter not installed"}

    db = get_sync_db()
    now = datetime.now(timezone.utc)
    processed = 0

    automations = list(db.automation.find({
        "enabled": True,
        "trigger_type": "schedule",
    }))

    for auto in automations:
        try:
            action_id = auto.get("action_id")
            if not action_id:
                continue

            trigger_config = auto.get("trigger_config") or {}
            cron_expr = trigger_config.get("cron_expression")
            if not cron_expr:
                continue

            # Determine last run time for this automation
            last_event = db.workflow_trigger_event.find_one(
                {
                    "trigger_context.automation_id": str(auto["_id"]),
                    "trigger_type": "schedule",
                },
                sort=[("created_at", -1)],
            )

            if last_event:
                base_time = last_event["created_at"]
                if base_time.tzinfo is None:
                    base_time = base_time.replace(tzinfo=timezone.utc)
            else:
                # First run — use automation creation time as base
                base_time = auto.get("created_at", now - timedelta(minutes=2))
                if base_time.tzinfo is None:
                    base_time = base_time.replace(tzinfo=timezone.utc)

            cron = croniter(cron_expr, base_time)
            next_run = cron.get_next(datetime)
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=timezone.utc)

            if next_run > now:
                continue  # Not due yet

            # Gather documents from trigger_config
            doc_uuids = trigger_config.get("document_uuids", [])
            folder_id = trigger_config.get("folder_id")

            doc_oids = []
            if doc_uuids:
                docs = list(db.smart_document.find(
                    {"uuid": {"$in": doc_uuids}},
                    {"_id": 1},
                ))
                doc_oids = [d["_id"] for d in docs]
            elif folder_id:
                docs = list(db.smart_document.find(
                    {"folder": folder_id, "processing": False},
                    {"_id": 1},
                ))
                doc_oids = [d["_id"] for d in docs]

            if auto.get("action_type") in ("workflow", "task"):
                event = {
                    "uuid": uuid4().hex,
                    "workflow": ObjectId(action_id),
                    "trigger_type": "schedule",
                    "status": "pending",
                    "documents": doc_oids,
                    "document_count": len(doc_oids),
                    "trigger_context": {
                        "automation_id": str(auto["_id"]),
                        "automation_name": auto.get("name", ""),
                        "cron_expression": cron_expr,
                    },
                    "created_at": now,
                    "process_after": now,
                    "attempt_number": 1,
                    "max_attempts": 3,
                    "output_delivery": {
                        "storage_status": None,
                        "notifications_sent": [],
                        "webhooks_called": [],
                        "chains_triggered": [],
                    },
                }
                db.workflow_trigger_event.insert_one(event)
                processed += 1
                logger.info(
                    "Created schedule trigger for automation '%s' (workflow %s)",
                    auto.get("name"), action_id,
                )

            elif auto.get("action_type") == "extraction":
                # Dispatch extraction via Celery task
                doc_uuid_list = []
                if doc_oids:
                    docs = list(db.smart_document.find(
                        {"_id": {"$in": doc_oids}},
                        {"uuid": 1},
                    ))
                    doc_uuid_list = [d["uuid"] for d in docs]

                if doc_uuid_list:
                    process_extraction_outputs.delay(
                        automation_id=str(auto["_id"]),
                        search_set_uuid=action_id,
                        document_uuids=doc_uuid_list,
                        user_id=auto.get("user_id", ""),
                    )
                    processed += 1

        except Exception as e:
            logger.error(
                "Error processing scheduled automation %s: %s",
                auto.get("name"), e,
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

    db = get_sync_db()
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

        # Check if the workflow owner is an admin (gates code execution)
        wf_user_id = workflow.get("user_id")
        wf_user_doc = db.user.find_one({"user_id": wf_user_id}) if wf_user_id else None
        wf_is_admin = bool(wf_user_doc and wf_user_doc.get("is_admin"))

        engine = build_workflow_engine(
            steps_data=steps_data,
            model=model,
            user_id=wf_user_id,
            system_config_doc=sys_config,
            allow_code_execution=wf_is_admin,
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
                "workflow_result": result_id,
                "documents_succeeded": len(doc_ids),
                "documents_failed": 0,
                "tokens_input": engine.usage.tokens_in,
                "tokens_output": engine.usage.tokens_out,
                "total_tokens": engine.usage.tokens_in + engine.usage.tokens_out,
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

        doc_ids = event.get("documents", [])
        db.workflow_trigger_event.update_one(
            {"_id": event["_id"]},
            {"$set": {
                "status": "failed",
                "completed_at": completed_at,
                "duration_ms": duration_ms,
                "error": str(e),
                "documents_succeeded": 0,
                "documents_failed": len(doc_ids),
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

        # Retries exhausted — deliver failure callback if configured
        ctx = event.get("trigger_context") or {}
        cb_url = ctx.get("callback_url")
        if cb_url:
            fail_now = datetime.now(timezone.utc)
            deliver_callback.delay(
                trigger_event_id=str(event["_id"]),
                callback_url=cb_url,
                payload={
                    "event": "automation.failed",
                    "trigger_event_id": str(event["_id"]),
                    "automation_id": ctx.get("automation_id", ""),
                    "action_type": "workflow",
                    "status": "failed",
                    "output": None,
                    "error": str(e),
                    "completed_at": fail_now.isoformat(),
                    "timestamp": fail_now.isoformat(),
                },
                user_id=workflow.get("user_id", ""),
            )

        return {"status": "failed", "error": str(e)}


# ---------------------------------------------------------------------------
# Process outputs (storage, notifications, webhooks, chains)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.process_outputs",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
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
    from app.services.passive_triggers import create_chain_trigger

    db = get_sync_db()
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

    # Find associated trigger event and work item
    work_item = None
    trigger_event = db.workflow_trigger_event.find_one({"workflow_result": result_doc["_id"]})
    if trigger_event:
        work_item = db.work_items.find_one({"trigger_event": trigger_event["_id"]})

    outputs = {"storage": None, "onedrive": None, "notifications": [], "webhooks": [], "chains": []}

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

    # 5. Chain triggers — dispatch to downstream workflows
    for chain_cfg in output_config.get("chains", []):
        target_workflow_id = chain_cfg.get("workflow_id")
        if not target_workflow_id:
            continue
        try:
            target_wf = db.workflow.find_one({"_id": ObjectId(target_workflow_id)})
            if not target_wf:
                logger.warning("Chain target workflow %s not found", target_workflow_id)
                continue

            # Pass the same documents to the chained workflow
            source_doc_ids = trigger_event.get("documents", []) if trigger_event else []
            chain_event = create_chain_trigger(
                source_event=trigger_event or {"uuid": str(result_doc.get("_id")), "workflow": workflow["_id"]},
                target_workflow_id=target_workflow_id,
                document_oids=source_doc_ids,
                automation_id=chain_cfg.get("automation_id"),
                automation_name=chain_cfg.get("automation_name"),
            )
            if chain_event:
                cr = {
                    "target_workflow_id": target_workflow_id,
                    "trigger_event_id": str(chain_event["_id"]),
                    "status": "created",
                }
                outputs["chains"].append(cr)
                if trigger_event:
                    db.workflow_trigger_event.update_one(
                        {"_id": trigger_event["_id"]},
                        {"$push": {"output_delivery.chains_triggered": cr}},
                    )
            else:
                outputs["chains"].append({
                    "target_workflow_id": target_workflow_id,
                    "status": "skipped",
                    "error": "Max chain depth exceeded",
                })
        except Exception as e:
            outputs["chains"].append({
                "target_workflow_id": target_workflow_id,
                "status": "failed",
                "error": str(e),
            })

    # 6. Per-request callback URL
    if trigger_event:
        cb_url = (trigger_event.get("trigger_context") or {}).get("callback_url")
        if cb_url:
            auto_ctx = trigger_event.get("trigger_context") or {}
            now = datetime.now(timezone.utc)
            deliver_callback.delay(
                trigger_event_id=str(trigger_event["_id"]),
                callback_url=cb_url,
                payload={
                    "event": "automation.completed" if result_doc.get("status") == "completed" else "automation.failed",
                    "trigger_event_id": str(trigger_event["_id"]),
                    "automation_id": auto_ctx.get("automation_id", ""),
                    "action_type": "workflow",
                    "status": result_doc.get("status", "completed"),
                    "output": (result_doc.get("final_output") or {}).get("output"),
                    "error": result_doc.get("error"),
                    "completed_at": now.isoformat(),
                    "timestamp": now.isoformat(),
                },
                user_id=workflow.get("user_id", ""),
            )

    # 7. Update work item status
    if work_item:
        new_status = "completed" if result_doc.get("status") == "completed" else "failed"
        db.work_items.update_one(
            {"_id": work_item["_id"]},
            {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc)}},
        )

    # 8. Clean up temporary API text-input documents
    if trigger_event:
        temp_uuids = (trigger_event.get("trigger_context") or {}).get("temp_doc_uuids", [])
        if temp_uuids:
            db.smart_document.delete_many({"uuid": {"$in": temp_uuids}})

    return outputs


# ---------------------------------------------------------------------------
# Process extraction outputs (async, for API-triggered extractions)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.process_extraction_outputs",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=10,
)
def process_extraction_outputs(
    self,
    automation_id: str,
    search_set_uuid: str,
    document_uuids: list[str],
    user_id: str,
    *,
    results: dict | None = None,
    extraction_event_id: str | None = None,
) -> dict:
    """Run extraction and/or process output_config for an automation.

    If *results* is None, runs the extraction first (used by schedule triggers).
    If *results* is provided, just processes outputs (used by API triggers).
    """
    from app.services.output_handlers import (
        call_webhook,
        save_extraction_results_to_folder,
        send_workflow_notification,
        should_send_notification,
    )

    db = get_sync_db()
    auto = db.automation.find_one({"_id": ObjectId(automation_id)})
    if not auto:
        if extraction_event_id:
            db.extraction_trigger_event.update_one(
                {"_id": ObjectId(extraction_event_id)},
                {"$set": {"status": "failed", "error": "Automation not found",
                          "completed_at": datetime.now(timezone.utc)}},
            )
        return {"error": "Automation not found"}

    # Mark extraction event as running
    ext_started_at = datetime.now(timezone.utc)
    if extraction_event_id:
        db.extraction_trigger_event.update_one(
            {"_id": ObjectId(extraction_event_id)},
            {"$set": {"status": "running", "started_at": ext_started_at}},
        )

    # Run extraction if results not provided
    if results is None:
        from app.services.extraction_engine import ExtractionEngine

        sys_config = db.system_config.find_one() or {}

        ss_doc = db.search_set.find_one({"uuid": search_set_uuid})
        extraction_config = (ss_doc or {}).get("extraction_config") or {}
        domain = (ss_doc or {}).get("domain")

        ss_items = list(db.search_set_item.find({
            "searchset": search_set_uuid,
            "searchtype": "extraction",
        }))
        keys = [item["searchphrase"] for item in ss_items]
        if not keys:
            if extraction_event_id:
                db.extraction_trigger_event.update_one(
                    {"_id": ObjectId(extraction_event_id)},
                    {"$set": {"status": "failed", "error": "No extraction keys found",
                              "completed_at": datetime.now(timezone.utc)}},
                )
            return {"error": "No extraction keys found"}

        field_metadata = [
            {"key": item["searchphrase"],
             "is_optional": item.get("is_optional", False),
             "enum_values": item.get("enum_values", [])}
            for item in ss_items
        ]

        # Wait for any documents still being processed (e.g. file uploads
        # where text extraction hasn't finished yet) before running the
        # LLM extraction.  Poll with back-off up to ~90 seconds.
        import time
        _PROCESSING_POLL_INTERVAL = 3  # seconds
        _PROCESSING_TIMEOUT = 90  # seconds
        _waited = 0
        while _waited < _PROCESSING_TIMEOUT:
            still_processing = db.smart_document.count_documents({
                "uuid": {"$in": document_uuids},
                "processing": True,
            })
            if still_processing == 0:
                break
            logger.info(
                "Waiting for %d document(s) to finish processing (%ds elapsed)",
                still_processing, _waited,
            )
            time.sleep(_PROCESSING_POLL_INTERVAL)
            _waited += _PROCESSING_POLL_INTERVAL

        results = []
        for doc_uuid in document_uuids:
            doc = db.smart_document.find_one({"uuid": doc_uuid})
            if not doc or not doc.get("raw_text"):
                logger.warning("Skipping doc %s: no raw_text available", doc_uuid)
                continue
            try:
                engine = ExtractionEngine(system_config_doc=sys_config, domain=domain)
                doc_results = engine.extract(
                    extract_keys=keys,
                    full_text=doc["raw_text"],
                    extraction_config_override=extraction_config,
                    field_metadata=field_metadata,
                )
                for entity in doc_results:
                    entity["document_id"] = doc_uuid
                    results.append(entity)
            except Exception as e:
                logger.error("Extraction failed for doc %s: %s", doc_uuid, e)
                results.append({"document_id": doc_uuid, "error": str(e)})

    output_config = auto.get("output_config") or {}
    if not output_config:
        if extraction_event_id:
            db.extraction_trigger_event.update_one(
                {"_id": ObjectId(extraction_event_id)},
                {"$set": {
                    "status": "completed",
                    "result": results,
                    "completed_at": datetime.now(timezone.utc),
                }},
            )
        return {"status": "completed", "results": results}

    automation_dict = {
        "name": auto.get("name"),
        "user_id": auto.get("user_id"),
        "trigger_type": auto.get("trigger_type"),
        "_id": auto["_id"],
    }

    result_doc = {
        "status": "completed",
        "trigger_type": auto.get("trigger_type", "api"),
        "final_output": {"output": results},
    }

    outputs = {"storage": None, "notifications": [], "webhooks": []}

    # Storage
    storage_cfg = output_config.get("storage", {})
    if storage_cfg.get("enabled"):
        try:
            path = save_extraction_results_to_folder(results, automation_dict, storage_cfg)
            outputs["storage"] = {"status": "completed", "path": path}
        except Exception as e:
            logger.error("Failed to save extraction results: %s", e)
            outputs["storage"] = {"status": "failed", "error": str(e)}

    # Notifications
    for notification in output_config.get("notifications", []):
        try:
            if should_send_notification(result_doc, notification):
                send_workflow_notification(result_doc, notification)
                outputs["notifications"].append({
                    "channel": notification.get("channel"),
                    "status": "sent",
                })
        except Exception as e:
            outputs["notifications"].append({
                "channel": notification.get("channel"),
                "status": "failed",
                "error": str(e),
            })

    # Webhooks
    for webhook_cfg in output_config.get("webhooks", []):
        try:
            call_webhook(result_doc, webhook_cfg)
            outputs["webhooks"].append({"url": webhook_cfg.get("url"), "status": "sent"})
        except Exception as e:
            outputs["webhooks"].append({
                "url": webhook_cfg.get("url"),
                "status": "failed",
                "error": str(e),
            })

    # Persist results and mark extraction event as completed
    if extraction_event_id:
        now = datetime.now(timezone.utc)
        duration_ms = int((now - ext_started_at).total_seconds() * 1000) if ext_started_at else None
        db.extraction_trigger_event.update_one(
            {"_id": ObjectId(extraction_event_id)},
            {"$set": {
                "status": "completed",
                "result": results,
                "completed_at": now,
                "duration_ms": duration_ms,
            }},
        )

        # Deliver per-request callback and clean up temp docs
        ext_event = db.extraction_trigger_event.find_one({"_id": ObjectId(extraction_event_id)})
        trigger_ctx = (ext_event.get("trigger_context") or {}) if ext_event else {}

        # Clean up temporary API text-input documents
        temp_uuids = trigger_ctx.get("temp_doc_uuids", [])
        if temp_uuids:
            db.smart_document.delete_many({"uuid": {"$in": temp_uuids}})

        cb_url = trigger_ctx.get("callback_url")
        if cb_url:
            deliver_callback.delay(
                trigger_event_id=extraction_event_id,
                callback_url=cb_url,
                payload={
                    "event": "automation.completed",
                    "trigger_event_id": extraction_event_id,
                    "automation_id": automation_id,
                    "action_type": "extraction",
                    "status": "completed",
                    "output": results,
                    "completed_at": now.isoformat(),
                    "timestamp": now.isoformat(),
                },
                user_id=user_id,
            )

    return {"status": "completed", "outputs": outputs}


# ---------------------------------------------------------------------------
# Deliver per-request callback with retries + HMAC signing
# ---------------------------------------------------------------------------


CALLBACK_RETRY_DELAYS = [10, 30, 90, 270, 810]


@celery_app.task(
    bind=True,
    name="tasks.passive.deliver_callback",
    max_retries=5,
    default_retry_delay=10,
)
def deliver_callback(
    self,
    trigger_event_id: str,
    callback_url: str,
    payload: dict,
    user_id: str,
) -> dict:
    """POST results to a caller-provided callback URL with HMAC signing and retries."""
    import json

    import httpx

    from app.services.output_handlers import compute_webhook_signature
    from app.utils.url_validation import validate_outbound_url

    try:
        validate_outbound_url(callback_url)
    except ValueError as e:
        logger.error("Invalid callback_url for event %s: %s", trigger_event_id, e)
        return {"status": "rejected", "error": str(e)}

    # Sign with the stored API-token hash. Receivers derive the signing
    # secret from their plaintext token via sha256(token) — the server never
    # stores plaintext, so the hash is the only shared value available.
    db = get_sync_db()
    user = db.user.find_one({"user_id": user_id})
    signing_secret = (user.get("api_token_hash") or "") if user else ""

    payload_bytes = json.dumps(payload, default=str).encode("utf-8")

    headers = {"Content-Type": "application/json", "X-Webhook-Id": trigger_event_id}
    if signing_secret:
        headers["X-Webhook-Signature"] = compute_webhook_signature(payload_bytes, signing_secret)

    try:
        resp = httpx.post(callback_url, content=payload_bytes, headers=headers, timeout=15.0)
        resp.raise_for_status()
        return {"status": "delivered", "http_status": resp.status_code}
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
        delay = CALLBACK_RETRY_DELAYS[min(self.request.retries, len(CALLBACK_RETRY_DELAYS) - 1)]
        logger.warning(
            "Callback delivery failed for %s (attempt %d): %s — retrying in %ds",
            trigger_event_id, self.request.retries + 1, exc, delay,
        )
        raise self.retry(exc=exc, countdown=delay)


# ---------------------------------------------------------------------------
# Beat task: cleanup old trigger events (daily)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="tasks.passive.cleanup_old_trigger_events",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=10,
)
def cleanup_old_trigger_events(self) -> dict:
    """Delete completed/failed/skipped trigger events older than 30 days."""
    db = get_sync_db()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    result = db.workflow_trigger_event.delete_many({
        "status": {"$in": ["completed", "failed", "skipped"]},
        "created_at": {"$lt": cutoff},
    })

    return {
        "deleted_count": result.deleted_count,
        "cutoff_date": cutoff.isoformat(),
    }
