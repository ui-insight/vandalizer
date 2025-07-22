import csv
import io
import os
import uuid
from copy import deepcopy
from pathlib import Path

from devtools import debug
from flask import (
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
from pypdf import PdfReader, PdfWriter

from app.models import SearchSet, SearchSetItem, SmartDocument, UserModelConfig
from app.utilities.config import settings
from app.utilities.extraction_manager3 import ExtractionManager3
from app.utilities.openai_interface import OpenAIInterface
from app.utilities.semantic_recommender import (
    SemanticRecommender,
)
from app.utils import load_user

from . import tasks


@tasks.route("/model/filter", methods=["POST"])
def filter_models() -> ResponseReturnValue:
    data = request.get_json()
    uuids = data.get("uuids", [])
    debug(data)
    validation_failed = False
    user = load_user()

    settings_models = [m.model_dump() for m in settings.models]
    debug(settings_models)
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
        if doc is not None:
            if not doc.valid:
                validation_failed = True
                break
    if validation_failed:
        # filter out the external models
        models = [m for m in model_config.available_models if not m.get("external")]
        debug(models)
        model_names = [m["name"] for m in models]
        current_model = (
            model_config.name if model_config.name in model_names else "qwen3-32k:32b"
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

    user = load_user()

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
@tasks.route("/extraction/add_search_set", methods=["POST"])
def add_search_set() -> ResponseReturnValue:
    """Add a new search set."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))

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
    return jsonify({"complete": True, "uuid": searchset.uuid})


# Add a term to a search set
@tasks.route("/extraction/add_search_term", methods=["POST"])
def add_search_term() -> ResponseReturnValue:
    """Add a term to an existing search set."""
    data = request.get_json()
    searchphrase = data["term"]
    searchset_uuid = data["search_set_uuid"]
    searchset = SearchSet.objects(uuid=searchset_uuid).first()
    searchtype = data["searchtype"]

    attachments = data.get("attachments", None)

    if searchset.is_global:
        user = load_user()
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


@tasks.route("/add_prompt", methods=["POST"])
def add_prompt() -> ResponseReturnValue:
    """Add a new prompt to the database."""
    data = request.get_json()
    title = data["title"]
    prompt = data["prompt"]
    space_id = data["space_id"]
    prompt_type = data["prompt_type"]
    if title == "" or prompt == "":
        return jsonify(
            {"complete": False, "error": "Title and prompt cannot be empty."},
        )

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


@tasks.route("/edit_prompt", methods=["POST"])
def edit_prompt() -> ResponseReturnValue:
    """Edit an existing prompt."""
    data = request.get_json()
    uuid = data["uuid"]
    load_user()
    prompt = SearchSetItem.objects(id=uuid).first()

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
    load_user()
    prompt_item = SearchSetItem.objects(id=uuid).first()

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
        template = render_template(
            "toolpanel/extractions/extraction_panel.html",
            search_set=search_set,
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
        "toolpanel/prompts/prompt_results.html",
        search_set=search_set,
        documents=documents,
    )
    response = {
        "template": template,
    }
    return jsonify(response)


@tasks.route("/extraction/update_title", methods=["POST"])
def update_extraction_title() -> ResponseReturnValue:
    """Update the title of an extraction step."""
    user = load_user()
    if user is None:
        return redirect(url_for("login"))
    extraction_data = request.get_json()
    extraction_uuid = extraction_data["extraction_uuid"]
    extraction_step = SearchSet.objects(uuid=extraction_uuid).first()
    extraction_step.title = extraction_data["title"]
    extraction_step.save()

    response = {"complete": True}
    return jsonify(response)


@tasks.route("/semantic_search", methods=["POST"])
def semantic_search() -> ResponseReturnValue:
    """Perform a semantic search."""
    abort(403)
    return jsonify({"error": "This endpoint is not available."})


def normalize_results(results):
    from collections import defaultdict

    if isinstance(results, list):
        collected = defaultdict(list)

        for d in results:
            if isinstance(d, dict):
                for k, v in d.items():
                    if v not in collected[k]:
                        collected[k].append(v)

        # Convert to string or comma-separated string
        flattened = {
            k: v[0] if len(v) == 1 else ", ".join(str(val) for val in v)
            for k, v in collected.items()
        }
        return flattened

    elif isinstance(results, dict):
        return results

    return {}


@tasks.route("/begin_search", methods=["POST"])
def begin_search() -> ResponseReturnValue:
    """Begin a search."""
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_uuids = data["document_uuids"]

    print(data)

    documents = []
    document_paths = []
    load_user()
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid).first()
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
        em = ExtractionManager3()
        em.root_path = current_app.root_path
        results = em.extract(keys, document_uuids)
        if len(results) == 1:
            results = results[0]

        debug(results)

        if (
            search_set.fillable_pdf_url != ""
            and search_set.fillable_pdf_url is not None
        ):
            bindings = {}
            for key in results:
                search_set_item = SearchSetItem.objects(searchphrase=key).first()
                bindings[search_set_item.pdf_binding] = results[key]

            # Define the file path for the CSV file
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

            # for page in reader.pages:
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

            # Return the path to the CSV file
            return send_file(
                "static/fillable_form.pdf",
                mimetype="text/pdf",
                as_attachment=True,
            )

        normalized_results = normalize_results(results)
        print(normalize_results)
        template = render_template(
            "toolpanel/extractions/extraction_panel.html",
            search_set=search_set,
            results=normalized_results,
            documents=documents,
        )
        response = {
            "template": template,
        }

        # Ingest workflow into vector database for future recommendations
        ingestion_text = ""
        ingestion_text += "# Documents selected:"

        for doc in documents:
            ingestion_text += f"\n{doc.raw_text}"

        persist_directory = Path("data/recommendations_vectordb")
        recommendation_manager = SemanticRecommender(
            persist_directory=persist_directory
        )

        debug("BEGINNING EXTRACTION RECOMMENDATION")

        recommendation_manager.ingest_recommendation_item(
            identifier=str(search_set.uuid),
            ingestion_text=ingestion_text,
            recommendation_type="Extraction",
        )

        return jsonify(response)
    template = render_template(
        "toolpanel/extractions/extraction_panel.html",
        search_set=search_set,
        documents=documents,
    )
    response = {
        "template": template,
    }
    return jsonify(response)


@tasks.route("/extract/build_from_document", methods=["POST"])
def build_extraction_from_document() -> ResponseReturnValue:
    """Build extraction from document."""
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_uuids = data["document_uuids"]
    load_user()

    documents = []

    search_set = SearchSet.objects(uuid=searchset_uuid).first()

    em = ExtractionManager3()
    em.root_path = current_app.root_path

    user = load_user()
    model_config = UserModelConfig.objects(user_id=user.user_id).first()
    model = settings.base_model
    if model_config is not None:
        model = model_config.name
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

    template = render_template(
        "toolpanel/extractions/extraction_panel.html",
        search_set=search_set,
    )
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
    search_set.delete()
    return jsonify({"success": True})


@tasks.route("/rename_search_set", methods=["POST"])
def rename_search_set() -> ResponseReturnValue:
    """Rename a search set."""
    data = request.get_json()
    search_set_uuid = data["search_set_uuid"]
    new_title = data["new_title"]
    search_set = SearchSet.objects(uuid=search_set_uuid).first()
    search_set.title = new_title
    search_set.save()

    return jsonify({"complete": True})


@tasks.route("/clone_search_set", methods=["POST"])
def clone_search_set() -> ResponseReturnValue:
    """Clone a search set."""
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

    return jsonify({"complete": True})


@tasks.route("/delete_search_set_item", methods=["POST"])
def delete_search_set_item() -> ResponseReturnValue:
    """Delete a search set item."""
    data = request.get_json()
    search_set_item_uuid = data["uuid"]
    search_set = SearchSetItem.objects(id=search_set_item_uuid).first()
    search_set.delete()
    return jsonify({"complete": True})


@tasks.route("/begin_prompt_search", methods=["POST"])
def begin_prompt_search() -> ResponseReturnValue:
    """Begin a prompt search."""
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_path = data["document"]

    search_set = SearchSet.objects(uuid=searchset_uuid).first()
    items = search_set.items()

    user = load_user()
    user_id = user.user_id

    if len(items) > 0:
        llm = OpenAIInterface()
        document_file_path = Path("static") / "uploads" / user_id / document_path
        if not Path.exists(str(document_file_path)):
            document_file_path = (
                Path(current_app.root_path) / "static" / "uploads" / document_path
            )

        llm.load_document(document_path)
        results = {}
        for item in items:
            results[item.searchphrase] = llm.ask_question_to_loaded_document(item)
        template = render_template(
            "toolpanel/prompts/prompt_results.html",
            search_set=search_set,
            results=results,
        )
        response = {
            "template": template,
        }
        return jsonify(response)
    template = render_template(
        "toolpanel/prompts/prompt_results.html",
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
