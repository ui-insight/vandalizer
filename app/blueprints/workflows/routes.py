"""Handle workflow routes."""

import json
import os
import tempfile
import uuid
from itertools import chain

import pypandoc
from bson import ObjectId
from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from werkzeug.utils import secure_filename

from app.models import (
    SearchSet,
    SearchSetItem,
    SmartDocument,
    Space,
    User,
    UserModelConfig,
    Workflow,
    WorkflowAttachment,
    WorkflowResult,
    WorkflowStep,
    WorkflowStepTask,
)
from app.utilities.config import settings
from app.utilities.document_helpers import save_excel_to_html
from app.utilities.workflow import execute_task_step_test, execute_workflow_task
from app.utils import load_user

from . import workflows


@workflows.route("/create_workflow", methods=["POST"])
def add_workflow() -> ResponseReturnValue:
    """Create a new workflow."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_data = request.get_json()
    workflow = Workflow(
        name=workflow_data["name"],
        description=workflow_data["description"],
        user_id=session["user_id"],
    )
    workflow.save()
    return jsonify(
        {
            "reroute": url_for(
                "home.index",
                section="Workflows",
                workflow_id=str(workflow.id),
            ),
        },
    )


@workflows.route("/edit", methods=["POST"])
def edit_workflow() -> ResponseReturnValue:
    """Edit an existing prompt."""
    data = request.get_json()
    uuid = data["uuid"]
    load_user()
    workflow = Workflow.objects(id=uuid).first()

    template = render_template(
        "workflows/edit_workflow.html",
        workflow=workflow,
    )
    response = {
        "template": template,
    }

    return jsonify(response)


@workflows.route("/delete", methods=["POST"])
def delete_workflow() -> ResponseReturnValue:
    """Delete a workflow by ID."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    data = request.get_json()
    uuid = data["uuid"]
    print(uuid)
    Workflow.objects(id=uuid).delete()
    return {"success": True}


@workflows.route("/update_workflow", methods=["POST"])
def update_workflow() -> ResponseReturnValue:
    """Update a workflow by ID."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_data = request.get_json()
    workflow_id = workflow_data["workflow_id"]
    workflow = Workflow.objects(id=workflow_id).first()
    workflow.name = workflow_data["name"]
    workflow.description = workflow_data["description"]
    workflow.save()
    return {"success": True}


@workflows.route("/workflow/run", methods=["POST"])
def run_workflow() -> ResponseReturnValue:
    """Run a workflow."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))

    workflow_data = request.get_json()
    workflow_id = workflow_data["workflow_id"]
    session_id = workflow_data["session_id"]
    document_uuids = workflow_data["document_uuids"]

    user_id = load_user().user_id

    workflow = Workflow.objects(id=workflow_id).first()
    workflow_result = WorkflowResult(workflow=workflow, session_id=session_id)
    workflow_result.save()
    attachments = [
        SmartDocument.objects(uuid=x.attachment).first() for x in workflow.attachments
    ]
    docs = [SmartDocument.objects(uuid=x).first() for x in document_uuids]
    for doc in docs:
        if not doc.valid:
            workflow_result.status = "failed"
            workflow_result.save()
            return jsonify(
                {
                    "output": [
                        f"The document {doc.title} failed validation, please fix the validation errors and try again: \n\n{doc.validation_feedback}"
                    ],
                    "steps": [],
                }
            )

    document_trigger_step = WorkflowStep(
        name="Document",
        data={"docs": docs, "attachments": attachments, "user_id": user_id},
    )
    document_trigger_step.save()

    model_config = UserModelConfig.objects(user_id=user.user_id).first()
    model = settings.base_model
    if model_config:
        model = model_config.name

    workflow_id = str(workflow.id)
    workflow_result_id = str(workflow_result.id)
    workflow_trigger_step_id = str(document_trigger_step.id)
    print("Running workflow", workflow_id, workflow_result_id, workflow_trigger_step_id)
    async_result = execute_workflow_task.delay(
        workflow_result_id=workflow_result_id,
        workflow_id=workflow_id,
        workflow_trigger_step_id=workflow_trigger_step_id,
        model=model,
    )
    print("Async result", async_result)
    workflow_output = async_result.get(timeout=600)
    if workflow_output is None:
        return jsonify({"error": "Workflow execution failed"})
    output = workflow_output.get("output")
    data = workflow_output.get("history")
    if not output:
        return {
            "output": [],
            "steps": [],
            "status": "error",
            "error": "Workflow failed to execute",
        }

    return {"output": output, "steps": data}


@workflows.route("/workflow/step/test", methods=["POST"])
def test_workflow_step() -> ResponseReturnValue:
    """Run a workflow step."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))

    workflow_data = request.get_json()
    task_name = workflow_data["task_name"]
    task_data = workflow_data["task_data"]
    document_uuids = workflow_data["document_uuids"]

    user_id = load_user().user_id
    print(workflow_data)
    docs = [SmartDocument.objects(uuid=x).first() for x in document_uuids]
    document_trigger_step = WorkflowStep(
        name="Document",
        data={"docs": docs, "user_id": user_id},
    )
    document_trigger_step.save()

    async_result = execute_task_step_test.delay(
        task_name=task_name,
        task_data=task_data,
        document_trigger_step_id=str(document_trigger_step.id),
    )
    workflow_output = async_result.get(timeout=600)
    if workflow_output is None:
        return jsonify({"error": "Workflow execution failed"})
    # output = workflow_output.get("output")
    print(workflow_output)

    return {"output": workflow_output}


# @MARK: ~~ Run integration
@workflows.route("/workflow/run", methods=["GET", "POST"])
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
        return jsonify({"error": "Workflow not found"}), 404

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
            pypandoc.convert_file(file_path, "pdf", outputfile=pdf_path)
            extension = "pdf"
            file_path = pdf_path
        elif extension in ["xlsx", "xls"]:
            html_path = os.path.join(upload_dir, f"{uid}.html")
            save_excel_to_html(file_path, html_path)
            extension = "html"
            file_path = html_path

        # **Create SmartDocument Object**
        document = SmartDocument(
            title=filename,
            path=f"{user.id}/{uid}.{extension}",
            extension=extension,
            uuid=uid,
            user_id=user.user_id,
            space="None",
        )
        document.save()
        document_uuids.append(uid)

    # **5. Prepare Workflow Execution**
    workflow_result = WorkflowResult(workflow=workflow, session_id=session_id)

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

    # **6. Execute the Workflow**
    workflow_output = execute_workflow_task.delay(
        workflow_result_id=str(workflow_result.id),
        workflow_id=str(workflow.id),
        workflow_trigger_step_id=workflow_trigger_step_id,
    )
    workflow_output = workflow_output.get()
    output = workflow_output["output"]
    data = workflow_output["history"]

    # **7. Return the Response**
    return jsonify({"output": output, "steps": data})


@workflows.route("/workflow/status", methods=["GET"])
def workflow_status() -> ResponseReturnValue:
    """Poll the workflow status."""
    session_id = request.args.get("session_id")

    if not session_id:
        return jsonify({"error": "workflow_id is required"}), 400

    # Get workflow status
    workflow_result = WorkflowResult.objects(session_id=session_id).first()

    if not workflow_result:
        return jsonify({"error": "Workflow not found"}), 404

    response = {
        "steps_completed": workflow_result.num_steps_completed,
        "total_steps": workflow_result.num_steps_total,
        # "time_elapsed": int(time_elapsed)
        "status": workflow_result.status,
    }

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
@workflows.route("/download", methods=["GET"])
def workflow_download() -> ResponseReturnValue:
    """Download workflow results."""
    session_id = request.args.get("session_id")

    if not session_id:
        return jsonify({"error": "workflow_id is required"}), 400

    # Get workflow status
    workflow_result = WorkflowResult.objects(session_id=session_id).first()

    if not workflow_result:
        return jsonify({"error": "Workflow not found"}), 404

    # Ensure the static folder exists
    os.makedirs(os.path.join(current_app.root_path, "static"), exist_ok=True)

    final_output = list(workflow_result.steps_output.values())[-1]

    tmp_file = tempfile.TemporaryFile()
    tmp_file.write(json.dumps(final_output["output"], indent=4).encode())
    tmp_file.seek(0)

    # Return the path to the CSV file
    return send_file(tmp_file, download_name="workflow_output.txt", as_attachment=True)


## @MARK: ~~ Integrate
@workflows.route("/integrate", methods=["POST"])
def workflow_integrate() -> ResponseReturnValue:
    """Integrate a workflow template."""
    user = load_user()
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

    template = render_template(
        "workflows/workflow.html",
        workflow=workflow,
    )

    response = {
        "template": template,
    }

    return jsonify(response)


@workflows.route("/update_title", methods=["POST"])
def update_workflow_title() -> ResponseReturnValue:
    """Update the title of a workflow."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_data = request.get_json()
    workflow_id = workflow_data["uuid"]
    workflow = Workflow.objects(id=ObjectId(workflow_id)).first()
    workflow.name = workflow_data["title"]
    workflow.save()

    response = {"complete": True}
    return jsonify(response)


## MARK: Workflow steps
@workflows.route("/add_workflow_step", methods=["POST"])
def add_workflow_step() -> ResponseReturnValue:
    """Add a new step to a workflow."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_step_data = request.get_json()
    workflow_id = workflow_step_data["workflow_id"]
    workflow = Workflow.objects(id=workflow_id).first()
    step_title = workflow_step_data["title"]

    workflow_step = WorkflowStep(name=step_title)
    workflow_step.save()
    workflow.steps.append(workflow_step)
    workflow.save()
    template = render_template(
        "workflows/workflow_steps/edit_workflow_step_modal.html",
        workflow=workflow,
        workflow_step_id=workflow_step.id,
        workflow_step=workflow_step,
    )

    response = {"template": template}
    return jsonify(response)


@workflows.route("/edit_step", methods=["POST"])
def edit_workflow_step() -> ResponseReturnValue:
    """Edit a step in a workflow."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_step_data = request.get_json()
    workflow_id = workflow_step_data["workflow_id"]
    workflow_step_id = workflow_step_data["workflow_step_id"]
    workflow = Workflow.objects(id=workflow_id).first()
    workflow_step = WorkflowStep.objects(id=workflow_step_id).first()
    template = render_template(
        "workflows/workflow_steps/edit_workflow_step_modal.html",
        workflow=workflow,
        workflow_step_id=workflow_step.id,
        workflow_step=workflow_step,
    )

    response = {"template": template}
    return jsonify(response)


@workflows.route("/step/update_title", methods=["POST"])
def update_workflow_step_title() -> ResponseReturnValue:
    """Update the title of a workflow step."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_step_data = request.get_json()
    workflow_step_id = workflow_step_data["workflow_step_id"]
    workflow_step = WorkflowStep.objects(id=ObjectId(workflow_step_id)).first()
    workflow_step.name = workflow_step_data["title"]
    workflow_step.save()

    response = {"complete": True}
    return jsonify(response)


@workflows.route("/step/add_task", methods=["POST"])
def add_workflow_add_task() -> ResponseReturnValue:
    """Add a task to a workflow step."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_step_data = request.get_json()
    workflow_id = workflow_step_data["workflow_id"]
    workflow_step_id = workflow_step_data["workflow_step_id"]
    workflow = Workflow.objects(id=workflow_id).first()
    workflow_step = WorkflowStep.objects(id=workflow_step_id).first()
    template = render_template(
        "workflows/workflow_steps/new_workflow_task_modal.html",
        workflow=workflow,
        workflow_step_id=workflow_step.id,
        workflow_step=workflow_step,
    )

    response = {"template": template}
    return jsonify(response)


@workflows.route("/step/add_step_task", methods=["POST"])
def add_workflow_step_task() -> ResponseReturnValue:
    """Add a task to a specific step in a workflow."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_step_data = request.get_json()
    workflow_step_id = workflow_step_data["workflow_step_id"]
    workflow_step = WorkflowStep.objects(id=workflow_step_id).first()
    task_name = workflow_step_data["task_name"]
    task_data = workflow_step_data["task_data"]
    workflow_step_task = WorkflowStepTask(name=task_name, data=task_data)
    workflow_step_task.save()
    workflow_step.tasks.append(workflow_step_task)
    workflow_step.save()
    return jsonify({"complete": True})


@workflows.route("/delete_step", methods=["POST"])
def delete_workflow_step() -> ResponseReturnValue:
    """Delete a specific step in a workflow."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))

    workflow_data = request.get_json()
    workflow_step_id = workflow_data["workflow_step_id"]
    step = WorkflowStep.objects(id=workflow_step_id).first()
    if not step:
        return jsonify({"success": False, "error": "Step not found"}), 404

    # Delete all associated WorkflowStepTasks
    for task in step.tasks:
        task.delete()

    # Remove references to the step in any Workflow
    Workflow.objects(steps=step).update(pull__steps=step)

    # Delete the WorkflowStep itself
    step.delete()

    return jsonify({"success": True})


@workflows.route("/delete_step_task", methods=["POST"])
def delete_workflow_step_task() -> ResponseReturnValue:
    """Delete a specific task in a workflow step."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))

    workflow_data = request.get_json()
    print(workflow_data)
    workflow_task_id = workflow_data["workflow_task_id"]
    task = WorkflowStepTask.objects(id=workflow_task_id).first()
    if not task:
        return jsonify({"success": False, "error": "Step not found"}), 404

    # Remove references to the step in any Workflow
    WorkflowStep.objects(tasks=task).update(pull__tasks=task)

    # Delete all associated WorkflowStepTasks
    task.delete()

    return jsonify({"success": True})


@workflows.route("/update_workflow_step", methods=["POST"])
def update_workflow_step() -> ResponseReturnValue:
    """Update a specific step in a workflow."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_data = request.get_json()
    workflow_id = workflow_data["workflow_id"]
    step_index = workflow_data["step_index"]
    step = workflow_data["step"]
    workflow = Workflow.objects(id=workflow_id).first()
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
        workflow_id = data["workflow_uuid"]
        search_set_id = data.get("search_set_id", None)
        manual_input = data.get("manual_input", None)
        workflow_step_id = data.get("workflow_step_id", None)
        task_id = data.get("workflow_task_id", None)
        workflow = Workflow.objects(id=workflow_id).first()
        workflow_step = WorkflowStep.objects(id=ObjectId(workflow_step_id)).first()
        workflow_step_task = None

        if search_set_id:
            searchset = SearchSet.objects(uuid=search_set_id).first()

            workflow_step_task = None
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    workflow_step_task.data = searchset.to_workflow_step_data()
                    workflow_step_task.save()
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

        elif manual_input:
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    workflow_step_task.data = {"searchphrases": manual_input}
                    workflow_step_task.save()
                return jsonify({"response": "success"})
            workflow_step_task = WorkflowStepTask(
                name="Extraction",
                data={"searchphrases": manual_input},
            )
            workflow_step_task.save()

            if workflow_step.tasks is None:
                workflow_step.tasks = []
            workflow_step.tasks.append(workflow_step_task)
            workflow_step.save()

        return jsonify({"response": "success"})
    return None


## @MARK: ~~ Attachments
@workflows.route("/add_attachment", methods=["GET", "POST"])
def workflow_add_attachment() -> ResponseReturnValue:
    """Handle the addition of attachments to a workflow step."""
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = next(iter(request.args.keys()))  # Get the JSON string key
        data = json.loads(data_str)  # Retrieve query parameters, if any
        workflow_id = data.get("workflow_uuid")
        space_id = data.get("space_id")
        user = load_user()

        workflow = Workflow.objects(id=workflow_id).first()
        current_space = Space.objects(uuid=space_id).first()
        files = SmartDocument.objects(
            user_id=user.user_id,
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
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = next(iter(request.args.keys()))  # Get the JSON string key
        data = json.loads(data_str)  # Retrieve query parameters, if any
        workflow_id = data.get("workflow_uuid")
        workflow_step_id = data.get("workflow_step_id")
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
            user_id=load_user().user_id,
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
        workflow_id = data["workflow_uuid"]
        workflow_step_id = data.get("workflow_step_id", None)
        task_id = data.get("workflow_task_id", None)
        search_set_item_id = data.get("search_set_item_id", None)
        manual_input = data.get("manual_input", None)
        workflow = Workflow.objects(id=workflow_id).first()
        workflow_step = WorkflowStep.objects(id=ObjectId(workflow_step_id)).first()

        if search_set_item_id:
            workflow_step_task = None
            searchsetitem = SearchSetItem.objects(id=search_set_item_id).first()
            # Editing
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    workflow_step_task.data = searchsetitem.to_workflow_step_data()
                    workflow_step_task.save()
            else:
                workflow_step_task = WorkflowStepTask(
                    name="Prompt",
                    data=searchsetitem.to_workflow_step_data(),
                )
                workflow_step_task.save()
                workflow_step.tasks.append(workflow_step_task)
                workflow_step.save()
        elif manual_input:
            workflow_step_task = None
            # Editing
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    workflow_step_task.data = {"prompt": manual_input}
                    workflow_step_task.save()
            else:
                workflow_step_task = WorkflowStepTask(
                    name="Prompt",
                    data={"prompt": manual_input},
                )
                workflow_step_task.save()
                workflow_step.tasks.append(workflow_step_task)
                workflow_step.save()

        return jsonify({"response": "success"})
    return None


## @MARK: ~~ Formatting
@workflows.route("/add_formatter_step", methods=["GET", "POST"])
def workflow_add_format_step() -> ResponseReturnValue:
    """Add a formatter step to the workflow."""
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
            user_id=load_user().user_id,
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

        workflow_id = data["workflow_uuid"]
        search_set_item_id = data.get("search_set_item_id", None)
        manual_input = data.get("manual_input", None)
        workflow = Workflow.objects(id=workflow_id).first()
        workflow_step = WorkflowStep.objects(id=ObjectId(workflow_step_id)).first()

        workflow_step_task = None

        if search_set_item_id:
            searchsetitem = SearchSetItem.objects(id=search_set_item_id).first()
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    workflow_step_task.data = searchsetitem.to_workflow_step_data()
                    workflow_step_task.save()
            else:
                workflow_step_task = WorkflowStepTask(
                    name="Formatter",
                    data=searchsetitem.to_workflow_step_data(),
                )
                workflow_step_task.save()
                workflow_step.tasks.append(workflow_step_task)
                workflow_step.save()
        elif manual_input:
            if task_id is not None and task_id != 0:
                workflow_step_task = WorkflowStepTask.objects(id=task_id).first()
                if workflow_step_task:
                    workflow_step_task.data = {"prompt": manual_input}
                    workflow_step_task.save()
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

        return jsonify({"response": "success"})
    return None


## @MARK: ~~ Documents
@workflows.route("/add_document_step", methods=["GET", "POST"])
def workflow_add_document_step() -> ResponseReturnValue:
    """Add a document step to the workflow."""
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
            user_id=workflow.user_id,
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
        data = request.get_json()
        workflow_id = data["workflow_uuid"]
        workflow = Workflow.objects(id=workflow_id).first()

        return jsonify({"response": "Placeholder"})
    return None
