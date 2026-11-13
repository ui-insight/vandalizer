import asyncio
import base64
import io
import logging
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from app.config import Settings
from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.user import User
from app.services.extraction_dispatch import record_extraction_dispatch
from app.services import access_control, audit_service
from app.utils.file_validation import is_allowed_file, is_valid_file_content
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    data: bytes
    extension: str
    title: str


def _safe_resolve(settings: Settings, relative_path: str) -> Path | None:
    root = Path(settings.upload_dir).resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        return None
    return target


async def upload_document(
    blob: str,
    filename: str,
    raw_extension: str,
    user: User,
    settings: Settings,
    folder: str | None = None,
    root_folder_name: str | None = None,
    certification_provisioning_key: str | None = None,
    replaces: SmartDocument | None = None,
) -> dict:
    """Store an upload and start reading it.

    ``replaces`` uploads a new version of that (already authorized) document:
    the new file lands in the same folder and team, skips the duplicate-name
    check, and the old version is marked superseded so it leaves the file
    list. Pages built from the old version then offer an update.
    """
    safe_name = secure_filename(filename)
    extension = raw_extension.lower().lstrip(".")
    user_id = user.user_id

    if certification_provisioning_key is not None and (
        len(certification_provisioning_key) != 64
        or any(char not in '0123456789abcdef' for char in certification_provisioning_key)
        or root_folder_name or not folder or folder == '0'
    ):
        raise ValueError('Course sample creation requires its original identity and lab folder.')

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

    target_folder = folder
    parent_folder: SmartFolder | None = None
    team_id: str | None = None

    if replaces is not None:
        if replaces.superseded_by:
            raise ValueError("A newer version of this file already exists. Upload to the latest version.")
        target_folder = replaces.folder or "0"
        team_id = replaces.team_id
        root_folder_name = None
    elif target_folder and target_folder != "0":
        parent_folder = await access_control.get_authorized_folder(target_folder, user, contribute=True)
        if not parent_folder:
            raise ValueError("Folder not found.")
        team_id = parent_folder.team_id

    if root_folder_name:
        new_folder = SmartFolder(
            title=root_folder_name,
            user_id=user_id if not team_id else None,
            parent_id=folder or "0",
            uuid=uuid.uuid4().hex,
            team_id=team_id,
        )
        await new_folder.insert()
        target_folder = new_folder.uuid

    if not target_folder:
        target_folder = "0"

    # De-duplicate
    existing: SmartDocument | None = None
    if replaces is not None:
        pass  # A new version may share its name with the version it replaces.
    elif team_id:
        existing = await SmartDocument.find_one(
            SmartDocument.title == safe_name,
            SmartDocument.team_id == team_id,
            SmartDocument.folder == target_folder,
            SmartDocument.soft_deleted != True,  # noqa: E712
            SmartDocument.superseded_by == None,  # noqa: E711 — older versions are hidden
        )
    else:
        existing = await SmartDocument.find_one(
            SmartDocument.title == safe_name,
            SmartDocument.user_id == user_id,
            SmartDocument.folder == target_folder,
            SmartDocument.soft_deleted != True,  # noqa: E712
            SmartDocument.superseded_by == None,  # noqa: E711 — older versions are hidden
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
    if extension.lower() == "xlsx":
        # The container check above only looks for an xl/ folder; a truncated
        # or corrupted workbook passes it and then fails extraction for good.
        # Refuse it here, with the reason, instead of storing a dead document.
        from app.services.document_readers import describe_damaged_workbook

        damaged = await asyncio.to_thread(describe_damaged_workbook, io.BytesIO(file_data))
        if damaged:
            raise ValueError(damaged)

    # Save file via storage backend
    from app.services.storage import get_storage

    storage = get_storage(settings)
    relative_path_str = f"{user_id}/{uid}.{extension}"
    await storage.write(relative_path_str, file_data)

    relative_path = Path(relative_path_str)

    document = SmartDocument(
        title=safe_name,
        processing=True,
        validating=True,
        valid=True,
        raw_text="",
        downloadpath=str(relative_path),
        path=str(relative_path),
        extension=extension,
        uuid=uid,
        user_id=user_id,
        team_id=team_id,
        folder=target_folder,
        task_id=None,
        task_status="layout",
        certification_provisioning_key=certification_provisioning_key,
    )
    if replaces is not None:
        document.version_root = replaces.version_root or replaces.uuid
        document.version_number = (replaces.version_number or 1) + 1
        document.previous_version_uuid = replaces.uuid
        # Claim the old version first: two concurrent uploads must not both
        # become "the" next version and fork the history.
        claimed = await SmartDocument.get_motor_collection().update_one(
            {"uuid": replaces.uuid, "superseded_by": None}, {"$set": {"superseded_by": uid}},
        )
        if claimed.modified_count != 1:
            try:
                await storage.delete(relative_path_str)
            except Exception:
                logger.exception("Could not remove unused version upload %s", relative_path_str)
            raise ValueError("A newer version of this file already exists. Upload to the latest version.")
    try:
        await document.insert()
    except BaseException as exc:
        if replaces is not None:
            # The new version was never stored; the old one is current again.
            await SmartDocument.get_motor_collection().update_one(
                {"uuid": replaces.uuid, "superseded_by": uid}, {"$set": {"superseded_by": None}},
            )
        if not isinstance(exc, DuplicateKeyError) or certification_provisioning_key is None:
            raise
        # Another request inserted the same active course source. Each upload
        # used a random storage path, so only this losing candidate is removed.
        existing = await SmartDocument.find_one(
            SmartDocument.certification_provisioning_key == certification_provisioning_key,
            SmartDocument.user_id == user_id, SmartDocument.folder == target_folder,
            SmartDocument.title == safe_name, SmartDocument.soft_deleted == False,  # noqa: E712
        )
        if existing is None or existing.path == relative_path_str:
            raise
        try:
            await storage.delete(relative_path_str)
        except Exception:
            logger.exception('Could not remove losing course sample upload %s', relative_path_str)
        return {"complete": True, "exists": True, "uuid": existing.uuid}

    # Only the inserted candidate needs a local task path and dispatch. An
    # interrupted/unknown dispatch still requires its own recovery protocol.
    local_path = storage.public_path(relative_path_str)
    if local_path is None:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}")
        tmp.write(file_data)
        tmp.close()
        local_path = tmp.name

    # Dispatch Celery tasks for extraction + validation
    from app.tasks.upload_tasks import dispatch_upload_tasks

    task_id = dispatch_upload_tasks(
        document_uuid=uid,
        extension=extension,
        document_path=local_path,
        user_id=user_id,
    )
    await record_extraction_dispatch(document, task_id)

    if replaces is not None:
        from app.services.page_sources import notify_source_revised

        await notify_source_revised(replaces, document)
        return {"complete": True, "uuid": uid, "document_id": str(document.id),
                "version_number": document.version_number, "replaces": replaces.uuid}
    return {"complete": True, "uuid": uid, "document_id": str(document.id)}


# Spreadsheet formats the viewer can render, and the reader for each. Parsing
# happens here rather than in the browser: these are untrusted uploads rendered
# in other people's sessions, and the client-side parser that used to handle
# .csv and .xls carried two unfixable HIGH CVEs (SheetJS left npm at 0.18.5,
# and prototype pollution on a crafted workbook is exactly this path).
SHEET_EXTENSIONS = ("xlsx", "xls", "csv")


async def render_xlsx_sheets(
    doc_uuid: str, settings: Settings, *, user: User
) -> dict | None:
    """Render a spreadsheet as per-sheet JSON for the document viewer.

    Handles .xlsx (evaluating formulas), .xls and .csv. Returns None when the
    document doesn't exist, isn't a spreadsheet, or the user lacks access.
    Returns None on parser failure too — caller can decide to surface a 404 in
    either case.
    """
    doc = await access_control.get_authorized_document(doc_uuid, user)
    if not doc:
        return None

    extension = (doc.extension or "").lower().lstrip(".")
    if extension not in SHEET_EXTENSIONS:
        return None

    from app.services.storage import get_storage

    storage = get_storage(settings)
    relative_path = doc.downloadpath or doc.path
    try:
        data = await storage.read(relative_path)
    except Exception:
        return None

    from app.services.document_readers import (
        DocumentReadError,
        extract_sheet_json_from_csv,
        extract_sheet_json_from_xls,
        extract_sheet_json_from_xlsx,
    )

    readers = {
        "xlsx": extract_sheet_json_from_xlsx,
        "xls": extract_sheet_json_from_xls,
        "csv": extract_sheet_json_from_csv,
    }

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}")
    try:
        tmp.write(data)
        tmp.close()
        return readers[extension](tmp.name)
    except DocumentReadError:
        # A refusal with a user-facing message (a binary named .csv): the
        # router turns it into a 4xx the viewer shows, not a bare 404.
        raise
    except Exception as e:
        logger.warning("sheet-json rendering failed for %s: %s", doc_uuid, e)
        return None
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass


async def download_document(
    doc_uuid: str, settings: Settings, *, user: User
) -> DownloadResult | None:
    doc = await access_control.get_authorized_document(doc_uuid, user)
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
    doc_uuid: str, settings: Settings, *, user: User
) -> bool:
    doc = await access_control.get_authorized_document(doc_uuid, user, manage=True)
    if not doc:
        return False

    # Delete the stored file (best-effort — don't block DB cleanup)
    relative_path = doc.downloadpath or doc.path
    if relative_path:
        from app.services.storage import get_storage

        storage = get_storage(settings)
        try:
            await storage.delete(relative_path)
        except Exception:
            logger.warning("Failed to delete file for document %s: %s", doc_uuid, relative_path)

    await doc.delete()
    # A deleted document's earlier text goes with it.
    from app.services import extraction_snapshots

    await extraction_snapshots.discard(doc.uuid)
    await _unlink_version(doc)
    await audit_service.log_event(
        action="document.delete",
        actor_user_id=user.user_id,
        resource_type="document",
        resource_id=doc.uuid,
        resource_name=doc.title,
        team_id=doc.team_id,
        detail={"folder": doc.folder},
    )
    return True


async def _unlink_version(doc: SmartDocument) -> None:
    """Close the gap a deleted version leaves in its file's history.

    Deleting the current version makes the previous one current again (it
    returns to the file list); deleting an older one links its neighbours.
    """
    if not (doc.previous_version_uuid or doc.superseded_by):
        return  # never revised: nothing to relink
    collection = SmartDocument.get_motor_collection()
    if doc.previous_version_uuid:
        await collection.update_one(
            {"uuid": doc.previous_version_uuid, "superseded_by": doc.uuid},
            {"$set": {"superseded_by": doc.superseded_by}},
        )
    if doc.superseded_by:
        await collection.update_one(
            {"uuid": doc.superseded_by, "previous_version_uuid": doc.uuid},
            {"$set": {"previous_version_uuid": doc.previous_version_uuid}},
        )


async def list_versions(doc: SmartDocument, user: User) -> list[dict]:
    """Every version of ``doc``'s file the caller can open, newest first."""
    root = doc.version_root or doc.uuid
    found = await SmartDocument.find(
        {"$or": [{"uuid": root}, {"version_root": root}], "soft_deleted": {"$ne": True}},
    ).to_list()
    team_access = await access_control.get_team_access_context(user)
    versions = []
    for item in sorted(found, key=lambda d: d.version_number or 1, reverse=True):
        if not await access_control.get_authorized_document(item.uuid, user, team_access=team_access):
            continue
        versions.append({
            "uuid": item.uuid, "title": item.title, "extension": item.extension,
            "version_number": item.version_number or 1,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "current": item.superseded_by is None,
            "processing": bool(item.processing),
        })
    return versions


async def rename_document(doc_uuid: str, new_title: str, *, user: User) -> bool:
    if not new_title.strip():
        raise ValueError("File name cannot be empty.")
    doc = await access_control.get_authorized_document(doc_uuid, user, manage=True)
    if not doc:
        return False
    if doc.title != new_title:
        doc.certification_provisioning_key = None
    doc.title = new_title
    if not doc.downloadpath:
        doc.downloadpath = doc.path
    await doc.save()
    return True


class DuplicateNotQueuedError(RuntimeError):
    """The copy's processing could not be queued, so the copy was taken back out."""


class _TitleOnly(BaseModel):
    title: Optional[str] = None


def _copy_title(title: str, n: int, extension: str | None = None) -> str:
    """``Report.pdf`` -> ``Report (Copy).pdf``, then ``Report (Copy 2).pdf``.

    The label goes before the suffix only when that suffix is the document's
    extension: a file renamed "Q3 Report v1.2" becomes "Q3 Report v1.2 (Copy)",
    not "Q3 Report v1 (Copy).2".
    """
    label = "(Copy)" if n == 1 else f"(Copy {n})"
    stem, dot, ext = title.rpartition(".")
    if dot and stem and extension and ext.lower() == extension.lower():
        return f"{stem} {label}.{ext}"
    return f"{title} {label}"


async def duplicate_document(doc_uuid: str, settings: Settings, *, user: User) -> dict | None:
    """Make an independent copy of a document in the same folder.

    The copy gets its own stored file (deleting either must not take the
    other's bytes) and carries the original's extracted text, so it is not
    read again; it then runs the steps an upload runs after reading (folder
    watch automations, search indexing). It starts a version history of its
    own and joins no knowledge base, and keeps the original's scheduled
    deletion and retention hold. Returns None when the caller cannot see the
    document; raises DuplicateNotQueuedError when its processing could not be
    queued (nothing is left behind).
    """
    doc = await access_control.get_authorized_document(doc_uuid, user)
    if not doc or doc.soft_deleted:
        return None

    from app.services.document_service import extraction_in_flight

    if extraction_in_flight(doc):
        raise ValueError("This file is still being read. Duplicate it once it's ready.")

    target_folder = doc.folder or "0"
    team_id = doc.team_id
    if target_folder != "0":
        folder = await access_control.get_authorized_folder(target_folder, user, contribute=True)
        if not folder:
            raise ValueError("You can't add files to this folder.")
        team_id = folder.team_id
    elif team_id and not await access_control.get_authorized_document(doc_uuid, user, manage=True):
        raise ValueError("You can't add files to this folder.")

    # The scope the upload duplicate-name check uses.
    scope: dict[str, object] = (
        {"team_id": team_id} if team_id else {"user_id": user.user_id, "team_id": None}
    )
    siblings = await SmartDocument.find({
        **scope,
        "folder": target_folder,
        "soft_deleted": {"$ne": True},
        "superseded_by": None,
    }).project(_TitleOnly).to_list()
    taken = {d.title for d in siblings}
    n = 1
    while _copy_title(doc.title, n, doc.extension) in taken:
        n += 1
    title = _copy_title(doc.title, n, doc.extension)

    from app.services.storage import get_storage

    storage = get_storage(settings)
    uid = uuid.uuid4().hex.upper()
    extension = doc.extension or "pdf"
    new_path = f"{user.user_id}/{uid}.{extension}"
    try:
        data = await storage.read(doc.downloadpath or doc.path)
    except Exception:
        logger.exception("Could not read stored file of %s to duplicate it", doc.uuid)
        raise ValueError("The stored file for this document could not be read, so it can't be copied.")
    await storage.write(new_path, data)

    # Only a successful reading is indexed. A failed one (even one that kept
    # some text) stays failed on the copy; Retry works on the copy's own file.
    failed = doc.task_status == "error"
    index = bool((doc.raw_text or "").strip()) and not failed
    copy = SmartDocument(
        title=title,
        path=new_path,
        downloadpath=new_path,
        extension=extension,
        uuid=uid,
        user_id=user.user_id,
        team_id=team_id,
        folder=target_folder,
        raw_text=doc.raw_text,
        text_markers=list(doc.text_markers or []),
        token_count=doc.token_count,
        num_pages=doc.num_pages,
        valid=doc.valid,
        validation_feedback=doc.validation_feedback,
        error_message=doc.error_message,
        error_retryable=doc.error_retryable,
        extraction_nonletter_ratio=doc.extraction_nonletter_ratio,
        text_layer_rejected=doc.text_layer_rejected,
        # The copy holds identical text, so it holds identical caveats.
        ingestion_warnings=list(doc.ingestion_warnings or []),
        unread_pages=list(doc.unread_pages or []),
        classification=doc.classification,
        classification_confidence=doc.classification_confidence,
        classified_at=doc.classified_at,
        classified_by=doc.classified_by,
        # A copy of a file Vandalizer wrote is still one.
        generated_by=doc.generated_by,
        # Retention: the copy must not outlive the original's scheduled
        # deletion, and a hold on the original holds the copy too.
        scheduled_deletion_at=doc.scheduled_deletion_at,
        retention_hold=bool(doc.retention_hold),
        retention_hold_reason=doc.retention_hold_reason,
        processing=False,
        # Reading is done: the copy is where an upload stands once its text
        # is in. Not an in-progress status, so the stuck-document sweep
        # leaves it alone while its steps are queued; indexing below moves it
        # through "readying" back to complete, as it does an upload.
        task_status="error" if failed else "complete",
        chromadb_ready=False,
        chunk_count=0,
    )
    try:
        await copy.insert()
    except BaseException:
        try:
            await storage.delete(new_path)
        except Exception:
            logger.exception("Could not remove unused duplicate file %s", new_path)
        raise

    if not failed:
        # The steps an upload runs once its text is in: update_document_fields
        # (which starts folder-watch automations, so a copy placed in a
        # watched folder counts as a new file there, as an upload does) and
        # then indexing, which also mirrors the copy into the project's
        # knowledge base when its folder belongs to one.
        from app.tasks.document_tasks import perform_semantic_ingestion, update_document_fields

        steps = update_document_fields.si(document_uuid=uid)
        if index:
            # The task reads the text from the copy; no need to queue it.
            steps = steps | perform_semantic_ingestion.si(
                raw_text="", document_uuid=uid, user_id=user.user_id,
            )
        try:
            steps.apply_async()
        except Exception:
            # Without its steps the copy would sit unindexed, and a retry
            # would make "(Copy 2)". Take it back out and say so.
            logger.exception("Could not queue processing for duplicate %s", uid)
            try:
                await copy.delete()
            except Exception:
                logger.exception("Could not remove unqueued duplicate %s", uid)
            try:
                await storage.delete(new_path)
            except Exception:
                logger.exception("Could not remove unused duplicate file %s", new_path)
            raise DuplicateNotQueuedError(
                "The copy could not be queued for processing, so it wasn't made. Try again in a moment."
            )

    return {"uuid": uid, "title": title}


async def move_document(file_uuid: str, folder_id: str, *, user: User) -> bool:
    doc = await access_control.get_authorized_document(file_uuid, user, manage=True)
    if not doc:
        return False

    target_team_id: str | None = None
    if folder_id != "0":
        folder = await access_control.get_authorized_folder(folder_id, user, contribute=True)
        if not folder:
            return False
        target_team_id = folder.team_id

    if doc.team_id != target_team_id:
        raise ValueError("Cannot move files between personal and team folders.")

    old_folder = doc.folder
    if old_folder != folder_id:
        doc.certification_provisioning_key = None
    doc.folder = folder_id
    await doc.save()

    # Re-sync the document's Project knowledge-base membership: moving a file into a
    # project's folder tree must index it into that project's implicit KB (so "chat
    # with this project" can see it instead of answering from the model's own
    # knowledge), and moving it out must drop it. Best-effort, async via Celery.
    if old_folder != folder_id:
        try:
            from app.tasks.document_tasks import sync_project_kb_on_move

            sync_project_kb_on_move.delay(doc.uuid, old_folder)
        except Exception:
            logger.warning(
                "Failed to dispatch project KB sync for moved document %s", doc.uuid
            )

    return True
