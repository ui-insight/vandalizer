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
    team_id: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    steps: list[PydanticObjectId] = []
    attachments: list[PydanticObjectId] = []
    num_executions: int = 0
    verified: bool = False
    created_by_user_id: Optional[str] = None
    input_config: dict = {}
    output_config: dict = {}
    resource_config: dict = {}
    stats: dict = {}
    version: int = 1
    parent_version_id: Optional[str] = None
    validation_plan: list[dict] = []
    # SHA256 of the workflow definition (steps/tasks/output_config) at the time
    # the plan was last generated or saved. Mismatch with the current
    # definition means the plan may reference steps or fields that no longer
    # exist — surfaced as a stale-plan warning in the Validate tab.
    validation_plan_definition_hash: Optional[str] = None
    validation_plan_updated_at: Optional[datetime.datetime] = None
    validation_inputs: list[dict] = []
    # Random opaque token that grants view-only access to anyone holding it.
    # Minted lazily the first time the owner copies a share link.
    share_token: Optional[str] = None
    # Optimizer-applied per-step overrides. The workflow engine consults this
    # at build time to swap per-step ``model`` and prompt variant without
    # rewriting the underlying WorkflowStep/WorkflowStepTask documents — so
    # a one-click revert restores the authored config.
    # Shape:
    #   {
    #     "step_overrides": {step_name: {"model": str, "prompt_variant": str | None}},
    #     "from_run_uuid": str,
    #   }
    config_override: Optional[dict] = None
    config_override_set_at: Optional[datetime.datetime] = None

    class Settings:
        name = "workflow"
        indexes = [
            "user_id",
            "team_id",
        ]


class WorkflowResult(Document):
    """Result of a workflow execution."""

    workflow: Optional[PydanticObjectId] = None
    num_steps_completed: int = 0
    num_steps_total: int = 0
    steps_output: dict = {}
    final_output: Optional[dict] = None
    # Sanitized step names marked is_output, snapshotted at run start.
    # Empty list means "no explicit selection" — fall back to the last step.
    output_step_names: list[str] = []
    start_time: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    status: str = "running"
    # Claimed once, atomically, by whichever pass first reaches the post-run
    # side effects (library write, execution counter). Those sit after
    # execute() and outside the try, so a failure there retries the whole task;
    # the resume then skips every step and lands back on them. Missing on rows
    # written before this existed, which a `None` query matches.
    finalized_at: Optional[datetime.datetime] = None
    # Heartbeat, stamped when a worker picks the run up and on every progress
    # write during execution. The stale-run reaper
    # (tasks.activity.reap_stale_workflow_runs) uses it to tell a dead run
    # (worker OOM-killed, hard time limit) from one still making progress.
    # None means no worker has started the run yet — or the row predates the
    # field, which the reaper's never-started sweep treats gently.
    last_progress_at: Optional[datetime.datetime] = None
    # Incremented at every task pickup. Bounds the poison-message loop that
    # acks_late + reject_on_worker_lost makes possible (a run that OOM-kills
    # its worker is requeued with a fresh retry counter each time); see
    # MAX_DELIVERY_ATTEMPTS in workflow_tasks.
    delivery_attempts: int = 0
    error: Optional[str] = None
    # Outputs the run was configured to deliver that failed after completion
    # (library write, notification, webhook). A run with entries here
    # completed — its results exist — but is not fully done; the owner is
    # belled and the failures are kept for the run record (#810). Passive
    # runs record the same concept structurally as ``output_delivery`` on
    # their trigger events (models/passive.py); unifying the two vocabularies
    # is deliberate follow-up work, not an accident of this field.
    delivery_failures: list[str] = []
    # Machine-readable error payload set by the runner when the failure has a
    # suggested user action (e.g. oversize-context with a convert-to-KB hint).
    # Schema: {"code": "context_over_budget", "suggested_action": "convert_to_kb",
    #          "oversize_documents": [{"uuid": ..., "title": ..., "token_count": ...}]}
    error_payload: Optional[dict] = None
    session_id: str
    # LLM model this run started on, snapshotted at dispatch. The model is
    # resolved once per run (user config → system default) and passed to the
    # execution task; a run that pauses at an approval gate loses that argument,
    # so the resume task reads it back from here to keep steps after the gate on
    # the same model. None for runs created before this field existed.
    model: Optional[str] = None
    # Celery task id of the execution job, captured at enqueue time so a user
    # can cancel an in-flight run (revoke + terminate). None for runs created
    # before this field existed or for runs that never enqueued a task.
    celery_task_id: Optional[str] = None
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
    # Citations aggregated from every KnowledgeBaseQuery step that ran. Each
    # entry: {document_id, document_title, page, sheet, chunk_id, score,
    # content_preview}. The frontend renders these as citation chips.
    retrieved_sources: list[dict] = []

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
