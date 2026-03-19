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
    input_config: Optional[dict] = None


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    user_id: str
    space: Optional[str] = None
    num_executions: int = 0
    steps: list[dict] = []  # Dereferenced step objects
    input_config: dict = {}


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
    batch_mode: bool = False


class WorkflowStatusResponse(BaseModel):
    status: str
    num_steps_completed: int = 0
    num_steps_total: int = 0
    current_step_name: Optional[str] = None
    current_step_detail: Optional[str] = None
    current_step_preview: Optional[str] = None
    final_output: Optional[Any] = None
    steps_output: Optional[dict] = None


class BatchStatusItem(BaseModel):
    session_id: str
    document_title: Optional[str] = None
    status: str
    num_steps_completed: int = 0
    num_steps_total: int = 0
    current_step_name: Optional[str] = None
    final_output: Optional[Any] = None


class BatchStatusResponse(BaseModel):
    status: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    items: list[BatchStatusItem] = []


class TestStepRequest(BaseModel):
    task_name: str
    task_data: dict
    document_uuids: list[str]
    model: Optional[str] = None


class ReorderStepsRequest(BaseModel):
    step_ids: list[str]


class ValidateWorkflowRequest(BaseModel):
    pass  # Plan is already persisted; output comes from last execution


class ValidationCheckDefinition(BaseModel):
    id: str
    name: str
    description: str = ""
    category: Optional[str] = None


class UpdateValidationPlanRequest(BaseModel):
    checks: list[ValidationCheckDefinition]


class ValidationPlanResponse(BaseModel):
    checks: list[ValidationCheckDefinition]


# ---------------------------------------------------------------------------
# Validation Inputs
# ---------------------------------------------------------------------------

class ValidationInputDefinition(BaseModel):
    id: str
    type: str  # "document" | "text"
    document_uuid: Optional[str] = None
    document_title: Optional[str] = None
    text: Optional[str] = None
    label: Optional[str] = None


class UpdateValidationInputsRequest(BaseModel):
    inputs: list[ValidationInputDefinition]


class ValidationInputsResponse(BaseModel):
    inputs: list[ValidationInputDefinition]


class CreateTempDocumentsRequest(BaseModel):
    texts: list[dict]  # [{"text": "...", "label": "..."}]


class ValidationCheckResult(BaseModel):
    name: str
    status: str  # PASS, FAIL, WARN, SKIP
    detail: Optional[str] = None
    check_id: Optional[str] = None
    consistency: Optional[float] = None  # 0-1, fraction of runs that agree
    run_statuses: Optional[list[str]] = None  # Status from each run
    run_details: Optional[list[str]] = None  # Detail from each run


class ValidateWorkflowResponse(BaseModel):
    grade: str  # A-F
    summary: str
    checks: list[ValidationCheckResult]
    score: Optional[float] = None  # Continuous 0-100
    check_pass_rate: Optional[float] = None  # 0-1
    consistency: Optional[float] = None  # 0-1
    num_runs: int = 1
    num_checks: int = 0
