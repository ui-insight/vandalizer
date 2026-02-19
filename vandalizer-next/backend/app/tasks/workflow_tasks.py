"""Celery tasks for workflow execution.

Uses pymongo (sync) for DB access — same pattern as Flask Celery workers.
Task names use 'tasks.workflow_next.*' to coexist with Flask's 'tasks.workflow.*'.
"""

from app.celery_app import celery_app


def _get_db():
    """Get sync pymongo database handle."""
    import os
    from pymongo import MongoClient

    mongo_host = os.environ.get("MONGO_HOST", "mongodb://localhost:27017/")
    mongo_db = os.environ.get("MONGO_DB", "osp")
    client = MongoClient(mongo_host)
    return client[mongo_db]


@celery_app.task(
    bind=True,
    name="tasks.workflow_next.execution",
    autoretry_for=(Exception,),
    rate_limit="1/s",
    max_retries=3,
    default_retry_delay=5,
)
def execute_workflow_task(self, workflow_result_id, workflow_id, trigger_step_data, model):
    """Execute a full workflow.

    Args:
        workflow_result_id: WorkflowResult document ID (str).
        workflow_id: Workflow document ID (str).
        trigger_step_data: Dict with 'doc_uuids' for the Document trigger step.
        model: LLM model name.
    """
    from bson import ObjectId

    from app.services.workflow_engine import build_workflow_engine, sanitize_step_name

    db = _get_db()

    # Load workflow and result
    workflow_doc = db.workflow.find_one({"_id": ObjectId(workflow_id)})
    result_doc = db.workflow_result.find_one({"_id": ObjectId(workflow_result_id)})

    if not workflow_doc or not result_doc:
        return {"status": "error", "error": "Workflow or result not found"}

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
                doc_uuids = trigger_step_data.get("doc_uuids", [])
                if doc_uuids:
                    doc_texts = []
                    for uuid in doc_uuids:
                        doc = db.smart_document.find_one({"uuid": uuid})
                        if doc and doc.get("raw_text"):
                            doc_texts.append(doc["raw_text"])
                    task_data["doc_texts"] = doc_texts

                tasks.append({"name": task_doc.get("name", ""), "data": task_data})

        steps_data.append({
            "name": step_doc.get("name", ""),
            "data": step_doc.get("data", {}),
            "tasks": tasks,
        })

    user_id = workflow_doc.get("user_id")

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
    )

    final_output, data = engine.execute(workflow_result_updater=update_progress)

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

    return {
        "status": "completed",
        "result_id": workflow_result_id,
        "workflow_id": workflow_id,
    }


@celery_app.task(bind=True, name="tasks.workflow_next.execution_step_test")
def execute_task_step_test(self, task_name, task_data, doc_uuids):
    """Test a single workflow step.

    Args:
        task_name: e.g. "Extraction", "Prompt", "Formatter"
        task_data: Task data dict.
        doc_uuids: List of document UUIDs for the trigger step.
    """
    from app.services.workflow_engine import (
        DocumentNode,
        ExtractionNode,
        FormatNode,
        MultiTaskNode,
        PromptNode,
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
    else:
        return {"error": f"Unknown task type: {task_name}"}

    process_node._sys_cfg = sys_config

    multi_node = MultiTaskNode(task_name)
    multi_node.add_tasks([process_node])
    nodes.append(multi_node)
    engine.add_node(multi_node)

    for i in range(1, len(nodes)):
        engine.connect(nodes[i - 1], nodes[i])

    final_output, _ = engine.execute()
    return final_output
