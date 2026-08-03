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


class ProductFeedback(Document):
    """Free-form, non-negative product feedback that isn't tied to a single
    chat message or extraction — a user telling us what's working, or an idea.

    Negatives deliberately stay on the support-ticket rails (they need triage,
    assignment, and a status that can close). This collection is the home for
    positive/idea signal so it stops dying write-only: the "What's Working"
    admin surface reads it alongside thumbs-up chat feedback and high extraction
    star ratings.
    """

    # "positive" = something worked well; "idea" = a suggestion offered warmly,
    # not a defect report. No "negative" — that path creates a support ticket.
    sentiment: str = "positive"
    message: str
    # Where it was captured, so the admin feed can group by surface and we can
    # add new capture points without schema churn (e.g. "support_panel").
    source: str = "support_panel"
    # Optional feature attribution when the surface knows it (e.g. "chat",
    # "extraction"). Free-form on purpose — capture points vary.
    feature: Optional[str] = None
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)

    class Settings:
        name = "product_feedback"
        indexes = [
            "sentiment",
            [("created_at", -1)],
        ]
