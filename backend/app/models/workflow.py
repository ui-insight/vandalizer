"""Workflow models matching existing MongoDB collections."""

import datetime
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


class WorkflowStepTask(Document):
    """A task within a workflow step."""

    name: str
    data: dict = {}

    class Settings:
        name = "workflow_step_task"


class WorkflowStep(Document):
    """A step within a workflow."""

    name: str
    tasks: list[PydanticObjectId] = []
    data: dict = {}
    is_output: bool = False

    class Settings:
        name = "workflow_step"


class WorkflowAttachment(Document):
    """An attachment within a workflow."""

    attachment: str

    class Settings:
        name = "workflow_attachment"


class Workflow(Document):
    """A complete workflow."""

    name: str
    description: Optional[str] = None
    user_id: str
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    steps: list[PydanticObjectId] = []
    attachments: list[PydanticObjectId] = []
    num_executions: int = 0
    space: Optional[str] = None
    verified: bool = False
    created_by_user_id: Optional[str] = None
    input_config: dict = {}
    output_config: dict = {}
    resource_config: dict = {}
    stats: dict = {}
    version: int = 1
    parent_version_id: Optional[str] = None
    validation_plan: list[dict] = []
    validation_inputs: list[dict] = []

    class Settings:
        name = "workflow"
        indexes = [
            "user_id",
            "space",
            [("user_id", 1), ("space", 1)],
        ]


class WorkflowResult(Document):
    """Result of a workflow execution."""

    workflow: Optional[PydanticObjectId] = None
    num_steps_completed: int = 0
    num_steps_total: int = 0
    steps_output: dict = {}
    final_output: Optional[dict] = None
    start_time: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    status: str = "running"
    session_id: str
    current_step_name: Optional[str] = None
    current_step_detail: Optional[str] = None
    current_step_preview: Optional[str] = None
    trigger_type: Optional[str] = None
    is_passive: bool = False
    input_context: Optional[dict] = None
    # Approval workflow fields
    paused_at_step_index: Optional[int] = None
    approval_request_id: Optional[str] = None
    # Batch run fields
    batch_id: Optional[str] = None
    document_title: Optional[str] = None

    class Settings:
        name = "workflow_result"
        indexes = [
            "session_id",
            "workflow",
            "batch_id",
            "status",
        ]


class WorkflowArtifact(Document):
    """Artifacts (files) created during workflow execution."""

    workflow_result_id: str
    artifact_type: Optional[str] = None
    filename: Optional[str] = None
    file_path: Optional[str] = None
    extracted_data: Optional[dict] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = "workflow_artifacts"
