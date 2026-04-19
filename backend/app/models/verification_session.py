"""Verification session model.

A guided-verification session lets a user confirm or correct each
field value the LLM extracted from a document *before* those values are
locked in as an ExtractionTestCase. The session is the handoff state
between the chat agent (which proposes) and the document viewer (which
steps the user through approvals).
"""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document
from pydantic import BaseModel, Field


class VerificationField(BaseModel):
    """A single field under review."""

    key: str
    extracted: str
    expected: Optional[str] = None  # User-corrected value, if any
    status: str = "pending"  # "pending" | "approved" | "corrected" | "skipped"


class VerificationSession(Document):
    """A pending test-case verification handoff, created by the chat agent."""

    uuid: str = ""
    search_set_uuid: str
    document_uuid: str
    document_title: str = ""
    label: str = ""
    fields: list[VerificationField] = []
    status: str = "pending"  # "pending" | "completed" | "cancelled"
    test_case_uuid: Optional[str] = None  # Set when finalised
    user_id: str
    team_id: Optional[str] = None
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )

    class Settings:
        name = "verification_sessions"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex

    def all_resolved(self) -> bool:
        """True when every field has been approved, corrected, or skipped."""
        return all(f.status != "pending" for f in self.fields)
