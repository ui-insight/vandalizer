"""Handles file routing."""

import base64
import io
import uuid
from pathlib import Path

from devtools import debug
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    request,
    send_file,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from pypdf import PdfReader

# Normalize filename/extension early
from werkzeug.utils import secure_filename

from app import limiter
from app.models import SearchSet, SearchSetItem, SmartDocument, SmartFolder
from app.utilities.config import get_user_model_name, is_external_model
from app.utilities.security import safe_get_document, validate_json_request
from app.utilities.document_manager import (
    DocumentManager,
    cleanup_document,
    perform_extraction_and_update,
    update_document_fields,
)
from app.utilities.fillable_pdf_manager import FillablePDFManager
from app.utilities.upload_manager import (
    perform_document_validation,
)

files = Blueprint("files", __name__)

# Mapping of extensions to their expected "magic numbers" (file signatures)
# This helps verify the file content matches its extension.
FILE_SIGNATURES = {
    ".pdf": [b"%PDF-"],
    ".docx": [b"PK\x03\x04"],  # Also the signature for .zip, .xlsx, etc.
    ".xlsx": [b"PK\x03\x04"],
    ".xls": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],  # Compound File Binary Format
}


ALLOWED_EXTS = {"pdf", "docx", "xlsx", "xls"}
HOME_ROUTE = "home.index"


def is_allowed_file(filename: str) -> bool:
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTS


def is_valid_file_content(data: bytes, extension: str) -> bool:
    ext = extension.lower().lstrip(".")
    header = data[:8192]  # sniff a bit more for safety

    if ext == "pdf":
        # Some PDFs may have leading whitespace/newlines before %PDF-
        # Search within the first 1KB for the magic string
        return b"%PDF-" in header[:1024]

    if ext in ("docx", "xlsx"):
        # OOXML containers are ZIPs with specific [Content_Types].xml pieces
        # Quick zip signature:
        if not header.startswith(b"PK\x03\x04"):
            return False
        try:
            import io
            import zipfile

            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if ext == "docx":
                    return any(name.startswith("word/") for name in zf.namelist())
                if ext == "xlsx":
                    return any(name.startswith("xl/") for name in zf.namelist())
        except Exception:
            return False
        return True

    # Fallback: unknown extension not supported
    return False


@login_required
@files.route("/upload", methods=["POST"])
def upload():
    user = current_user
    if not user:
        return redirect(url_for("auth.login"))

    # Safer JSON parsing (won't 400 before your own code runs)
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Invalid JSON payload."}), 400

    user = current_user
    user_id = user.get_id()
    space = data.get("space")
    parent_folder_id = data.get("folder") or None
    new_folder_name = (data.get("rootFolderName") or "").strip() or None

    blob = data.get("contentAsBase64String")
    filename = (data.get("fileName") or "").strip()
    raw_extension = (data.get("extension") or "").strip()

    if not blob or not filename or not space:
        return jsonify(
            {"error": "Missing required fields: file content, file name, or space."}
        ), 400

    safe_filename = secure_filename(filename)
    extension = raw_extension.lower().lstrip(".")

    # --- SECURITY CHECK 1: Validate file extension (case-insensitive) ---
    if not is_allowed_file(safe_filename):
        return jsonify(
            {
                "error": f"File type '{extension}' is not allowed.",
                "code": "EXTENSION_NOT_ALLOWED",
            }
        ), 400

    # Create folder if requested
    if new_folder_name:
        smart_folder = SmartFolder(
            title=new_folder_name,
            user_id=user_id,
            space=space,
            parent_id=parent_folder_id,
        )
        smart_folder.save()
        target_folder = smart_folder.id
    else:
        target_folder = parent_folder_id

    if not target_folder:
        target_folder = "0"

    # De-duplicate on (title, user, space, folder)
    existing = SmartDocument.objects(
        title=safe_filename,
        user_id=user_id,
        space=space,
        folder=str(target_folder),
    )
    if existing.count() > 0:
        return jsonify({"complete": True, "exists": True}), 200

    uid = uuid.uuid4().hex.upper()

    # Base64 decode with clearer errors and a size sanity check (optional)
    try:
        imgdata = base64.b64decode(blob, validate=True)
    except (ValueError, TypeError) as e:
        current_app.logger.warning("Base64 decode failed for %s: %s", safe_filename, e)
        return jsonify({"error": "Invalid base64 string.", "code": "BAD_BASE64"}), 400

    # --- SECURITY CHECK 2: Validate content signature more leniently for PDFs ---
    if not is_valid_file_content(imgdata, extension):
        return jsonify(
            {
                "error": "File content does not match its extension.",
                "code": "MAGIC_MISMATCH",
            }
        ), 400

    # Save to per-user directory
    relative_file_path = Path(user.get_id()) / f"{uid}.{extension}"
    base_upload_dir = Path(current_app.root_path) / "static" / "uploads"
    base_upload_dir.mkdir(parents=True, exist_ok=True)
    upload_dir = base_upload_dir / user.get_id()
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / f"{uid}.{extension}"
    with file_path.open("wb") as f:
        f.write(imgdata)

    # Persist doc
    document = SmartDocument(
        title=safe_filename,
        processing=True,
        valid=True,
        raw_text="",
        downloadpath=str(relative_file_path),
        path=str(relative_file_path),
        extension=extension,
        uuid=uid,
        user_id=user_id,
        space=space,
        folder=str(target_folder),
        task_id=None,
        task_status="layout",
    )
    document.save()

    # Check if the user's selected model is external.
    model_name = get_user_model_name(user_id)
    selected_model_is_external = is_external_model(model_name)

    # Kick off tasks
    extraction_task = perform_extraction_and_update.s(
        document_uuid=document.uuid,
        extension=extension,
    )
    validation_task = perform_document_validation.s(
        document_uuid=document.uuid,
        document_path=str(file_path),
    )

    if selected_model_is_external:
        # External model: Sequential flow (extraction -> validation)
        # Document not usable until both complete
        workflow = extraction_task | validation_task
        workflow_task_result = workflow.apply_async(
            link=update_document_fields.si(document.uuid),
            link_error=cleanup_document.si(document.uuid),
        )
        document.task_id = workflow_task_result.id
    else:
        # Internal model: Parallel flow
        # Document usable after extraction, validation runs in background
        workflow_task_result = extraction_task.apply_async(
            link=update_document_fields.si(document.uuid),
            link_error=cleanup_document.si(document.uuid),
        )
        document.task_id = workflow_task_result.id

        # Run validation in the background independently with background=True flag
        # Pass None for document_text - the task will extract it from the file
        validation_task_background = perform_document_validation.s(
            document_text=None,
            document_uuid=document.uuid,
            document_path=str(file_path),
            background=True,
        )
        validation_task_background.apply_async()

    document.save()

    # Passive Vandalizer: Check for workflows watching this folder
    try:
        from app.models import Workflow
        from app.utilities.passive_triggers import create_folder_watch_trigger
        
        # Find workflows with folder watch enabled for this folder
        watching_workflows = Workflow.objects(
            input_config__folder_watch__enabled=True
        )
        
        for workflow in watching_workflows:
            folder_watch_config = workflow.input_config.get("folder_watch", {})
            watched_folders = folder_watch_config.get("folders", [])
            
            # Check if this folder is being watched
            if str(target_folder) in watched_folders or target_folder in watched_folders:
                # Create a pending trigger event
                create_folder_watch_trigger(workflow, document)
                
    except Exception as e:
        # Log error but don't fail the upload
        current_app.logger.error(f"Error creating folder watch trigger: {e}")

    return jsonify({"complete": True, "uuid": uid}), 200


@files.route("/poll_status", methods=["GET"])
@limiter.exempt
def poll_status() -> ResponseReturnValue:
    """Poll the status of a document's processing."""
    document_uuid = request.args.get("docid")
    if not document_uuid:
        return jsonify(
            {
                "status": "error",
                "status_messages": ["Missing document UUID"],
                "complete": True,
                "raw_text": "",
                "validation_feedback": "",
                "valid": True,
            },
        )
    debug(f"Polling status for document UUID: {document_uuid}")
    document = SmartDocument.objects(uuid=document_uuid).first()
    if not document:
        return jsonify({"error": "Document not found"}), 404
    debug(document)
    status_messages = []
    if document.task_status == "readying":
        status_messages.append("Getting ready…")
        if document.valid:
            status_messages.append("Document passed validation checks...")
        else:
            status_messages.append("Document failed validation checks...")

    complete = document.task_status == "complete" or document.task_status == "error"
    return jsonify(
        {
            "status": document.task_status,
            "status_messages": status_messages,
            "complete": complete,
            "raw_text": document.raw_text if not document.processing else "",
            "validation_feedback": document.validation_feedback,
            "valid": document.valid,
            "path": document.path,
        },
    )


@files.route("/rename_document", methods=["POST"])
def rename_document() -> ResponseReturnValue:
    """Rename a document."""
    data = request.get_json()
    document_uuid = data["uuid"]
    new_title = data["newName"]

    if not is_allowed_file(new_title):
        return jsonify({"error": f"File name '{new_title}' is not allowed."}), 400

    document = SmartDocument.objects(uuid=document_uuid).first()
    document.title = new_title
    if not document.downloadpath:
        document.downloadpath = document.path
    document.save()
    return jsonify({"complete": True})


@files.route("/rename_folder", methods=["POST"])
@login_required
@validate_json_request({"uuid": str, "newName": str})
def rename_folder() -> ResponseReturnValue:
    """Rename a folder."""
    data = request.get_json()
    document_uuid = data["uuid"]
    new_title = data["newName"]

    document = safe_get_document(SmartFolder, uuid=document_uuid)
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

    download_path = document.downloadpath if document.downloadpath else document.path

    document_file_path = (
        Path(current_app.root_path) / "static" / "uploads" / download_path
    )

    return send_file(document_file_path, as_attachment=True)


@files.route("/delete_document")
def delete_document() -> ResponseReturnValue:
    """Delete a document record and its file, but never crash the server."""
    doc_id = request.args.get("docid")
    user_id = current_user.get_id()
    if not doc_id:
        flash("No document specified.", "warning")
        return _redirect_home()
    document = SmartDocument.objects(uuid=doc_id).first()
    if not document:
        flash("Document not found.", "warning")
        return _redirect_home()

    # 1) Delete via manager (e.g. remove metadata/storage)
    try:
        DocumentManager().delete_document(
            user_id=user_id,
            document_id=doc_id,  # noqa: COM812
        )
    except Exception as e:
        current_app.logger.error(f"[delete_document] manager error: {e}")
        flash("Could not remove document metadata.", "danger")

    # 2) Try removing the file (but don’t bail out if it’s missing)
    file_path = document.absolute_path
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception as e:
            current_app.logger.error(f"[delete_document] file delete error: {e}")
            flash("Failed to delete document file.", "danger")
    else:
        current_app.logger.warning(f"[delete_document] file not found: {file_path}")
        flash("Document file was already gone.", "info")

    # 3) Always attempt to delete the DB record
    try:
        document.delete()
    except Exception as e:
        current_app.logger.error(f"[delete_document] db delete error: {e}")
        flash("Failed to delete document record.", "danger")
    else:
        flash("Document deleted successfully.", "success")

    return _redirect_home()


def _redirect_home():
    folder_id = request.args.get("folder_id")
    if folder_id:
        return redirect(url_for(HOME_ROUTE, folder_id=folder_id))
    return redirect(url_for(HOME_ROUTE))


@files.route("/delete_folder")
def delete_folder() -> ResponseReturnValue:
    """Delete a folder and all its contents."""
    folder_id = request.args.get("folder_id")
    folder = SmartFolder.objects(uuid=folder_id).first()

    if not folder:
        flash("Folder not found.", "warning")
        return _redirect_home()

    if folder.is_shared_team_root:
        flash("Shared team folders cannot be deleted.", "warning")
        return _redirect_home()

    SmartFolder.objects.filter(uuid=folder_id).delete()

    # Delete all subfolders and subdocuments
    SmartFolder.objects.filter(parent_id=folder_id).delete()
    SmartDocument.objects.filter(folder=folder_id).delete()

    return redirect(url_for(HOME_ROUTE))


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
@login_required
def toggle_default_doc() -> ResponseReturnValue:
    """Toggle the default document status."""
    doc_id = request.args.get("doc_id")
    request.args.get("folder_id")
    redirect_url = request.args.get("redirect_url")

    doc = safe_get_document(SmartDocument, uuid=doc_id)
    doc.is_default = not doc.is_default
    doc.save()

    return redirect(f"/home?{redirect_url}")


@login_required
@files.route("/create_folder", methods=["POST"])
def create_folder() -> ResponseReturnValue:
    """Create a new folder."""
    parent_id = request.form["parent_id"]
    name = request.form["name"]
    space_id = request.form["space_id"]
    folder_type = request.form["folder_type"]
    user = current_user
    current_team = user.ensure_current_team()

    if folder_type == "individual":
        folder = SmartFolder.objects.create(
            title=name,
            parent_id=parent_id,
            space=space_id,
            user_id=current_user.user_id,
            uuid=uuid.uuid4().hex,
        )
        return redirect(url_for(HOME_ROUTE, folder_id=folder.uuid))
    else:
        folder = SmartFolder.objects.create(
            title=name,
            parent_id=parent_id,
            space=space_id,
            team_id=current_team.uuid,
            uuid=uuid.uuid4().hex,
        )
        return redirect(url_for(HOME_ROUTE, folder_id=folder.uuid))


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
