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
    submitter_org: Optional[str] = None
    submitter_role: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None

    # Extended submission fields
    item_version_hash: Optional[str] = None
    run_instructions: Optional[str] = None
    evaluation_notes: Optional[str] = None
    known_limitations: Optional[str] = None
    example_inputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    intended_use_tags: list[str] = Field(default_factory=list)
    test_files: list[dict] = Field(default_factory=list)  # [{original_name, stored_name, path}]

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


class VerifiedItemMetadata(Document):
    item_kind: str
    item_id: str  # ObjectId as string
    display_name: Optional[str] = None
    description: Optional[str] = None
    markdown: Optional[str] = None
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_by_user_id: Optional[str] = None

    class Settings:
        name = "verified_item_metadata"


class VerifiedCollection(Document):
    title: str
    description: Optional[str] = None
    promo_image_url: Optional[str] = None
    item_ids: list[str] = Field(default_factory=list)  # list of LibraryItem IDs
    created_by_user_id: str
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "verified_collections"
