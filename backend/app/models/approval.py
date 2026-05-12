"""Approval request model for workflow review gates."""

import datetime
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


# Status values
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_EXPIRED = "expired"
STATUS_ESCALATED = "escalated"

# Assignee role values — how the workflow author specifies who reviews
ASSIGNEE_SPECIFIC_USERS = "specific_users"
ASSIGNEE_WORKFLOW_OWNER = "workflow_owner"
ASSIGNEE_TEAM_ADMINS = "team_admins"

# Timeout actions
TIMEOUT_NONE = "none"
TIMEOUT_APPROVE = "approve"
TIMEOUT_REJECT = "reject"
TIMEOUT_ESCALATE = "escalate"

# Artifact kinds — drive the review-screen renderer
ARTIFACT_UNKNOWN = "unknown"
ARTIFACT_TEXT = "text"
ARTIFACT_MARKDOWN = "markdown"
ARTIFACT_JSON = "json"
ARTIFACT_EXTRACTION_TABLE = "extraction_table"
ARTIFACT_DOCUMENT_RENDER = "document_render"


class ApprovalRequest(Document):
    """Represents a pending human review within a workflow execution."""

    uuid: str
    workflow_result_id: PydanticObjectId
    workflow_id: PydanticObjectId
    step_index: int  # where in the DAG we paused
    step_name: str

    # Context for the reviewer
    workflow_name: str = ""
    requester_user_id: Optional[str] = None
    team_id: Optional[str] = None
    source_doc_uuids: list[str] = []

    # The artifact under review
    artifact_kind: str = ARTIFACT_UNKNOWN
    data_for_review: dict = {}
    edited_artifact: Optional[dict] = None
    review_instructions: str = ""

    # Assignment
    assignee_role: str = ASSIGNEE_SPECIFIC_USERS
    assigned_to_user_ids: list[str] = []

    # Timeout / escalation
    expires_at: Optional[datetime.datetime] = None
    timeout_action: str = TIMEOUT_NONE
    escalation_user_ids: list[str] = []

    # Lifecycle
    status: str = STATUS_PENDING
    reviewer_user_id: Optional[str] = None
    reviewer_comments: str = ""
    decision_at: Optional[datetime.datetime] = None
    expired_at: Optional[datetime.datetime] = None
    escalated_at: Optional[datetime.datetime] = None

    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )

    class Settings:
        name = "approval_request"
        indexes = [
            "uuid",
            "status",
            "workflow_result_id",
            "team_id",
            "expires_at",
            [("status", 1), ("created_at", -1)],
            [("assigned_to_user_ids", 1), ("status", 1)],
        ]
