import csv
import os
import uuid
from copy import deepcopy
from pathlib import Path

from devtools import debug
from flask import (
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask.typing import ResponseReturnValue
from pypdf import PdfReader, PdfWriter

from app.models import SearchSet, SearchSetItem, SmartDocument
from app.utilities.extraction_manager3 import ExtractionManager3
from app.utilities.openai_interface import OpenAIInterface
from app.utils import load_user

from . import tasks


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


@tasks.route("/begin_search", methods=["POST"])
def begin_search() -> ResponseReturnValue:
    """Begin a search."""
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_uuids = data["document_uuids"]

    documents = []
    document_paths = []
    load_user()
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid).first()
        documents.append(document)
        absolute_path = document.absolute_path
        document_paths.append(absolute_path)

    search_set = SearchSet.objects(uuid=searchset_uuid).first()
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
        results = em.extract(keys, document_paths)
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

        template = render_template(
            "toolpanel/extractions/extraction_panel.html",
            search_set=search_set,
            results=results,
            documents=documents,
        )
        response = {
            "template": template,
        }
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
    document_paths = []
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid).first()
        documents.append(document)
        absolute_path = document.absolute_path
        document_paths.append(absolute_path)

    search_set = SearchSet.objects(uuid=searchset_uuid).first()

    em = ExtractionManager3()
    em.root_path = current_app.root_path
    keys = em.build_from_documents(document_paths)

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

    user_id = load_user().user_id

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


@tasks.route("/export_extraction", methods=["GET"])
def export_extraction() -> ResponseReturnValue:
    """Export the extraction results to a CSV file."""
    result_json = request.args.to_dict()

    # Convert the dictionary to a list of rows
    rows = []
    for key, value in result_json.items():
        rows.append([key, value])

    # Define the file path for the CSV file
    csv_file_path = Path(current_app.root_path) / "static" / "export.csv"

    # Write the rows to the CSV file
    with Path.open(csv_file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    # Return the path to the CSV file
    return send_file("static/export.csv", mimetype="text/csv", as_attachment=True)


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
