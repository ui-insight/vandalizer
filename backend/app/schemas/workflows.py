"""Request/response models for workflow endpoints."""

from typing import Any, Optional
from pydantic import BaseModel

from app.schemas.user import AuthorRef
from app.utils.naming import EntityName, OptionalEntityName


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class CreateWorkflowRequest(BaseModel):
    name: EntityName
    description: Optional[str] = None


class UpdateWorkflowRequest(BaseModel):
    name: OptionalEntityName = None
    description: Optional[str] = None
    input_config: Optional[dict] = None
    output_config: Optional[dict] = None


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    user_id: str
    # Set when the workflow is shared with a team; None for personal workflows
    # or workflows that have been removed from their team library.
    team_id: Optional[str] = None
    num_executions: int = 0
    steps: list[dict] = []  # Dereferenced step objects
    input_config: dict = {}
    output_config: dict = {}
    # True when the caller can edit / delete / remove-from-team this workflow.
    # Mirrors can_manage_workflow: creator OR team owner/admin.
    can_manage: bool = True
    created_by: Optional[AuthorRef] = None


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
    output_step_names: list[str] = []
    approval_request_id: Optional[str] = None
    error: Optional[str] = None
    error_payload: Optional[dict] = None
    retrieved_sources: list[dict] = []


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
    # Name of the workflow step this check is primarily about. Drives the
    # per-step quality breakdown in the validate response. Auto-generated
    # plans now always populate this; older plans may omit it.
    target_step: Optional[str] = None
    # "auto" (LLM-generated) or "manual" (user-authored). Regenerating the
    # plan replaces auto checks but preserves manual ones. Older checks omit
    # this and are treated as auto.
    source: Optional[str] = None


class UpdateValidationPlanRequest(BaseModel):
    checks: list[ValidationCheckDefinition]


class ValidationPlanResponse(BaseModel):
    checks: list[ValidationCheckDefinition]
    # Stale-plan detection: true when the workflow definition changed since
    # the plan was generated/saved, or when checks target steps that no
    # longer exist. PUT/generate responses always return fresh (False).
    plan_stale: bool = False
    stale_reasons: list[str] = []  # "definition_changed" | "orphaned_checks"
    orphaned_check_ids: list[str] = []


# ---------------------------------------------------------------------------
# Validation Inputs
# ---------------------------------------------------------------------------

class ValidationInputDefinition(BaseModel):
    id: str
    type: str  # "document" | "text"
    document_uuid: Optional[str] = None
    document_title: Optional[str] = None
    document_exists: Optional[bool] = None
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


class StaticDiagnostic(BaseModel):
    code: str  # e.g. "dangling_search_set", "empty_step_output"
    level: str  # "error" | "warning" | "info"
    message: str
    target_step: Optional[str] = None
    details: dict = {}


class ValidateWorkflowResponse(BaseModel):
    grade: str  # A-F
    summary: str
    checks: list[ValidationCheckResult]
    score: Optional[float] = None  # Combined 0-100 (quality + stability)
    quality_score: Optional[float] = None  # 0-100: how good is the output
    stability_score: Optional[float] = None  # 0-100: how consistent across runs
    stability_detail: Optional[dict] = None  # Breakdown of stability measurement
    check_pass_rate: Optional[float] = None  # 0-1, unweighted
    weighted_pass_rate: Optional[float] = None  # 0-1, weighted by category importance
    consistency: Optional[float] = None  # 0-1, evaluator agreement (diagnostic)
    num_runs: int = 1
    num_checks: int = 0
    # Phase 2A diagnostics (previously stripped by response_model filtering).
    output_comparison: Optional[dict] = None
    baseline_no_workflow_score: Optional[float] = None
    lift_vs_no_workflow: Optional[float] = None
    baseline_no_workflow_detail: Optional[dict] = None
    step_breakdown: list[dict] = []
    judge_variance: Optional[float] = None
    # Static + runtime deterministic diagnostics (new).
    static_diagnostics: list[StaticDiagnostic] = []
    # True when this run was graded against a plan that no longer matches the
    # workflow definition — the grade card renders a regenerate caveat.
    plan_stale: bool = False
