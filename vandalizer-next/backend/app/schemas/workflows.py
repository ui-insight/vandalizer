"""Request/response models for workflow endpoints."""

from typing import Any, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class CreateWorkflowRequest(BaseModel):
    name: str
    space: Optional[str] = None
    description: Optional[str] = None


class UpdateWorkflowRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    user_id: str
    space: Optional[str] = None
    num_executions: int = 0
    steps: list[dict] = []  # Dereferenced step objects


# ---------------------------------------------------------------------------
# Steps & Tasks
# ---------------------------------------------------------------------------

class AddStepRequest(BaseModel):
    name: str
    data: dict = {}
    is_output: bool = False


class UpdateStepRequest(BaseModel):
    name: Optional[str] = None
    data: Optional[dict] = None
    is_output: Optional[bool] = None


class AddTaskRequest(BaseModel):
    name: str
    data: dict = {}


class UpdateTaskRequest(BaseModel):
    name: Optional[str] = None
    data: Optional[dict] = None


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class RunWorkflowRequest(BaseModel):
    document_uuids: list[str]
    model: Optional[str] = None


class WorkflowStatusResponse(BaseModel):
    status: str
    num_steps_completed: int = 0
    num_steps_total: int = 0
    current_step_name: Optional[str] = None
    current_step_detail: Optional[str] = None
    current_step_preview: Optional[str] = None
    final_output: Optional[Any] = None
    steps_output: Optional[dict] = None


class TestStepRequest(BaseModel):
    task_name: str
    task_data: dict
    document_uuids: list[str]
    model: Optional[str] = None
