import asyncio
import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.config import Settings
from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.user import User
from app.services import access_control
from app.services.extraction_restarts import claim_extraction_restart


#: Human-readable text for each stored ingestion-warning code. Kept beside the
#: predicate rather than in the router so chat, the file list, and the
#: extraction path all say the same thing about the same document.
INGESTION_WARNING_LABELS = {
    "partial_ocr": "only part of this document could be converted",
    "sparse_text": "far less text than its page count suggests",
    # A page showing content — typically an image of a page with no text
    # layer — that no reader got text from, so it is missing from the text.
    "unread_pages": "some pages could not be read and are missing from its text",
    # Emitted by the extraction path from `is_extraction_low_quality`, which
    # reads the stored nonletter ratio rather than these codes. Without an
    # entry here `ingestion_warnings()` filtered it straight back out, so the
    # extraction run reported a warning code that rendered as nothing.
    "low_quality_text": "most of the stored text is unreadable",
    # Emitted by the extraction path when a document contributed nothing to a
    # run (no stored text and no loadable file) — never stored on the
    # document itself, but registered here so the renderer that maps codes to
    # words (#803) can't repeat the low_quality_text story above.
    "no_extractable_text": "this document could not be read and contributed nothing to the run",
    # The pdf_hidden_text scrub could not inspect the file, so text the page
    # never displays may have reached the stored content unfiltered.
    "hidden_text_unchecked": "the hidden-text safety check could not run on this document",
}


def ingestion_warnings(doc: SmartDocument) -> list[str]:
    """Stored warning codes for a document, ignoring any we no longer emit."""
    return [
        code for code in (getattr(doc, "ingestion_warnings", None) or [])
        if code in INGESTION_WARNING_LABELS
    ]


def warning_text_for_codes(codes: list[str]) -> str:
    """The warnings as one readable clause, from codes alone.

    Same registry as ``ingestion_warning_text``, for callers holding codes
    rather than a document (extraction runs record per-document warnings
    that never live on the document itself).
    """
    labels = [INGESTION_WARNING_LABELS[c] for c in codes if c in INGESTION_WARNING_LABELS]
    return "; ".join(labels)


def ingestion_warning_text(doc: SmartDocument) -> str:
    """The warnings as one readable clause, or "" when there are none."""
    labels = []
    for code in ingestion_warnings(doc):
        pages = getattr(doc, "unread_pages", None) or []
        if code == "unread_pages" and pages:
            # Name the pages: "which page?" is the user's next question, and
            # the viewer shows them all.
            listed = ", ".join(str(p) for p in pages[:10]) + (", …" if len(pages) > 10 else "")
            if len(pages) == 1:
                labels.append(f"page {listed} could not be read and is missing from its text")
            else:
                labels.append(f"pages {listed} could not be read and are missing from its text")
        else:
            labels.append(INGESTION_WARNING_LABELS[code])
    return "; ".join(labels)


#: Warning codes that mean "the stored text is real but incomplete/degraded".
#: hidden_text_unchecked is deliberately NOT here: that document's text may
#: contain EXTRA unvetted content, the inverse risk — telling the user content
#: may be missing (and to retry extraction for "the full text") would assert
#: the opposite of what happened.
COMPLETENESS_WARNING_CODES = frozenset({"partial_ocr", "sparse_text", "low_quality_text", "unread_pages"})


def is_partially_ingested(doc: SmartDocument) -> bool:
    """True when the stored text is real but is not the whole document."""
    return any(c in COMPLETENESS_WARNING_CODES for c in ingestion_warnings(doc))


def has_unchecked_hidden_text(doc: SmartDocument) -> bool:
    """True when the hidden-text scrub could not inspect this document."""
    return "hidden_text_unchecked" in ingestion_warnings(doc)


def is_extraction_low_quality(doc: SmartDocument) -> bool:
    """True when the document's stored text is a garbled extraction (non-letter
    ratio above the configured threshold). Documents never measured (legacy, or
    text that bypassed extraction) are not flagged."""
    ratio = doc.extraction_nonletter_ratio
    if ratio is None:
        return False
    return ratio > Settings().extraction_max_nonletter_ratio


class _ChildDocument(BaseModel):
    """Just enough of a document to count it and date its folder; the list
    must not pull every child's ``raw_text`` to say "12 items"."""

    folder: Optional[str] = None
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None


class _ChildFolder(BaseModel):
    id: Any = Field(default=None, alias="_id")
    parent_id: Optional[str] = None
    user_id: Optional[str] = None
    team_id: Optional[str] = None


def _created_at(object_id: Any) -> datetime.datetime | None:
    """A folder stores no dates; its ObjectId carries when it was created.

    Returned naive in server-local time, the convention ``SmartDocument``'s
    ``datetime.now()`` timestamps already use, so the two compare and render
    alike.
    """
    generated = getattr(object_id, "generation_time", None)
    if not isinstance(generated, datetime.datetime):
        return None
    return generated.astimezone().replace(tzinfo=None)


async def _folder_summaries(
    folders: list[SmartFolder], user: User, *, in_project: bool
) -> dict[str, dict]:
    """Item count and last-modified date for each listed folder.

    Both are derived at read time. The count is the folder's direct contents
    as this viewer would see them on opening it (same owner/team rule as the
    listing itself). "Modified" is the newest of: the folder's creation, a
    file in it being added or changed, a subfolder being created in it.
    """
    if not folders:
        return {}
    uuids = [f.uuid for f in folders]
    # A project root's contents belong to several people; so does everything
    # under a project. Those are not narrowed to the viewer's own items.
    shared = set(uuids) if in_project else await access_control.project_root_folder_uuids(uuids)
    by_uuid = {f.uuid: f for f in folders}

    def visible(parent_uuid: str | None, item: Any) -> bool:
        parent = by_uuid.get(parent_uuid or "")
        if parent is None:
            return False
        if parent.uuid in shared:
            return True
        if parent.team_id:
            return bool(item.team_id == parent.team_id)
        return bool(item.user_id == user.user_id)

    child_documents = await SmartDocument.find(
        {"folder": {"$in": uuids}, "soft_deleted": {"$ne": True}, "superseded_by": None},
        projection_model=_ChildDocument,
    ).to_list()
    child_folders = await SmartFolder.find(
        {"parent_id": {"$in": uuids}}, projection_model=_ChildFolder
    ).to_list()

    counts = {u: 0 for u in uuids}
    latest: dict[str, datetime.datetime | None] = {f.uuid: _created_at(f.id) for f in folders}

    def note(parent_uuid: str, when: Any) -> None:
        counts[parent_uuid] += 1
        if isinstance(when, datetime.datetime):
            if when.tzinfo is not None:
                when = when.astimezone().replace(tzinfo=None)
            current = latest.get(parent_uuid)
            if current is None or when > current:
                latest[parent_uuid] = when

    for d in child_documents:
        if d.folder and visible(d.folder, d):
            note(d.folder, d.updated_at)
    for child in child_folders:
        if child.parent_id and visible(child.parent_id, child):
            note(child.parent_id, _created_at(child.id))

    summaries: dict[str, dict] = {}
    for u in uuids:
        modified = latest.get(u)
        summaries[u] = {"item_count": counts[u], "updated_at": modified.isoformat() if modified else ""}
    return summaries


def _stored_sizes(documents: list[SmartDocument]) -> dict[str, int]:
    """Size on disk of each listed file, keyed by uuid. Files that are not
    there (or sit outside the upload root) are simply absent."""
    root = Path(Settings().upload_dir).resolve()
    sizes: dict[str, int] = {}
    for d in documents:
        try:
            target = (root / d.path).resolve()
            if target.is_relative_to(root) and target.is_file():
                sizes[d.uuid] = target.stat().st_size
        except (OSError, TypeError, ValueError):
            continue
    return sizes


async def list_contents(
    *,
    user: User,
    folder: str | None = None,
    team_uuid: str | None = None,
) -> dict:
    folder_id = folder or "0"
    team_access = await access_control.get_team_access_context(user)

    folders: list[SmartFolder] = []
    documents: list[SmartDocument] = []
    in_project = False

    if folder_id != "0":
        current_folder = await access_control.get_authorized_folder(
            folder_id, user, team_access=team_access
        )
        if not current_folder:
            return {"folders": [], "documents": []}

        project = await access_control.find_folder_project(current_folder.uuid)
        if project:
            in_project = True
            candidate_folders = await SmartFolder.find({"parent_id": current_folder.uuid}).to_list()
            folders = [f for f in candidate_folders if await access_control.get_authorized_folder(f.uuid, user, team_access=team_access)]
            candidate_documents = await SmartDocument.find({"folder": current_folder.uuid, "soft_deleted": {"$ne": True}, "superseded_by": None}).to_list()
            documents = [d for d in candidate_documents if await access_control.get_authorized_document(d.uuid, user, team_access=team_access)]
        elif current_folder.team_id:
            folders = await SmartFolder.find(
                SmartFolder.parent_id == current_folder.uuid,
                SmartFolder.team_id == current_folder.team_id,
            ).to_list()
            documents = await SmartDocument.find(
                {
                    "folder": current_folder.uuid,
                    "team_id": current_folder.team_id,
                    "soft_deleted": {"$ne": True},
                    "superseded_by": None,
                }
            ).to_list()
        else:
            folders = await SmartFolder.find(
                SmartFolder.parent_id == current_folder.uuid,
                SmartFolder.user_id == user.user_id,
            ).to_list()
            documents = await SmartDocument.find(
                {
                    "folder": current_folder.uuid,
                    "user_id": user.user_id,
                    "soft_deleted": {"$ne": True},
                    "superseded_by": None,
                }
            ).to_list()
    else:
        folders = await SmartFolder.find(
            SmartFolder.parent_id == "0",
            SmartFolder.user_id == user.user_id,
        ).to_list()
        if team_uuid and (team_uuid in team_access.team_uuids or user.is_admin):
            team_folders = await SmartFolder.find(
                SmartFolder.parent_id == "0",
                SmartFolder.team_id == team_uuid,
            ).to_list()
            existing_uuids = {f.uuid for f in folders}
            for folder_doc in team_folders:
                if folder_doc.uuid not in existing_uuids:
                    folders.append(folder_doc)

        documents = await SmartDocument.find(
            {
                "folder": "0",
                "user_id": user.user_id,
                "soft_deleted": {"$ne": True},
                "superseded_by": None,
            }
        ).to_list()

    summaries = await _folder_summaries(folders, user, in_project=in_project)
    sizes = await asyncio.to_thread(_stored_sizes, documents)

    return {
        "folders": [
            {
                "id": str(f.id),
                "title": f.title,
                "uuid": f.uuid,
                "parent_id": f.parent_id,
                "is_shared_team_root": f.is_shared_team_root,
                "team_id": f.team_id,
                **summaries.get(f.uuid, {"item_count": 0, "updated_at": ""}),
            }
            for f in folders
        ],
        "documents": [
            {
                "id": str(d.id),
                "title": d.title,
                "uuid": d.uuid,
                "extension": d.extension,
                "processing": d.processing,
                "valid": d.valid,
                "validation_feedback": d.validation_feedback,
                "task_status": d.task_status,
                "folder": d.folder,
                "created_at": d.created_at.isoformat() if d.created_at else "",
                "updated_at": d.updated_at.isoformat() if d.updated_at else "",
                # None when the stored file is not on disk (nothing to measure).
                "size_bytes": sizes.get(d.uuid),
                "token_count": d.token_count,
                "num_pages": d.num_pages,
                "classification": d.classification,
                "classification_confidence": d.classification_confidence,
                "classified_at": d.classified_at.isoformat() if d.classified_at else None,
                "classified_by": d.classified_by,
                "retention_hold": d.retention_hold,
                "soft_deleted": d.soft_deleted,
                "version_number": d.version_number,
                "chromadb_ready": d.chromadb_ready,
                "chunk_count": d.chunk_count,
                "ingest_error": d.ingest_error,
                "error_message": d.error_message,
                "error_retryable": d.error_retryable,
                "extraction_low_quality": is_extraction_low_quality(d),
                "ingestion_warnings": ingestion_warnings(d),
                # The list endpoint is what feeds the file browser; serving
                # only codes here left the caveat icon dark on the exact
                # screen #803 is about.
                "ingestion_warning_text": ingestion_warning_text(d),
            }
            for d in documents
        ],
    }

async def collect_folder_document_uuids(
    *,
    folder_uuid: str,
    user: User,
    include_subfolders: bool = True,
) -> list[str] | None:
    """Return the uuids of every (non-deleted) SmartDocument inside a folder.

    Walks subfolders when ``include_subfolders`` is set. Returns ``None`` if the
    folder is missing or the user can't access it. The returned uuids are still
    re-authorized individually by the caller (e.g. ``add_documents``).
    """
    team_access = await access_control.get_team_access_context(user)
    root = await access_control.get_authorized_folder(
        folder_uuid, user, team_access=team_access
    )
    if not root:
        return None

    project = await access_control.find_folder_project(root.uuid)
    if project:
        # Project collaborators may contribute files under different user IDs;
        # traverse the authorized subtree rather than the current user's files.
        folder_uuids = [root.uuid]
        frontier = [root.uuid] if include_subfolders else []
        seen = {root.uuid}
        while frontier:
            children = await SmartFolder.find({"parent_id": {"$in": frontier}}).to_list()
            frontier = []
            for child in children:
                if child.uuid not in seen and await access_control.get_authorized_folder(child.uuid, user, team_access=team_access):
                    seen.add(child.uuid)
                    folder_uuids.append(child.uuid)
                    frontier.append(child.uuid)
        documents = await SmartDocument.find({"folder": {"$in": folder_uuids}, "soft_deleted": {"$ne": True}, "superseded_by": None}).to_list()
        return [d.uuid for d in documents if await access_control.get_authorized_document(d.uuid, user, team_access=team_access)]

    # Resolve the set of folder uuids to scan (root + descendants).
    folder_uuids = [root.uuid]
    if include_subfolders:
        if root.team_id:
            all_folders = await SmartFolder.find(
                SmartFolder.team_id == root.team_id
            ).to_list()
        else:
            all_folders = await SmartFolder.find(
                SmartFolder.user_id == user.user_id
            ).to_list()
        children_by_parent: dict[str, list[str]] = {}
        for f in all_folders:
            children_by_parent.setdefault(f.parent_id, []).append(f.uuid)
        queue = [root.uuid]
        seen = {root.uuid}
        while queue:
            pending_folder_uuid = queue.pop()
            for descendant_uuid in children_by_parent.get(pending_folder_uuid, []):
                if descendant_uuid not in seen:
                    seen.add(descendant_uuid)
                    folder_uuids.append(descendant_uuid)
                    queue.append(descendant_uuid)

    scope = (
        {"team_id": root.team_id}
        if root.team_id
        else {"user_id": user.user_id}
    )
    documents = await SmartDocument.find(
        {
            "folder": {"$in": folder_uuids},
            "soft_deleted": {"$ne": True},
            # A revised file's older versions stay in its version history only.
            "superseded_by": None,
            **scope,
        }
    ).to_list()
    return [d.uuid for d in documents]


async def poll_status(doc_uuid: str, user: User) -> dict | None:
    doc = await access_control.get_authorized_document(doc_uuid, user)
    if not doc:
        return None

    status_messages = []
    if doc.task_status == "readying":
        status_messages.append("Getting ready...")
        if doc.valid:
            status_messages.append("Document passed validation checks...")
        else:
            status_messages.append("Document failed validation checks...")

    complete = doc.task_status in ("complete", "error")

    return {
        "status": doc.task_status,
        "status_messages": status_messages,
        "complete": complete,
        "raw_text": doc.raw_text if not doc.processing else "",
        "validation_feedback": doc.validation_feedback,
        "valid": doc.valid,
        "path": doc.path,
        "error_message": doc.error_message,
        "error_retryable": doc.error_retryable,
        "processing": doc.processing,
        "extension": (doc.extension or "").lower().lstrip(".") or None,
        "title": doc.title,
        "extraction_low_quality": is_extraction_low_quality(doc),
        "ingestion_warnings": ingestion_warnings(doc),
        "ingestion_warning_text": ingestion_warning_text(doc),
    }


def extraction_in_flight(doc: SmartDocument) -> bool:
    """An extraction holds the document (it may still be stale; callers that
    can replace a dead one check ``extraction_is_stale`` as well)."""
    # Lazy: the tasks module pulls in Celery and the sync DB.
    from app.tasks.document_tasks import _IN_PROGRESS_TASK_STATUSES

    return bool(doc.processing) or doc.task_status in _IN_PROGRESS_TASK_STATUSES


EXTRACTION_STOPPED_MESSAGE = (
    "Text extraction was stopped. Retry to read this document again."
)


async def cancel_extraction(doc: SmartDocument) -> bool:
    """Stop a document's in-flight extraction so it can be restarted.

    Flips the document to a retryable error first, then revokes the worker.
    The DB write is the source of truth: clearing ``task_id`` is what makes
    the extraction task drop its result if the revoke does not reach it (a
    pool that cannot terminate, a worker mid-write), since every write that
    task makes is filtered on its own task id. Callers check authorization.

    Returns False when nothing was in flight by the time the write landed.
    """
    import logging

    # Lazy: the tasks module and the Celery app pull in the worker stack.
    from app.celery_app import celery_app
    from app.tasks.document_tasks import _IN_PROGRESS_TASK_STATUSES

    task_id = doc.task_id
    result = await SmartDocument.get_motor_collection().update_one(
        {
            "_id": doc.id,
            "$or": [
                {"processing": True},
                {"task_status": {"$in": _IN_PROGRESS_TASK_STATUSES}},
            ],
        },
        {"$set": {
            "processing": False,
            "task_status": "error",
            "task_id": None,
            "error_message": EXTRACTION_STOPPED_MESSAGE,
            "error_retryable": True,
        },
         # Like a restart: the stopped run's later steps (update, ingestion,
         # cleanup) are filtered on the revision and now match nothing.
         "$inc": {"_extraction_restart_revision": 1}},
    )
    if not result.matched_count:
        return False

    # SIGTERM the prefork child reading it; a task still queued (or waiting
    # out an OCR retry backoff under the same id) is dropped when it arrives.
    if task_id:
        try:
            celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
        except Exception:
            logging.getLogger(__name__).warning(
                "Failed to revoke extraction task %s for document %s",
                task_id, doc.uuid, exc_info=True,
            )
    return True


async def restart_extraction(
    doc: SmartDocument, user_id: str, *, request_ocr: bool = False,
) -> dict:
    """Clear a document's extracted text and re-dispatch the upload chain.

    Shared by the document's Retry extraction and a knowledge-base source's
    Reprocess, so both re-read a page the same way. Callers check
    ``extraction_in_flight`` and authorization first.

    A retry re-reads the pages with OCR when the previous extraction failed or
    produced unreadable text; a healthy document is re-read the ordinary way,
    unless ``request_ocr`` asks for OCR explicitly (the "Re-run OCR" action).
    Returns the dispatched task id and the OCR decisions, for the audit log.
    """
    import datetime as _datetime

    from app.tasks.upload_tasks import dispatch_upload_tasks

    # Both reads must happen before the field resets below wipe the evidence
    # they are based on.
    previous_task_status = doc.task_status
    low_quality = is_extraction_low_quality(doc)
    # Two reasons to re-read with OCR, and they are not interchangeable. An
    # errored document usually has no stored text — every in-task error write
    # clears it — so if OCR is down the reader may still fall back to a local
    # reading, which is strictly more than it has. A low-quality document's
    # local reading is exactly what is being replaced, so it may not be
    # re-stored: ocr_required makes the reader raise instead, and the
    # extraction task retries it with backoff. Two errored documents fall on
    # the second side: one moved to error by the cleanup task or the stuck-
    # document reaper still holds its text and its ratio, and one whose layer
    # was already refused carries text_layer_rejected — the ratio that proved
    # it is cleared by this very dispatch, so the refusal is what survives to
    # the next click.
    #
    # Both flags are PDF-only: the extraction task forwards them to the PDF
    # reader and to nothing else, so setting them for a DOCX or a spreadsheet
    # would only record a requirement in the audit log that was never applied.
    is_pdf = (doc.extension or "").lower().lstrip(".") == "pdf"
    # Pages no reader got text from are exactly what a retry is for: without
    # OCR first it would take the same local reading and miss them again.
    missed_pages = "unread_pages" in (doc.ingestion_warnings or [])
    force_ocr = is_pdf and (
        request_ocr or doc.task_status == "error" or low_quality or missed_pages
    )
    ocr_required = is_pdf and (low_quality or doc.text_layer_rejected)
    await claim_extraction_restart(doc, {
        'task_status': 'extracting', 'processing': True,
        'validating': True, '_validation_heartbeat_at': _datetime.datetime.now(),
        # Takes ownership from any earlier run still going: its writes are
        # filtered on its own task id (and on this claim's new revision).
        'task_id': None,
        'updated_at': _datetime.datetime.now(), 'error_message': None,
        'error_retryable': None,
        'raw_text': '', 'token_count': 0, 'text_markers': [],
        'extraction_nonletter_ratio': None, 'ingestion_warnings': [],
        **({'text_layer_rejected': True} if ocr_required else {}),
    })

    task_id = dispatch_upload_tasks(
        document_uuid=doc.uuid,
        extension=doc.extension or "",
        document_path=doc.path,
        user_id=user_id,
        force_ocr=force_ocr,
        ocr_required=ocr_required,
        extraction_revision=doc._extraction_restart_revision,
    )
    return {
        "task_id": task_id,
        "force_ocr": force_ocr,
        "ocr_required": ocr_required,
        "previous_task_status": previous_task_status,
    }
