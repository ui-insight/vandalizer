"""Handles file routing."""

import base64
import io
import os
import threading
import uuid
from pathlib import Path

import pypandoc
from devtools import debug
from flask import (
    abort,
    current_app,
    jsonify,
    redirect,
    request,
    send_file,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from pypdf import PdfReader

from app.models import SearchSet, SearchSetItem, SmartDocument, SmartFolder
from app.utilities.document_manager import (
    DocumentManager,
    perform_ocr_and_semantic_ingestion,
    perform_semantic_ingestion,
)
from app.utilities.document_readers import (
    extract_text_from_doc,
    extract_text_from_html,
)
from app.utilities.excel_helper import save_excel_to_html
from app.utilities.fillable_pdf_manager import FillablePDFManager
from app.utils import load_user

from . import files


@files.route("/upload", methods=["POST"])
def upload() -> ResponseReturnValue:
    """Handle file upload."""
    user = load_user()
    if user is None:
        return redirect(url_for("auth.login"))

    json_data = request.get_json()
    blob = json_data["contentAsBase64String"]
    filename = json_data["fileName"]
    extension = json_data["extension"]
    space = json_data["space"]
    folder = json_data["folder"]
    user_id = user.user_id
    debug(user_id)

    if folder is None or folder == "":
        folder = "0"

    if (
        SmartDocument.objects(
            title=filename,
            space=space,
            user_id=user.user_id,
            folder=folder,
        ).count()
        > 0
    ):
        return jsonify({"complete": True})

    imgdata = base64.b64decode(blob)
    uid = uuid.uuid4().hex.upper()

    # Update the stored path to include the user's id folder
    relative_file_path = Path(user_id) / f"{uid}.{extension}"
    debug(relative_file_path)

    # Define base upload directory
    base_upload_dir = Path(current_app.root_path) / "static" / "uploads"
    if not Path.exists(base_upload_dir):
        os.makedirs(base_upload_dir)

    # Create a directory for the user based on their id
    upload_dir = Path(base_upload_dir) / user_id
    if not Path.exists(upload_dir):
        os.makedirs(upload_dir)

    # Save the file to the user's directory
    file_path = Path(upload_dir) / f"{uid}.{extension}"
    with Path.open(file_path, "wb") as f:
        f.write(imgdata)

    debug(file_path)

    user_id = user.user_id

    raw_text = ""
    document = SmartDocument(
        title=filename,
        processing=True,
        raw_text=raw_text,
        path=relative_file_path,
        extension=extension,
        uuid=uid,
        user_id=user.user_id,
        space=space,
        folder=folder,
    )
    document.save()

    if extension == "docx":
        # Convert to PDF
        pdf_path = Path(upload_dir) / f"{uid}.pdf"
        docx_path = Path(upload_dir) / f"{uid}.docx"
        pypandoc.convert_file(docx_path, "pdf", outputfile=pdf_path)
        extension = "pdf"
        raw_text = extract_text_from_doc(docx_path)
        document.raw_text = raw_text
        document.processing = False
        document.save()
        thread = threading.Thread(
            target=perform_semantic_ingestion,
            args=(document, user_id, raw_text),
        )
        thread.start()

    elif extension in ["xlsx", "xls"]:
        # Convert to HTML
        html_path = Path(upload_dir) / f"{uid}.html"
        excel_path = Path(upload_dir) / f"{uid}.{extension}"
        save_excel_to_html(excel_path, html_path)
        extension = "html"
        raw_text = extract_text_from_html(html_path)
        document.raw_text = raw_text
        document.processing = False
        document.save()
        thread = threading.Thread(
            target=perform_semantic_ingestion,
            args=(document, user_id, raw_text),
        )
        thread.start()

    elif extension == "pdf":
        # Extract text from PDF in a background thread
        pdf_path = Path(upload_dir) / f"{uid}.pdf"
        thread = threading.Thread(
            target=perform_ocr_and_semantic_ingestion,
            args=(document, user_id),
        )
        thread.start()

    return jsonify({"complete": True, "uuid": uid, "folder_id": folder})


@files.route("/poll_status", methods=["GET"])
def poll_status() -> ResponseReturnValue:
    """Poll the status of a document's processing."""
    document_uuid = request.args.get("docid")
    document = SmartDocument.objects(uuid=document_uuid).first()
    return jsonify(
        {
            "complete": not document.processing and document.raw_text != "",
            "raw_text": document.raw_text if not document.processing else "",
        },
    )


@files.route("/rename_document", methods=["POST"])
def rename_document() -> ResponseReturnValue:
    """Rename a document."""
    data = request.get_json()
    document_uuid = data["uuid"]
    new_title = data["newName"]

    document = SmartDocument.objects(uuid=document_uuid).first()
    document.title = new_title
    document.save()
    return jsonify({"complete": True})


@files.route("/rename_folder", methods=["POST"])
def rename_folder() -> ResponseReturnValue:
    """Rename a folder."""
    data = request.get_json()
    document_uuid = data["uuid"]
    new_title = data["newName"]

    document = SmartFolder.objects(uuid=document_uuid).first()
    document.title = new_title
    document.save()
    return jsonify({"complete": True})


@files.route("/move_file", methods=["POST"])
def move_file() -> ResponseReturnValue:
    """Move a file to another folder."""
    data = request.get_json()
    file_uuid = data["fileUUID"]
    folder_id = data["folderID"]

    document = SmartDocument.objects(uuid=file_uuid).first()
    document.folder = folder_id
    document.save()

    return jsonify({"complete": True})


@files.route("/download_document")
def download_document() -> ResponseReturnValue:
    """Download a document."""
    document_uuid = request.args.get("docid")

    if not document_uuid:
        abort(400, description="Missing document UUID")

    document = SmartDocument.objects(uuid=document_uuid).first()
    if not document:
        abort(404, description="Document not found")

    document_file_path = (
        Path(current_app.root_path) / "static" / "uploads" / document.path
    )

    return send_file(document_file_path, as_attachment=True)


@files.route("/delete_document")
def delete_documents() -> ResponseReturnValue:
    """Delete a document."""
    document_uuid = request.args.get("docid")
    document = SmartDocument.objects(uuid=document_uuid).first()
    if document:
        document_manager = DocumentManager()
        document_manager.delete_document(
            user_id=session["user_id"],
            document_id=document_uuid,
        )

        document_file_path = (
            Path(current_app.root_path) / "static" / "uploads" / document.path
        )
        os.remove(document_file_path)

        document.delete()

    folder_id = request.args.get("folder_id")
    if folder_id:
        return redirect(url_for("home.index", folder_id=folder_id))

    return redirect(url_for("home.index"))


@files.route("/delete_folder")
def delete_folder() -> ResponseReturnValue:
    """Delete a folder and all its contents."""
    folder_id = request.args.get("folder_id")
    SmartFolder.objects.filter(uuid=folder_id).delete()

    # Delete all subfolders and subdocuments
    SmartFolder.objects.filter(parent_id=folder_id).delete()
    SmartDocument.objects.filter(folder=folder_id).delete()

    return redirect(url_for("home.index"))


@files.route("/move_item", methods=["POST"])
def move_item() -> ResponseReturnValue:
    """Move a document or folder to another folder."""
    item_type = request.form.get("item_type")
    item_id = request.form.get("item_id")
    target_folder_id = request.form.get("target_folder_id")

    if item_type == "folder":
        SmartFolder.objects.filter(id=item_id).update(parent_id=target_folder_id)
    elif item_type == "document":
        SmartDocument.objects.filter(uuid=item_id).update(folder_id=target_folder_id)

    return redirect(url_for("main.file_browser"))


@files.route("/toggle_default_doc")
def toggle_default_doc() -> ResponseReturnValue:
    """Toggle the default document status."""
    load_user()
    doc_id = request.args.get("doc_id")
    request.args.get("folder_id")
    redirect_url = request.args.get("redirect_url")

    doc = SmartDocument.objects(uuid=doc_id).first()
    doc.is_default = not doc.is_default
    doc.save()

    return redirect(f"/home?{redirect_url}")


@files.route("/create_folder", methods=["POST"])
def create_folder() -> ResponseReturnValue:
    """Create a new folder."""
    parent_id = request.form["parent_id"]
    name = request.form["name"]
    space_id = request.form["space_id"]

    folder = SmartFolder.objects.create(
        title=name,
        parent_id=parent_id,
        space=space_id,
        user_id=session["user_id"],
        uuid=uuid.uuid4().hex,
    )
    return redirect(url_for("home.index", folder_id=folder.uuid))


@files.route("/upload_fillable_pdf", methods=["POST"])
def upload_fillable_pdf() -> ResponseReturnValue:
    """Upload a fillable PDF."""
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    search_set_uuid = request.form.get("search_set_uuid")
    searchset = SearchSet.objects(uuid=search_set_uuid).first()
    for item in searchset.items():
        item.delete()

    # Read the PDF file
    file_stream = io.BytesIO(file.read())
    pdf_reader = PdfReader(file_stream)
    fields = pdf_reader.get_fields()

    # Write to the filesystem
    # Save the file to the filesystem
    file_path = Path(current_app.root_path) / "static" / "uploads" / file.filename
    file.seek(0)  # Go back to the start of the file
    with Path.open(file_path, "wb") as f:
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

    bindings = output["fields"]

    for item in bindings:
        key = next(iter(item.keys()))
        value = item[key]
        item_obj = SearchSetItem(
            searchphrase=value,
            searchset=search_set_uuid,
            searchtype="extraction",
            pdf_binding=key,
        )
        item_obj.save()

    return jsonify("Success"), 200


@files.route("/read_pdf", methods=["POST"])
def read_pdf() -> ResponseReturnValue:
    """Read a PDF file from base64 string and extract text."""
    json_data = request.get_json()
    blob = json_data["contentAsBase64String"]
    json_data["fileName"]

    imgdata = base64.b64decode(blob)
    uid = uuid.uuid4().hex.upper()
    with Path.open(
        Path(current_app.root_path) / "static" / "temp" / f"{uid}.pdf",
        "wb",
    ) as f:
        f.write(imgdata)

    pdf = PdfReader(Path(current_app.root_path) / "static" / "temp" / f"{uid}.pdf")
    number_of_pages = len(pdf.pages)
    full_text = ""
    for i in range(number_of_pages):
        full_text = full_text + pdf.pages[i].extract_text() + " "

    return jsonify({"full_text": full_text})
