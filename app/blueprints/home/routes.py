"""Handles primary routing for the home page and related functionalities."""

import json
import os
import uuid
from itertools import chain

from devtools import debug
from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_dance.contrib.azure import azure
from mongoengine.queryset.visitor import Q

from app import CURRENT_RELEASE_VERSION, RELEASE_NOTES, app
from app.models import (
    SearchSet,
    SearchSetItem,
    SmartDocument,
    SmartFolder,
    Space,
    UserModelConfig,
    Workflow,
    WorkflowStep,
)
from app.utilities.config import settings
from app.utilities.document_manager import (
    perform_extraction_and_update,
    perform_semantic_ingestion,
)
from app.utilities.openai_interface import OpenAIInterface
from app.utilities.upload_manager import (
    perform_document_validation,
)
from app.utils import is_dev, load_user

from . import home


@app.context_processor
def inject_current_model():
    """
    Runs on *every* template render.  Looks up the user's ModelConfig,
    and makes `current_model` available in all templates.
    """
    user = load_user()
    model_config = UserModelConfig.objects(user_id=user.user_id).first()
    models = [m.model_dump() for m in settings.models]
    current_model = settings.base_model
    if model_config:
        current_model = model_config.name
        if len(model_config.available_models) > 0:
            models = json.loads(json.dumps(model_config.available_models))

    debug(current_model)
    debug(models)
    return {"current_model": current_model, "models": models}


def verify_document(document: SmartDocument, user_id: str) -> None:
    """Verify and update the document if necessary."""
    debug("Updating old document", document.title)
    debug("Document processing", document.processing)

    extension = document.extension

    if not document.raw_text or document.raw_text == "":
        # check if there is a task running
        if not document.task_id:
            extraction_task = perform_extraction_and_update.s(
                document_uuid=document.uuid, extension=extension
            )

            validation_task = perform_document_validation.s(
                document_uuid=document.uuid, document_path=document.absolute_path
            )

            ingestion_task = perform_semantic_ingestion.s(
                document.uuid,
                user_id,
            )
            workflow_task_result = extraction_task | validation_task | ingestion_task
            document.task_id = workflow_task_result.id
            document.save()


@home.route("/")
def index() -> ResponseReturnValue:
    """Primary entry point."""
    # production environment
    if not is_dev():
        if not azure.authorized:
            return redirect(url_for("azure.login"))
        if "user_id" not in session:
            debug("No user session")
            resp = azure.get("/v1.0/me")
            user_info = resp.json()
            if "id" not in user_info:
                debug("Got nothing from azure")
                session["user_id"] = "admin"
            else:
                debug("Got user info from azure")
                user_id = user_info["id"]
                session["user_id"] = user_id

    user = load_user()
    user_id = user.user_id
    section = request.args.get("section", default="Chat").strip()

    document = None
    # Get the space
    spaces = list(Space.objects())
    if len(spaces) == 0:
        space = Space(title="Default Space", uuid=uuid.uuid4().hex)
        space.save()
        spaces = list(Space.objects())

    if request.args.get("space_id"):
        session["space_id"] = request.args.get("space_id")
        current_space = Space.objects(uuid=request.args.get("space_id")).first()
    elif "space_id" in session and session["space_id"] != "":
        current_space = Space.objects(uuid=session["space_id"]).first()
    else:
        current_space = spaces[0]

    if current_space not in spaces:
        current_space = spaces[0]

    documents = []

    # Check for documents
    if request.args.get("docid"):
        doc_id = request.args.get("docid")
        document = SmartDocument.objects(uuid=doc_id).first()
        documents.append(document)
        verify_document(document, user_id)
        current_space = Space.objects(uuid=document.space).first()

    if request.args.get("docids"):
        doc_ids = request.args.get("docids").split(",")
        for doc_id in doc_ids:
            document = SmartDocument.objects(uuid=doc_id).first()
            documents.append(document)
            verify_document(document, user_id)

        current_space = Space.objects(uuid=document.first.space).first()

    spaces.remove(current_space)
    spaces.insert(0, current_space)

    # Get workflow if it exists
    workflow_template = ""
    workflow_step_template = ""
    workflow_id = request.args.get("workflow_id", default=0)
    if workflow_id != 0:
        workflow = Workflow.objects(id=request.args.get("workflow_id")).first()

        workflow_template = render_template(
            "workflows/workflow.html",
            workflow=workflow,
        )

        workflow_step_id = request.args.get("workflow_step_id", default=0)
        if workflow_step_id != 0:
            workflow_step = WorkflowStep.objects(id=workflow_step_id).first()
            workflow_step_template = render_template(
                "workflows/workflow_steps/edit_workflow_step_modal.html",
                workflow=workflow,
                workflow_step_id=workflow_step.id,
                workflow_step=workflow_step,
            )

        # Get workflow if it exists

        workflow_step_id = request.args.get("workflow_step_id", default=0)
        if workflow_step_id != 0:
            workflow_step = WorkflowStep.objects(id=workflow_step_id).first()
            workflow_step_template = render_template(
                "workflows/workflow_steps/edit_workflow_step_modal.html",
                workflow=workflow,
                workflow_step_id=workflow_step.id,
                workflow_step=workflow_step,
            )

    # Get workflow if it exists

    # Get the extraction and prompt sets
    global_extraction_sets = SearchSet.objects(
        space=current_space.uuid,
        is_global=True,
        set_type="extraction",
    ).all()
    user_extraction_sets = SearchSet.objects(
        user_id=user.user_id,
        space=current_space.uuid,
        is_global=False,
        set_type="extraction",
    ).all()
    extraction_sets = list(chain(global_extraction_sets, user_extraction_sets))

    # Get the prompt sets

    prompts = SearchSetItem.objects(
        user_id=user.user_id,
        space_id=current_space.uuid,
        searchtype="prompt",
    ).all()

    formatters = SearchSetItem.objects(
        user_id=user.user_id,
        space_id=current_space.uuid,
        searchtype="formatter",
    ).all()

    # Workflows
    workflows = Workflow.objects(
        user_id=user.user_id,
    ).all()

    # Get the folders
    current_folder_id = "0"
    current_folder_parent_id = "0"
    if request.args.get("folder_id"):
        current_folder_id = request.args.get("folder_id")

    base_query = Q(
        user_id=user.user_id,
        space=current_space.uuid,
        folder=current_folder_id,
    )

    default_doc_query = Q(user_id=user.user_id, is_default=True)

    folder_docs = (
        SmartDocument.objects(base_query | default_doc_query)
        .order_by("-created_at")
        .all()
    )
    # Check for OCR and semantic ingestion for documents in the folder
    # This should resolve the issue with old documents not being processed

    if current_folder_id not in {0, "0"}:
        folder_docs = (
            SmartDocument.objects(base_query | default_doc_query)
            .order_by("-created_at")
            .all()
        )

        folder = SmartFolder.objects(uuid=current_folder_id).first()
        if folder:
            current_folder_parent_id = folder.parent_id
    folders = SmartFolder.objects(
        user_id=user.user_id,
        space=current_space.uuid,
        parent_id="0",
    ).all()
    if current_folder_id != 0:
        folders = SmartFolder.objects(
            user_id=user.user_id,
            space=current_space.uuid,
            parent_id=current_folder_id,
        ).all()

    total_token_counts = 0
    for doc in folder_docs:
        total_token_counts += doc.token_count

    # Release Notes
    release_seen = request.cookies.get("release_seen")
    show_release_panel = release_seen != CURRENT_RELEASE_VERSION

    # Release Notes
    release_seen = request.cookies.get("release_seen")
    show_release_panel = release_seen != CURRENT_RELEASE_VERSION

    # user = load_user()
    # models = []

    # model_config = ModelConfig.objects(
    #     user_id=user.user_id,
    # ).first()
    # model = settings.base_model
    # settings_models = [m.model_dump() for m in settings.models]
    # if model_config is None:
    #     model_config = ModelConfig(user_id=user.user_id, name=model)
    #     model_config.available_models = [m.model_dump() for m in settings.models]
    #     model_config.save()
    #     models = settings_models
    # else:
    #     if len(model_config.available_models) == 0:
    #         models = settings_models

    # debug(models)
    # debug(settings.models)

    return render_template(
        "index.html",
        extraction_sets=extraction_sets,
        prompts=prompts,
        # models=models,
        # current_model=model,
        formatters=formatters,
        folders=folders,
        current_folder_parent_id=current_folder_parent_id,
        current_folder_id=current_folder_id,
        documents=documents,
        folder_docs=folder_docs,
        spaces=spaces,
        current_space_id=spaces[0].uuid,
        section=section,
        max_context_length=settings.max_context_length,
        workflows=workflows,
        workflow_template=workflow_template,
        workflow_step_template=workflow_step_template,
        workflow_id=workflow_id,
        release_notes=RELEASE_NOTES,
        show_release_panel=show_release_panel,
        current_release=CURRENT_RELEASE_VERSION,
    )


@home.route("/chat", methods=["POST"])
def chat() -> ResponseReturnValue:
    """Handle chat requests."""
    data = request.get_json()
    message = data["message"]
    document_uuids = data["document_uuids"]
    folder = data["folder_uuid"]
    documents = []
    user_id = load_user().user_id
    debug(document_uuids)
    # migrate to new document user's location
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid, is_default=False).first()
        if document is not None:
            documents.append(document)
            # find related html documents (excel converted to html)
            if document.extension == "html":
                html_files = [
                    f
                    for f in os.listdir(
                        os.path.join(
                            current_app.root_path,
                            "static",
                            "uploads",
                            user_id,
                        ),
                    )
                    if f.startswith(document.uuid)
                    and f != document.path
                    and f.endswith(".html")
                ]

                for html_file in html_files:
                    html_doc = SmartDocument(
                        title=document.title,
                        path=html_file,
                        extension="html",
                        uuid=uuid.uuid4().hex,
                        user_id=user_id,
                        space=document.space,
                        folder=document.folder,
                    )
                    documents.append(html_doc)

    debug("Documents", [document.extension for document in documents])
    # default context docs
    docs = SmartDocument.objects(folder=folder, is_default=True).all()

    user = load_user()

    debug(documents)
    debug(docs)
    model_config = UserModelConfig.objects(user_id=user.user_id).first()
    model = settings.base_model
    if model_config:
        model = model_config.name

    response = OpenAIInterface().ask_question_to_documents(
        model,
        current_app.root_path,
        documents,
        message,
        default_docs=docs,
        user_id=user_id,
        session=session,
    )
    response["question"] = message
    return jsonify(response)


@home.route("/static/fontawesome/webfonts/<path:filename>")
def serve_fonts(filename):
    if filename.endswith(".woff2"):
        return send_from_directory(
            "static/fontawesome/webfonts",
            filename,
            mimetype="font/woff2",
        )
    if filename.endswith(".ttf"):
        return send_from_directory(
            "static/fontawesome/webfonts",
            filename,
            mimetype="font/ttf",
        )
    return send_from_directory("static/fontawesome/webfonts", filename)
