#!/usr/bin/env python3
"""Celery tasks for passive workflow processing."""

from datetime import datetime, timedelta
from uuid import uuid4

from app import app, mail
from app.celery_worker import celery_app
from app.models import (
    Workflow,
    WorkflowResult,
    WorkflowStep,
    WorkflowTriggerEvent,
    SmartDocument,
)
from app.utilities.passive_triggers import (
    apply_file_filters,
    evaluate_conditions,
    check_workflow_budget,
    check_throttling,
)
from app.utilities.workflow import build_workflow_engine
from app.utilities.config import get_default_model_name


@celery_app.task(name="tasks.passive.process_pending_triggers")
def process_pending_triggers():
    """
    Process WorkflowTriggerEvents that are ready to execute.
    Runs every minute via Celery Beat.
    """
    
    now = datetime.utcnow()
    
    # Find pending events ready to process
    pending_events = WorkflowTriggerEvent.objects(
        status="pending",
        process_after__lte=now
    ).limit(100)  # Batch size
    
    processed_count = 0
    
    for event in pending_events:
        try:
            workflow = event.workflow
            
            if not workflow:
                event.status = "failed"
                event.error = "Workflow not found"
                event.save()
                continue
            
            # Check if folder watch is still enabled
            folder_watch_config = workflow.input_config.get("folder_watch", {})
            if not folder_watch_config.get("enabled"):
                event.status = "skipped"
                event.error = "Folder watch disabled"
                event.save()
                continue
            
            # Apply file filters
            file_filters = folder_watch_config.get("file_filters", {})
            filtered_docs = apply_file_filters(list(event.documents), file_filters)
            
            if not filtered_docs:
                event.status = "skipped"
                event.error = "No documents passed file filters"
                event.save()
                continue
            
            # Apply conditions
            conditions = workflow.input_config.get("conditions", [])
            if not evaluate_conditions(filtered_docs, conditions):
                event.status = "skipped"
                event.error = "Documents did not meet conditions"
                event.save()
                continue
            
            # Check budget
            can_run, budget_reason = check_workflow_budget(workflow)
            if not can_run:
                event.status = "skipped"
                event.error = budget_reason
                event.save()
                continue
            
            # Check throttling
            can_run, throttle_reason = check_throttling(workflow)
            if not can_run:
                # Re-queue for later
                event.process_after = now + timedelta(seconds=60)
                event.save()
                continue
            
            # Queue execution
            event.status = "queued"
            event.queued_at = now
            event.documents = filtered_docs
            event.document_count = len(filtered_docs)
            event.save()
            
            execute_workflow_passive.delay(str(event.id))
            processed_count += 1
            
        except Exception as e:
            event.status = "failed"
            event.error = f"Processing error: {str(e)}"
            event.save()
    
    return {"processed": processed_count, "timestamp": now.isoformat()}


@celery_app.task(name="tasks.passive.execute_workflow_passive")
def execute_workflow_passive(trigger_event_id):
    """Execute a workflow for a passive trigger."""
    
    event = WorkflowTriggerEvent.objects(id=trigger_event_id).first()
    if not event:
        return {"error": "Trigger event not found"}
    
    workflow = event.workflow
    if not workflow:
        event.status = "failed"
        event.error = "Workflow not found"
        event.save()
        return {"error": "Workflow not found"}
    
    try:
        # Update status
        event.status = "running"
        event.started_at = datetime.utcnow()
        event.save()
        
        # Create WorkflowResult
        result = WorkflowResult(
            workflow=workflow,
            session_id=uuid4().hex,
            status="running",
            trigger_event=event,
            trigger_type=event.trigger_type,
            is_passive=True,
            input_context=event.trigger_context or {}
        )
        result.save()
        
        # Prepare document trigger step
        docs = list(event.documents)
        document_trigger_step = WorkflowStep(
            name="Document",
            data={"docs": docs, "user_id": workflow.user_id}
        )
        document_trigger_step.save()
        
        # Build steps
        steps = [document_trigger_step] + list(workflow.steps)
        
        # Execute workflow (reuse existing engine)
        model = get_default_model_name()
        
        engine = build_workflow_engine(steps, workflow, model, user_id=workflow.user_id)
        final_output, data = engine.execute(result)
        
        # Update result
        result.final_output = {"output": final_output, "data": data}
        result.status = "completed"
        result.save()
        
        # Update event
        event.status = "completed"
        event.completed_at = datetime.utcnow()
        event.duration_ms = int((event.completed_at - event.started_at).total_seconds() * 1000)
        event.workflow_result = result
        event.documents_succeeded = len(event.documents)
        event.save()
        
        # Update workflow stats
        stats = workflow.stats or {}
        stats["total_runs"] = stats.get("total_runs", 0) + 1
        stats["passive_runs"] = stats.get("passive_runs", 0) + 1
        stats["successful_runs"] = stats.get("successful_runs", 0) + 1
        stats["documents_processed"] = stats.get("documents_processed", 0) + len(event.documents)
        stats["last_run_at"] = event.completed_at
        stats["last_passive_run_at"] = event.completed_at
        workflow.stats = stats
        workflow.save()
        
        # Process outputs (async)
        process_outputs.delay(str(result.id))
        
        return {
            "status": "completed",
            "workflow_result_id": str(result.id),
            "event_id": str(event.id)
        }
        
    except Exception as e:
        event.status = "failed"
        event.completed_at = datetime.utcnow()
        event.error = str(e)
        
        if event.started_at:
            event.duration_ms = int((event.completed_at - event.started_at).total_seconds() * 1000)
        
        event.save()
        
        # Update workflow stats for failure
        stats = workflow.stats or {}
        stats["total_runs"] = stats.get("total_runs", 0) + 1
        stats["passive_runs"] = stats.get("passive_runs", 0) + 1
        stats["failed_runs"] = stats.get("failed_runs", 0) + 1
        workflow.stats = stats
        workflow.save()
        
        # Check retry
        retry_config = workflow.resource_config.get("retry", {})
        max_retries = retry_config.get("max_retries", 3)
        
        if event.attempt_number < max_retries:
            event.attempt_number += 1
            event.status = "pending"
            retry_delay = retry_config.get("retry_delay_seconds", 300)
            event.process_after = datetime.utcnow() + timedelta(seconds=retry_delay)
            event.next_retry_at = event.process_after
            event.save()
            
            return {
                "status": "retry_scheduled",
                "attempt": event.attempt_number,
                "next_retry": event.next_retry_at.isoformat()
            }
        
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="tasks.passive.process_outputs")
def process_outputs(workflow_result_id):
    """Process output configuration after workflow completes."""
    
    from app.utilities.output_handlers import (
        save_results_to_folder,
        send_workflow_notification,
        should_send_notification,
    )
    
    result = WorkflowResult.objects(id=workflow_result_id).first()
    if not result:
        return {"error": "WorkflowResult not found"}
    
    workflow = result.workflow
    if not workflow:
        return {"error": "Workflow not found"}
    
    output_config = workflow.output_config or {}
    event = result.trigger_event
    
    outputs_processed = {
        "storage": None,
        "notifications": []
    }
    
    # 1. Storage
    storage_config = output_config.get("storage", {})
    if storage_config.get("enabled"):
        try:
            path = save_results_to_folder(result, storage_config)
            outputs_processed["storage"] = {"status": "completed", "path": path}
            
            if event:
                event.output_delivery["storage_status"] = "completed"
                event.output_delivery["storage_path"] = path
                event.save()
        except Exception as e:
            outputs_processed["storage"] = {"status": "failed", "error": str(e)}
            
            if event:
                event.output_delivery["storage_status"] = "failed"
                event.output_delivery["storage_error"] = str(e)
                event.save()
    
    # 2. Notifications
    notifications = output_config.get("notifications", [])
    for notification in notifications:
        try:
            if should_send_notification(result, notification):
                send_workflow_notification(result, notification)
                
                notification_result = {
                    "channel": notification.get("channel"),
                    "recipients": notification.get("recipients"),
                    "sent_at": datetime.utcnow().isoformat(),
                    "status": "sent"
                }
                outputs_processed["notifications"].append(notification_result)
                
                if event:
                    event.output_delivery["notifications_sent"].append(notification_result)
                    event.save()
        except Exception as e:
            notification_result = {
                "channel": notification.get("channel"),
                "status": "failed",
                "error": str(e)
            }
            outputs_processed["notifications"].append(notification_result)
            
            if event:
                event.output_delivery["notifications_sent"].append(notification_result)
                event.save()
    
    return outputs_processed


@celery_app.task(name="tasks.passive.cleanup_old_trigger_events")
def cleanup_old_trigger_events():
    """Clean up old completed/failed trigger events. Runs daily."""
    
    # Delete events older than 30 days
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    
    deleted_count = WorkflowTriggerEvent.objects(
        status__in=["completed", "failed", "skipped"],
        created_at__lt=cutoff_date
    ).delete()
    
    return {
        "deleted_count": deleted_count,
        "cutoff_date": cutoff_date.isoformat(),
        "timestamp": datetime.utcnow().isoformat()
    }
