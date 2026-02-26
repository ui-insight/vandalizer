"""Handle workflow routes."""

import asyncio
import datetime
import io
import json
import os
import uuid
from itertools import chain

import pypandoc
from bson import ObjectId
from devtools import debug
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask.typing import ResponseReturnValue
from celery.result import AsyncResult
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app import limiter
from app.celery_worker import celery_app
from app.blueprints.home.routes import _get_teams, markdown_or_html_to_pdf_bytes
from app.models import (
    SearchSet,
    SearchSetItem,
    SmartDocument,
    SmartFolder,
    Space,
    User,
    Workflow,
    WorkflowAttachment,
    WorkflowResult,
    WorkflowStep,
    WorkflowStepTask,
)
from app.utilities.agents import create_chat_agent
from app.utilities.analytics_helper import ActivityType, activity_start
from app.utilities.config import get_user_model_name, settings
from app.utilities.document_helpers import save_excel_to_html
from app.utilities.library_helpers import (
    _get_or_create_personal_library,
    add_object_to_library,
)
from app.utilities.edit_history import build_changes, history_for, log_edit_history
from app.utilities.semantic_recommender import (
    SemanticRecommender,
)
from app.utilities.workflow import (
    execute_task_step_test,
    execute_workflow_task,
)

# Singleton instance for recommendations to avoid repeated initialization
_recommendation_manager_instance = None

def get_recommendation_manager():
    """Get or create singleton SemanticRecommender instance."""
    global _recommendation_manager_instance
    if _recommendation_manager_instance is None:
        persist_directory = "data/recommendations_vectordb"
        _recommendation_manager_instance = SemanticRecommender(
            persist_directory=persist_directory,
        )
    return _recommendation_manager_instance

def clear_recommendations_cache():
    """Clear the recommendations cache to force fresh results."""
    global _recommendations_cache
    _recommendations_cache.clear()
    debug("Recommendations cache cleared")

# --- Browser automation helpers ---

def _collect_extraction_variables_from_step(step: WorkflowStep) -> list[str]:
    if not step:
        return []

    variables = []

    try:
        step_items = step.extraction_items()
        if isinstance(step_items, list):
            variables.extend(step_items)
    except Exception:
        pass

    for task in step.tasks or []:
        if not task:
            continue
        try:
            task_items = task.extraction_items()
            if isinstance(task_items, list):
                variables.extend(task_items)
        except Exception:
            continue

    seen = set()
    cleaned = []
    for name in variables:
        if name is None:
            continue
        var_name = str(name).strip()
        if not var_name or var_name in seen:
            continue
        seen.add(var_name)
        if var_name.startswith("previous_step."):
            cleaned.append(var_name)
        else:
            cleaned.append(f"previous_step.{var_name}")

    return cleaned


def _get_previous_step_variables(workflow: Workflow, workflow_step_id: str) -> list[str]:
    if not workflow or not workflow_step_id:
        return []

    steps = list(workflow.steps or [])
    step_ids = [str(step.id) for step in steps]

    try:
        step_index = step_ids.index(str(workflow_step_id))
    except ValueError:
        return []

    if step_index <= 0:
        return []

    previous_step = steps[step_index - 1]
    return _collect_extraction_variables_from_step(previous_step)

# Server-side cache for recommendations (TTL: 30 seconds - reduced for faster updates)
_CACHE_TTL_SECONDS = 30
_recommendations_cache = {}
from app.utilities.verification_helpers import user_can_modify_verified

workflows = Blueprint("workflows", __name__)

WORKFLOW_NOT_FOUND_MESSAGE = "Workflow not found"


def _workflow_user_or_none():
    try:
        if current_user.is_authenticated:
            return current_user
    except Exception:
        return None
    return None


def _verified_workflow_forbidden():
    return (
        jsonify(
            {
                "error": "forbidden",
                "message": "Verified workflows can only be modified by examiners.",
            }
        ),
        403,
    )


def _workflow_is_editable(workflow: Workflow | None) -> bool:
    return bool(workflow and user_can_modify_verified(_workflow_user_or_none(), workflow))


def _workflow_for_step(step: WorkflowStep | None) -> Workflow | None:
    if not step:
        return None
    return Workflow.objects(steps=step).first()


def _workflow_for_task(task: WorkflowStepTask | None) -> Workflow | None:
    if not task:
        return None
    step = WorkflowStep.objects(tasks=task).first()
    return _workflow_for_step(step)


def _task_summary(task_name: str | None, task_data: dict | None) -> str:
    name = (task_name or "Task").strip() or "Task"
    if not task_data:
        return name
    if task_data.get("search_set_title"):
        return f"{name}: {task_data.get('search_set_title')}"
    if task_data.get("search_set_item_title"):
        return f"{name}: {task_data.get('search_set_item_title')}"
    if task_data.get("prompt"):
        return f"{name}: {task_data.get('prompt')}"
    if task_data.get("searchphrases"):
        return f"{name}: {task_data.get('searchphrases')}"
    return name


@login_required
@workflows.route("/create_workflow", methods=["POST"])
def add_workflow() -> ResponseReturnValue:
    """Create a new workflow."""
    user = current_user
    user_id = user.get_id()
    if user is None:
        return redirect(url_for("auth.login"))
    workflow_data = request.get_json()
    workflow = Workflow(
        name=workflow_data["name"],
        description=workflow_data["description"],
        user_id=current_user.user_id,
    )
    workflow.save()

    library = _get_or_create_personal_library(user.user_id)
    add_object_to_library(workflow, library=library, added_by_user_id=user.user_id)
    return jsonify(
        {
            "uuid": str(workflow.id),
        },
    )


@workflows.route("/edit", methods=["POST"])
def edit_workflow() -> ResponseReturnValue:
    """Edit an existing prompt."""
    data = request.get_json()
    uuid = data["uuid"]
    workflow = Workflow.objects(id=uuid).first()
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    template = render_template(
        "workflows/edit_workflow.html",
        workflow=workflow,
        history_entries=history_for("workflow", str(workflow.id)),
    )
    response = {
        "template": template,
    }

    return jsonify(response)


@login_required
@workflows.route("/delete_workflow", methods=["POST"])
def delete_workflow() -> ResponseReturnValue:
    """Delete a workflow by ID."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    data = request.get_json()
    uuid = data["uuid"]
    print(uuid)
    workflow = Workflow.objects(id=uuid).first()
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    WorkflowResult.objects(workflow=workflow).delete()
    workflow.delete()
    return {"success": True}


@login_required
@workflows.route("/update_workflow", methods=["POST"])
def update_workflow() -> ResponseReturnValue:
    """Update a workflow by ID."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    workflow_data = request.get_json()
    workflow_id = workflow_data["workflow_id"]
    workflow = Workflow.objects(id=workflow_id).first()
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    changes = build_changes(
        {
            "name": (workflow.name, workflow_data["name"]),
            "description": (workflow.description, workflow_data["description"]),
        }
    )
    workflow.name = workflow_data["name"]
    workflow.description = workflow_data["description"]
    workflow.save()
    log_edit_history(
        kind="workflow",
        obj_id=str(workflow.id),
        user=_workflow_user_or_none(),
        action="update",
        changes=changes,
    )
    return {"success": True}


@login_required
@workflows.route("/edit_configuration", methods=["POST"])
def edit_configuration() -> ResponseReturnValue:
    """Edit workflow with configuration tabs (Input/Output)."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    
    data = request.get_json()
    uuid = data["uuid"]
    workflow = Workflow.objects(id=uuid).first()
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    # Get available folders for the user
    from app.models import SmartFolder
    folders = SmartFolder.objects(user_id=user.get_id()).only('uuid', 'title', 'parent_id')
    
    # Build folder paths
    available_folders = []
    for folder in folders:
        # Build folder path by traversing parents
        path_parts = [folder.title]
        current = folder
        while current.parent_id and current.parent_id != "0":
            parent = SmartFolder.objects(uuid=current.parent_id).only('title', 'parent_id').first()
            if parent:
                path_parts.insert(0, parent.title)
                current = parent
            else:
                break
        
        available_folders.append({
            'uuid': folder.uuid,
            'title': folder.title,
            'path': ' / '.join(path_parts)
        })

    # Prepare workflow config for JS
    workflow_config = {
        'workflow_id': str(workflow.id),
        'input_config': workflow.input_config or {},
        'output_config': workflow.output_config or {},
        'available_folders': available_folders
    }

    template = render_template(
        "workflows/edit_workflow_config.html",
        workflow=workflow,
        workflow_config=workflow_config
    )
    return {"template": template}


@login_required
@workflows.route("/save_configuration", methods=["POST"])
def save_configuration() -> ResponseReturnValue:
    """Save workflow input/output configuration."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    
    data = request.get_json()
    workflow_id = data.get("workflow_id")
    workflow = Workflow.objects(id=workflow_id).first()
    
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    try:
        # Update basic fields
        if "name" in data:
            workflow.name = data["name"]
        if "description" in data:
            workflow.description = data["description"]
        
        # Update input configuration
        if "input_config" in data:
            workflow.input_config = data["input_config"]
        
        # Update output configuration
        if "output_config" in data:
            workflow.output_config = data["output_config"]
        
        workflow.updated_at = datetime.datetime.now()
        workflow.save()
        
        # Log the change
        log_edit_history(
            kind="workflow",
            obj_id=str(workflow.id),
            user=_workflow_user_or_none(),
            action="update_configuration",
            changes={
                "input_config": "Updated",
                "output_config": "Updated"
            },
        )
        
        return jsonify({"success": True, "workflow_id": str(workflow.id)})
    
    except Exception as e:
        current_app.logger.error(f"Error saving workflow configuration: {e}")
        return jsonify({"error": str(e)}), 500


@login_required
@workflows.route("/search_documents", methods=["POST"])
def search_documents() -> ResponseReturnValue:
    """Search documents for fixed document picker."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))

    data = request.get_json()
    query = (data.get("query") or "").strip()

    filters = {"user_id": user.get_id()}
    if query:
        filters["title__icontains"] = query

    docs = (
        SmartDocument.objects(**filters)
        .only("uuid", "title", "extension")
        .order_by("-created_at")
        .limit(50)
    )

    results = [
        {"uuid": doc.uuid, "title": doc.title, "extension": doc.extension}
        for doc in docs
    ]

    return jsonify({"documents": results})


@login_required
@workflows.route("/workflow/run", methods=["POST"])
def run_workflow() -> ResponseReturnValue:
    """Run a workflow."""
    user = current_user
    user_id = user.get_id()
    if user is None:
        return redirect(url_for("auth.login"))

    workflow_data = request.get_json()
    workflow_id = workflow_data["workflow_id"]
    session_id = workflow_data["session_id"]
    current_space_id = workflow_data.get("current_space_id", "None")
    document_uuids = workflow_data.get("document_uuids") or []

    workflow = Workflow.objects(id=workflow_id).first()

    # Merge fixed documents from input_config
    from app.utilities.workflow import resolve_fixed_documents
    fixed_docs = resolve_fixed_documents(workflow) if workflow else []
    fixed_doc_uuids = [doc.uuid for doc in fixed_docs]
    document_uuids = list(dict.fromkeys(document_uuids + fixed_doc_uuids))

    if not document_uuids:
        return (
            jsonify(
                {"status": "error", "message": "Select a document before running."}
            ),
            400,
        )
    workflow_result = WorkflowResult(workflow=workflow, session_id=session_id)
    workflow_result.save()
    workflow = Workflow.objects(id=workflow_id).first()
    for attachment in workflow.attachments:
        if attachment:
            attachment.delete()

    # Clear the attachments list from the workflow and save
    workflow.attachments = []
    workflow.save()

    if not workflow:
        return jsonify({"status": "error", "message": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    attachments = [
        # SmartDocument.objects(uuid=x.attachment).first() for x in workflow.attachments
    ]
    docs = [SmartDocument.objects(uuid=x).first() for x in document_uuids]

    document_trigger_step = WorkflowStep(
        name="Document",
        data={"docs": docs, "attachments": attachments, "user_id": user_id},
    )
    document_trigger_step.save()

    model = get_user_model_name(user_id)

    workflow_id = str(workflow.id)
    workflow_result_id = str(workflow_result.id)
    workflow_trigger_step_id = str(document_trigger_step.id)
    print("Running workflow", workflow_id, workflow_result_id, workflow_trigger_step_id)

    current_team, my_teams = _get_teams(user)

    # Check if there's an existing completed activity for this workflow
    # If so, reuse it instead of creating a new one
    from app.models import ActivityEvent

    existing_activity = (
        ActivityEvent.objects(
            type=ActivityType.WORKFLOW_RUN,
            user_id=user_id,
            workflow=workflow,
            status="completed",
        )
        .order_by("-started_at")
        .first()
    )

    if existing_activity:
        # Reuse the existing activity with new results
        activity = existing_activity
        activity.workflow_result = workflow_result
        activity.status = "queued"
        activity.started_at = datetime.datetime.now(datetime.timezone.utc)
        activity.last_updated_at = datetime.datetime.now(datetime.timezone.utc)
        activity.finished_at = None
        activity.error = None
        activity.steps_completed = 0
        activity.result_snapshot = None
        activity.save()
    else:
        # Create a new activity for first-time run
        activity = activity_start(
            type=ActivityType.WORKFLOW_RUN,
            user_id=user_id,
            title=workflow.name,
            team_id=current_team.uuid,
            space=current_space_id,
            workflow=workflow,
            workflow_result=workflow_result,
            document_uuids=document_uuids,
        )

    async_result = execute_workflow_task.delay(
        workflow_result_id=workflow_result_id,
        workflow_id=workflow_id,
        workflow_trigger_step_id=workflow_trigger_step_id,
        model=model,
    )
    # Note: Workflow recommendation ingestion now happens asynchronously
    # in the execute_workflow_task Celery task
    return jsonify(
        {
            "status": "accepted",
            "workflow_result_id": workflow_result_id,
            "task_id": async_result.id,
            "activity_id": str(activity.id),
        },
    ), 202


@login_required
@workflows.route("/workflow/recommendations", methods=["POST"])
def get_workflow_recommendations_sync() -> ResponseReturnValue:
    """Get workflow recommendations synchronously (for immediate results)."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))

    request_data = request.get_json()
    document_uuids = request_data.get("uuids", [])
    limit = request_data.get("limit", 5)

    if not document_uuids:
        return jsonify({"recommendations": []}), 200

    # Create cache key from sorted UUIDs
    cache_key = ",".join(sorted(document_uuids))

    # Check server-side cache first
    now = datetime.datetime.now()
    if cache_key in _recommendations_cache:
        cached_data, cached_time = _recommendations_cache[cache_key]
        age_seconds = (now - cached_time).total_seconds()

        if age_seconds < _CACHE_TTL_SECONDS:
            debug(f"Using server-side cache (age: {age_seconds:.1f}s)")
            return jsonify(cached_data), 200

    # try:
    # Load documents - use __in for batch query instead of loop
    documents = list(SmartDocument.objects(uuid__in=document_uuids))

    if not documents:
        return jsonify(
            {"recommendations": [], "message": "No valid documents found"}
        ), 200

    are_documents_valid = True
    for document in documents:
        if not document.valid:
            are_documents_valid = False

    # Use singleton instance to avoid re-initialization overhead
    recommendation_manager = get_recommendation_manager()

    # Get recommendations
    recommendations = recommendation_manager.search_recommendations(
        selected_documents=documents,
        limit=limit,
    )

    templates = []

    recommended_workflows = []
    recommended_extractions = []  # Separate list for extractions to avoid type confusion
    for recommendation in recommendations:
        identifier = recommendation["identifier"]
        recommendation_type = recommendation["recommendation_type"]
        debug(f"Processing recommendation: type={recommendation_type}, identifier={identifier}")
        
        if recommendation_type == "Workflow":
            workflow = Workflow.objects(id=identifier).first()
            if workflow and (workflow not in recommended_workflows):
                recommended_workflows.append(workflow)

                template = render_template(
                    "toolpanel/recommendations/recommendation-workflow.html",
                    workflow=workflow,
                    user=user,
                )
                templates.append(template)
                debug(f"Added workflow recommendation: {workflow.id}")
        elif recommendation_type == "Extraction":
            debug(f"Processing Extraction recommendation with identifier: {identifier}")
            search_set = SearchSet.objects(uuid=identifier).first()
            debug(f"SearchSet lookup result: {search_set.uuid if search_set else 'None'}")
            if search_set and (search_set not in recommended_extractions):
                recommended_extractions.append(search_set)
                try:
                    template = render_template(
                        "toolpanel/recommendations/recommendation-extraction.html",
                        search_set=search_set,
                    )
                    templates.append(template)
                    debug(f"Successfully rendered extraction recommendation template for {identifier}")
                except Exception as e:
                    debug(f"Error rendering extraction recommendation template: {e}")
                    import traceback
                    debug(f"Traceback: {traceback.format_exc()}")
            else:
                if not search_set:
                    debug(f"SearchSet not found for identifier: {identifier}")
                else:
                    debug(f"SearchSet {identifier} already in recommended_extractions list")
    if len(templates) == 0:
        template = render_template(
            "toolpanel/recommendations/recommendations-none.html",
        )
        templates.append(template)
    else:
        templates = [
            render_template(
                "toolpanel/recommendations/recommendation-title.html",
            )
        ] + templates

    print(recommendations)

    # Prepare response
    response_data = {"templates": templates, "are_documents_valid": are_documents_valid}

    # Cache the response (store both data and timestamp)
    _recommendations_cache[cache_key] = (response_data, now)

    # Clean up old cache entries (simple LRU: keep only last 100 entries)
    if len(_recommendations_cache) > 100:
        # Remove oldest entries
        sorted_cache = sorted(_recommendations_cache.items(), key=lambda x: x[1][1])
        for old_key, _ in sorted_cache[:20]:  # Remove 20 oldest
            del _recommendations_cache[old_key]

    return jsonify(response_data), 200

    # except Exception as e:
    #     print(e)
    #     return jsonify({"error": str(e), "recommendations": []}), 500


@login_required
@workflows.route("/workflow/step/test", methods=["POST"])
def test_workflow_step() -> ResponseReturnValue:
    """Run a workflow step."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))

    workflow_data = request.get_json()
    task_name = workflow_data["task_name"]
    task_data = workflow_data["task_data"]
    document_uuids = workflow_data.get("document_uuids") or []
    if not document_uuids:
        return (
            jsonify({"error": "Select a document before testing this step."}),
            400,
        )

    user_id = user.get_id()
    print(workflow_data)
    docs = [SmartDocument.objects(uuid=x).first() for x in document_uuids]
    document_trigger_step = WorkflowStep(
        name="Document",
        data={"docs": docs, "user_id": user_id},
    )
    document_trigger_step.save()

    model = get_user_model_name(user_id)

    task_data["user_id"] = user_id
    task_data["model"] = model

    async_result = execute_task_step_test.delay(
        task_name=task_name,
        task_data=task_data,
        document_trigger_step_id=str(document_trigger_step.id),
    )

    return (
        jsonify({"status": "accepted", "task_id": async_result.id}),
        202,
    )


# @MARK: ~~ Run integration
@workflows.route("/run_integrated", methods=["POST"])
def run_workflow_integrated() -> ResponseReturnValue:
    """Run the integrated workflow and return the result."""
    # **1. Authenticate User via API Key**
    api_key = request.headers.get("x-api-key")
    if not api_key:
        return jsonify({"error": "API key is missing"}), 401

    user = User.objects(id=api_key).first()
    if user is None:
        return jsonify({"error": "Invalid API key"}), 401

    # **2. Generate Session ID**
    session_id = str(uuid.uuid4())

    # **3. Get Workflow ID**
    workflow_id = request.form.get("workflowID")
    if not workflow_id:
        return jsonify({"error": "workflowID is required"}), 400

    workflow = Workflow.objects(id=workflow_id).first()
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    user_id = current_user.get_id()

    # **4. Handle File Uploads**
    uploaded_files = request.files.getlist("file")
    if not uploaded_files:
        return (
            jsonify(
                {
                    "error": "At least one file must be uploaded. Make sure the @ symbol precedes your path if using bash.",
                },
            ),
            400,
        )

    document_uuids = []

    for file in uploaded_files:
        # Secure the filename
        filename = secure_filename(file.filename)
        extension = os.path.splitext(filename)[1][1:].lower()
        uid = uuid.uuid4().hex.upper()

        # Create upload directory if it doesn't exist
        upload_dir = os.path.join(
            current_app.root_path,
            "static",
            "uploads",
            str(user.id),
        )
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)

        file_path = os.path.join(upload_dir, f"{uid}.{extension}")
        file.save(file_path)

        # **Optional: Handle File Conversion**
        if extension == "docx":
            pdf_path = os.path.join(upload_dir, f"{uid}.pdf")
            # SHENEMAN
            pypandoc.convert_file(file_path, "pdf", outputfile=pdf_path)
            pypandoc.convert_file(file_path, "pdf", outputfile=pdf_path, extra_args="--pdf-engine=xelatex")
            extension = "pdf"
        elif extension in ["xlsx", "xls"]:
            html_path = os.path.join(upload_dir, f"{uid}.html")
            save_excel_to_html(file_path, html_path)
            extension = "html"

        # **Create SmartDocument Object**
        document = SmartDocument(
            title=filename,
            downloadpath=f"{user.id}/{uid}.{extension}",
            path=f"{user.id}/{uid}.{extension}",
            extension=extension,
            uuid=uid,
            user_id=user_id,
            space="None",
        )
        document.save()
        document_uuids.append(uid)

    # Merge fixed documents from input_config
    from app.utilities.workflow import resolve_fixed_documents
    fixed_docs = resolve_fixed_documents(workflow)
    fixed_doc_uuids = [doc.uuid for doc in fixed_docs]
    document_uuids = list(dict.fromkeys(document_uuids + fixed_doc_uuids))

    # **5. Prepare Workflow Execution**
    workflow_result = WorkflowResult(workflow=workflow, session_id=session_id)
    workflow_result.save()
    # Since we can't look up attachments, we'll assume there are none or handle them accordingly
    attachments = []
    # If your workflow has predefined attachments, you might need to handle them differently

    # Retrieve the SmartDocument objects we just created
    docs = [SmartDocument.objects(uuid=uuid).first() for uuid in document_uuids]

    document_trigger_step = WorkflowStep(
        name="Document",
        data={"docs": docs, "attachments": attachments},
    )

    workflow_trigger_step_id = str(document_trigger_step.id)

    model = get_user_model_name(user.user_id)

    # **6. Execute the Workflow**
    workflow_output = execute_workflow_task.delay(
        workflow_result_id=str(workflow_result.id),
        workflow_id=str(workflow.id),
        workflow_trigger_step_id=workflow_trigger_step_id,
        model=model,
    )
    workflow_output = workflow_output.get()
    output = workflow_output["output"]
    data = workflow_output["history"]

    # **7. Return the Response**
    return jsonify({"output": output, "steps": data})


@workflows.route("/workflow/status", methods=["GET"])
@limiter.exempt
def workflow_status() -> ResponseReturnValue:
    """Poll the workflow status."""
    session_id = request.args.get("session_id")

    if not session_id:
        return jsonify({"error": "workflow_id is required"}), 400

    # Get workflow status
    workflow_result = WorkflowResult.objects(session_id=session_id).first()

    if not workflow_result:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404
    final_output = None
    if workflow_result.final_output:
        final_output = workflow_result.final_output.get("output", None)
    debug("Workflow result", final_output)

    # Get the associated activity
    activity = None
    activity_id = None
    from app.models import ActivityEvent

    activity = ActivityEvent.objects(workflow_result=workflow_result).first()
    if activity:
        activity_id = str(activity.id)

    started_at = activity.started_at.isoformat() if activity and activity.started_at else None
    finished_at = activity.finished_at.isoformat() if activity and activity.finished_at else None
    duration_seconds = None
    if activity and activity.started_at and activity.finished_at:
        duration_seconds = (activity.finished_at - activity.started_at).total_seconds()

    response = {
        "steps_completed": workflow_result.num_steps_completed,
        "total_steps": workflow_result.num_steps_total,
        "output": final_output,
        "status": workflow_result.status,
        "activity_id": activity_id,
        "workflow_result_id": str(workflow_result.id),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "current_step_name": workflow_result.current_step_name,
        "current_step_detail": workflow_result.current_step_detail,
        "current_step_preview": workflow_result.current_step_preview,
    }

    return jsonify(response)


@login_required
@workflows.route("/workflow/step/status/<task_id>", methods=["GET"])
@limiter.exempt
def workflow_step_test_status(task_id: str) -> ResponseReturnValue:
    """Poll the status of a workflow step test Celery task."""
    if not task_id:
        return jsonify({"error": "task_id is required"}), 400

    result = AsyncResult(task_id, app=celery_app)
    state = result.state
    response: dict[str, object] = {
        "task_id": task_id,
        "state": state,
    }

    if result.successful():
        response["output"] = result.result
    elif result.failed():
        err = result.result
        response["error"] = str(err)

    return jsonify(response)


# @socketio.on("workflow_status")
# def workflow_status_socket(data):
#     print("Workflow websocket", data)
#     session_id = data.get("session_id")

#     if not session_id:
#         emit("workflow_status", {"error": "session_id is required"})
#         return

#     # Get workflow status
#     workflow_result = WorkflowResult.objects(session_id=session_id).first()

#     if not workflow_result:
#         emit("workflow_status", {"error": "Workflow not found"})
#         return

#     response = {
#         "steps_completed": workflow_result.num_steps_completed,
#         "total_steps": workflow_result.num_steps_total,
#         "steps_output": workflow_result.steps_output,
#         "status": workflow_result.status,
#     }

#     emit("workflow_status", response)


## @MARK: Download
@login_required
@workflows.route("/download", methods=["GET"])
def workflow_download() -> ResponseReturnValue:
    session_id = request.args.get("session_id")
    fmt = request.args.get("format", "txt").lower()

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    # 1) fetch the result object
    workflow_result = WorkflowResult.objects(session_id=session_id).first()
    if not workflow_result:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    # 2) pull the final output payload (prefer the stored final_output field, fall back to last step)
    final_payload = workflow_result.final_output or {}
    final_output = final_payload.get("output")
    if final_output is None:
        steps_outputs = list(workflow_result.steps_output.values())
        if steps_outputs:
            final_output = steps_outputs[-1].get("output")

    if isinstance(final_output, (list, dict)):
        raw_json = json.dumps(final_output, indent=2, default=str)
        final_output_str = raw_json
    elif final_output is None:
        raw_json = ""
        final_output_str = ""
    else:
        raw_json = final_output
        final_output_str = final_output

    if not raw_json:
        raw_json = "No workflow output was produced."
    print(raw_json)
    # 3) ask the LLM to format
    #    tailor the prompt to each format
    if fmt == "csv":
        prompt = (
            "Convert the following HTML document into a well formatted CSV. "
            "Use commas as separators and include a header row.\n\n"
            "Do not include any description of your own or commentary, just return what we are going to output.\n\n"
            f"{raw_json}"
        )
    elif fmt == "pdf":
        # you might ask for a simple text layout or markdown-to-PDF
        prompt = (
            "Lay out the following HTML data into a well-structured document that I can export as a PDF. "
            "Please format your entire response using HTML.\n\n"
            "IMPORTANT STYLING RULES:\n"
            "- Use ONLY inline styles with concrete color values (e.g., color: #333, background: #f5f5f5)\n"
            "- DO NOT use CSS variables like var(--anything)\n"
            "- DO NOT use CSS functions except rgb() and rgba()\n"
            "- Use simple, standard HTML tags: h1-h6, p, ul, ol, li, table, strong, em\n"
            "- Keep styling minimal and use hex colors or named colors (black, white, gray, etc.)\n\n"
            "Use headings, paragraphs, bullet points, and bold text as appropriate to create a clear and readable layout. "
            "Do not include any of your own commentary or descriptions outside of the HTML output.\n\n"
            f"Here is the data to format:\n\n{raw_json}"
        )
    else:  # txt
        prompt = (
            "Convert the following HTML document into plain text format. "
            "Strip out all HTML tags and formatting. "
            "Do NOT use markdown syntax (no *, #, or other markdown formatting). "
            "Return only clean, readable plain text with proper line breaks and indentation.\n\n"
            "Do not include any description of your own or commentary, just return the plain text output.\n\n"
            f"{raw_json}"
        )

    user = current_user

    if fmt == "pdf":
        formatted = final_output_str
    else:
        model = get_user_model_name(user.user_id)

        chat_agent = create_chat_agent(model)
        # get current event loop
        # if there is no current loop, create a new one
        formatted = asyncio.run(chat_agent.run(prompt))
        formatted = formatted.output

    if fmt == "csv":
        # return as a downloadable CSV file
        return (
            formatted,
            200,
            {
                "Content-Type": "text/csv",
                "Content-Disposition": f"attachment; filename=workflow_output_{session_id}.csv",
            },
        )
    elif fmt == "pdf":
        # Convert HTML to PDF bytes
        pdf_bytes = markdown_or_html_to_pdf_bytes(formatted)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"workflow_output_{session_id}.pdf",
        )
    else:
        # return as a downloadable text file
        return (
            formatted,
            200,
            {
                "Content-Type": "text/plain",
                "Content-Disposition": f"attachment; filename=workflow_output_{session_id}.txt",
            },
        )

        # Remove the tick marks before and after blocks
        formatted = formatted.strip("`").strip()

    # 4) package it up
    buf = io.BytesIO()
    debug(f"Format is {fmt}")
    if fmt == "csv":
        buf.write(formatted.encode("utf-8"))
        buf.seek(0)
        return send_file(
            buf,
            mimetype="text/csv",
            as_attachment=True,
            download_name="workflow_output.csv",
        )
    elif fmt == "pdf":
        buf = markdown_or_html_to_pdf_bytes(formatted, input_format="markdown")
        return send_file(
            buf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="workflow_output.pdf",
        )

    else:  # txt
        buf.write(formatted.encode("utf-8"))
        buf.seek(0)
        return send_file(
            buf,
            mimetype="text/plain",
            as_attachment=True,
            download_name="workflow_output.txt",
        )


## @MARK: ~~ Integrate
@login_required
@workflows.route("/integrate", methods=["POST"])
def workflow_integrate() -> ResponseReturnValue:
    """Integrate a workflow template."""
    user = current_user
    data = request.get_json()
    workflow_id = data.get("workflow_id")

    workflow = Workflow.objects(id=workflow_id).first()

    template = render_template(
        "workflows/modals/workflow_integration.html",
        workflow=workflow,
        user=user,
    )
    response = {"template": template}
    return jsonify(response)


@workflows.route("/fetch_workflow", methods=["POST"])
def fetch_workflow() -> ResponseReturnValue:
    """Fetch a specific workflow."""
    data = request.get_json()
    workflow_id = data["workflow_uuid"]
    workflow = Workflow.objects(id=workflow_id).first()
    can_customize = _workflow_is_editable(workflow)

    # Get user and folders for Input/Output configuration
    user = current_user
    folders = SmartFolder.objects(user_id=user.get_id()).only('uuid', 'title', 'parent_id')
    
    # Build folder paths for dropdown
    available_folders = []
    for folder in folders:
        path_parts = [folder.title]
        current = folder
        while current.parent_id:
            parent = SmartFolder.objects(uuid=current.parent_id).first()
            if parent:
                path_parts.insert(0, parent.title)
                current = parent
            else:
                break
        available_folders.append({
            'uuid': folder.uuid,
            'title': folder.title,
            'path': ' / '.join(path_parts)
        })
    
    # Prepare workflow configuration for tabs
    workflow_config = {
        'workflow_id': str(workflow.id),
        'input_config': workflow.input_config or {},
        'output_config': workflow.output_config or {},
        'available_folders': available_folders
    }

    template = render_template(
        "workflows/workflow.html",
        workflow=workflow,
        can_customize_workflow=can_customize,
        workflow_config=workflow_config,
    )

    response = {
        "template": template,
    }

    return jsonify(response)


@login_required
@workflows.route("/update_title", methods=["POST"])
def update_workflow_title() -> ResponseReturnValue:
    """Update the title of a workflow."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    workflow_data = request.get_json()
    workflow_id = workflow_data["uuid"]
    workflow = Workflow.objects(id=ObjectId(workflow_id)).first()
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    before_title = workflow.name
    workflow.name = workflow_data["title"]
    workflow.save()
    changes = build_changes({"title": (before_title, workflow_data["title"])})
    log_edit_history(
        kind="workflow",
        obj_id=str(workflow.id),
        user=_workflow_user_or_none(),
        action="update_title",
        changes=changes,
    )

    response = {"complete": True}
    return jsonify(response)


## MARK: Workflow steps
@login_required
@workflows.route("/add_workflow_step", methods=["POST"])
def add_workflow_step() -> ResponseReturnValue:
    """Add a new step to a workflow."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    workflow_step_data = request.get_json()
    workflow_id = workflow_step_data["workflow_id"]
    workflow = Workflow.objects(id=workflow_id).first()
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    step_title = workflow_step_data["title"]

    # Check if the last step is an output step - if so, don't allow adding more steps
    if workflow.steps and workflow.steps[-1].is_output:
        return jsonify({
            "error": "Cannot add steps after an output step. Output steps must be the final step in a workflow."
        }), 400

    workflow_step = WorkflowStep(name=step_title)
    debug(workflow_step_data)
    workflow_step.save()
    workflow.steps.append(workflow_step)
    workflow.save()
    changes = build_changes({"step": ("", step_title)})
    log_edit_history(
        kind="workflow",
        obj_id=str(workflow.id),
        user=_workflow_user_or_none(),
        action="add_step",
        changes=changes,
    )
    template = render_template(
        "workflows/workflow_steps/edit_workflow_step_modal.html",
        workflow=workflow,
        workflow_step_id=workflow_step.id,
        workflow_step=workflow_step,
    )

    response = {"template": template}
    return jsonify(response)


@login_required
@workflows.route("/edit_step", methods=["POST"])
def edit_workflow_step() -> ResponseReturnValue:
    """Edit a step in a workflow."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    workflow_step_data = request.get_json()
    workflow_id = workflow_step_data["workflow_id"]
    workflow_step_id = workflow_step_data["workflow_step_id"]
    workflow = Workflow.objects(id=workflow_id).first()
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    workflow_step = WorkflowStep.objects(id=workflow_step_id).first()
    template = render_template(
        "workflows/workflow_steps/edit_workflow_step_modal.html",
        workflow=workflow,
        workflow_step_id=workflow_step.id,
        workflow_step=workflow_step,
    )

    response = {"template": template}
    return jsonify(response)


@login_required
@workflows.route("/step/update_title", methods=["POST"])
def update_workflow_step_title() -> ResponseReturnValue:
    """Update the title of a workflow step."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    workflow_step_data = request.get_json()
    workflow_step_id = workflow_step_data["workflow_step_id"]
    workflow_step = WorkflowStep.objects(id=ObjectId(workflow_step_id)).first()
    if not workflow_step:
        return jsonify({"error": "Step not found"}), 404

    workflow = _workflow_for_step(workflow_step)
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    before_title = workflow_step.name
    workflow_step.name = workflow_step_data["title"]
    workflow_step.save()
    changes = build_changes({"step_title": (before_title, workflow_step.name)})
    log_edit_history(
        kind="workflow",
        obj_id=str(workflow.id),
        user=_workflow_user_or_none(),
        action="rename_step",
        changes=changes,
    )

    response = {"complete": True}
    return jsonify(response)


@login_required
@workflows.route("/step/add_task", methods=["POST"])
def add_workflow_add_task() -> ResponseReturnValue:
    """Add a task to a workflow step."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    workflow_step_data = request.get_json()
    workflow_id = workflow_step_data["workflow_id"]
    workflow_step_id = workflow_step_data["workflow_step_id"]
    workflow = Workflow.objects(id=workflow_id).first()
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    workflow_step = WorkflowStep.objects(id=workflow_step_id).first()
    template = render_template(
        "workflows/workflow_steps/new_workflow_task_modal.html",
        workflow=workflow,
        workflow_step_id=workflow_step.id,
        workflow_step=workflow_step,
    )

    response = {"template": template}
    return jsonify(response)


@login_required
@workflows.route("/step/add_step_task", methods=["POST"])
def add_workflow_step_task() -> ResponseReturnValue:
    """Add a task to a specific step in a workflow."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    workflow_step_data = request.get_json()
    workflow_step_id = workflow_step_data["workflow_step_id"]
    workflow_step = WorkflowStep.objects(id=workflow_step_id).first()
    if not workflow_step:
        return jsonify({"error": "Step not found"}), 404

    workflow = _workflow_for_step(workflow_step)
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    task_name = workflow_step_data["task_name"]
    task_data = workflow_step_data["task_data"]
    workflow_step_task = WorkflowStepTask(name=task_name, data=task_data)
    workflow_step_task.save()
    workflow_step.tasks.append(workflow_step_task)
    workflow_step.save()
    changes = build_changes(
        {"task": ("", _task_summary(task_name, task_data))}
    )
    log_edit_history(
        kind="workflow",
        obj_id=str(workflow.id),
        user=_workflow_user_or_none(),
        action="add_task",
        changes=changes,
    )
    return jsonify({"complete": True})


@login_required
@workflows.route("/delete_step", methods=["POST"])
def delete_workflow_step() -> ResponseReturnValue:
    """Delete a specific step in a workflow."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))

    workflow_data = request.get_json()
    workflow_step_id = workflow_data["workflow_step_id"]
    step = WorkflowStep.objects(id=workflow_step_id).first()
    if not step:
        return jsonify({"success": False, "error": "Step not found"}), 404

    workflow = _workflow_for_step(step)
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    # Delete all associated WorkflowStepTasks
    for task in step.tasks:
        task.delete()

    # Remove references to the step in any Workflow
    Workflow.objects(steps=step).update(pull__steps=step)

    # Delete the WorkflowStep itself
    step.delete()
    changes = build_changes({"step": (step.name, "")})
    log_edit_history(
        kind="workflow",
        obj_id=str(workflow.id),
        user=_workflow_user_or_none(),
        action="remove_step",
        changes=changes,
    )

    return jsonify({"success": True})


@login_required
@workflows.route("/delete_step_task", methods=["POST"])
def delete_workflow_step_task() -> ResponseReturnValue:
    """Delete a specific task in a workflow step."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))

    workflow_data = request.get_json()
    print(workflow_data)
    workflow_task_id = workflow_data["workflow_task_id"]
    task = WorkflowStepTask.objects(id=workflow_task_id).first()
    if not task:
        return jsonify({"success": False, "error": "Step not found"}), 404

    workflow = _workflow_for_task(task)
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    # Remove references to the step in any Workflow
    WorkflowStep.objects(tasks=task).update(pull__tasks=task)

    # Delete all associated WorkflowStepTasks
    task.delete()
    changes = build_changes({"task": (_task_summary(task.name, task.data), "")})
    log_edit_history(
        kind="workflow",
        obj_id=str(workflow.id),
        user=_workflow_user_or_none(),
        action="remove_task",
        changes=changes,
    )

    return jsonify({"success": True})


@login_required
@workflows.route("/update_workflow_step", methods=["POST"])
def update_workflow_step() -> ResponseReturnValue:
    """Update a specific step in a workflow."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    workflow_data = request.get_json()
    workflow_id = workflow_data["workflow_id"]
    step_index = workflow_data["step_index"]
    step = workflow_data["step"]
    workflow = Workflow.objects(id=workflow_id).first()
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    if not _workflow_is_editable(workflow):
        return _verified_workflow_forbidden()

    if step_index < len(workflow.steps):
        error = "Step index out of range"
        return jsonify({"error": error})
    workflow.steps[step_index] = step
    workflow.save()
    return redirect("/home?section=Workflows")


## @MARK: ~~ Extraction
@workflows.route("/add_extraction_step", methods=["GET", "POST"])
def workflow_add_extraction_step() -> ResponseReturnValue:
    """Add an extraction step to a workflow."""
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = next(iter(request.args.keys()))  # Get the JSON string key
        data = json.loads(data_str)  # Retrieve query parameters, if any
        workflow_id = data.get("workflow_uuid")
        space_id = data.get("space_id")

        is_editing = data.get("is_editing") or False
        workflow_task_id = ""
        workflow_task = None

        if is_editing:
            workflow_task_id = data.get("workflow_task_id")
            workflow_task = WorkflowStepTask.objects(
                id=ObjectId(workflow_task_id),
            ).first()

        workflow = Workflow.objects(id=workflow_id).first()

        current_space = Space.objects(uuid=space_id).first()
        global_extraction_sets = SearchSet.objects(
            space=current_space.uuid,
            is_global=True,
            set_type="extraction",
        ).all()
        user_extraction_sets = SearchSet.objects(
            user_id=workflow.user_id,
            space=current_space.uuid,
            is_global=False,
            set_type="extraction",
        ).all()
        extraction_sets_objects = list(
            chain(global_extraction_sets, user_extraction_sets),
        )

        template = render_template(
            "workflows/modals/workflow_add_extractions_modal.html",
            workflow=workflow,
            extraction_sets=extraction_sets_objects,
            is_editing=is_editing,
            workflow_task_id=workflow_task_id,
            workflow_task=workflow_task,
        )
        response = {"template": template}
        return jsonify(response)

    if request.method == "POST":
        # Handle POST request - create a new WorkflowStep

        data = request.get_json()
        debug(data)
        search_set_id = data.get("search_set_id", None)
        manual_input = data.get("manual_input", None)
        workflow_step_id = data.get("workflow_step_id", None)
        task_id = data.get("workflow_task_id", None)
        task_input_config = data.get("input_config", {"source": "step_input"})
        task_output_config = data.get("output_config", {"post_process_prompt": ""})
        workflow_step = WorkflowStep.objects(id=ObjectId(workflow_step_id)).first()
        workflow_step_task = None
        workflow = _workflow_for_step(workflow_step) if workflow_step else None

        if search_set_id:
            searchset = SearchSet.objects(id=ObjectId(search_set_id)).first()

            workflow_step_task = None
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    before_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    workflow_step_task.data = searchset.to_workflow_step_data()
                    workflow_step_task.save()
                    after_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    changes = build_changes({"task": (before_summary, after_summary)})
                    if workflow:
                        log_edit_history(
                            kind="workflow",
                            obj_id=str(workflow.id),
                            user=_workflow_user_or_none(),
                            action="update_task",
                            changes=changes,
                        )
            else:
                workflow_step_task = WorkflowStepTask(
                    name="Extraction",
                    data=searchset.to_workflow_step_data(),
                )
                workflow_step_task.save()
                if workflow_step.tasks is None:
                    workflow_step.tasks = []
                workflow_step.tasks.append(workflow_step_task)
                workflow_step.save()
                changes = build_changes(
                    {"task": ("", _task_summary("Extraction", workflow_step_task.data))}
                )
                if workflow:
                    log_edit_history(
                        kind="workflow",
                        obj_id=str(workflow.id),
                        user=_workflow_user_or_none(),
                        action="add_task",
                        changes=changes,
                    )

        elif manual_input:
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    before_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    workflow_step_task.data = {"searchphrases": manual_input}
                    workflow_step_task.save()
                    after_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    changes = build_changes({"task": (before_summary, after_summary)})
                    if workflow:
                        log_edit_history(
                            kind="workflow",
                            obj_id=str(workflow.id),
                            user=_workflow_user_or_none(),
                            action="update_task",
                            changes=changes,
                        )
            else:
                workflow_step_task = WorkflowStepTask(
                    name="Extraction",
                    data={"searchphrases": manual_input},
                )
                workflow_step_task.save()

                if workflow_step.tasks is None:
                    workflow_step.tasks = []
                workflow_step.tasks.append(workflow_step_task)
                workflow_step.save()
                changes = build_changes(
                    {"task": ("", _task_summary("Extraction", workflow_step_task.data))}
                )
                if workflow:
                    log_edit_history(
                        kind="workflow",
                        obj_id=str(workflow.id),
                        user=_workflow_user_or_none(),
                        action="add_task",
                        changes=changes,
                    )

        # Persist task-level input/output config
        if workflow_step_task:
            workflow_step_task.data["input_config"] = task_input_config
            workflow_step_task.data["output_config"] = task_output_config
            workflow_step_task.save()

        return jsonify({"response": "success"})
    return None


## @MARK: ~~ Attachments
@login_required
@workflows.route("/add_attachment", methods=["GET", "POST"])
def workflow_add_attachment() -> ResponseReturnValue:
    """Handle the addition of attachments to a workflow step."""
    user = current_user
    user_id = user.get_id()
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = next(iter(request.args.keys()))  # Get the JSON string key
        data = json.loads(data_str)  # Retrieve query parameters, if any
        workflow_id = data.get("workflow_uuid")
        space_id = data.get("space_id")
        user = current_user

        workflow = Workflow.objects(id=workflow_id).first()
        current_space = Space.objects(uuid=space_id).first()
        files = SmartDocument.objects(
            user_id=user_id,
            space=current_space.uuid,
        )

        template = render_template(
            "workflows/modals/workflow_add_attachments_modal.html",
            workflow=workflow,
            files=files,
        )
        response = {"template": template}
        return jsonify(response)
    if request.method == "POST":
        # Handle POST request - create a new WorkflowStep
        data = request.get_json()
        workflow_id = data["workflow_uuid"]
        document_uuid = data["document_uuid"]

        workflow = Workflow.objects(id=workflow_id).first()
        attachment = WorkflowAttachment(attachment=document_uuid)
        attachment.save()
        workflow.attachments.append(attachment)
        workflow.save()

        return jsonify({"response": "Placeholder"})
    return None


## @MARK: ~~ Prompts
@workflows.route("/add_prompt_step", methods=["GET", "POST"])
def workflow_add_prompt_step() -> ResponseReturnValue:
    """Add a prompt step to the workflow."""
    user_id = current_user.get_id()
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = next(iter(request.args.keys()))  # Get the JSON string key
        data = json.loads(data_str)  # Retrieve query parameters, if any
        workflow_id = data.get("workflow_uuid")
        space_id = data.get("space_id")

        is_editing = data.get("is_editing") or False
        workflow_task_id = ""
        workflow_task = None

        workflow = Workflow.objects(id=workflow_id).first()
        current_space = Space.objects(uuid=space_id).first()

        if is_editing:
            workflow_task_id = data.get("workflow_task_id")
            workflow_task = WorkflowStepTask.objects(id=workflow_task_id).first()

        prompts = SearchSetItem.objects(
            user_id=user_id,
            space_id=current_space.uuid,
            searchtype="prompt",
        ).all()

        template = render_template(
            "workflows/modals/workflow_add_prompt_modal.html",
            workflow=workflow,
            prompts=prompts,
            is_editing=is_editing,
            workflow_task_id=workflow_task_id,
            workflow_task=workflow_task,
        )
        response = {"template": template}
        return jsonify(response)

    if request.method == "POST":
        # Handle POST request - create a new WorkflowStep
        data = request.get_json()
        workflow_step_id = data.get("workflow_step_id", None)
        task_id = data.get("workflow_task_id", None)
        search_set_item_id = data.get("search_set_item_id", None)
        manual_input = data.get("manual_input", None)
        task_input_config = data.get("input_config", {"source": "step_input"})
        task_output_config = data.get("output_config", {"post_process_prompt": ""})
        workflow_step = WorkflowStep.objects(id=ObjectId(workflow_step_id)).first()
        workflow = _workflow_for_step(workflow_step) if workflow_step else None

        if search_set_item_id:
            workflow_step_task = None
            searchsetitem = SearchSetItem.objects(id=search_set_item_id).first()
            # Editing
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    before_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    workflow_step_task.data = searchsetitem.to_workflow_step_data()
                    workflow_step_task.save()
                    after_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    changes = build_changes({"task": (before_summary, after_summary)})
                    if workflow:
                        log_edit_history(
                            kind="workflow",
                            obj_id=str(workflow.id),
                            user=_workflow_user_or_none(),
                            action="update_task",
                            changes=changes,
                        )
            else:
                workflow_step_task = WorkflowStepTask(
                    name="Prompt",
                    data=searchsetitem.to_workflow_step_data(),
                )
                workflow_step_task.save()
                workflow_step.tasks.append(workflow_step_task)
                workflow_step.save()
                changes = build_changes(
                    {"task": ("", _task_summary("Prompt", workflow_step_task.data))}
                )
                if workflow:
                    log_edit_history(
                        kind="workflow",
                        obj_id=str(workflow.id),
                        user=_workflow_user_or_none(),
                        action="add_task",
                        changes=changes,
                    )
        elif manual_input:
            workflow_step_task = None
            # Editing
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    before_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    workflow_step_task.data = {"prompt": manual_input}
                    workflow_step_task.save()
                    after_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    changes = build_changes({"task": (before_summary, after_summary)})
                    if workflow:
                        log_edit_history(
                            kind="workflow",
                            obj_id=str(workflow.id),
                            user=_workflow_user_or_none(),
                            action="update_task",
                            changes=changes,
                        )
            else:
                workflow_step_task = WorkflowStepTask(
                    name="Prompt",
                    data={"prompt": manual_input},
                )
                workflow_step_task.save()
                workflow_step.tasks.append(workflow_step_task)
                workflow_step.save()
                changes = build_changes(
                    {"task": ("", _task_summary("Prompt", workflow_step_task.data))}
                )
                if workflow:
                    log_edit_history(
                        kind="workflow",
                        obj_id=str(workflow.id),
                        user=_workflow_user_or_none(),
                        action="add_task",
                        changes=changes,
                    )

        # Persist task-level input/output config
        if workflow_step_task:
            workflow_step_task.data["input_config"] = task_input_config
            workflow_step_task.data["output_config"] = task_output_config
            workflow_step_task.save()

        return jsonify({"response": "success"})
    return None


## @MARK: ~~ Formatting
@workflows.route("/add_formatter_step", methods=["GET", "POST"])
def workflow_add_format_step() -> ResponseReturnValue:
    """Add a formatter step to the workflow."""
    user_id = current_user.get_id()
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = next(iter(request.args.keys()))  # Get the JSON string key
        data = json.loads(data_str)  # Retrieve query parameters, if any
        workflow_id = data.get("workflow_uuid")
        space_id = data.get("space_id")

        is_editing = data.get("is_editing") or False
        workflow_task = None
        workflow_task_id = ""

        if is_editing:
            workflow_task_id = data.get("workflow_task_id")
            workflow_task = WorkflowStepTask.objects(id=workflow_task_id).first()

        workflow = Workflow.objects(id=workflow_id).first()

        current_space = Space.objects(uuid=space_id).first()
        formatters = SearchSetItem.objects(
            user_id=user_id,
            space_id=current_space.uuid,
            searchtype="formatter",
        ).all()

        template = render_template(
            "workflows/modals/workflow_add_formatting_modal.html",
            workflow=workflow,
            formatters=formatters,
            is_editing=is_editing,
            workflow_task=workflow_task,
            workflow_task_id=workflow_task_id,
        )
        response = {"template": template}
        return jsonify(response)

    if request.method == "POST":
        # Handle POST request - create a new WorkflowStep
        data = request.get_json()
        workflow_step_id = data.get("workflow_step_id", None)
        task_id = data.get("workflow_task_id", None)

        search_set_item_id = data.get("search_set_item_id", None)
        manual_input = data.get("manual_input", None)
        task_input_config = data.get("input_config", {"source": "step_input"})
        task_output_config = data.get("output_config", {"post_process_prompt": ""})
        workflow_step = WorkflowStep.objects(id=ObjectId(workflow_step_id)).first()
        workflow = _workflow_for_step(workflow_step) if workflow_step else None

        workflow_step_task = None

        if search_set_item_id:
            searchsetitem = SearchSetItem.objects(id=search_set_item_id).first()
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    before_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    workflow_step_task.data = searchsetitem.to_workflow_step_data()
                    workflow_step_task.save()
                    after_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    changes = build_changes({"task": (before_summary, after_summary)})
                    if workflow:
                        log_edit_history(
                            kind="workflow",
                            obj_id=str(workflow.id),
                            user=_workflow_user_or_none(),
                            action="update_task",
                            changes=changes,
                        )
            else:
                workflow_step_task = WorkflowStepTask(
                    name="Formatter",
                    data=searchsetitem.to_workflow_step_data(),
                )
                workflow_step_task.save()
                workflow_step.tasks.append(workflow_step_task)
                workflow_step.save()
                changes = build_changes(
                    {"task": ("", _task_summary("Formatter", workflow_step_task.data))}
                )
                if workflow:
                    log_edit_history(
                        kind="workflow",
                        obj_id=str(workflow.id),
                        user=_workflow_user_or_none(),
                        action="add_task",
                        changes=changes,
                    )
        elif manual_input:
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    before_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    workflow_step_task.data = {"prompt": manual_input}
                    workflow_step_task.save()
                    after_summary = _task_summary(
                        workflow_step_task.name, workflow_step_task.data
                    )
                    changes = build_changes({"task": (before_summary, after_summary)})
                    if workflow:
                        log_edit_history(
                            kind="workflow",
                            obj_id=str(workflow.id),
                            user=_workflow_user_or_none(),
                            action="update_task",
                            changes=changes,
                        )
            else:
                workflow_step_task = WorkflowStepTask(
                    name="Formatter",
                    data={"prompt": manual_input},
                )
                workflow_step_task.save()
                if workflow_step.tasks is None:
                    workflow_step.tasks = []
                workflow_step.tasks.append(workflow_step_task)
                workflow_step.save()
                changes = build_changes(
                    {"task": ("", _task_summary("Formatter", workflow_step_task.data))}
                )
                if workflow:
                    log_edit_history(
                        kind="workflow",
                        obj_id=str(workflow.id),
                        user=_workflow_user_or_none(),
                        action="add_task",
                        changes=changes,
                    )

        # Persist task-level input/output config
        if workflow_step_task:
            workflow_step_task.data["input_config"] = task_input_config
            workflow_step_task.data["output_config"] = task_output_config
            workflow_step_task.save()

        return jsonify({"response": "success"})
    return None


## @MARK: ~~ Documents
@workflows.route("/add_document_step", methods=["GET", "POST"])
def workflow_add_document_step() -> ResponseReturnValue:
    """Add a document step to the workflow."""
    user_id = current_user.get_id()
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = next(iter(request.args.keys()))  # Get the JSON string key
        data = json.loads(data_str)  # Retrieve query parameters, if any
        workflow_id = data.get("workflow_uuid")
        space_id = data.get("space_id")

        workflow = Workflow.objects(id=workflow_id).first()

        current_space = Space.objects(uuid=space_id).first()
        global_extraction_sets = SearchSet.objects(
            space=current_space.uuid,
            is_global=True,
            set_type="document",
        ).all()
        user_extraction_sets = SearchSet.objects(
            user_id=user_id,
            space=current_space.uuid,
            is_global=False,
            set_type="extraction",
        ).all()
        extraction_sets_objects = list(
            chain(global_extraction_sets, user_extraction_sets),
        )
        extraction_sets = [
            extraction["title"]
            for extraction in extraction_sets_objects
            if "title" in extraction
        ]

        template = render_template(
            "workflows/modals/workflow_add_documents_modal.html",
            workflow=workflow,
            extraction_sets=extraction_sets,
        )
        response = {"template": template}
        return jsonify(response)

    if request.method == "POST":
        # Handle POST request - create a new WorkflowStep

        return jsonify({"response": "Placeholder"})
    return None


@login_required
@workflows.route("/duplicate/<workflow_id>")
def duplicate_workflow(workflow_id):
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    # 1) Load original
    orig = Workflow.objects(id=workflow_id).first()
    user_id = user.get_id()
    if not orig:
        return
        # abort(404, "Workflow not found")

    # 2) Duplicate each step & task
    new_steps = []
    for step in orig.steps:
        # duplicate tasks
        new_tasks = []
        for task in step.tasks:
            dup_task = WorkflowStepTask(name=task.name, data=task.data.copy()).save()
            new_tasks.append(dup_task)

        dup_step = WorkflowStep(
            name=step.name, tasks=new_tasks, data=(step.data or {}).copy()
        ).save()
        new_steps.append(dup_step)

    # 3) Duplicate attachments
    new_atts = []
    for att in orig.attachments:
        dup_att = WorkflowAttachment(attachment=att.attachment).save()
        new_atts.append(dup_att)

    # 4) Create the new Workflow
    dup_wf = Workflow(
        name=orig.name,
        description=orig.description,
        user_id=user_id,
        space=Space.objects()[0].uuid,  # or however you track the user’s active space
        steps=new_steps,
        attachments=new_atts,
        # created_at and updated_at default to now()
    )
    dup_wf.save()

    flash("Workflow duplicated into your space!", "success")
    return redirect(url_for("home.index", sesction="Workflows"))

@login_required
@workflows.route("/add_browser_automation_step", methods=["GET", "POST"])
def add_browser_automation_step() -> ResponseReturnValue:
    """Add a browser automation step to a workflow."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))

    if request.method == "GET":
        # Handle GET request - return the template
        data_str = next(iter(request.args.keys()))  # Get the JSON string key
        data = json.loads(data_str)
        workflow_id = data.get("workflow_uuid")
        workflow_step_id = data.get("workflow_step_id")
        is_editing = data.get("is_editing") or False
        workflow_task_id = data.get("workflow_task_id", "")
        workflow_task = None

        if is_editing and workflow_task_id:
            workflow_task = WorkflowStepTask.objects(
                id=ObjectId(workflow_task_id),
            ).first()

        workflow = Workflow.objects(id=workflow_id).first()
        external_variables = _get_previous_step_variables(workflow, workflow_step_id)

        template = render_template(
            "workflows/workflow_steps/workflow_add_browser_automation_modal.html",
            workflow=workflow,
            workflow_step_id=workflow_step_id,
            is_editing=is_editing,
            workflow_task_id=workflow_task_id,
            workflow_task=workflow_task,
            external_variables=external_variables,
        )
        response = {"template": template}
        return jsonify(response)

    if request.method == "POST":
        # Handle POST request - save the step configuration
        data = request.get_json()
        workflow_step_id = data.get("workflow_step_id")
        workflow_task_id = data.get("workflow_task_id")
        actions = data.get("actions", [])
        summarization = data.get("summarization", {})
        allowed_domains = data.get("allowed_domains", [])
        model = data.get("model", "claude-sonnet-4-5")
        timeout_seconds = data.get("timeout_seconds", 300)

        # Debug logging
        print(f"[Browser Automation Save] Received {len(actions)} actions")
        print(f"[Browser Automation Save] Actions: {actions}")
        print(f"[Browser Automation Save] Task ID: {workflow_task_id}")

        # Find the workflow step
        if workflow_step_id and workflow_step_id != '{{ workflow_step.id }}':
            step = WorkflowStep.objects(id=workflow_step_id).first()
            if not step:
                return jsonify({"success": False, "error": "Step not found"}), 404
        else:
            step = None

        task_data = {
            "actions": actions,
            "summarization": summarization,
            "allowed_domains": allowed_domains,
            "model": model,
            "timeout_seconds": timeout_seconds
        }

        if workflow_task_id and workflow_task_id != '{{ workflow_task_id }}':
            # Update existing task
            task = WorkflowStepTask.objects(id=ObjectId(workflow_task_id)).first()
            if task:
                task.data = task_data
                task.save()
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": "Task not found"}), 404

        # Create new task
        task = WorkflowStepTask(
            name="BrowserAutomation",
            data=task_data
        )
        task.save()

        # If we have a step ID, add the task to it
        if step:
            if step.tasks is None:
                step.tasks = []
            step.tasks.append(task)
            step.save()
            return jsonify({"success": True})

        # If no step ID, create a new step
        workflow_id = data.get("workflow_id") or data.get("workflow_uuid")
        if workflow_id:
            workflow = Workflow.objects(id=workflow_id).first()
            if workflow:
                step = WorkflowStep(name="Browser Automation Step")
                step.tasks = [task]
                step.save()
                workflow.steps.append(step)
                workflow.save()
                return jsonify({"success": True, "step_id": str(step.id)})

        return jsonify({"success": False, "error": "Could not save step"}), 400

    return jsonify({"error": "Method not allowed"}), 405

@login_required
@workflows.route("/add_document_renderer_step", methods=["GET"])
def add_document_renderer_step() -> ResponseReturnValue:
    return _render_output_node_modal("document_renderer", "Document Renderer")

@login_required
@workflows.route("/add_form_filler_step", methods=["GET"])
def add_form_filler_step() -> ResponseReturnValue:
    return _render_output_node_modal("form_filler", "Form Filler")

@login_required
@workflows.route("/add_data_export_step", methods=["GET"])
def add_data_export_step() -> ResponseReturnValue:
    return _render_output_node_modal("data_export", "Data Export")

@login_required
@workflows.route("/add_package_builder_step", methods=["GET"])
def add_package_builder_step() -> ResponseReturnValue:
    return _render_output_node_modal("package_builder", "Package Builder")

def _render_output_node_modal(node_type, node_type_name):
    data_str = next(iter(request.args.keys()))
    data = json.loads(data_str)
    workflow_step_id = data.get("workflow_step_id")

    template = render_template(
        "workflows/workflow_steps/workflow_add_output_node_modal.html",
        node_type=node_type,
        node_type_name=node_type_name,
        node_type_camel=node_type.title().replace("_", ""),
        workflow_step_id=workflow_step_id
    )
    return jsonify({"template": template})

@login_required
@workflows.route("/save_output_step", methods=["POST"])
def save_output_step() -> ResponseReturnValue:
    data = request.get_json()
    workflow_step_id = data.get("workflow_step_id")
    workflow_task_id = data.get("workflow_task_id")
    node_type = data.get("node_type")
    config = data.get("config")

    task_name_map = {
        "document_renderer": "DocumentRenderer",
        "form_filler": "FormFiller",
        "data_export": "DataExport",
        "package_builder": "PackageBuilder"
    }

    # Find step logic
    step = WorkflowStep.objects(id=workflow_step_id).first()
    if not step:
        return jsonify({"error": "Step not found"}), 404

    # Update or Create Task
    task_data = {"config": config, "name": task_name_map.get(node_type, "OutputNode")}

    if workflow_task_id:
        task = WorkflowStepTask.objects(id=workflow_task_id).first()
        if task:
           task.name = task_name_map.get(node_type, "OutputNode")
           task.data = task_data
           task.save()
           if not step.is_output:
               step.is_output = True
               step.save()
    else:
        task = WorkflowStepTask(
            name=task_name_map.get(node_type, "OutputNode"),
            data=task_data
        )
        task.save()
        step.tasks.append(task)
        step.is_output = True
        step.save()

    return jsonify({"success": True})


# =========================================================
# @MARK: ~~ Evaluation / Self-Validation
# =========================================================


@login_required
@workflows.route("/workflow/<workflow_id>/generate-eval-plan", methods=["POST"])
def generate_eval_plan(workflow_id: str) -> ResponseReturnValue:
    """Generate an evaluation plan for a workflow."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))

    workflow = Workflow.objects(id=workflow_id).first()
    if not workflow:
        return jsonify({"error": WORKFLOW_NOT_FOUND_MESSAGE}), 404

    data = request.get_json() or {}
    coverage_level = data.get("coverage_level", "standard")
    if coverage_level not in ("quick", "standard", "exhaustive"):
        coverage_level = "standard"

    from app.utilities.evaluation_tasks import generate_evaluation_plan_task

    async_result = generate_evaluation_plan_task.delay(
        workflow_id=workflow_id,
        coverage_level=coverage_level,
        user_id=user.get_id(),
    )

    return (
        jsonify({"status": "accepted", "task_id": async_result.id}),
        202,
    )


@login_required
@workflows.route("/workflow-runs/<run_id>/validate", methods=["POST"])
def validate_workflow_run(run_id: str) -> ResponseReturnValue:
    """Run validation against a completed workflow result."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))

    workflow_result = WorkflowResult.objects(id=run_id).first()
    if not workflow_result:
        return jsonify({"error": "Workflow result not found"}), 404

    if workflow_result.status != "completed":
        return (
            jsonify({"error": "Workflow must be completed before validation"}),
            400,
        )

    data = request.get_json() or {}
    plan_id = data.get("plan_id")

    if not plan_id:
        from app.models import EvaluationPlan

        plan = (
            EvaluationPlan.objects(workflow=workflow_result.workflow)
            .order_by("-created_at")
            .first()
        )
        if not plan:
            return (
                jsonify(
                    {"error": "No evaluation plan found. Generate one first."}
                ),
                404,
            )
        plan_id = str(plan.id)

    from app.utilities.evaluation_tasks import run_validation_task

    async_result = run_validation_task.delay(
        plan_id=plan_id,
        workflow_result_id=run_id,
        user_id=user.get_id(),
    )

    return (
        jsonify({"status": "accepted", "task_id": async_result.id}),
        202,
    )


@login_required
@workflows.route("/workflow-runs/<run_id>/validation-report", methods=["GET"])
def get_validation_report(run_id: str) -> ResponseReturnValue:
    """Get the validation report for a workflow run."""
    from app.models import EvaluationRun

    evaluation_run = (
        EvaluationRun.objects(workflow_result=run_id)
        .order_by("-created_at")
        .first()
    )

    if not evaluation_run:
        return jsonify({"error": "No validation report found"}), 404

    return jsonify(
        {
            "uuid": evaluation_run.uuid,
            "status": evaluation_run.status,
            "overall_score": evaluation_run.overall_score,
            "grade": evaluation_run.grade,
            "num_passed": evaluation_run.num_passed,
            "num_failed": evaluation_run.num_failed,
            "num_warned": evaluation_run.num_warned,
            "num_skipped": evaluation_run.num_skipped,
            "check_results": evaluation_run.check_results,
            "started_at": evaluation_run.started_at.isoformat()
            if evaluation_run.started_at
            else None,
            "finished_at": evaluation_run.finished_at.isoformat()
            if evaluation_run.finished_at
            else None,
            "model_used": evaluation_run.model_used,
            "error": evaluation_run.error,
        }
    )


@workflows.route("/eval-plan/status/<task_id>", methods=["GET"])
def eval_plan_status(task_id: str) -> ResponseReturnValue:
    """Poll the status of an evaluation plan generation task."""
    if not task_id:
        return jsonify({"error": "task_id is required"}), 400

    result = AsyncResult(task_id, app=celery_app)
    state = result.state
    response: dict[str, object] = {"task_id": task_id, "state": state}

    if result.successful():
        response["result"] = result.result
    elif result.failed():
        response["error"] = str(result.result)

    return jsonify(response)


@workflows.route("/validation/status/<task_id>", methods=["GET"])
def validation_status(task_id: str) -> ResponseReturnValue:
    """Poll the status of a validation run task."""
    if not task_id:
        return jsonify({"error": "task_id is required"}), 400

    result = AsyncResult(task_id, app=celery_app)
    state = result.state
    response: dict[str, object] = {"task_id": task_id, "state": state}

    if result.successful():
        response["result"] = result.result
    elif result.failed():
        response["error"] = str(result.result)

    return jsonify(response)
