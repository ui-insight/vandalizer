import csv
import io
import os
import uuid
from copy import deepcopy
from pathlib import Path

from devtools import debug
from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from markupsafe import escape
from pypdf import PdfReader, PdfWriter

from app.models import (
    ActivityType,
    SearchSet,
    SearchSetItem,
    SmartDocument,
    UserModelConfig,
)
from app.utilities.analytics_helper import ActivityType, activity_finish, activity_start
from app.utilities.chat_manager import ChatManager
from app.utilities.config import settings
from app.utilities.extraction_manager_nontyped import ExtractionManagerNonTyped
from app.utilities.extraction_tasks import normalize_results, perform_extraction_task
from app.utilities.library_helpers import (
    _get_or_create_personal_library,
    add_object_to_library,
)

# SemanticRecommender is now accessed via singleton in workflows.routes
from app.utilities.verification_helpers import user_can_modify_verified

tasks = Blueprint("tasks", __name__)

EXTRACTION_PANEL_TEMPLATE = "toolpanel/extractions/extraction_panel.html"


def _active_user_or_none():
    """Return the authenticated user or None."""
    try:
        if current_user.is_authenticated:
            return current_user
    except Exception:
        return None
    return None


def _verified_edit_forbidden_response():
    return (
        jsonify(
            {
                "error": "forbidden",
                "message": "Verified items can only be modified by examiners.",
            }
        ),
        403,
    )


def _can_edit_search_set(search_set: SearchSet | None) -> bool:
    return bool(
        search_set and user_can_modify_verified(_active_user_or_none(), search_set)
    )


def _render_extraction_panel(search_set: SearchSet, **context):
    context.setdefault("can_edit_extraction", _can_edit_search_set(search_set))
    context["search_set"] = search_set
    return render_template(EXTRACTION_PANEL_TEMPLATE, **context)


@login_required
@tasks.route("/model/filter", methods=["POST"])
def filter_models() -> ResponseReturnValue:
    data = request.get_json()
    uuids = data.get("uuids", [])
    validation_failed = False
    user = current_user

    settings_models = [m.model_dump() for m in settings.models]
    model_config = UserModelConfig.objects(user_id=user.user_id).first()
    if not model_config:
        model_config = UserModelConfig(user_id=user.user_id, name=settings.base_model)
        model_config.available_models = settings_models
        model_config.save()

    model_config.available_models = settings_models
    model_config.save()

    # refresh the  model config
    model_config = UserModelConfig.objects(user_id=user.user_id).first()

    current_model = settings.base_model
    print(current_model)
    models = settings_models
    if len(uuids) == 0:
        if model_config:
            current_model = model_config.name
        return jsonify({"models": settings_models, "current_model": current_model})
    for uuid in uuids:
        doc = SmartDocument.objects(uuid=uuid).first()
        if doc is not None and not doc.valid:
            validation_failed = True
            break
    if validation_failed:
        # filter out the external models
        models = [m for m in model_config.available_models if not m.get("external")]
        model_names = [m["name"] for m in models]
        current_model = (
            model_config.name
            if model_config.name in model_names
            else "gpt-oss-32k:120b"
        )
    elif model_config:
        current_model = model_config.name

    return jsonify({"models": models, "current_model": current_model})


@tasks.route("/model/update", methods=["POST"])
def update_model() -> ResponseReturnValue:
    """Update the model for a search set."""
    data = request.get_json()
    debug(data)
    name = data.get("name")
    temperature = data.get("temperature", 0.7)
    top_p = data.get("top_p", 0.9)

    user = current_user
    if not getattr(user, "is_authenticated", False) or not getattr(
        user, "user_id", None
    ):
        return jsonify({"error": "login required"}), 401

    model_config = UserModelConfig.objects(user_id=user.user_id).first()
    if model_config is None:
        model_config = UserModelConfig(
            user_id=user.user_id, name=name, temperature=temperature, top_p=top_p
        )
    else:
        model_config.name = name
        model_config.temperature = temperature
        model_config.top_p = top_p
    model_config.save()

    response = {"current_model": name}
    return jsonify(response)


# Add a extraction set
@login_required
@tasks.route("/extraction/add_search_set", methods=["POST"])
def add_search_set() -> ResponseReturnValue:
    """Add a new search set."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))

    data = request.get_json()
    debug(data)
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

    searchset.save()

    library = _get_or_create_personal_library(user.user_id)
    add_object_to_library(searchset, library=library, added_by_user_id=user.user_id)

    return jsonify({"complete": True, "uuid": searchset.uuid})


# Add a term to a search set
@login_required
@tasks.route("/extraction/add_search_term", methods=["POST"])
def add_search_term() -> ResponseReturnValue:
    """Add a term to an existing search set."""
    data = request.get_json()
    searchphrase = data["term"]
    searchphrase = escape(searchphrase)
    searchset_uuid = data["search_set_uuid"]
    searchset = SearchSet.objects(uuid=searchset_uuid).first()
    searchtype = data["searchtype"]

    attachments = data.get("attachments", None)

    if searchset.is_global:
        user = current_user
        if not user.is_admin:
            return jsonify(
                {
                    "complete": False,
                    "error": "You do not have permission to add to this search set.",
                },
            )

    searchsetitem = SearchSetItem(
        searchphrase=searchphrase,
        searchset=searchset_uuid,
        searchtype=searchtype,
    )
    if attachments:
        searchsetitem.text_blocks = attachments

    searchsetitem.save()

    template = render_template(
        "toolpanel/search_set_item.html",
        search_set=searchset,
        item=searchsetitem,
        item_index=searchset.items().count(),  # Assuming items is a
    )
    response = {
        "complete": True,
        "template": template,
    }
    return jsonify(response)


@login_required
@tasks.route("/add_prompt", methods=["POST"])
def add_prompt() -> ResponseReturnValue:
    """Add a new prompt to the database."""
    data = request.get_json()
    title = data["title"]
    prompt = data["prompt"]
    # sanitize the input
    title = escape(title)
    prompt = escape(prompt)
    space_id = data["space_id"]
    prompt_type = data["prompt_type"]
    if title == "" or prompt == "":
        return jsonify(
            {"complete": False, "error": "Title and prompt cannot be empty."},
        )

    user = current_user

    searchsetitem = SearchSetItem(
        searchphrase=prompt,
        title=title,
        space_id=space_id,
        user_id=user.user_id,
        searchtype=prompt_type,
    )

    searchsetitem.save()

    library = _get_or_create_personal_library(user.user_id)
    add_object_to_library(searchsetitem, library=library, added_by_user_id=user.user_id)

    response = {"complete": True}
    return jsonify(response)


@tasks.route("/edit_prompt", methods=["POST"])
def edit_prompt() -> ResponseReturnValue:
    """Edit an existing prompt."""
    data = request.get_json()
    uuid = data["uuid"]
    prompt = SearchSetItem.objects(id=uuid).first()
    if not prompt:
        return jsonify({"error": "not found"}), 404

    if not user_can_modify_verified(_active_user_or_none(), prompt):
        return _verified_edit_forbidden_response()

    template = render_template(
        "toolpanel/prompts/edit_prompt.html",
        prompt=prompt,
    )
    response = {
        "template": template,
    }

    return jsonify(response)


@tasks.route("/update_prompt", methods=["POST"])
def update_prompt() -> ResponseReturnValue:
    """Update an existing prompt in the database."""
    data = request.get_json()
    uuid = data["uuid"]
    title = data["title"]
    prompt = data["prompt"]
    prompt_item = SearchSetItem.objects(id=uuid).first()
    if not prompt_item:
        return jsonify({"error": "not found"}), 404

    if not user_can_modify_verified(_active_user_or_none(), prompt_item):
        return _verified_edit_forbidden_response()

    prompt_item.title = title
    prompt_item.searchphrase = prompt
    prompt_item.save()

    response = {
        "success": True,
    }

    return jsonify(response)


@tasks.route("/fetch_search_set_item", methods=["POST"])
def fetch_search_set_item() -> ResponseReturnValue:
    """Fetch a specific search set item by UUID."""
    data = request.get_json()
    uuid = data["uuid"]

    searchsetitem = SearchSetItem.objects(id=uuid).first()

    response = {"prompt": searchsetitem.searchphrase}
    return jsonify(response)


@tasks.route("/search_results", methods=["POST"])
def grab_template() -> ResponseReturnValue:
    """Grab the template for displaying search results."""
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_uuids = data["document_uuids"]

    edit_mode = data["edit_mode"]
    documents = []
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid).first()
        documents.append(document)

    search_set = SearchSet.objects(uuid=searchset_uuid).first()

    if search_set is None:
        return jsonify({"error": "Search set not found."})

    if search_set.set_type == "extraction":
        template = _render_extraction_panel(
            search_set,
            documents=documents,
        )
        response = {
            "template": template,
        }

        return jsonify(response)
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
    template = render_template(
        PROMPT_RESULTS_TEMPLATE,
        search_set=search_set,
        documents=documents,
    )
    response = {
        "template": template,
    }
    return jsonify(response)


@login_required
@tasks.route("/extraction/update_title", methods=["POST"])
def update_extraction_title() -> ResponseReturnValue:
    """Update the title of an extraction step."""
    user = current_user
    if user is None:
        return redirect(url_for("auth.login"))
    extraction_data = request.get_json()
    extraction_uuid = extraction_data["extraction_uuid"]
    extraction_step = SearchSet.objects(uuid=extraction_uuid).first()
    if not extraction_step:
        return jsonify({"error": "not found"}), 404

    if not user_can_modify_verified(_active_user_or_none(), extraction_step):
        return _verified_edit_forbidden_response()

    extraction_step.title = extraction_data["title"]
    extraction_step.save()

    response = {"complete": True}
    return jsonify(response)


PROMPT_RESULTS_TEMPLATE = "toolpanel/prompts/prompt_results.html"


@tasks.route("/semantic_search", methods=["POST"])
def semantic_search() -> ResponseReturnValue:
    """Perform a semantic search."""
    abort(403)
    return jsonify({"error": "This endpoint is not available."})


@tasks.route("/begin_search", methods=["POST"])
def begin_search() -> ResponseReturnValue:
    """Begin a search - now runs asynchronously using Celery."""
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_uuids = data["document_uuids"]

    debug(data)

    documents = []
    document_paths = []
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid).first()
        if document:
            documents.append(document)
            absolute_path = document.absolute_path
            document_paths.append(absolute_path)

    search_set = SearchSet.objects(uuid=searchset_uuid).first()
    debug(f"Searching for search set: {searchset_uuid}")

    user_model_config = UserModelConfig.objects(user_id=current_user.get_id()).first()
    model = settings.base_model
    if user_model_config is not None:
        model = user_model_config.name

    keys = []
    items = []
    if search_set is not None:
        items = search_set.items()
    for item in items:
        if item.searchtype == "extraction":
            keys.append(item.searchphrase)

    if len(keys) > 0:
        # Create activity event for the extraction run
        user = current_user
        current_team = user.ensure_current_team()
        activity = activity_start(
            type=ActivityType.SEARCH_SET_RUN,
            title=search_set.title if search_set and search_set.title else "Extraction",
            user_id=user.get_id(),
            team_id=current_team.uuid,
            search_set_uuid=searchset_uuid,
        )
        activity.status = "queued"
        activity.save()

        # Start async extraction task
        fillable_pdf_url = (
            search_set.fillable_pdf_url
            if search_set and hasattr(search_set, "fillable_pdf_url")
            else None
        )

        perform_extraction_task.apply_async(
            args=[
                str(activity.id),
                searchset_uuid,
                document_uuids,
                keys,
                current_app.root_path,
                fillable_pdf_url,
            ]
        )

        # Return immediately with activity info
        response = {
            "status": "queued",
            "activity_id": str(activity.id),
            "message": "Extraction task started",
        }
        return jsonify(response)

    # No keys to extract
    response = {
        "status": "error",
        "message": "No extraction keys found",
    }
    return jsonify(response), 400


@tasks.route("/extraction_status/<activity_id>", methods=["GET"])
def extraction_status(activity_id: str) -> ResponseReturnValue:
    """Check the status of an extraction task."""
    from app.models import ActivityEvent

    activity = ActivityEvent.objects(id=activity_id).first()
    if not activity:
        return jsonify({"error": "Activity not found"}), 404

    response = {
        "activity_id": str(activity.id),
        "status": activity.status,
        "title": activity.title,
    }

    # If completed, include results and rendered template
    if activity.status == "completed" and activity.result_snapshot:
        search_set_uuid = activity.result_snapshot.get("search_set_uuid")
        document_uuids = activity.result_snapshot.get("document_uuids", [])
        normalized_results = activity.result_snapshot.get("normalized", [])

        # Get search set and documents
        search_set = SearchSet.objects(uuid=search_set_uuid).first()
        documents = []
        for doc_uuid in document_uuids:
            document = SmartDocument.objects(uuid=doc_uuid).first()
            if document:
                documents.append(document)

        # Render template
        template = _render_extraction_panel(
            search_set,
            results=normalized_results,
            documents=documents,
        )

        response["template"] = template
        response["results"] = normalized_results

    elif activity.status == "failed":
        response["error"] = getattr(activity, "error", "Unknown error")

    return jsonify(response)


@tasks.route("/begin_search_sync", methods=["POST"])
def begin_search_sync() -> ResponseReturnValue:
    """Begin a search synchronously - fallback for cases that need immediate results."""
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_uuids = data["document_uuids"]

    print(data)

    documents = []
    document_paths = []
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid).first()
        if document:
            documents.append(document)
            absolute_path = document.absolute_path
            document_paths.append(absolute_path)

    search_set = SearchSet.objects(uuid=searchset_uuid).first()
    print("Searching for search set")
    print(searchset_uuid)
    keys = []
    items = []
    if search_set is not None:
        items = search_set.items()
    for item in items:
        if item.searchtype == "extraction":
            keys.append(item.searchphrase)

    if len(keys) > 0:
        # Create activity event for the extraction run
        user = current_user
        current_team = user.ensure_current_team()
        activity = activity_start(
            type=ActivityType.SEARCH_SET_RUN,
            title=search_set.title if search_set and search_set.title else "Extraction",
            user_id=user.get_id(),
            team_id=current_team.uuid,
            search_set_uuid=searchset_uuid,
        )
        # activity.documents_touched = (len(document_uuids),)
        activity.save()

        em = ExtractionManagerNonTyped()
        em.root_path = current_app.root_path
        # get current model
        user_config = UserModelConfig.objects(user_id=current_user.user_id).first()
        model_name = settings.base_model
        if user_config:
            model_name = user_config.name

        results = em.extract(keys, document_uuids, model_name)
        raw_results = deepcopy(results)

        if len(results) == 1:
            results = results[0]

        debug(f"Raw extraction results: {results}")

        # Handle empty or no results
        if not results:
            template = _render_extraction_panel(
                search_set,
                results={},
                documents=documents,
            )
            return jsonify({"template": template})

        # Normalize results
        normalized_results = normalize_results(results)
        debug(f"Normalized results: {normalized_results}")

        # Handle fillable PDF if configured
        if (
            search_set.fillable_pdf_url != ""
            and search_set.fillable_pdf_url is not None
        ):
            bindings = {}
            for key, value in normalized_results.items():
                search_set_item = SearchSetItem.objects(searchphrase=key).first()
                if search_set_item and search_set_item.pdf_binding:
                    bindings[search_set_item.pdf_binding] = value

            # Define the file path for the PDF file
            pdf_path = (
                Path(current_app.root_path)
                / "static"
                / "uploads"
                / search_set.fillable_pdf_url
            )

            reader = PdfReader(pdf_path)
            reader.get_fields()
            writer = PdfWriter()
            writer.append(reader)

            writer.update_page_form_field_values(
                writer.pages[0],
                bindings,
                auto_regenerate=False,
            )

            output_pdf_path = (
                Path(current_app.root_path) / "static" / "fillable_form.pdf"
            )
            with Path.open(output_pdf_path, "wb") as f:
                writer.write(f)

            return send_file(
                "static/fillable_form.pdf",
                mimetype="application/pdf",
                as_attachment=True,
            )

        normalized_results = normalize_results(results)
        print(normalize_results)

        activity_finish(activity)
        activity.result_snapshot = {
            "raw": raw_results,
            "normalized": normalized_results,
            "document_uuids": document_uuids,
            "search_set_uuid": searchset_uuid,
        }
        activity.save()

        template = _render_extraction_panel(
            search_set,
            results=normalized_results,
            documents=documents,
        )
        response = {
            "template": template,
            "activity_id": str(activity.id),
        }

        # Ingest extraction into vector database for future recommendations
        # Use singleton instance to avoid expensive re-initialization
        try:
            from app.blueprints.workflows.routes import get_recommendation_manager

            recommendation_manager = get_recommendation_manager()

            ingestion_text = "# Documents selected:"
            for doc in documents:
                ingestion_text += f"\n{doc.raw_text}"

            debug("BEGINNING EXTRACTION RECOMMENDATION")

            recommendation_manager.ingest_recommendation_item(
                identifier=str(search_set.uuid),
                ingestion_text=ingestion_text,
                recommendation_type="Extraction",
            )
            # Clear recommendations cache so new extraction appears immediately
            try:
                from app.blueprints.workflows.routes import clear_recommendations_cache

                clear_recommendations_cache()
            except Exception as cache_error:
                debug(f"Error clearing recommendations cache: {cache_error}")
        except Exception as e:
            debug(f"Error ingesting extraction recommendation: {e}")

        return jsonify(response)

    template = _render_extraction_panel(
        search_set,
        documents=documents,
    )
    response = {
        "template": template,
    }
    return jsonify(response)


@login_required
@tasks.route("/extract/build_from_document", methods=["POST"])
def build_extraction_from_document() -> ResponseReturnValue:
    """Build extraction from document."""
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_uuids = data["document_uuids"]

    search_set = SearchSet.objects(uuid=searchset_uuid).first()
    if not search_set:
        return jsonify({"error": "not found"}), 404

    if not user_can_modify_verified(_active_user_or_none(), search_set):
        return _verified_edit_forbidden_response()

    user_id = current_user.get_id()
    user_model_config = UserModelConfig.objects(user_id=user_id).first()
    model = settings.base_model
    if user_model_config is not None:
        model = user_model_config.name

    em = ExtractionManagerNonTyped()
    em.root_path = current_app.root_path

    keys = em.build_from_documents(document_uuids, model)

    if "entities" in keys:
        bindings = keys["entities"]
        for item in bindings:
            item_obj = SearchSetItem(
                searchphrase=item,
                searchset=search_set.uuid,
                searchtype="extraction",
            )
            item_obj.save()
    else:
        response = {
            "complete": False,
        }
        return jsonify(response)

    template = _render_extraction_panel(search_set)
    response = {
        "template": template,
    }

    return jsonify(response)


@tasks.route("/delete_search_set", methods=["POST"])
def delete_search_set() -> ResponseReturnValue:
    """Delete a search set."""
    data = request.get_json()
    search_set_uuid = data["uuid"]
    search_set = SearchSet.objects(uuid=search_set_uuid).first()
    if not search_set:
        return jsonify({"error": "not found"}), 404

    if not user_can_modify_verified(_active_user_or_none(), search_set):
        return _verified_edit_forbidden_response()

    search_set.delete()
    return jsonify({"success": True})


@tasks.route("/rename_search_set", methods=["POST"])
def rename_search_set() -> ResponseReturnValue:
    """Rename a search set."""
    data = request.get_json()
    search_set_uuid = data["search_set_uuid"]
    new_title = data["new_title"]
    search_set = SearchSet.objects(uuid=search_set_uuid).first()
    if not search_set:
        return jsonify({"error": "not found"}), 404

    if not user_can_modify_verified(_active_user_or_none(), search_set):
        return _verified_edit_forbidden_response()

    search_set.title = new_title
    search_set.save()

    return jsonify({"complete": True})


@tasks.route("/clone_search_set", methods=["POST"])
def clone_search_set() -> ResponseReturnValue:
    """Clone a search set."""
    user = current_user
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    data = request.get_json()
    search_set_uuid = data["search_set_uuid"]
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

    # Add the cloned search set to the user's library
    library = _get_or_create_personal_library(user.user_id)
    add_object_to_library(
        new_search_set, library=library, added_by_user_id=user.user_id
    )

    return jsonify({"complete": True})


@tasks.route("/delete_search_set_item", methods=["POST"])
def delete_search_set_item() -> ResponseReturnValue:
    """Delete a search set item."""
    data = request.get_json()
    search_set_item_uuid = data["uuid"]
    item = SearchSetItem.objects(id=search_set_item_uuid).first()
    if not item:
        return jsonify({"error": "Search set item not found"}), 404
    search_type = (item.searchtype or "").lower()
    user = _active_user_or_none()
    if search_type == "extraction":
        parent = SearchSet.objects(uuid=item.searchset).first()
        if not user_can_modify_verified(user, parent):
            return _verified_edit_forbidden_response()
    else:
        if not user_can_modify_verified(user, item):
            return _verified_edit_forbidden_response()

    item.delete()
    return jsonify({"complete": True})


@login_required
@tasks.route("/begin_prompt_search", methods=["POST"])
def begin_prompt_search() -> ResponseReturnValue:
    """Begin a prompt search."""
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_path = data["document"]

    search_set = SearchSet.objects(uuid=searchset_uuid).first()
    items = search_set.items()

    user = current_user
    user_id = user.user_id

    if len(items) > 0:
        llm = ChatManager()

        llm.load_document(document_path)
        results = {}
        for item in items:
            results[item.searchphrase] = llm.ask_question_to_loaded_document(item)
        template = render_template(
            PROMPT_RESULTS_TEMPLATE,
            search_set=search_set,
            results=results,
        )
        response = {
            "template": template,
        }
        return jsonify(response)
    template = render_template(
        PROMPT_RESULTS_TEMPLATE,
        search_set=search_set,
    )
    response = {
        "template": template,
    }
    return jsonify(response)


@tasks.route("/export_extraction", methods=["POST"])
def export_extraction():
    """Export the extraction results to a CSV file."""
    # 1) Grab your data from form-POST or JSON
    if request.is_json:
        data = request.get_json(force=True)
    else:
        data = request.form.to_dict()

    # 2) Build CSV in memory
    si = io.StringIO()
    writer = csv.writer(si)
    # Optional header row
    writer.writerow(["Search Term", "Result"])

    for term, result in data.items():
        writer.writerow([term, result])

    # 3) Create a response with the CSV data
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=export.csv"
    output.headers["Content-Type"] = "text/csv; charset=utf-8"

    return output


@tasks.route("/download_fillable", methods=["GET"])
def download_fillable() -> ResponseReturnValue:
    """Download a fillable PDF with the extraction results."""
    result_json = request.args.to_dict()
    bindings = {}
    search_set_uuid = result_json["search_set_uuid"]
    search_set = SearchSet.objects(uuid=search_set_uuid).first()
    del result_json["search_set_uuid"]
    for key, value in result_json.items():
        search_set_item = SearchSetItem.objects(searchphrase=key).first()
        bindings[search_set_item.pdf_binding] = value

    # Define the file path for the CSV file
    pdf_path = os.path.join(
        current_app.root_path,
        "static",
        "uploads",
        search_set.fillable_pdf_url,
    )

    reader = PdfReader(pdf_path)
    reader.get_fields()
    writer = PdfWriter()
    writer.append(reader)

    # for page in reader.pages:
    writer.update_page_form_field_values(
        writer.pages[0],
        bindings,
        auto_regenerate=False,
    )

    output_pdf_path = Path(current_app.root_path) / "static" / "fillable_form.pdf"
    with Path.open(output_pdf_path, "wb") as f:
        writer.write(f)

    # Return the path to the CSV file
    return send_file(
        "static/fillable_form.pdf",
        mimetype="text/pdf",
        as_attachment=True,
    )
