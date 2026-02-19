"""Verification request model for library items."""

import datetime
import uuid as uuid_mod
from enum import Enum
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


class VerificationStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class VerificationRequest(Document):
    uuid: str = Field(default_factory=lambda: str(uuid_mod.uuid4()))
    item_kind: str  # "workflow" or "search_set"
    item_id: PydanticObjectId
    status: str = VerificationStatus.SUBMITTED.value

    # Submitter info
    submitter_user_id: str
    submitter_name: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None

    # Reviewer info
    reviewer_user_id: Optional[str] = None
    reviewer_notes: Optional[str] = None

    # Timestamps
    submitted_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    reviewed_at: Optional[datetime.datetime] = None

    class Settings:
        name = "verification_requests"
