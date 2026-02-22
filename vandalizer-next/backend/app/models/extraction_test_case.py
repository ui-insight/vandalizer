"""Extraction test case model for validation testing."""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document


class ExtractionTestCase(Document):
    """A test case for validating extraction accuracy and consistency."""

    uuid: str = ""
    search_set_uuid: str
    label: str
    source_type: str  # "text" | "document"
    source_text: Optional[str] = None
    document_uuid: Optional[str] = None
    expected_values: dict[str, str] = {}
    user_id: str
    created_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)

    class Settings:
        name = "extraction_test_cases"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
