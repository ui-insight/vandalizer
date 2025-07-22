"""Handle workflow routes."""

import asyncio
import io
import json
import os
import re
import uuid
from itertools import chain
from pathlib import Path

import pypandoc
from bson import ObjectId
from devtools import debug
from flask import (
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
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
from app.utilities.agents import create_chat_agent
from app.utilities.config import settings
from app.utilities.document_helpers import save_excel_to_html
from app.utilities.semantic_recommender import (
    SemanticRecommender,
)
from app.utilities.workflow import (
    execute_task_step_test,
    execute_workflow_task,
)
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


@workflows.route("/delete_workflow", methods=["POST"])
def delete_workflow() -> ResponseReturnValue:
    """Delete a workflow by ID."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    data = request.get_json()
    uuid = data["uuid"]
    print(uuid)
    workflow = Workflow.objects(id=uuid).first()

    WorkflowResult.objects(workflow=workflow).delete()
    workflow.delete()
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
    # Ingest workflow into vector database for future recommendations
    ingestion_text = ""
    ingestion_text += "# Documents selected:"

    for doc in docs:
        ingestion_text += f"\n{doc.raw_text}"

    persist_directory = Path("data/recommendations_vectordb")
    recommendation_manager = SemanticRecommender(persist_directory=persist_directory)
    recommendation_manager.ingest_recommendation_item(
        identifier=workflow_id,
        ingestion_text=ingestion_text,
        recommendation_type="Workflow",
    )
    return jsonify(
        {
            "status": "accepted",
            "workflow_result_id": workflow_result_id,
            "task_id": async_result.id,
        },
    ), 202


@workflows.route("/workflow/recommendations", methods=["POST"])
def get_workflow_recommendations_sync() -> ResponseReturnValue:
    """Get workflow recommendations synchronously (for immediate results)."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))

    request_data = request.get_json()
    document_uuids = request_data.get("uuids", [])
    space = request_data.get("space")
    limit = request_data.get("limit", 5)

    if not document_uuids:
        return jsonify({"recommendations": []}), 200

    user_id = user.user_id

    try:
        # Load documents
        documents = []
        for uuid in document_uuids:
            doc = SmartDocument.objects(uuid=uuid).first()
            if doc:
                documents.append(doc)

        if not documents:
            return jsonify(
                {"recommendations": [], "message": "No valid documents found"}
            ), 200

        persist_directory = Path("data/recommendations_vectordb")
        recommendation_manager = SemanticRecommender(
            persist_directory=persist_directory,
        )

        # Get recommendations
        recommendations = recommendation_manager.search_recommendations(
            selected_documents=documents,
            limit=limit,
        )

        templates = []

        # No recommendations, show a standard experience
        if len(recommendations) == 0:
            template = render_template(
                "toolpanel/recommendations/recommendations-none.html",
            )
            templates.append(template)
        else:  # Render the recommendations
            templates.append(
                render_template(
                    "toolpanel/recommendations/recommendation-title.html",
                )
            )
            recommended_workflows = []
            for recommendation in recommendations:
                identifier = recommendation["identifier"]
                recommendation_type = recommendation["recommendation_type"]
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
                elif recommendation_type == "Extraction":
                    search_set = SearchSet.objects(id=identifier).first()
                    if search_set and (search_set not in recommended_workflows):
                        recommended_workflows.append(search_set)
                        template = render_template(
                            "toolpanel/recommendations/recommendation-extraction.html",
                            search_set=search_set,
                        )
                        templates.append(template)
        print(recommendations)
        return jsonify({"templates": templates}), 200

    except Exception as e:
        return jsonify({"error": str(e), "recommendations": []}), 500


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

    model_config = UserModelConfig.objects(user_id=user.user_id).first()
    model = settings.base_model
    if model_config:
        model = model_config.name

    task_data["user_id"] = user_id
    task_data["model"] = model

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
            downloadpath=f"{user.id}/{uid}.{extension}",
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
    final_output = None
    if workflow_result.final_output:
        final_output = workflow_result.final_output.get("output", None)
    debug("Workflow result", final_output)

    response = {
        "steps_completed": workflow_result.num_steps_completed,
        "total_steps": workflow_result.num_steps_total,
        "output": final_output,
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


def convert_inline_markdown_to_tags(text):
    """Converts inline Markdown to ReportLab's supported XML tags."""
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.*?)__", r"<b>\1</b>", text)
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    text = re.sub(r"_(.*?)_", r"<i>\1</i>", text)
    text = re.sub(r"~~(.*?)~~", r"<strike>\1</strike>", text)
    text = re.sub(r"`(.*?)`", r'<font face="Courier">\1</font>', text)
    return text


def generate_pdf_from_markdown(formatted_markdown: str):
    """
    Generates a PDF from a Markdown string using a robust parser.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )

    styles = getSampleStyleSheet()

    # --- STYLE MODIFICATIONS (Corrected) ---
    styles["h1"].fontSize = 18
    styles["h1"].leading = 22
    styles["h1"].spaceAfter = 12

    styles["h2"].fontSize = 14
    styles["h2"].leading = 18
    styles["h2"].spaceAfter = 10

    # Modify the existing 'h3' style instead of adding it
    styles["h3"].fontSize = 12
    styles["h3"].leading = 14
    styles["h3"].spaceAfter = 8

    # Modify the existing 'Bullet' style for all list items
    styles["Bullet"].firstLineIndent = 0
    styles["Bullet"].spaceBefore = 3

    story = []

    # Enhanced Parser
    lines = formatted_markdown.strip().split("\n")
    in_ul = False
    in_ol = False
    list_items = []

    for line in lines:
        line = line.strip()

        is_ul_item = line.startswith(("* ", "- "))
        is_ol_item = re.match(r"^\d+\.\s", line)

        if (in_ul and not is_ul_item) or (in_ol and not is_ol_item):
            story.append(
                ListFlowable(list_items, bulletType="bullet" if in_ul else "1")
            )
            list_items = []
            in_ul = in_ol = False
            story.append(Spacer(1, 0.1 * inch))

        if line.startswith("# "):
            text = convert_inline_markdown_to_tags(line[2:])
            story.append(Paragraph(text, styles["h1"]))
        elif line.startswith("## "):
            text = convert_inline_markdown_to_tags(line[3:])
            story.append(Paragraph(text, styles["h2"]))
        elif line.startswith("### "):
            text = convert_inline_markdown_to_tags(line[4:])
            story.append(Paragraph(text, styles["h3"]))
        elif is_ul_item:
            if not in_ul:
                in_ul = True
            text = convert_inline_markdown_to_tags(line[2:])
            list_items.append(ListItem(Paragraph(text, styles["Bullet"])))
        elif is_ol_item:
            if not in_ol:
                in_ol = True
            text = convert_inline_markdown_to_tags(re.sub(r"^\d+\.\s", "", line))
            # Reuse the 'Bullet' style for numbered list items to avoid errors
            list_items.append(ListItem(Paragraph(text, styles["Bullet"])))
        elif line:
            text = convert_inline_markdown_to_tags(line)
            story.append(Paragraph(text, styles["Normal"]))
            story.append(Spacer(1, 0.1 * inch))

    if in_ul or in_ol:
        story.append(ListFlowable(list_items, bulletType="bullet" if in_ul else "1"))

    doc.build(story)

    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="workflow_output.pdf",
    )


## @MARK: Download
@workflows.route("/download", methods=["GET"])
def workflow_download() -> ResponseReturnValue:
    session_id = request.args.get("session_id")
    fmt = request.args.get("format", "txt").lower()

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    # 1) fetch the result object
    workflow_result = WorkflowResult.objects(session_id=session_id).first()
    if not workflow_result:
        return jsonify({"error": "Workflow not found"}), 404

    # 2) pull the final output payload
    final_output = list(workflow_result.steps_output.values())[-1]["output"]
    raw_json = json.dumps(final_output, indent=2)
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
            "Please format your entire response using Markdown.\n\n"
            "Use headings, paragraphs, bullet points, and bold text as appropriate to create a clear and readable layout. "
            "Do not include any of your own commentary or descriptions outside of the Markdown output.\n\n"
            f"Here is the HTML data:\n\n{raw_json}"
        )
    else:  # txt
        prompt = (
            "Pretty-print the following HTML document into a well-formatted text document. Strip out all html tags. Just give me clean, indented text.\n\n"
            "Do not include any description of your own or commentary, just return what we are going to output.\n\n"
            f"{raw_json}"
        )

    user = load_user()
    model_config = UserModelConfig.objects(user_id=user.user_id).first()
    if model_config:
        model = model_config.name
    else:
        model = settings.base_model
    chat_agent = create_chat_agent(model)
    # get current event loop
    # if there is no current loop, create a new one
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    formatted = loop.run_until_complete(
        chat_agent.run(prompt),
    )
    formatted = formatted.output

    # Remove the tick marks before and after blocks
    formatted = formatted.strip("`").strip()

    # 4) package it up
    buf = io.BytesIO()
    print(f"Format is {fmt}")
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
        return generate_pdf_from_markdown(formatted)

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
    debug(workflow_step_data)
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
        debug(data)
        workflow_id = data["workflow_uuid"]
        search_set_id = data.get("search_set_id", None)
        manual_input = data.get("manual_input", None)
        workflow_step_id = data.get("workflow_step_id", None)
        task_id = data.get("workflow_task_id", None)
        workflow = Workflow.objects(id=workflow_id).first()
        workflow_step = WorkflowStep.objects(id=ObjectId(workflow_step_id)).first()
        workflow_step_task = None

        if search_set_id:
            searchset = SearchSet.objects(id=ObjectId(search_set_id)).first()

            # if not searchset:
            #     return jsonify({"error": "Search set not found"})

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

        debug(workflow_step_task)
        debug(workflow_step.tasks)
        debug(workflow_step)
        debug(workflow)

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


@workflows.route("/duplicate/<workflow_id>")
def duplicate_workflow(workflow_id):
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    # 1) Load original
    orig = Workflow.objects(id=workflow_id).first()
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
        user_id=user.user_id,
        space=Space.objects()[0].uuid,  # or however you track the user’s active space
        steps=new_steps,
        attachments=new_atts,
        # created_at and updated_at default to now()
    ).save()

    flash("Workflow duplicated into your space!", "success")
    return redirect(url_for("home.index", sesction="Workflows"))
