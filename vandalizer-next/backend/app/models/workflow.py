"""Workflow models matching existing MongoDB collections."""

import datetime
from typing import Optional

from beanie import Document, PydanticObjectId


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
    created_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)
    updated_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)
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

    class Settings:
        name = "workflow"


class WorkflowResult(Document):
    """Result of a workflow execution."""

    workflow: Optional[PydanticObjectId] = None
    num_steps_completed: int = 0
    num_steps_total: int = 0
    steps_output: dict = {}
    final_output: Optional[dict] = None
    start_time: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)
    status: str = "running"
    session_id: str
    current_step_name: Optional[str] = None
    current_step_detail: Optional[str] = None
    current_step_preview: Optional[str] = None
    trigger_type: Optional[str] = None
    is_passive: bool = False
    input_context: Optional[dict] = None

    class Settings:
        name = "workflow_result"


class WorkflowArtifact(Document):
    """Artifacts (files) created during workflow execution."""

    workflow_result_id: str
    artifact_type: Optional[str] = None
    filename: Optional[str] = None
    file_path: Optional[str] = None
    extracted_data: Optional[dict] = None
    created_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)

    class Settings:
        name = "workflow_artifacts"
