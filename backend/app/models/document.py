import datetime
from typing import Optional

from pydantic import Field
from beanie import Document


class SmartDocument(Document):
    path: str
    downloadpath: str
    processing: bool = False
    validating: bool = False
    valid: bool = True
    validation_feedback: Optional[str] = None
    task_id: Optional[str] = None
    task_status: Optional[str] = None
    error_message: Optional[str] = None
    title: str
    raw_text: str = ""
    extension: str = "pdf"
    uuid: str
    user_id: str
    team_id: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    folder: Optional[str] = None
    is_default: bool = False
    token_count: int = 0
    num_pages: int = 0

    # Retrieval readiness — set by perform_semantic_ingestion. A document is
    # only safe to use via Knowledge Base retrieval once chromadb_ready is True.
    chromadb_ready: bool = False
    chunk_count: int = 0
    ingest_error: Optional[str] = None

    # Extraction quality — set by perform_extraction_and_update. Fraction of
    # non-whitespace chars in raw_text that are neither alphanumeric nor common
    # punctuation; a garbled (e.g. CID-mangled) text layer measures far above
    # Settings.extraction_max_nonletter_ratio while clean extractions are ~0.
    # None = not measured (legacy docs, or docs whose text bypassed extraction).
    extraction_nonletter_ratio: Optional[float] = None

    # Ingestion warnings — machine-readable codes for the ways an extraction can
    # succeed and still not be the whole document. Emptiness and garbling are
    # already covered (task_status="error" and the ratio above); these are the
    # partial outcomes that used to be a log line only:
    #   "partial_ocr"  — the converter reported per-document errors and returned
    #                    what it managed. Real text, not all of it.
    #   "sparse_text"  — far too few characters for the PDF's page count. A
    #                    400-page scan yielding 150 characters clears the
    #                    whole-document minimum and is still a failure.
    # None/[] = measured and clean, or never measured (legacy documents).
    ingestion_warnings: list[str] = []

    # Per-location char-offset markers from text extraction, used to attach
    # page (PDF) or sheet (XLSX) metadata to chunks for citations. Empty for
    # formats with no location structure (docx, txt, html, code).
    # Shape: [{"char_offset": int, "kind": "page"|"sheet", "value": int|str}]
    text_markers: list[dict] = []

    # Data classification (FERPA, CUI, etc.)
    classification: Optional[str] = None  # unrestricted | internal | ferpa | cui | itar
    classification_confidence: Optional[float] = None
    classified_at: Optional[datetime.datetime] = None
    classified_by: Optional[str] = None  # "auto" or user_id

    # Onboarding
    is_onboarding_sample: bool = False

    # Data retention
    retention_hold: bool = False
    retention_hold_reason: Optional[str] = None
    scheduled_deletion_at: Optional[datetime.datetime] = None
    soft_deleted: bool = False
    soft_deleted_at: Optional[datetime.datetime] = None

    # Provenance for documents created by a workflow's "save output" config.
    # Used to skip own-origin docs when re-running the same workflow.
    origin_workflow_id: Optional[str] = None
    origin_workflow_run_id: Optional[str] = None
    origin_run_at: Optional[datetime.datetime] = None

    class Settings:
        name = "smart_document"
        indexes = [
            "uuid",
            "user_id",
            "team_id",
            [("user_id", 1), ("folder", 1)],
            [("team_id", 1), ("folder", 1)],
            "created_at",
            "origin_workflow_id",
        ]
