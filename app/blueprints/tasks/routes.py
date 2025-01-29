from flask import Blueprint, request, jsonify, current_app, redirect, url_for, render_template, send_file
from app.models import SmartDocument, SearchSet, SearchSetItem
from app.utilities.semantic_ingest import SemanticIngest
from app.utils import load_user
from app.utilities.openai_interface import OpenAIInterface
from app.utilities.extraction_manager3 import ExtractionManager3
from app.utilities.extraction_manager2 import ExtractionManager2
from copy import deepcopy
import csv, os, uuid

from pypdf import PdfReader, PdfWriter

from . import tasks

# Add a extraction set
@tasks.route("/extraction/add_search_set", methods=["POST"])
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
    # if user.is_admin:
    #     searchset.is_global = True
    searchset.save()
    return jsonify({"complete": True, "uuid": searchset.uuid})

# Add a term to a search set
@tasks.route("/extraction/add_search_term", methods=["POST"])
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


@tasks.route("/add_prompt", methods=["POST"])
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


@tasks.route("/edit_prompt", methods=["POST"])
def edit_prompt():
    data = request.get_json()
    uuid = data["uuid"]
    user = load_user()
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
def update_prompt():
    data = request.get_json()
    uuid = data["uuid"]
    title = data["title"]
    prompt = data["prompt"]
    user = load_user()
    prompt_item = SearchSetItem.objects(id=uuid).first()

    prompt_item.title = title
    prompt_item.searchphrase = prompt
    prompt_item.save()

    response = {
        "success": True,
    }

    return jsonify(response)


## MARK: Tasks - Extraction
@tasks.route("/fetch_search_set_item", methods=["POST"])
def fetch_search_set_item():
    data = request.get_json()
    uuid = data["uuid"]

    searchsetitem = SearchSetItem.objects(id=uuid).first()

    response = {"prompt": searchsetitem.searchphrase}
    return jsonify(response)


@tasks.route("/search_results", methods=["POST"])
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
        template = render_template(
            "toolpanel/extractions/extraction_panel.html",
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


@tasks.route("/extraction/update_title", methods=["POST"])
def update_extraction_title():
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


@tasks.route("/begin_search", methods=["POST"])
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
        em = ExtractionManager3()
        em.root_path = current_app.root_path
        results = em.extract(keys, document_paths)[0]

        if search_set.fillable_pdf_url != "" and search_set.fillable_pdf_url != None:
            bindings = {}
            for key in results:
                print(key)
                search_set_item = SearchSetItem.objects(searchphrase=key).first()
                bindings[search_set_item.pdf_binding] = results[key]

            print(bindings)
            # Define the file path for the CSV file
            pdf_path = os.path.join(
                current_app.root_path, "static", "uploads", search_set.fillable_pdf_url
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

            output_pdf_path = os.path.join(current_app.root_path, "static", "fillable_form.pdf")
            with open(output_pdf_path, "wb") as f:
                writer.write(f)

            # Return the path to the CSV file
            return send_file(
                "static/fillable_form.pdf", mimetype="text/pdf", as_attachment=True
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
    else:
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
def build_extraction_from_document():
    data = request.get_json()
    print(data)
    searchset_uuid = data["search_set_uuid"]
    document_uuids = data["document_uuids"]

    documents = []
    document_paths = []
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid).first()
        documents.append(document)
        document_paths.append(document.path)

    search_set = SearchSet.objects(uuid=searchset_uuid).first()

    em = ExtractionManager2()
    em.root_path = current_app.root_path
    keys = em.build_from_documents(document_paths)
    print(keys)

    if "entities" in keys:
        bindings = keys["entities"]
        for item in bindings:
            item = SearchSetItem(
                searchphrase=item,
                searchset=search_set.uuid,
                searchtype="extraction",
            )
            item.save()
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
    return jsonify(response)


@tasks.route("/delete_search_set", methods=["POST"])
def delete_search_set():
    data = request.get_json()
    search_set_uuid = data["uuid"]
    print(search_set_uuid)
    search_set = SearchSet.objects(uuid=search_set_uuid).first()
    search_set.delete()
    return jsonify({"success": True})


@tasks.route("/rename_search_set", methods=["POST"])
def rename_search_set():
    data = request.get_json()
    search_set_uuid = data["search_set_uuid"]
    new_title = data["new_title"]
    print(search_set_uuid)
    search_set = SearchSet.objects(uuid=search_set_uuid).first()
    search_set.title = new_title
    search_set.save()

    return jsonify({"complete": True})


@tasks.route("/clone_search_set", methods=["POST"])
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


@tasks.route("/delete_search_set_item", methods=["POST"])
def delete_search_set_item():
    data = request.get_json()
    print("Deleting search set item")
    search_set_item_uuid = data["uuid"]
    print(search_set_item_uuid)
    search_set = SearchSetItem.objects(id=search_set_item_uuid).first()
    search_set.delete()
    return jsonify({"complete": True})


@tasks.route("/begin_prompt_search", methods=["POST"])
def begin_prompt_search():
    data = request.get_json()
    searchset_uuid = data["search_set_uuid"]
    document_path = data["document"]

    search_set = SearchSet.objects(uuid=searchset_uuid).first()
    keys = []
    items = search_set.items()

    if len(items) > 0:
        llm = OpenAIInterface()
        llm.load_document(current_app.root_path, document_path)
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
    



@tasks.route("/export_extraction", methods=["GET"])
def export_extraction():
    result_json = request.args.to_dict()
    # result_json = data['result_json']

    # Convert the dictionary to a list of rows
    rows = []
    for key, value in result_json.items():
        rows.append([key, value])

    # Define the file path for the CSV file
    csv_file_path = os.path.join(current_app.root_path, "static", "export.csv")

    print(rows)
    # Write the rows to the CSV file
    with open(csv_file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    # Return the path to the CSV file
    return send_file("static/export.csv", mimetype="text/csv", as_attachment=True)


@tasks.route("/download_fillable", methods=["GET"])
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
        current_app.root_path, "static", "uploads", search_set.fillable_pdf_url
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

    output_pdf_path = os.path.join(current_app.root_path, "static", "fillable_form.pdf")
    with open(output_pdf_path, "wb") as f:
        writer.write(f)

    # Return the path to the CSV file
    return send_file(
        "static/fillable_form.pdf", mimetype="text/pdf", as_attachment=True
    )