"""Celery tasks for React backend workflow execution.

Registered as 'tasks.workflow_next.*' to coexist with Flask's 'tasks.workflow.*'.
Uses pymongo (sync) for DB access — same pattern as existing Celery workers.
Reuses node classes and engine from app.utilities.workflow.
"""

import os

from pymongo import MongoClient

from app.celery_worker import celery_app


def _get_db():
    """Get sync pymongo database handle."""
    mongo_host = os.environ.get("MONGO_HOST", "mongodb://localhost:27017/")
    mongo_db = os.environ.get("MONGO_DB", "osp")
    client = MongoClient(mongo_host)
    return client[mongo_db]


class _PyMongoResultProxy:
    """Mimics a MongoEngine WorkflowResult for the Flask workflow engine.

    The Flask engine calls attributes like .num_steps_completed, .steps_output,
    .status, .save(), etc. This proxy stores those in memory and flushes to
    MongoDB via pymongo on .save().
    """

    def __init__(self, db, result_id):
        from bson import ObjectId
        self._db = db
        self._id = ObjectId(result_id)
        self.num_steps_completed = 0
        self.num_steps_total = 0
        self.steps_output = {}
        self.status = "running"
        self.current_step_name = None
        self.current_step_detail = None
        self.current_step_preview = None

    @property
    def id(self):
        return self._id

    def save(self):
        self._db.workflow_result.update_one(
            {"_id": self._id},
            {"$set": {
                "num_steps_completed": self.num_steps_completed,
                "num_steps_total": self.num_steps_total,
                "steps_output": self.steps_output,
                "status": self.status,
                "current_step_name": self.current_step_name,
                "current_step_detail": self.current_step_detail,
                "current_step_preview": self.current_step_preview,
            }},
        )


class _SimpleDocumentNode:
    """Lightweight Document trigger node that accepts raw UUID strings."""

    def __init__(self, data):
        self.name = "Document"
        self.doc_uuids = data.get("doc_uuids", [])
        self.inputs = {}
        self.outputs = {}

    def process(self, inputs=None):
        return {"step_name": self.name, "output": self.doc_uuids, "input": None}


def _build_engine(steps_data, model, user_id=None, system_config_doc=None):
    """Build a WorkflowEngine from step data dicts (React backend format)."""
    from app.utilities.workflow import (
        ExtractionNode,
        FormatNode,
        MultiTaskNode,
        PromptNode,
        WorkflowEngine,
    )

    engine = WorkflowEngine()
    nodes = []

    for step in steps_data:
        step_name = step.get("name", "")
        step_data = step.get("data", {})

        if step_name == "Document":
            node = _SimpleDocumentNode(step_data)
            nodes.append(node)
        else:
            tasks = []
            for task in step.get("tasks", []):
                task_name = task.get("name", "")
                task_data = task.get("data", {})
                task_data["user_id"] = user_id
                task_data["model"] = model

                if task_name == "Extraction":
                    n = ExtractionNode(data=task_data)
                    n._sys_cfg = system_config_doc
                    tasks.append(n)
                elif task_name == "Prompt":
                    n = PromptNode(data=task_data)
                    n._sys_cfg = system_config_doc
                    tasks.append(n)
                elif task_name == "Formatter":
                    n = FormatNode(data=task_data)
                    n._sys_cfg = system_config_doc
                    tasks.append(n)

            if tasks:
                multi = MultiTaskNode(step_name)
                multi.add_tasks(tasks)
                nodes.append(multi)

    for node in nodes:
        engine.add_node(node)
    for i in range(1, len(nodes)):
        engine.connect(nodes[i - 1], nodes[i])

    return engine


@celery_app.task(
    bind=True,
    name="tasks.workflow_next.execution",
    autoretry_for=(Exception,),
    rate_limit="1/s",
    max_retries=3,
    default_retry_delay=5,
)
def execute_workflow_task(self, workflow_result_id, workflow_id, trigger_step_data, model):
    """Execute a full workflow dispatched from the React backend."""
    from bson import ObjectId

    db = _get_db()

    workflow_doc = db.workflow.find_one({"_id": ObjectId(workflow_id)})
    result_doc = db.workflow_result.find_one({"_id": ObjectId(workflow_result_id)})

    if not workflow_doc or not result_doc:
        return {"status": "error", "error": "Workflow or result not found"}

    sys_config = db.system_config.find_one() or {}

    # Build steps data from workflow step documents
    steps_data = [{"name": "Document", "data": trigger_step_data, "tasks": []}]

    for step_id in workflow_doc.get("steps", []):
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
                    items = list(db.search_set_item.find({
                        "searchset": task_data["search_set_uuid"],
                        "searchtype": "extraction",
                    }))
                    task_data["keys"] = [item["searchphrase"] for item in items]

                # Pre-load doc texts
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

    # Create a proxy that the Flask engine can use like a MongoEngine object
    result_proxy = _PyMongoResultProxy(db, workflow_result_id)

    engine = _build_engine(
        steps_data=steps_data,
        model=model,
        user_id=user_id,
        system_config_doc=sys_config,
    )

    final_output, data = engine.execute(workflow_result=result_proxy)

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
    """Test a single workflow step dispatched from the React backend."""
    from app.utilities.workflow import (
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
