import urllib.parse
from datetime import datetime
from app.utilities.prompt_optimization import background_retrain_model
from app.utilities.excel_helper import save_excel_to_html
from app.utilities.workflow import WorkflowThread, build_workflow_engine
from flask import (
    url_for,
    send_file,
    redirect,
    render_template,
    flash,
    g,
    session,
    jsonify,
    Response,
    send_file,
)
from app import app
from app.models import (
    User,
    SmartDocument,
    Space,
    SearchSet,
    SearchSetItem,
    ExtractionQualityRecord,
    SmartFolder,
    Feedback,
    FeedbackCounter,
    Workflow,
    WorkflowStep,
    WorkflowAttachment,
    WorkflowResult,
)
from app.forms import LoginForm, SpaceForm
import os
import base64
from flask import request
from app.utilities.extraction_manager2 import ExtractionManager2
from app.utilities.semantic_ingest import SemanticIngest
from app.utilities.openai_interface import (
    OpenAIInterface,
    num_tokens_from_text,
    max_context_length,
)
from app.utilities.fillable_pdf_manager import FillablePDFManager
import uuid
import threading

import multiprocessing as mp

import json
import csv
from itertools import chain
from copy import deepcopy
from pypdf import PdfReader, PdfWriter
import io
import datetime

# OAuth
import secrets
from oauthlib.oauth2.rfc6749.errors import TokenExpiredError
from oauthlib.oauth2.rfc6749.errors import MismatchingStateError
from flask_dance.contrib.azure import azure, make_azure_blueprint

from mongoengine.queryset.visitor import Q

import pypandoc

blueprint = make_azure_blueprint(
    client_id=app.config["CLIENT_ID"],
    client_secret=app.config["CLIENT_SECRET"],
    tenant=app.config["TENANT_NAME"],
)

app.register_blueprint(blueprint, url_prefix="/login")


@app.errorhandler(MismatchingStateError)
def mismatching_state(e):
    return redirect(url_for("azure.login"))


@app.route("/")
def index():
    # if azure.authorized:
    #     print("Already authorized")
    #     return redirect(url_for("home"))

    print("Not authorized")
    return render_template("landing.html")


@app.route("/login")
def login():
    if not azure.authorized:
        return redirect(url_for("azure.login"))
    else:
        return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


#######################################
######## HOME ######
#######################################
## MARK: Home


@app.route("/home")
def home():
    # production environment
    if "dev" in os.uname().nodename or "prod" in os.environ.get("APP_ENV", "prod"):
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
    print(section)

    document = None

    # Get the space
    spaces = list(Space.objects())
    if len(spaces) == 0:
        space = Space(title="Default Space", uuid=uuid.uuid4().hex)
        space.save()
        spaces = list(Space.objects())

    if request.args.get("id"):
        current_space = Space.objects(uuid=request.args.get("id")).first()
    else:
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
    workflow_id = request.args.get("workflow_id", default=0)
    if workflow_id != 0:
        workflow = Workflow.objects(id=request.args.get("workflow_id")).first()

        workflow_template = render_template(
            "toolpanel/workflows/workflow.html",
            workflow=workflow,
        )

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

    print(len(extraction_sets))

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
        workflow_id=workflow_id,
    )


## MARK: Uploads


@app.route("/upload_fillable_pdf", methods=["POST"])
def upload_fillable_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    search_set_uuid = request.form.get("search_set_uuid")
    print(search_set_uuid)
    searchset = SearchSet.objects(uuid=search_set_uuid).first()
    for item in searchset.items():
        item.delete()

    # Read the PDF file
    file_stream = io.BytesIO(file.read())
    pdf_reader = PdfReader(file_stream)
    fields = pdf_reader.get_fields()

    # Write to the filesystem
    # Save the file to the filesystem
    file_path = os.path.join(app.root_path, "static", "uploads", file.filename)
    file.seek(0)  # Go back to the start of the file
    with open(file_path, "wb") as f:
        f.write(file.read())

    searchset.fillable_pdf_url = file.filename
    searchset.save()

    # Extract field names and options
    field_options = {}
    for field_name, field_data in fields.items():
        if "/Opt" in field_data:
            field_options[field_name] = field_data["/Opt"]
        else:
            field_options[field_name] = "No options"

    fillable_manager = FillablePDFManager()
    output = fillable_manager.build_set_from_items(field_options)
    # output = json.loads(output)
    bindings = output["fields"]
    print(output)

    for item in bindings:
        key = list(item.keys())[0]
        value = item[key]
        item = SearchSetItem(
            searchphrase=value,
            searchset=search_set_uuid,
            searchtype="extraction",
            pdf_binding=key,
        )
        item.save()

    return jsonify("Success"), 200


@app.route("/upload", methods=["GET", "POST"])
def upload():
    user = load_user()
    if user is None:
        return redirect(url_for("login"))

    # TODO convert docx documents to pdf using pypandoc (pypandoc.convert_file)
    # TODO convert excel documents to csv using pandas (pd.read_excel)

    json_data = request.get_json()
    blob = json_data["contentAsBase64String"]
    filename = json_data["fileName"]
    extension = json_data["extension"]
    space = json_data["space"]
    folder = json_data["folder"]

    print("Folder is")
    print(folder)
    if folder is None or folder == "":
        folder = "0"

    if (
        SmartDocument.objects(
            title=filename, space=space, user_id=user.user_id, folder=folder
        ).count()
        > 0
    ):
        return jsonify({"complete": True})

    imgdata = base64.b64decode(blob)
    uid = uuid.uuid4().hex.upper()

    with open(
        os.path.join(app.root_path, "static", "uploads", f"{uid}.{extension}"), "wb"
    ) as f:
        f.write(imgdata)

    # create upload directory if it doesn't exist
    if not os.path.exists(os.path.join(app.root_path, "static", "uploads")):
        os.makedirs(os.path.join(app.root_path, "static", "uploads"))

    if extension == "docx":
        # convert to pdf
        pdf_path = os.path.join(app.root_path, "static", "uploads", f"{uid}.pdf")
        docx_path = os.path.join(app.root_path, "static", "uploads", f"{uid}.docx")
        pypandoc.convert_file(docx_path, "pdf", outputfile=pdf_path)
        extension = "pdf"

    elif extension == "xlsx" or extension == "xls":
        # convert to html
        html_path = os.path.join(app.root_path, "static", "uploads", f"{uid}.html")
        excel_path = os.path.join(
            app.root_path, "static", "uploads", f"{uid}.{extension}"
        )
        save_excel_to_html(excel_path, html_path)
        extension = "html"

    document = SmartDocument(
        title=filename,
        path=f"{uid}.{extension}",
        extension=extension,
        uuid=uid,
        user_id=user.user_id,
        space=space,
        folder=folder,
        # token_count=token_count,
        # num_pages=number_of_pages,
    )
    document.save()

    # Create a new thread and start it
    thread = threading.Thread(target=ingest_semantics, args=(document,))
    thread.start()
    return jsonify({"complete": True, "uuid": uid, "folder_id": folder})


@app.route("/read_pdf", methods=["POST"])
def read_pdf():
    # user = load_user()
    # if user is None:
    # 	return redirect(url_for('login'))

    json_data = request.get_json()
    blob = json_data["contentAsBase64String"]
    filename = json_data["fileName"]

    imgdata = base64.b64decode(blob)
    uid = uuid.uuid4().hex.upper()
    with open(os.path.join(app.root_path, "static", "temp", f"{uid}.pdf"), "wb") as f:
        f.write(imgdata)

    pdf = PdfReader(os.path.join(app.root_path, "static", "temp", f"{uid}.pdf"))
    number_of_pages = len(pdf.pages)
    full_text = ""
    for i in range(number_of_pages):
        full_text = full_text + pdf.pages[i].extract_text() + " "

    print(full_text)
    return jsonify({"full_text": full_text})


def ingest_semantics(document):
    semantics = SemanticIngest()
    semantics.ingest(document=document)


## MARK: Chat


@app.route("/api/chat", methods=["POST"])
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
                        os.path.join(app.root_path, "static", "uploads")
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

    response = OpenAIInterface().ask_question_to_documents(
        app.root_path, documents, message, default_docs=docs
    )
    print(response)
    return jsonify(response)


## MARK: Tasks


@app.route("/api/add_search_set", methods=["POST"])
def add_search_set():
    user = load_user()
    if user is None:
        return redirect(url_for("login"))

    data = request.get_json()
    title = data["title"]
    space = data["space_id"]
    search_type = data["search_type"]
    searchset = SearchSet(
        title=title,
        uuid=uuid.uuid4().hex,
        space=space,
        user_id=user.user_id,
        status="active",
        set_type=search_type,
    )
    if user.is_admin:
        searchset.is_global = True
    searchset.save()
    return jsonify({"complete": True})


@app.route("/api/add_search_term", methods=["POST"])
def add_search_term():
    data = request.get_json()
    print(data)
    searchphrase = data["term"]
    searchset_uuid = data["search_set_uuid"]
    searchset = SearchSet.objects(uuid=searchset_uuid).first()
    searchtype = data["searchtype"]

    attachments = data["attachments"] if "attachments" in data else None
    print(searchphrase)
    print(attachments)

    if searchset.is_global:
        user = load_user()
        if not user.is_admin:
            return jsonify(
                {
                    "complete": False,
                    "error": "You do not have permission to add to this search set.",
                }
            )

    searchsetitem = SearchSetItem(
        searchphrase=searchphrase, searchset=searchset_uuid, searchtype=searchtype
    )
    if attachments:
        searchsetitem.text_blocks = attachments

    searchsetitem.save()

    print(searchsetitem)
    template = render_template(
        "toolpanel/search_set_item.html", search_set=searchset, item=searchsetitem
    )
    response = {
        "complete": True,
        "template": template,
    }
    return jsonify(response)


@app.route("/api/add_prompt", methods=["POST"])
def add_prompt():
    data = request.get_json()
    title = data["title"]
    prompt = data["prompt"]
    space_id = data["space_id"]
    prompt_type = data["prompt_type"]
    user = load_user()

    searchsetitem = SearchSetItem(
        searchphrase=prompt,
        title=title,
        space_id=space_id,
        user_id=user.user_id,
        searchtype=prompt_type,
    )

    searchsetitem.save()
    response = {"complete": True}
    return jsonify(response)


@app.route("/api/fetch_search_set_item", methods=["POST"])
def fetch_search_set_item():
    data = request.get_json()
    uuid = data["uuid"]

    searchsetitem = SearchSetItem.objects(id=uuid).first()

    response = {"prompt": searchsetitem.searchphrase}
    return jsonify(response)


@app.route("/api/search_results", methods=["POST"])
def grab_template():
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_uuids = data["document_uuids"]

    edit_mode = data["edit_mode"]
    documents = []
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid).first()
        documents.append(document)

    search_set = SearchSet.objects(uuid=searchset_uuid).first()

    print("Document count: " + str(len(documents)))

    if search_set is None:
        return jsonify({"error": "Search set not found."})

    if search_set.set_type == "extraction":
        if edit_mode:
            template = render_template(
                "toolpanel/extractions/edit_search_results.html",
                search_set=search_set,
                documents=documents,
                bindable_fields=search_set.get_fillable_fields(),
            )

            response = {
                "template": template,
            }

            return jsonify(response)
        else:
            template = render_template(
                "toolpanel/extractions/search_results.html",
                search_set=search_set,
                documents=documents,
            )
            response = {
                "template": template,
            }

            return jsonify(response)
    else:
        if edit_mode:
            template = render_template(
                "toolpanel/prompts/edit_prompt_results.html",
                search_set=search_set,
                documents=documents,
            )
            response = {
                "template": template,
            }
            return jsonify(response)
        else:
            template = render_template(
                "toolpanel/prompts/prompt_results.html",
                search_set=search_set,
                documents=documents,
            )
            response = {
                "template": template,
            }
            return jsonify(response)


@app.route("/api/semantic_search", methods=["POST"])
def semantic_search():
    data = request.get_json()
    search_term = data["search_term"]
    document_uuids = data["document_uuids"]

    documents = []
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid).first()
        documents.append(document)

    semantics = SemanticIngest()
    results = semantics.search(search_term, documents.first)
    print(results)

    response = {
        "results": results,
    }
    return jsonify(response)


@app.route("/api/begin_search", methods=["POST"])
def begin_search():
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_uuids = data["document_uuids"]

    documents = []
    document_paths = []
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid).first()
        documents.append(document)
        document_paths.append(document.path)

    print("Fetch loading template:" + searchset_uuid)

    search_set = SearchSet.objects(uuid=searchset_uuid).first()
    keys = []
    items = []
    if search_set is not None:
        items = search_set.items()
    for item in items:
        if item.searchtype == "extraction":
            keys.append(item.searchphrase)

    if len(keys) > 0:
        em = ExtractionManager2()
        em.root_path = app.root_path
        results = em.extract(keys, document_paths)
        print(results)
        template = render_template(
            "toolpanel/extractions/search_results.html",
            search_set=search_set,
            results=results,
            documents=documents,
        )
        response = {
            "template": template,
        }
        return jsonify(response)
    else:
        template = render_template(
            "toolpanel/extractions/search_results.html",
            search_set=search_set,
            documents=documents,
        )
        response = {
            "template": template,
        }
        return jsonify(response)


@app.route("/delete_search_set", methods=["GET"])
def delete_search_set():
    search_set_uuid = request.args.get("uuid")
    print(search_set_uuid)
    search_set = SearchSet.objects(id=search_set_uuid).first()
    search_set.delete()
    return redirect("/")


@app.route("/api/rename_search_set", methods=["POST"])
def rename_search_set():
    data = request.get_json()
    search_set_uuid = data["search_set_uuid"]
    new_title = data["new_title"]
    print(search_set_uuid)
    search_set = SearchSet.objects(uuid=search_set_uuid).first()
    search_set.title = new_title
    search_set.save()

    return jsonify({"complete": True})


@app.route("/api/clone_search_set", methods=["POST"])
def clone_search_set():
    data = request.get_json()
    search_set_uuid = data["search_set_uuid"]
    print(search_set_uuid)
    search_set = SearchSet.objects(uuid=search_set_uuid).first()
    new_search_set = deepcopy(search_set)
    new_search_set.id = None
    new_search_set.uuid = uuid.uuid4().hex
    new_search_set.is_global = False
    new_search_set.title = "Copy of " + new_search_set.title
    new_search_set.save()

    # Clone the search set items
    for item in search_set.items():
        new_item = deepcopy(item)
        new_item.id = None
        new_item.searchset = new_search_set.uuid
        new_item.save()

    return jsonify({"complete": True})


@app.route("/api/delete_search_set_item", methods=["POST"])
def delete_search_set_item():
    data = request.get_json()
    print("Deleting search set item")
    search_set_item_uuid = data["uuid"]
    print(search_set_item_uuid)
    search_set = SearchSetItem.objects(id=search_set_item_uuid).first()
    search_set.delete()
    return jsonify({"complete": True})


@app.route("/api/begin_prompt_search", methods=["POST"])
def begin_prompt_search():
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_path = data["document"]

    search_set = SearchSet.objects(uuid=searchset_uuid).first()
    keys = []
    items = search_set.items()

    if len(items) > 0:
        llm = OpenAIInterface()
        llm.load_document(app.root_path, document_path)
        results = {}
        for item in items:
            results[item.searchphrase] = llm.ask_question_to_loaded_document(item)
        print(results)
        template = render_template(
            "toolpanel/prompts/prompt_results.html",
            search_set=search_set,
            results=results,
        )
        response = {
            "template": template,
        }
        return jsonify(response)
    else:
        template = render_template(
            "toolpanel/prompts/prompt_results.html", search_set=search_set
        )
        response = {
            "template": template,
        }
        return jsonify(response)


## MARK: Workflows
@app.route("/api/create_workflow", methods=["POST"])
def add_workflow():
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_data = request.get_json()
    print("workflow_data", workflow_data)
    workflow = Workflow(
        name=workflow_data["name"],
        description=workflow_data["description"],
        user_id=session["user_id"],
    )
    workflow.save()
    return redirect("/home?section=Workflows")


@app.route("/api/delete_workflow", methods=["GET"])
def delete_workflow():
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_id = request.args.get("workflow_id")
    Workflow.objects(id=workflow_id).delete()
    return redirect("/home?section=Workflows")


@app.route("/api/update_workflow", methods=["POST"])
def update_workflow():
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_data = request.get_json()
    workflow_id = workflow_data["workflow_id"]
    workflow = Workflow.objects(id=workflow_id).first()
    workflow.name = workflow_data["name"]
    workflow.description = workflow_data["description"]
    workflow.save()
    return redirect("/home?section=Workflows")


@app.route("/api/workflow/run", methods=["POST"])
def run_workflow():
    user = load_user()
    if user is None:
        return redirect(url_for("login"))

    workflow_data = request.get_json()
    workflow_id = workflow_data["workflow_id"]
    session_id = workflow_data["session_id"]
    document_uuids = workflow_data["document_uuids"]
    download = workflow_data.get("download", False)  # Get the 'download' flag

    workflow = Workflow.objects(id=workflow_id).first()
    workflow_result = WorkflowResult(workflow=workflow, session_id=session_id)
    attachments = [
        SmartDocument.objects(uuid=x.attachment).first() for x in workflow.attachments
    ]
    docs = [SmartDocument.objects(uuid=x).first() for x in document_uuids]
    document_trigger_step = WorkflowStep(
        name="Document", data=dict(docs=docs, attachments=attachments)
    )
    steps = [document_trigger_step]
    for step in workflow.steps:
        steps.append(step)

    engine = build_workflow_engine(steps, workflow=workflow)
    workflow_thread = WorkflowThread(target=engine.execute, args=(workflow_result,))
    workflow_thread.start()
    output, data = workflow_thread.join()
    # output, data = engine.execute(workflow_result)

    return {"output": output, "steps": data}


@app.route("/api/workflow/status", methods=["GET"])
def workflow_status():
    session_id = request.args.get("session_id")

    if not session_id:
        return jsonify({"error": "workflow_id is required"}), 400

    # Get workflow status
    workflow_result = WorkflowResult.objects(session_id=session_id).first()

    if not workflow_result:
        return jsonify({"error": "Workflow not found"}), 404

    # # Calculate time elapsed in seconds
    # time_elapsed = (datetime.now() - workflow["start_time"]).total_seconds()

    response = {
        "steps_completed": workflow_result.num_steps_completed,
        "total_steps": workflow_result.num_steps_total,
        # "time_elapsed": int(time_elapsed)
    }

    return jsonify(response)


@app.route("/api/workflow/download", methods=["GET"])
def workflow_download():
    session_id = request.args.get("session_id")

    if not session_id:
        return jsonify({"error": "workflow_id is required"}), 400

    # Get workflow status
    workflow_result = WorkflowResult.objects(session_id=session_id).first()

    if not workflow_result:
        return jsonify({"error": "Workflow not found"}), 404

    # # Calculate time elapsed in seconds
    # time_elapsed = (datetime.now() - workflow["start_time"]).total_seconds()

    # Ensure the static folder exists
    os.makedirs(os.path.join(app.root_path, "static"), exist_ok=True)

    output_file_path = os.path.join(app.root_path, "static", "workflow_output.txt")
    final_output = list(workflow_result.steps_output.values())[-1]
    print(final_output)

    with open(output_file_path, "w") as f:  # Open as text file for string output
        f.write(final_output["output"])  # Assuming output is a string

    # Return the path to the CSV file
    return send_file(
        "static/workflow_output.txt", mimetype="text/plain", as_attachment=True
    )


@app.route("/api/fetch_workflow", methods=["POST"])
def fetch_workflow():
    data = request.get_json()
    workflow_id = data["workflow_uuid"]
    workflow = Workflow.objects(id=workflow_id).first()

    template = render_template(
        "toolpanel/workflows/workflow.html",
        workflow=workflow,
    )

    response = {
        "template": template,
    }

    return jsonify(response)


## MARK: Workflow steps
@app.route("/api/add_workflow_step", methods=["POST"])
def add_workflow_step():
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_data = request.get_json()
    workflow_id = workflow_data["workflow_id"]
    workflow = Workflow.objects(id=workflow_id).first()
    step = workflow_data["step"]
    workflow.steps.append(step)
    workflow.save()
    return redirect("/home?section=Workflows")


@app.route("/api/workflow/delete_step", methods=["POST"])
def delete_workflow_step():
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    workflow_data = request.get_json()
    workflow_step_id = workflow_data["workflow_step_id"]
    step = WorkflowStep.objects(id=workflow_step_id).first()
    if not step:
        return jsonify({"success": False, "error": "Step not found"}), 404

    # Find any Workflow containing this step and remove the reference
    Workflow.objects(steps=step).update(pull__steps=step)
    step.delete()

    return jsonify({"success": True})


@app.route("/api/update_workflow_step", methods=["POST"])
def update_workflow_step():
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


## MARK: ~~ Extraction
@app.route("/api/workflows/add_extraction_step", methods=["GET", "POST"])
def workflow_add_extraction_step():
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = list(request.args.keys())[0]  # Get the JSON string key
        data = json.loads(data_str)  # Retrieve query parameters, if any
        workflow_id = data.get("workflow_uuid")
        space_id = data.get("space_id")

        is_editing = data.get("editing") or False
        workflow_step_id = ""
        workflow_step = None

        if is_editing:
            workflow_step_id = data.get("workflow_step_id")
            workflow_step = WorkflowStep.objects(id=workflow_step_id).first()

        workflow = Workflow.objects(id=workflow_id).first()

        current_space = Space.objects(uuid=space_id).first()
        global_extraction_sets = SearchSet.objects(
            space=current_space.uuid, is_global=True, set_type="extraction"
        ).all()
        user_extraction_sets = SearchSet.objects(
            user_id=workflow.user_id,
            space=current_space.uuid,
            is_global=False,
            set_type="extraction",
        ).all()
        extraction_sets_objects = list(
            chain(global_extraction_sets, user_extraction_sets)
        )

        template = render_template(
            "toolpanel/workflows/modals/workflow_add_extractions_modal.html",
            workflow=workflow,
            extraction_sets=extraction_sets_objects,
            is_editing=is_editing,
            workflow_step_id=workflow_step_id,
            workflow_step=workflow_step,
        )
        response = {"template": template}
        return jsonify(response)

    elif request.method == "POST":
        # Handle POST request - create a new WorkflowStep
        data = request.get_json()
        workflow_id = data["workflow_uuid"]
        search_set_id = data["search_set_id"] if "search_set_id" in data else None
        manual_input = data["manual_input"] if "manual_input" in data else None
        step_id = data["step_id"] if "step_id" in data else None
        workflow = Workflow.objects(id=workflow_id).first()

        if search_set_id:
            searchset = SearchSet.objects(uuid=search_set_id).first()

            workflow_step = None
            if step_id != None and step_id != 0:
                workflow_step = WorkflowStep.objects(id=step_id).first()
                if workflow_step:
                    workflow_step.data = searchset.to_workflow_step_data()
                    workflow_step.save()
            else:
                workflow_step = WorkflowStep(
                    name="Extraction", data=searchset.to_workflow_step_data()
                )
                workflow_step.save()
                workflow.steps.append(workflow_step)
                workflow.save()

        elif manual_input:
            workflow_step = None
            if step_id != None and step_id != 0:
                workflow_step = WorkflowStep.objects(id=step_id).first()
                if workflow_step:
                    workflow_step.data = {"searchphrases": manual_input}
                    workflow_step.save()
            else:
                workflow_step = WorkflowStep(
                    name="Extraction", data={"searchphrases": manual_input}
                )
                workflow_step.save()
                workflow.steps.append(workflow_step)

            workflow.save()

        return jsonify({"response": "success"})


## MARK: ~~ Attachments
@app.route("/api/workflows/add_attachment", methods=["GET", "POST"])
def workflow_add_attachment():
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = list(request.args.keys())[0]  # Get the JSON string key
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
            "toolpanel/workflows/modals/workflow_add_attachments_modal.html",
            workflow=workflow,
            files=files,
        )
        response = {"template": template}
        return jsonify(response)
    elif request.method == "POST":
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


## MARK: ~~ Prompts
@app.route("/api/workflows/add_prompt_step", methods=["GET", "POST"])
def workflow_add_prompt_step():
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = list(request.args.keys())[0]  # Get the JSON string key
        data = json.loads(data_str)  # Retrieve query parameters, if any
        workflow_id = data.get("workflow_uuid")
        space_id = data.get("space_id")

        is_editing = data.get("editing") or False
        workflow_step_id = ""
        workflow_step = None

        if is_editing:
            workflow_step_id = data.get("workflow_step_id")
            workflow_step = WorkflowStep.objects(id=workflow_step_id).first()

        workflow = Workflow.objects(id=workflow_id).first()

        current_space = Space.objects(uuid=space_id).first()

        prompts = SearchSetItem.objects(
            user_id=load_user().user_id,
            space_id=current_space.uuid,
            searchtype="prompt",
        ).all()

        template = render_template(
            "toolpanel/workflows/modals/workflow_add_prompt_modal.html",
            workflow=workflow,
            prompts=prompts,
            is_editing=is_editing,
            workflow_step_id=workflow_step_id,
            workflow_step=workflow_step,
        )
        response = {"template": template}
        return jsonify(response)

    elif request.method == "POST":
        # Handle POST request - create a new WorkflowStep
        data = request.get_json()
        workflow_id = data["workflow_uuid"]
        step_id = data["step_id"] if "step_id" in data else None
        search_set_item_id = (
            data["search_set_item_id"] if "search_set_item_id" in data else None
        )
        manual_input = data["manual_input"] if "manual_input" in data else None
        workflow = Workflow.objects(id=workflow_id).first()

        if search_set_item_id:
            workflow_step = None
            searchsetitem = SearchSetItem.objects(id=search_set_item_id).first()
            if step_id != None and step_id != 0:
                workflow_step = WorkflowStep.objects(id=step_id).first()
                if workflow_step:
                    workflow_step.data = searchsetitem.to_workflow_step_data()
                    workflow_step.save()
            else:
                workflow_step = WorkflowStep(
                    name="Prompt", data=searchsetitem.to_workflow_step_data()
                )
                workflow_step.save()
                workflow.steps.append(workflow_step)
                workflow.save()
        elif manual_input:
            workflow_step = None
            if step_id != None and step_id != 0:
                workflow_step = WorkflowStep.objects(id=step_id).first()
                if workflow_step:
                    workflow_step.data = {"prompt": manual_input}
                    workflow_step.save()
            else:
                workflow_step = WorkflowStep(
                    name="Prompt", data={"prompt": manual_input}
                )
                workflow_step.save()
                workflow.steps.append(workflow_step)
                workflow.save()

        return jsonify({"response": "success"})


## MARK: ~~ Formatting
@app.route("/api/workflows/add_formatter_step", methods=["GET", "POST"])
def workflow_add_format_step():
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = list(request.args.keys())[0]  # Get the JSON string key
        data = json.loads(data_str)  # Retrieve query parameters, if any
        workflow_id = data.get("workflow_uuid")
        space_id = data.get("space_id")

        is_editing = data.get("editing") or False
        workflow_step = None
        workflow_step_id = ""

        if is_editing:
            workflow_step_id = data.get("workflow_step_id")
            workflow_step = WorkflowStep.objects(id=workflow_step_id).first()

        workflow = Workflow.objects(id=workflow_id).first()

        current_space = Space.objects(uuid=space_id).first()
        formatters = SearchSetItem.objects(
            user_id=load_user().user_id,
            space_id=current_space.uuid,
            searchtype="formatter",
        ).all()

        template = render_template(
            "toolpanel/workflows/modals/workflow_add_formatting_modal.html",
            workflow=workflow,
            formatters=formatters,
            is_editing=is_editing,
            workflow_step=workflow_step,
            workflow_step_id=workflow_step_id,
        )
        response = {"template": template}
        return jsonify(response)

    elif request.method == "POST":

        # Handle POST request - create a new WorkflowStep
        data = request.get_json()
        step_id = data["step_id"] if "step_id" in data else None
        workflow_id = data["workflow_uuid"]
        search_set_item_id = (
            data["search_set_item_id"] if "search_set_item_id" in data else None
        )
        manual_input = data["manual_input"] if "manual_input" in data else None
        workflow = Workflow.objects(id=workflow_id).first()

        if search_set_item_id:
            searchsetitem = SearchSetItem.objects(id=search_set_item_id).first()
            workflow_step = None
            if step_id != None and step_id != 0:
                workflow_step = WorkflowStep.objects(id=step_id).first()
                if workflow_step:
                    workflow_step.data = searchsetitem.to_workflow_step_data()
                    workflow_step.save()
            else:
                workflow_step = WorkflowStep(
                    name="Formatter", data=searchsetitem.to_workflow_step_data()
                )
                workflow_step.save()
                workflow.steps.append(workflow_step)
                workflow.save()
        elif manual_input:
            workflow_step = None
            if step_id != None and step_id != 0:
                workflow_step = WorkflowStep.objects(id=step_id).first()
                if workflow_step:
                    workflow_step.data = {"prompt": manual_input}
                    workflow_step.save()
            else:
                workflow_step = WorkflowStep(
                    name="Formatter", data={"prompt": manual_input}
                )
                workflow_step.save()
                workflow.steps.append(workflow_step)
                workflow.save()

        return jsonify({"response": "success"})


## MARK: ~~ Documents
@app.route("/api/workflows/add_document_step", methods=["GET", "POST"])
def workflow_add_document_step():
    if request.method == "GET":
        # Handle GET request - retrieve and return the template
        data_str = list(request.args.keys())[0]  # Get the JSON string key
        data = json.loads(data_str)  # Retrieve query parameters, if any
        workflow_id = data.get("workflow_uuid")
        space_id = data.get("space_id")

        workflow = Workflow.objects(id=workflow_id).first()

        current_space = Space.objects(uuid=space_id).first()
        global_extraction_sets = SearchSet.objects(
            space=current_space.uuid, is_global=True, set_type="document"
        ).all()
        user_extraction_sets = SearchSet.objects(
            user_id=workflow.user_id,
            space=current_space.uuid,
            is_global=False,
            set_type="extraction",
        ).all()
        extraction_sets_objects = list(
            chain(global_extraction_sets, user_extraction_sets)
        )
        extraction_sets = ["Create a new set"] + [
            extraction["title"]
            for extraction in extraction_sets_objects
            if "title" in extraction
        ]

        template = render_template(
            "toolpanel/workflows/modals/workflow_add_documents_modal.html",
            workflow=workflow,
            extraction_sets=extraction_sets,
        )
        response = {"template": template}
        return jsonify(response)

    elif request.method == "POST":
        # Handle POST request - create a new WorkflowStep
        data = request.get_json()
        workflow_id = data["workflow_uuid"]
        workflow = Workflow.objects(id=workflow_id).first()

        return jsonify({"response": "Placeholder"})


## MARK: File management


@app.route("/rename_document", methods=["POST"])
def rename_document():
    data = request.get_json()
    document_uuid = data["uuid"]
    new_title = data["newName"]

    document = SmartDocument.objects(uuid=document_uuid).first()
    document.title = new_title
    document.save()
    return jsonify({"complete": True})


@app.route("/rename_folder", methods=["POST"])
def rename_folder():
    data = request.get_json()
    document_uuid = data["uuid"]
    new_title = data["newName"]

    print(document_uuid)
    print(new_title)

    document = SmartFolder.objects(uuid=document_uuid).first()
    document.title = new_title
    document.save()
    return jsonify({"complete": True})


@app.route("/move_file", methods=["POST"])
def move_file():
    data = request.get_json()
    file_uuid = data["fileUUID"]
    folder_id = data["folderID"]

    document = SmartDocument.objects(uuid=file_uuid).first()
    document.folder = folder_id
    document.save()

    return jsonify({"complete": True})


@app.route("/delete_document", methods=["GET"])
def delete_documents():
    document_uuid = request.args.get("docid")
    document = SmartDocument.objects(uuid=document_uuid).first()
    document.delete()
    semantics = SemanticIngest()
    semantics.delete(document)
    if document.extension == "html":
        # delete html files lmke doc_uuid-*.html
        html_files = [
            f
            for f in os.listdir(os.path.join(app.root_path, "static", "uploads"))
            if f.startswith(document.uuid)
        ]
        for html_file in html_files:
            os.remove(os.path.join(app.root_path, "static", "uploads", html_file))
    folder_id = request.args.get("folder_id")
    if folder_id:
        return redirect("/home?folder_id=" + folder_id)

    return redirect("/home")


@app.route("/files/delete_folder", methods=["GET"])
def delete_folder():
    folder_id = request.args.get("folder_id")
    SmartFolder.objects.filter(uuid=folder_id).delete()

    # Delete all subfolders
    SmartFolder.objects.filter(parent_id=folder_id).delete()

    # Delete all subdocuments
    SmartDocument.objects.filter(folder=folder_id).delete()
    return redirect("/home")


@app.route("/files/move_item", methods=["POST"])
def move_item():
    item_type = request.POST.get("item_type")
    item_id = request.POST.get("item_id")
    target_folder_id = request.POST.get("target_folder_id")

    if item_type == "folder":
        SmartFolder.objects.filter(id=item_id).update(parent_id=target_folder_id)
    elif item_type == "document":
        SmartDocument.objects.filter(uuid=item_id).update(folder_id=target_folder_id)

    return redirect("file_browser")


@app.route("/files/toggle_default_doc", methods=["GET"])
def add_default_doc():
    user = load_user()
    doc_id = request.args.get("doc_id")
    folder_id = request.args.get("folder_id")
    redirect_url = request.args.get("redirect_url")
    redirect_url = f"/home?{redirect_url}"

    doc = SmartDocument.objects(uuid=doc_id).first()
    # toggle the default doc
    doc.is_default = not doc.is_default
    doc.save()

    return redirect(redirect_url)


@app.route("/files/create_folder", methods=["GET", "POST"])
def create_folder():
    parent_id = request.form["parent_id"]
    name = request.form["name"]
    space_id = request.form["space_id"]
    SmartFolder.objects.create(
        title=name,
        parent_id=parent_id,
        space=space_id,
        user_id=session["user_id"],
        uuid=uuid.uuid4().hex,
    )
    return redirect("/home")


##################
# Spaces         #
##################
## MARK: Spaces
@app.route("/spaces/new", methods=["GET", "POST"])
def new_space():
    if request.method == "POST":
        title = request.form["title"]
        space = Space(title=title, uuid=uuid.uuid4().hex)
        space.save()
        return redirect("/home?id=" + space.uuid)
    return render_template("spaces/new.html")


@app.route("/submit_rating", methods=["POST"])
def submit_rating():
    data = request.get_json()
    print(data)
    pdf_title = data["pdf_title"]
    rating = data["rating"]
    comment = data["comment"]
    result_json = data["result_json"]
    result_json_str = json.dumps(result_json)
    record = ExtractionQualityRecord(
        pdf_title=pdf_title,
        star_rating=rating,
        comment=comment,
        result_json=result_json_str,
    )
    record.save()
    return jsonify({"complete": True})


@app.route("/export_extraction", methods=["GET"])
def export_extraction():
    result_json = request.args.to_dict()
    # result_json = data['result_json']

    # Convert the dictionary to a list of rows
    rows = []
    for key, value in result_json.items():
        rows.append([key, value])

    # Define the file path for the CSV file
    csv_file_path = os.path.join(app.root_path, "static", "export.csv")

    print(rows)
    # Write the rows to the CSV file
    with open(csv_file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    # Return the path to the CSV file
    return send_file("static/export.csv", mimetype="text/csv", as_attachment=True)


@app.route("/download_fillable", methods=["GET"])
def download_fillable():
    result_json = request.args.to_dict()
    bindings = {}
    search_set_uuid = result_json["search_set_uuid"]
    search_set = SearchSet.objects(uuid=search_set_uuid).first()
    del result_json["search_set_uuid"]
    for key, value in result_json.items():
        print(key)
        search_set_item = SearchSetItem.objects(searchphrase=key).first()
        bindings[search_set_item.pdf_binding] = value

    print(bindings)
    # Define the file path for the CSV file
    pdf_path = os.path.join(
        app.root_path, "static", "uploads", search_set.fillable_pdf_url
    )

    print(pdf_path)
    reader = PdfReader(pdf_path)
    fields = reader.get_fields()
    writer = PdfWriter()
    writer.append(reader)

    # for page in reader.pages:
    writer.update_page_form_field_values(
        writer.pages[0], bindings, auto_regenerate=False
    )

    output_pdf_path = os.path.join(app.root_path, "static", "fillable_form.pdf")
    with open(output_pdf_path, "wb") as f:
        writer.write(f)

    # Return the path to the CSV file
    return send_file(
        "static/fillable_form.pdf", mimetype="text/pdf", as_attachment=True
    )


@app.route("/build_admin")
def build_admin():
    user = User(user_id="admin", is_admin=True)
    user.save()
    session["user_id"] = "admin"


def load_user():
    if "dev" in os.environ.get("APP_ENV"):
        # Create a admin
        user = User.objects(user_id="0").first()
        if not user:
            user = User(user_id="0", is_admin=True)
            user.save()
        session["user_id"] = "0"
        return user
    if "user_id" in session:
        user = User.objects(user_id=session["user_id"]).first()
        if user:
            return user
        else:
            user = User(user_id=session["user_id"], is_admin=False)
            user.save()
            print("Built new user" + user.user_id)
            return user
    return None


####### Feedback #######
## MARK: Feedback
@app.route("/feedback", methods=["POST"])
def feedback():

    user = load_user()
    user_id = user.user_id
    data = request.get_json()

    feedback_type = data.get("feedback_type")
    question = data.get("question")
    answer = data.get("answer")
    context = data.get("context")
    context = " ".join(context)
    docs_uuids = data.get("docs_uuids")

    print("feedback_type", feedback_type)
    print("question", question)
    print("docs_uuids", docs_uuids)
    feedback = Feedback(
        user_id=user_id,
        feedback=feedback_type,
        question=question,
        answer=answer,
        context=context,
        docs_uuids=docs_uuids,
    )

    feedback.save()

    # Maintain feedback count
    feedback_counter = FeedbackCounter.objects().first()

    if not feedback_counter:
        feedback_counter = FeedbackCounter(count=0)

    feedback_counter.count += 1
    feedback_counter.save()
    max_feedback_count = 100

    print("feedback_counter", feedback_counter.count)

    if feedback_counter.count >= max_feedback_count:
        feedback_counter.count = 0  # Reset count after 10 feedbacks
        feedback_counter.save()

        feedback_list = Feedback.objects().order_by("-id")[
            :max_feedback_count
        ]  # Get latest 10 feedbacks

        # feedback_list = Feedback.objects().all()

        root_path = app.root_path
        process = mp.Process(
            target=background_retrain_model, args=(feedback_list, root_path)
        )
        process.start()

    response = {
        "complete": True,
    }
    return jsonify(response)
