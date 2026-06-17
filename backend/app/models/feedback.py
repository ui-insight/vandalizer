"""Extraction quality feedback model."""

import datetime
from typing import Optional

from beanie import Document
from pydantic import Field


class ChatFeedback(Document):
    conversation_uuid: Optional[str] = None
    message_index: Optional[int] = None
    rating: str = "up"  # "up" or "down"
    comment: Optional[str] = None
    user_id: Optional[str] = None
    # KB the rated message answered from (when known — supplied by the chat
    # surface when the message used RAG). Phase 5 of the loop-closure plan:
    # an elevated thumbs-down rate per KB auto-enqueues a shadow KB
    # autovalidate run so the feedback signal becomes input to the optimizer
    # instead of dying in this collection.
    kb_uuid: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)

    class Settings:
        name = "chat_feedback"
        indexes = [
            "conversation_uuid",
            "kb_uuid",
            [("kb_uuid", 1), ("created_at", -1)],
        ]


class ExtractionQualityRecord(Document):
    pdf_title: str
    star_rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None
    result_json: Optional[str] = None
    user_id: Optional[str] = None
    search_set_uuid: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)

    class Settings:
        name = "extraction_quality_record"
