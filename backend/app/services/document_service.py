from app.config import Settings
from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.user import User
from app.services import access_control


#: Human-readable text for each stored ingestion-warning code. Kept beside the
#: predicate rather than in the router so chat, the file list, and the
#: extraction path all say the same thing about the same document.
INGESTION_WARNING_LABELS = {
    "partial_ocr": "only part of this document could be converted",
    "sparse_text": "far less text than its page count suggests",
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
    labels = [INGESTION_WARNING_LABELS[c] for c in ingestion_warnings(doc)]
    return "; ".join(labels)


#: Warning codes that mean "the stored text is real but incomplete/degraded".
#: hidden_text_unchecked is deliberately NOT here: that document's text may
#: contain EXTRA unvetted content, the inverse risk — telling the user content
#: may be missing (and to retry extraction for "the full text") would assert
#: the opposite of what happened.
COMPLETENESS_WARNING_CODES = frozenset({"partial_ocr", "sparse_text", "low_quality_text"})


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

    if folder_id != "0":
        current_folder = await access_control.get_authorized_folder(
            folder_id, user, team_access=team_access
        )
        if not current_folder:
            return {"folders": [], "documents": []}

        if current_folder.team_id:
            folders = await SmartFolder.find(
                SmartFolder.parent_id == current_folder.uuid,
                SmartFolder.team_id == current_folder.team_id,
            ).to_list()
            documents = await SmartDocument.find(
                {
                    "folder": current_folder.uuid,
                    "team_id": current_folder.team_id,
                    "soft_deleted": {"$ne": True},
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
            }
        ).to_list()

    return {
        "folders": [
            {
                "id": str(f.id),
                "title": f.title,
                "uuid": f.uuid,
                "parent_id": f.parent_id,
                "is_shared_team_root": f.is_shared_team_root,
                "team_id": f.team_id,
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
                "token_count": d.token_count,
                "num_pages": d.num_pages,
                "classification": d.classification,
                "classification_confidence": d.classification_confidence,
                "classified_at": d.classified_at.isoformat() if d.classified_at else None,
                "classified_by": d.classified_by,
                "retention_hold": d.retention_hold,
                "soft_deleted": d.soft_deleted,
                "chromadb_ready": d.chromadb_ready,
                "chunk_count": d.chunk_count,
                "ingest_error": d.ingest_error,
                "error_message": d.error_message,
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
            current = queue.pop()
            for child in children_by_parent.get(current, []):
                if child not in seen:
                    seen.add(child)
                    folder_uuids.append(child)
                    queue.append(child)

    scope = (
        {"team_id": root.team_id}
        if root.team_id
        else {"user_id": user.user_id}
    )
    documents = await SmartDocument.find(
        {
            "folder": {"$in": folder_uuids},
            "soft_deleted": {"$ne": True},
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
        "processing": doc.processing,
        "title": doc.title,
        "extraction_low_quality": is_extraction_low_quality(doc),
        "ingestion_warnings": ingestion_warnings(doc),
        "ingestion_warning_text": ingestion_warning_text(doc),
    }
