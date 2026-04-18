"""Celery tasks for workflow execution.

Uses pymongo (sync) for DB access  - same pattern as Flask Celery workers.
Task names use 'tasks.workflow_next.*' to coexist with Flask's 'tasks.workflow.*'.
"""

import logging

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)


def _notify_approval_reviewers_sync(
    db, assigned_user_ids: list[str], workflow_name: str,
    step_name: str, instructions: str, approval_uuid: str,
) -> None:
    """Create in-app notifications and send emails to assigned reviewers (sync context)."""
    import secrets
    from datetime import datetime, timezone
    from app.config import Settings

    settings = Settings()
    now = datetime.now(timezone.utc)

    for user_id in assigned_user_ids:
        # In-app notification
        db.notification.insert_one({
            "uuid": secrets.token_urlsafe(12),
            "user_id": user_id,
            "kind": "approval_request",
            "title": f"Approval needed: {workflow_name}",
            "body": f"Step \"{step_name}\" is waiting for your review.",
            "link": f"/approvals?id={approval_uuid}",
            "read": False,
            "created_at": now,
        })

        # Email
        user_doc = db.user.find_one({"user_id": user_id})
        if user_doc and user_doc.get("email"):
            from app.services.email_service import approval_request_email, send_email
            import asyncio

            subject, html = approval_request_email(
                reviewer_name=user_doc.get("name", user_id),
                workflow_name=workflow_name,
                step_name=step_name,
                instructions=instructions,
                approval_uuid=approval_uuid,
                frontend_url=settings.frontend_url,
            )
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(send_email(user_doc["email"], subject, html, settings))
                loop.close()
            except Exception:
                logger.exception("Failed to send approval email to %s", user_id)


def _get_db():
    """Get sync pymongo database handle."""
    from pymongo import MongoClient

    from app.config import Settings
    settings = Settings()
    client = MongoClient(settings.mongo_host)
    return client[settings.mongo_db]


@celery_app.task(
    bind=True,
    name="tasks.workflow_next.execution",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    rate_limit="1/s",
    max_retries=3,
    default_retry_delay=5,
)
def execute_workflow_task(self, workflow_result_id, workflow_id, trigger_step_data, model, activity_id=None):
    """Execute a full workflow.

    Args:
        workflow_result_id: WorkflowResult document ID (str).
        workflow_id: Workflow document ID (str).
        trigger_step_data: Dict with 'doc_uuids' for the Document trigger step.
        model: LLM model name.
        activity_id: Optional ActivityEvent ID to track this run in the rail.
    """
    from bson import ObjectId

    from app.services.workflow_engine import build_workflow_engine

    db = _get_db()

    # Load workflow and result
    workflow_doc = db.workflow.find_one({"_id": ObjectId(workflow_id)})
    result_doc = db.workflow_result.find_one({"_id": ObjectId(workflow_result_id)})

    if not workflow_doc or not result_doc:
        raise ValueError(f"Workflow {workflow_id} or result {workflow_result_id} not found")

    # Load system config for sync engine
    sys_config = db.system_config.find_one() or {}

    # Build steps data from workflow steps
    steps_data = [{"name": "Document", "data": trigger_step_data, "tasks": []}]

    for step_id in workflow_doc.get("steps", []):
        step_doc = db.workflow_step.find_one({"_id": step_id})
        if not step_doc:
            continue

        tasks = []
        for task_id in step_doc.get("tasks", []):
            task_doc = db.workflow_step_task.find_one({"_id": task_id})
            if task_doc:
                # Resolve extraction keys from search set
                task_data = dict(task_doc.get("data", {}))
                if task_doc.get("name") == "Extraction" and task_data.get("search_set_uuid"):
                    ss = db.search_set.find_one({"uuid": task_data["search_set_uuid"]})
                    if ss:
                        items = list(db.search_set_item.find({
                            "searchset": task_data["search_set_uuid"],
                            "searchtype": "extraction",
                        }))
                        task_data["keys"] = [item["searchphrase"] for item in items]

                # Pre-load doc texts for extraction and prompt nodes
                doc_uuids = list(trigger_step_data.get("doc_uuids", []))

                # Merge fixed documents from workflow input_config
                fixed_doc_config = (workflow_doc.get("input_config") or {}).get("fixed_documents", [])
                for fd in fixed_doc_config:
                    fd_uuid = fd.get("uuid") if isinstance(fd, dict) else str(fd)
                    if fd_uuid and fd_uuid not in doc_uuids:
                        doc_uuids.append(fd_uuid)

                if doc_uuids:
                    doc_texts = []
                    for uuid in doc_uuids:
                        doc = db.smart_document.find_one({"uuid": uuid})
                        if doc and doc.get("raw_text"):
                            doc_texts.append(doc["raw_text"])
                        else:
                            logger.warning(
                                "Document %s has no raw_text — it may still be processing or text extraction failed",
                                uuid,
                            )
                    if not doc_texts:
                        logger.error(
                            "None of the %d input documents have raw_text available — workflow will produce no output",
                            len(doc_uuids),
                        )
                    task_data["doc_texts"] = doc_texts

                # Pre-load specific document text when input_source is "select_document"
                if task_data.get("input_source") == "select_document" and task_data.get("selected_document_uuid"):
                    sel_doc = db.smart_document.find_one({"uuid": task_data["selected_document_uuid"]})
                    if sel_doc and sel_doc.get("raw_text"):
                        task_data["selected_doc_text"] = sel_doc["raw_text"]

                tasks.append({"name": task_doc.get("name", ""), "data": task_data})

        steps_data.append({
            "name": step_doc.get("name", ""),
            "data": step_doc.get("data", {}),
            "tasks": tasks,
        })

    user_id = workflow_doc.get("user_id")

    # Check if the user is an admin (gates code execution)
    user_doc = db.user.find_one({"user_id": user_id}) if user_id else None
    is_admin = bool(user_doc and user_doc.get("is_admin"))

    # Update result to running
    db.workflow_result.update_one(
        {"_id": ObjectId(workflow_result_id)},
        {"$set": {
            "status": "running",
            "num_steps_completed": 0,
            "num_steps_total": len(steps_data) - 1,
            "steps_output": {},
        }},
    )

    # Progress updater using pymongo
    def update_progress(updates: dict):
        set_ops = {}
        for k, v in updates.items():
            set_ops[k] = v
        if set_ops:
            db.workflow_result.update_one(
                {"_id": ObjectId(workflow_result_id)},
                {"$set": set_ops},
            )

    engine = build_workflow_engine(
        steps_data=steps_data,
        model=model,
        user_id=user_id,
        system_config_doc=sys_config,
        allow_code_execution=is_admin,
    )

    # Mark activity as running
    if activity_id:
        try:
            db.activity_event.update_one(
                {"_id": ObjectId(activity_id)},
                {"$set": {"status": "running"}},
            )
        except Exception as e:
            logger.warning("Could not update activity to running: %s", e)

    try:
        final_output, data = engine.execute(workflow_result_updater=update_progress)
    except Exception as e:
        logger.error("Workflow execution failed for %s: %s", workflow_id, e)
        db.workflow_result.update_one(
            {"_id": ObjectId(workflow_result_id)},
            {"$set": {"status": "error", "error": str(e)}},
        )
        if activity_id:
            try:
                from datetime import datetime, timezone
                db.activity_event.update_one(
                    {"_id": ObjectId(activity_id)},
                    {"$set": {"status": "failed", "error": str(e)[:2000], "finished_at": datetime.now(timezone.utc)}},
                )
            except Exception:
                pass
        raise

    # Check if workflow paused for approval
    if isinstance(final_output, dict) and final_output.get("_approval_pause"):
        import uuid as uuid_mod

        # Find the step index (count of executed steps)
        nodes = engine.get_topological_order()
        step_index = 0
        for idx, node in enumerate(nodes):
            if node.name == "Approval":
                step_index = idx
                break

        approval_uuid = str(uuid_mod.uuid4())
        from datetime import datetime, timezone
        db.approval_request.insert_one({
            "uuid": approval_uuid,
            "workflow_result_id": ObjectId(workflow_result_id),
            "workflow_id": ObjectId(workflow_id),
            "step_index": step_index,
            "step_name": "Approval",
            "data_for_review": final_output.get("_data_for_review", {}),
            "review_instructions": final_output.get("_review_instructions", ""),
            "status": "pending",
            "assigned_to_user_ids": final_output.get("_assigned_to_user_ids", []),
            "created_at": datetime.now(timezone.utc),
        })

        db.workflow_result.update_one(
            {"_id": ObjectId(workflow_result_id)},
            {"$set": {
                "status": "pending_approval",
                "paused_at_step_index": step_index,
                "approval_request_id": approval_uuid,
                "current_step_name": "Approval",
                "current_step_detail": "Waiting for human review",
            }},
        )

        # Notify assigned reviewers
        workflow_doc = db.workflow.find_one({"_id": ObjectId(workflow_id)})
        workflow_name = workflow_doc.get("name", "Workflow") if workflow_doc else "Workflow"
        assigned_ids = final_output.get("_assigned_to_user_ids", [])
        review_instructions = final_output.get("_review_instructions", "")
        _notify_approval_reviewers_sync(
            db, assigned_ids, workflow_name, "Approval",
            review_instructions, approval_uuid,
        )

        return {
            "status": "pending_approval",
            "approval_uuid": approval_uuid,
            "result_id": workflow_result_id,
        }

    # Save final result
    db.workflow_result.update_one(
        {"_id": ObjectId(workflow_result_id)},
        {"$set": {
            "status": "completed",
            "final_output": {"output": final_output, "data": data},
        }},
    )

    # Increment workflow execution count
    db.workflow.update_one(
        {"_id": ObjectId(workflow_id)},
        {"$inc": {"num_executions": 1}},
    )

    # Update activity and generate AI title
    if activity_id:
        try:
            from datetime import datetime, timezone
            doc_uuids = trigger_step_data.get("doc_uuids", [])
            # Read step counts from the WorkflowResult
            wr_doc = db.workflow_result.find_one(
                {"_id": ObjectId(workflow_result_id)},
                {"num_steps_completed": 1, "num_steps_total": 1},
            )
            usage_update = {
                "status": "completed",
                "finished_at": datetime.now(timezone.utc),
                "last_updated_at": datetime.now(timezone.utc),
                "workflow_result": ObjectId(workflow_result_id),
                "tokens_input": engine.usage.tokens_in,
                "tokens_output": engine.usage.tokens_out,
                "total_tokens": engine.usage.tokens_in + engine.usage.tokens_out,
                "steps_completed": (wr_doc or {}).get("num_steps_completed", 0),
                "steps_total": (wr_doc or {}).get("num_steps_total", 0),
            }
            db.activity_event.update_one(
                {"_id": ObjectId(activity_id)},
                {"$set": usage_update},
            )
            from app.tasks.activity_tasks import generate_activity_description_task
            generate_activity_description_task.delay(activity_id, "workflow_run", doc_uuids)
        except Exception as e:
            logger.warning("Could not finalize activity for workflow %s: %s", workflow_id, e)

    # Fire-and-forget auto-validation if validation plan exists
    from app.tasks.quality_tasks import auto_validate_workflow
    auto_validate_workflow.delay(workflow_id)

    return {
        "status": "completed",
        "result_id": workflow_result_id,
        "workflow_id": workflow_id,
    }


@celery_app.task(
    bind=True,
    name="tasks.workflow_next.execution_step_test",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=5,
)
def execute_task_step_test(self, task_name, task_data, doc_uuids):
    """Test a single workflow step.

    Args:
        task_name: e.g. "Extraction", "Prompt", "Formatter"
        task_data: Task data dict.
        doc_uuids: List of document UUIDs for the trigger step.
    """
    from app.services.workflow_engine import (
        APICallNode,
        AddDocumentNode,
        BrowserAutomationNode,
        CodeExecutionNode,
        CrawlerNode,
        DataExportNode,
        DescribeImageNode,
        DocumentNode,
        DocumentRendererNode,
        ExtractionNode,
        FormatNode,
        FormFillerNode,
        MultiTaskNode,
        PackageBuilderNode,
        PromptNode,
        ResearchNode,
        WebsiteNode,
        WorkflowEngine,
    )

    db = _get_db()
    sys_config = db.system_config.find_one() or {}

    # Pre-load doc texts
    doc_texts = []
    for uuid in doc_uuids:
        doc = db.smart_document.find_one({"uuid": uuid})
        if doc and doc.get("raw_text"):
            doc_texts.append(doc["raw_text"])
    task_data["doc_texts"] = doc_texts

    # Pre-load specific document text when input_source is "select_document"
    if task_data.get("input_source") == "select_document" and task_data.get("selected_document_uuid"):
        sel_doc = db.smart_document.find_one({"uuid": task_data["selected_document_uuid"]})
        if sel_doc and sel_doc.get("raw_text"):
            task_data["selected_doc_text"] = sel_doc["raw_text"]

    engine = WorkflowEngine()
    nodes = []

    doc_node = DocumentNode({"doc_uuids": doc_uuids})
    nodes.append(doc_node)
    engine.add_node(doc_node)

    if task_name == "Extraction":
        process_node = ExtractionNode(data=task_data)
    elif task_name == "Prompt":
        process_node = PromptNode(data=task_data)
    elif task_name == "Formatter":
        process_node = FormatNode(data=task_data)
    elif task_name == "AddWebsite":
        process_node = WebsiteNode(data=task_data)
    elif task_name == "AddDocument":
        process_node = AddDocumentNode(data=task_data)
    elif task_name == "DescribeImage":
        process_node = DescribeImageNode(data=task_data)
    elif task_name == "CodeNode":
        process_node = CodeExecutionNode(data=task_data)
    elif task_name == "CrawlerNode":
        process_node = CrawlerNode(data=task_data)
    elif task_name == "ResearchNode":
        process_node = ResearchNode(data=task_data)
    elif task_name == "APINode":
        process_node = APICallNode(data=task_data)
    elif task_name == "DocumentRenderer":
        process_node = DocumentRendererNode(data=task_data)
    elif task_name == "FormFiller":
        process_node = FormFillerNode(data=task_data)
    elif task_name == "DataExport":
        process_node = DataExportNode(data=task_data)
    elif task_name == "PackageBuilder":
        process_node = PackageBuilderNode(data=task_data)
    elif task_name == "BrowserAutomation":
        process_node = BrowserAutomationNode(data=task_data)
    else:
        raise ValueError(f"Unknown task type: {task_name}")

    process_node._sys_cfg = sys_config

    multi_node = MultiTaskNode(task_name)
    multi_node.add_tasks([process_node])
    nodes.append(multi_node)
    engine.add_node(multi_node)

    for i in range(1, len(nodes)):
        engine.connect(nodes[i - 1], nodes[i])

    final_output, _ = engine.execute()
    return final_output


@celery_app.task(
    bind=True,
    name="tasks.workflow.resume_after_approval",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=5,
)
def resume_workflow_after_approval(self, approval_uuid):
    """Resume a workflow after an approval request has been approved."""
    from bson import ObjectId

    from app.services.workflow_engine import build_workflow_engine

    db = _get_db()

    approval_doc = db.approval_request.find_one({"uuid": approval_uuid})
    if not approval_doc:
        raise ValueError(f"Approval {approval_uuid} not found")
    if approval_doc.get("status") != "approved":
        raise ValueError(f"Approval {approval_uuid} is not approved")

    workflow_result_id = str(approval_doc["workflow_result_id"])
    workflow_id = str(approval_doc["workflow_id"])
    step_index = approval_doc.get("step_index", 0)

    workflow_doc = db.workflow.find_one({"_id": ObjectId(workflow_id)})
    result_doc = db.workflow_result.find_one({"_id": ObjectId(workflow_result_id)})
    if not workflow_doc or not result_doc:
        raise ValueError(f"Workflow or result not found for approval {approval_uuid}")

    sys_config = db.system_config.find_one() or {}

    # Rebuild steps_data (same as execute_workflow_task)
    trigger_data = result_doc.get("input_context", {}) or {}
    doc_uuids = trigger_data.get("doc_uuids", [])
    steps_data = [{"name": "Document", "data": trigger_data, "tasks": []}]

    for step_oid in workflow_doc.get("steps", []):
        step_doc = db.workflow_step.find_one({"_id": step_oid})
        if not step_doc:
            continue
        tasks = []
        for task_oid in step_doc.get("tasks", []):
            task_doc = db.workflow_step_task.find_one({"_id": task_oid})
            if task_doc:
                task_data = dict(task_doc.get("data", {}))
                if task_doc.get("name") == "Extraction" and task_data.get("search_set_uuid"):
                    ss = db.search_set.find_one({"uuid": task_data["search_set_uuid"]})
                    if ss:
                        items = list(db.search_set_item.find({
                            "searchset": task_data["search_set_uuid"],
                            "searchtype": "extraction",
                        }))
                        task_data["keys"] = [item["searchphrase"] for item in items]
                if doc_uuids:
                    doc_texts = []
                    for uuid in doc_uuids:
                        doc = db.smart_document.find_one({"uuid": uuid})
                        if doc and doc.get("raw_text"):
                            doc_texts.append(doc["raw_text"])
                        else:
                            logger.warning(
                                "Document %s has no raw_text — it may still be processing or text extraction failed",
                                uuid,
                            )
                    if not doc_texts:
                        logger.error(
                            "None of the %d input documents have raw_text available — workflow will produce no output",
                            len(doc_uuids),
                        )
                    task_data["doc_texts"] = doc_texts
                if task_data.get("input_source") == "select_document" and task_data.get("selected_document_uuid"):
                    sel_doc = db.smart_document.find_one({"uuid": task_data["selected_document_uuid"]})
                    if sel_doc and sel_doc.get("raw_text"):
                        task_data["selected_doc_text"] = sel_doc["raw_text"]
                tasks.append({"name": task_doc.get("name", ""), "data": task_data})
        steps_data.append({
            "name": step_doc.get("name", ""),
            "data": step_doc.get("data", {}),
            "tasks": tasks,
        })

    user_id = workflow_doc.get("user_id")

    # Check if the user is an admin (gates code execution)
    user_doc = db.user.find_one({"user_id": user_id}) if user_id else None
    is_admin = bool(user_doc and user_doc.get("is_admin"))

    # Get saved output from before the pause
    saved_output = approval_doc.get("data_for_review")
    initial_output = {"output": saved_output, "step_name": "Approval"} if saved_output else None

    # Update result to running
    db.workflow_result.update_one(
        {"_id": ObjectId(workflow_result_id)},
        {"$set": {"status": "running", "current_step_detail": "Resuming after approval"}},
    )

    def update_progress(updates: dict):
        set_ops = {}
        for k, v in updates.items():
            set_ops[k] = v
        if set_ops:
            db.workflow_result.update_one(
                {"_id": ObjectId(workflow_result_id)},
                {"$set": set_ops},
            )

    engine = build_workflow_engine(
        steps_data=steps_data,
        model=workflow_doc.get("resource_config", {}).get("model", "gpt-4o-mini"),
        user_id=user_id,
        system_config_doc=sys_config,
        allow_code_execution=is_admin,
    )

    try:
        final_output, data = engine.execute(
            workflow_result_updater=update_progress,
            start_index=step_index + 1,
            initial_output=initial_output,
        )
    except Exception as e:
        logger.error("Workflow resume failed for %s: %s", workflow_id, e)
        db.workflow_result.update_one(
            {"_id": ObjectId(workflow_result_id)},
            {"$set": {"status": "error", "error": str(e)}},
        )
        raise

    db.workflow_result.update_one(
        {"_id": ObjectId(workflow_result_id)},
        {"$set": {
            "status": "completed",
            "final_output": {"output": final_output, "data": data},
        }},
    )

    db.workflow.update_one(
        {"_id": ObjectId(workflow_id)},
        {"$inc": {"num_executions": 1}},
    )

    return {
        "status": "completed",
        "result_id": workflow_result_id,
        "workflow_id": workflow_id,
    }
