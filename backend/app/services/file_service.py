import base64
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.utils.file_validation import is_allowed_file, is_valid_file_content
from werkzeug.utils import secure_filename


@dataclass
class DownloadResult:
    data: bytes
    extension: str
    title: str


async def upload_document(
    blob: str,
    filename: str,
    raw_extension: str,
    space: str,
    user_id: str,
    settings: Settings,
    folder: str | None = None,
    root_folder_name: str | None = None,
    team_id: str | None = None,
) -> dict:
    safe_name = secure_filename(filename)
    extension = raw_extension.lower().lstrip(".")

    if not is_allowed_file(safe_name):
        raise ValueError(f"File type '{extension}' is not allowed.")

    # Pre-decode size estimate (base64 expands ~4/3x) — cheap check before DB queries
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    estimated_size = len(blob) * 3 // 4
    if estimated_size > max_bytes:
        raise ValueError(
            f"File too large: estimated {estimated_size / (1024 * 1024):.1f}MB "
            f"exceeds {settings.max_upload_size_mb}MB limit."
        )

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
        return {"complete": True, "exists": True, "uuid": existing.uuid}

    uid = uuid.uuid4().hex.upper()

    try:
        file_data = base64.b64decode(blob, validate=True)
    except (ValueError, TypeError):
        raise ValueError("Invalid base64 string.")

    # Post-decode exact size check
    if len(file_data) > max_bytes:
        raise ValueError(
            f"File too large: {len(file_data) / (1024 * 1024):.1f}MB "
            f"exceeds {settings.max_upload_size_mb}MB limit."
        )

    if not is_valid_file_content(file_data, extension):
        raise ValueError("File content does not match its extension.")

    # Save file via storage backend
    from app.services.storage import get_storage

    storage = get_storage(settings)
    relative_path_str = f"{user_id}/{uid}.{extension}"
    await storage.write(relative_path_str, file_data)

    # Celery tasks need a local filesystem path; use public_path() for local
    # storage or write a temporary file for remote backends (e.g. S3).
    local_path = storage.public_path(relative_path_str)
    if local_path is None:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}")
        tmp.write(file_data)
        tmp.close()
        local_path = tmp.name

    relative_path = Path(relative_path_str)

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
        team_id=team_id,
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
        document_path=local_path,
        user_id=user_id,
    )
    document.task_id = task_id
    await document.save()

    return {"complete": True, "uuid": uid, "document_id": str(document.id)}


async def download_document(
    doc_uuid: str, settings: Settings, *, user_id: str | None = None
) -> DownloadResult | None:
    filters = [SmartDocument.uuid == doc_uuid]
    if user_id is not None:
        filters.append(SmartDocument.user_id == user_id)
    doc = await SmartDocument.find_one(*filters)
    if not doc:
        return None
    from app.services.storage import get_storage

    storage = get_storage(settings)
    relative_path = doc.downloadpath or doc.path
    try:
        data = await storage.read(relative_path)
    except Exception:
        return None
    ext = doc.extension or Path(relative_path).suffix.lstrip(".")
    return DownloadResult(data=data, extension=ext, title=doc.title or doc_uuid)


async def delete_document(
    doc_uuid: str, settings: Settings, *, user_id: str | None = None
) -> bool:
    filters = [SmartDocument.uuid == doc_uuid]
    if user_id is not None:
        filters.append(SmartDocument.user_id == user_id)
    doc = await SmartDocument.find_one(*filters)
    if not doc:
        return False
    from app.services.storage import get_storage

    storage = get_storage(settings)
    relative_path = doc.downloadpath or doc.path
    await storage.delete(relative_path)
    await doc.delete()
    return True


async def rename_document(doc_uuid: str, new_title: str, *, user_id: str | None = None) -> bool:
    if not new_title.strip():
        raise ValueError("File name cannot be empty.")
    filters = [SmartDocument.uuid == doc_uuid]
    if user_id is not None:
        filters.append(SmartDocument.user_id == user_id)
    doc = await SmartDocument.find_one(*filters)
    if not doc:
        return False
    doc.title = new_title
    if not doc.downloadpath:
        doc.downloadpath = doc.path
    await doc.save()
    return True


async def move_document(file_uuid: str, folder_id: str, *, user_id: str | None = None) -> bool:
    filters = [SmartDocument.uuid == file_uuid]
    if user_id is not None:
        filters.append(SmartDocument.user_id == user_id)
    doc = await SmartDocument.find_one(*filters)
    if not doc:
        return False
    doc.folder = folder_id
    await doc.save()
    return True
