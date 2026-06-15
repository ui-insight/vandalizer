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
    RETURNED = "returned"


class ValidationOrigin(str, Enum):
    VALIDATED_BY_SUBMITTER = "validated_by_submitter"
    PENDING_ADMIN_VALIDATION = "pending_admin_validation"
    UNVALIDATED_LEGACY = "unvalidated_legacy"


class VerificationRequest(Document):
    uuid: str = Field(default_factory=lambda: str(uuid_mod.uuid4()))
    item_kind: str  # "workflow", "search_set", or "knowledge_base"
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

    # Validation snapshot (attached at submission time)
    validation_snapshot: Optional[dict] = None
    validation_score: Optional[float] = None
    validation_tier: Optional[str] = None
    return_guidance: Optional[str] = None

    # Validation origin — how this submission carries validation data
    validation_origin: str = ValidationOrigin.VALIDATED_BY_SUBMITTER.value

    # Examiner-curated additions during review (Phase C)
    # Shape: {"test_cases": [...], "queries": [...], "regression_inputs": [...], "run_uuid": str | None, "run_score": float | None}
    examiner_baseline_additions: Optional[dict] = None

    # Claim-for-review lock (Phase C) — soft lock so two reviewers don't duplicate work
    claimed_by_user_id: Optional[str] = None
    claimed_at: Optional[datetime.datetime] = None

    # Reviewer info
    reviewer_user_id: Optional[str] = None
    reviewer_notes: Optional[str] = None

    # Timestamps
    submitted_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    reviewed_at: Optional[datetime.datetime] = None

    class Settings:
        name = "verification_request"
        indexes = [
            "uuid",
            "submitter_user_id",
            "status",
            "item_id",
            "validation_origin",
            "claimed_by_user_id",
        ]


class VerifiedItemMetadata(Document):
    item_kind: str
    item_id: str  # ObjectId as string
    display_name: Optional[str] = None
    description: Optional[str] = None
    markdown: Optional[str] = None
    organization_ids: list[str] = Field(default_factory=list)  # Org UUIDs for visibility scoping

    # Static creator credit ("by Jane Doe at University of Idaho"). Plain text,
    # not a user reference — it must survive catalog export/seeding to installs
    # where the original user account doesn't exist.
    credit_name: Optional[str] = None
    credit_org: Optional[str] = None

    # Quality fields (populated by quality_service)
    quality_score: Optional[float] = None
    quality_tier: Optional[str] = None
    quality_grade: Optional[str] = None
    last_validated_at: Optional[datetime.datetime] = None
    validation_run_count: int = 0

    # Official baseline frozen at approval (Phase A)
    # The pinned validation snapshot that travels with the catalog entry.
    # Drift monitoring re-runs against this; approve-time set; admins can refresh retroactively.
    official_baseline: Optional[dict] = None
    official_baseline_pinned_at: Optional[datetime.datetime] = None
    official_baseline_source_run_uuid: Optional[str] = None
    official_baseline_score: Optional[float] = None
    official_baseline_pinned_by_user_id: Optional[str] = None
    official_baseline_history: list[dict] = Field(default_factory=list)
    # Last drift check (Phase E)
    last_drift_check_at: Optional[datetime.datetime] = None
    last_drift_score: Optional[float] = None  # the score the live config achieved on the pinned baseline

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
    featured: bool = False
    item_ids: list[str] = Field(default_factory=list)  # list of LibraryItem IDs
    created_by_user_id: str
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "verified_collection"
