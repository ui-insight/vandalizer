"""Approval request model for workflow review gates."""

import datetime
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


class ApprovalRequest(Document):
    """Represents a pending human review within a workflow execution."""

    uuid: str
    workflow_result_id: PydanticObjectId
    workflow_id: PydanticObjectId
    step_index: int  # where in the DAG we paused
    step_name: str
    data_for_review: dict = {}  # snapshot of outputs so far
    review_instructions: str = ""
    status: str = "pending"  # pending | approved | rejected
    assigned_to_user_ids: list[str] = []
    reviewer_user_id: Optional[str] = None
    reviewer_comments: str = ""
    decision_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )

    class Settings:
        name = "approval_request"
        indexes = [
            "uuid",
            "status",
            "workflow_result_id",
            [("status", 1), ("created_at", -1)],
        ]
