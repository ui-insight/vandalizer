from flask import (
    Blueprint,
    request,
    jsonify,
    redirect,
    url_for,
    session,
    render_template,
    send_from_directory,
    current_app,
)
from app.models import (
    SmartDocument,
    SmartFolder,
    SearchSet,
    SearchSetItem,
    Space,
    Workflow,
    WorkflowStep,
)
from app.utilities.semantic_ingest import SemanticIngest
import uuid, os, threading
from app.utils import load_user, ingest_semantics, is_dev
from flask_dance.contrib.azure import azure
from itertools import chain
from mongoengine.queryset.visitor import Q
from app.utilities.config import max_context_length
from app.utilities.openai_interface import OpenAIInterface
from . import home
from app import CURRENT_RELEASE_VERSION, RELEASE_NOTES


@home.route("/")
def index():
    # production environment
    if not is_dev():
        if not azure.authorized:
            return redirect(url_for("azure.login"))
        if "user_id" not in session:
            print("No user session")
            resp = azure.get("/v1.0/me")
            user_info = resp.json()
            if "id" not in user_info:
                print("Got nothing from azure")
                session["user_id"] = "admin"
            else:
                print("Got user info from azure")
                user_id = user_info["id"]
                session["user_id"] = user_id

    user = load_user()
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
        current_space = Space.objects(uuid=document.space).first()
        semantics = SemanticIngest()
        if not semantics.check_for_collection(document):
            thread = threading.Thread(target=ingest_semantics, args=(document,))
            thread.start()

    if request.args.get("docids"):
        doc_ids = request.args.get("docids").split(",")
        for doc_id in doc_ids:
            document = SmartDocument.objects(uuid=doc_id).first()
            documents.append(document)

        current_space = Space.objects(uuid=document.first.space).first()
        semantics = SemanticIngest()
        if documents.count == 1:
            try:
                if not semantics.check_for_collection(documents.first):
                    thread = threading.Thread(
                        target=ingest_semantics, args=(documents.first,)
                    )
                    thread.start()
            except:
                print("Error checking for collection")

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

    # Get the extraction and prompt sets
    global_extraction_sets = SearchSet.objects(
        space=current_space.uuid, is_global=True, set_type="extraction"
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
        user_id=user.user_id, space_id=current_space.uuid, searchtype="prompt"
    ).all()

    formatters = SearchSetItem.objects(
        user_id=user.user_id, space_id=current_space.uuid, searchtype="formatter"
    ).all()

    # Workflows
    workflows = Workflow.objects(
        user_id=user.user_id,
        # space=current_space.uuid,
    ).all()

    # Get the folders
    current_folder_id = "0"
    current_folder_parent_id = "0"
    if request.args.get("folder_id"):
        current_folder_id = request.args.get("folder_id")

    base_query = Q(
        user_id=user.user_id, space=current_space.uuid, folder=current_folder_id
    )

    default_doc_query = Q(user_id=user.user_id, is_default=True)

    folder_docs = (
        SmartDocument.objects(base_query | default_doc_query)
        .order_by("-created_at")
        .all()
    )

    if current_folder_id != 0 and current_folder_id != "0":
        folder_docs = (
            SmartDocument.objects(base_query | default_doc_query)
            .order_by("-created_at")
            .all()
        )

        folder = SmartFolder.objects(uuid=current_folder_id).first()
        if folder:
            current_folder_parent_id = folder.parent_id
    folders = SmartFolder.objects(
        user_id=user.user_id, space=current_space.uuid, parent_id="0"
    ).all()
    if current_folder_id != 0:
        folders = SmartFolder.objects(
            user_id=user.user_id, space=current_space.uuid, parent_id=current_folder_id
        ).all()

    total_token_counts = 0
    for doc in folder_docs:
        total_token_counts += doc.token_count

    # Release Notes
    release_seen = request.cookies.get("release_seen")
    show_release_panel = release_seen != CURRENT_RELEASE_VERSION

    return render_template(
        "index.html",
        extraction_sets=extraction_sets,
        prompts=prompts,
        formatters=formatters,
        folders=folders,
        current_folder_parent_id=current_folder_parent_id,
        current_folder_id=current_folder_id,
        documents=documents,
        folder_docs=folder_docs,
        spaces=spaces,
        current_space_id=spaces[0].uuid,
        section=section,
        max_context_length=max_context_length,
        workflows=workflows,
        workflow_template=workflow_template,
        workflow_step_template=workflow_step_template,
        workflow_id=workflow_id,
        release_notes=RELEASE_NOTES,
        show_release_panel=show_release_panel,
        current_release=CURRENT_RELEASE_VERSION,
    )


@home.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data["message"]
    document_uuids = data["document_uuids"]
    folder = data["folder_uuid"]
    documents = []
    print(document_uuids)
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid, is_default=False).first()
        if document != None:
            documents.append(document)
            # find related html documents (excel converted to html)
            if document.extension == "html":
                html_files = [
                    f
                    for f in os.listdir(
                        os.path.join(current_app.root_path, "static", "uploads")
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
                        user_id=document.user_id,
                        space=document.space,
                        folder=document.folder,
                    )
                    documents.append(html_doc)

    print("Documents", [document.extension for document in documents])
    # default context docs
    docs = SmartDocument.objects(folder=folder, is_default=True).all()

    user_id = load_user().user_id
    response = OpenAIInterface().ask_question_to_documents(
        current_app.root_path,
        documents,
        message,
        default_docs=docs,
        user_id=user_id,
        session=session,
    )
    response["question"] = message
    print(response)
    return jsonify(response)


@home.route("/static/fontawesome/webfonts/<path:filename>")
def serve_fonts(filename):
    if filename.endswith(".woff2"):
        return send_from_directory(
            "static/fontawesome/webfonts", filename, mimetype="font/woff2"
        )
    elif filename.endswith(".ttf"):
        return send_from_directory(
            "static/fontawesome/webfonts", filename, mimetype="font/ttf"
        )
    else:
        return send_from_directory("static/fontawesome/webfonts", filename)
