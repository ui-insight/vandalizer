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

    class Settings:
        name = "smart_document"
