import base64
import uuid
from pathlib import Path

from app.config import Settings
from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.utils.file_validation import is_allowed_file, is_valid_file_content
from werkzeug.utils import secure_filename


async def upload_document(
    blob: str,
    filename: str,
    raw_extension: str,
    space: str,
    user_id: str,
    settings: Settings,
    folder: str | None = None,
    root_folder_name: str | None = None,
) -> dict:
    safe_name = secure_filename(filename)
    extension = raw_extension.lower().lstrip(".")

    if not is_allowed_file(safe_name):
        raise ValueError(f"File type '{extension}' is not allowed.")

    # Create folder if requested
    target_folder = folder
    if root_folder_name:
        new_folder = SmartFolder(
            title=root_folder_name,
            user_id=user_id,
            space=space,
            parent_id=folder or "0",
            uuid=uuid.uuid4().hex,
        )
        await new_folder.insert()
        target_folder = str(new_folder.id)

    if not target_folder:
        target_folder = "0"

    # De-duplicate
    existing = await SmartDocument.find_one(
        SmartDocument.title == safe_name,
        SmartDocument.user_id == user_id,
        SmartDocument.space == space,
        SmartDocument.folder == target_folder,
    )
    if existing:
        return {"complete": True, "exists": True}

    uid = uuid.uuid4().hex.upper()

    try:
        file_data = base64.b64decode(blob, validate=True)
    except (ValueError, TypeError):
        raise ValueError("Invalid base64 string.")

    if not is_valid_file_content(file_data, extension):
        raise ValueError("File content does not match its extension.")

    # Save file
    relative_path = Path(user_id) / f"{uid}.{extension}"
    upload_dir = Path(settings.upload_dir) / user_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{uid}.{extension}"
    file_path.write_bytes(file_data)

    document = SmartDocument(
        title=safe_name,
        processing=True,
        valid=True,
        raw_text="",
        downloadpath=str(relative_path),
        path=str(relative_path),
        extension=extension,
        uuid=uid,
        user_id=user_id,
        space=space,
        folder=target_folder,
        task_id=None,
        task_status="layout",
    )
    await document.insert()

    # Dispatch Celery tasks for extraction + validation
    from app.tasks.upload_tasks import dispatch_upload_tasks

    task_id = dispatch_upload_tasks(
        document_uuid=uid,
        extension=extension,
        document_path=str(file_path),
    )
    document.task_id = task_id
    await document.save()

    return {"complete": True, "uuid": uid, "document_id": str(document.id)}


async def download_document(doc_uuid: str, settings: Settings) -> Path | None:
    doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
    if not doc:
        return None
    download_path = doc.downloadpath or doc.path
    return Path(settings.upload_dir) / download_path


async def delete_document(doc_uuid: str, settings: Settings) -> bool:
    doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
    if not doc:
        return False
    # Delete file
    download_path = doc.downloadpath or doc.path
    file_path = Path(settings.upload_dir) / download_path
    if file_path.exists():
        file_path.unlink()
    await doc.delete()
    return True


async def rename_document(doc_uuid: str, new_title: str) -> bool:
    if not is_allowed_file(new_title):
        raise ValueError(f"File name '{new_title}' is not allowed.")
    doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
    if not doc:
        return False
    doc.title = new_title
    if not doc.downloadpath:
        doc.downloadpath = doc.path
    await doc.save()
    return True


async def move_document(file_uuid: str, folder_id: str) -> bool:
    doc = await SmartDocument.find_one(SmartDocument.uuid == file_uuid)
    if not doc:
        return False
    doc.folder = folder_id
    await doc.save()
    return True
