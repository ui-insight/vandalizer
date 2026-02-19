"""Extraction quality feedback model."""

import datetime
from typing import Optional

from beanie import Document
from pydantic import Field


class ExtractionQualityRecord(Document):
    pdf_title: str
    star_rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None
    result_json: Optional[str] = None
    user_id: Optional[str] = None
    search_set_uuid: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)

    class Settings:
        name = "extraction_quality_records"
