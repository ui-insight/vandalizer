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
    title: str
    raw_text: str = ""
    extension: str = "pdf"
    uuid: str
    space: str
    user_id: str
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    folder: Optional[str] = None
    is_default: bool = False
    token_count: int = 0
    num_pages: int = 0

    # Data classification (FERPA, CUI, etc.)
    classification: Optional[str] = None  # unrestricted | internal | ferpa | cui | itar
    classification_confidence: Optional[float] = None
    classified_at: Optional[datetime.datetime] = None
    classified_by: Optional[str] = None  # "auto" or user_id

    # Data retention
    retention_hold: bool = False
    retention_hold_reason: Optional[str] = None
    scheduled_deletion_at: Optional[datetime.datetime] = None
    soft_deleted: bool = False
    soft_deleted_at: Optional[datetime.datetime] = None

    class Settings:
        name = "smart_document"
        indexes = [
            "uuid",
            "user_id",
            "space",
            [("user_id", 1), ("space", 1)],
            [("user_id", 1), ("folder", 1)],
            "created_at",
        ]
