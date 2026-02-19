"""Office/M365 models — IntakeConfig and WorkItem."""

import datetime
import uuid as uuid_mod
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


class IntakeConfig(Document):
    uuid: str = Field(default_factory=lambda: str(uuid_mod.uuid4()))
    name: str
    intake_type: str  # "outlook_shared", "outlook_folder", "onedrive_drop"
    enabled: bool = False

    # Source config
    mailbox_address: Optional[str] = None
    outlook_folder_id: Optional[str] = None
    drive_id: Optional[str] = None
    folder_path: Optional[str] = None

    # Routing
    default_workflow: Optional[PydanticObjectId] = None
    triage_enabled: bool = False

    # Filtering
    file_filters: dict = Field(default_factory=lambda: {"types": [], "max_size_bytes": 0})

    # Ownership
    owner_user_id: str
    team_id: Optional[str] = None

    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "intake_configs"


class WorkItem(Document):
    uuid: str = Field(default_factory=lambda: str(uuid_mod.uuid4()))
    source: str  # "outlook_shared", "outlook_folder", "onedrive_drop", "manual"
    status: str = "received"  # received/triaged/processing/awaiting_review/completed/failed/rejected

    # Email metadata
    subject: Optional[str] = None
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    received_at: Optional[datetime.datetime] = None

    # Triage
    triage_category: Optional[str] = None
    triage_confidence: Optional[float] = None
    triage_tags: list[str] = Field(default_factory=list)
    triage_summary: Optional[str] = None
    sensitivity_flags: list[str] = Field(default_factory=list)

    # Workflow routing
    matched_workflow: Optional[PydanticObjectId] = None
    intake_config: Optional[PydanticObjectId] = None

    # Feedback
    feedback_action: Optional[str] = None
    feedback_note: Optional[str] = None

    # Ownership
    owner_user_id: Optional[str] = None
    team_id: Optional[str] = None

    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "work_items"
