"""ValidationRun model  - persists validation run results for quality tracking."""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document
from pydantic import Field


class ValidationRun(Document):
    """A single validation run result, linked to a search set or workflow."""

    uuid: str = ""
    item_kind: str  # "search_set" | "workflow"
    item_id: str  # SearchSet uuid or Workflow ObjectId as str
    item_name: str = ""
    run_type: str  # "extraction" | "workflow"
    accuracy: Optional[float] = None  # 0-1 (extraction only)
    consistency: Optional[float] = None  # 0-1 (extraction only)
    grade: Optional[str] = None  # A-F (workflow only)
    score: float = 0.0  # Unified 0-100 (computed)
    # The model that actually executed the run (not merely the one requested —
    # a config-pinned model wins over a caller's fallback, and the label must
    # say which one ran). None when no single task model is attributable, e.g.
    # a workflow validation graded over executions from mixed models.
    model: Optional[str] = None
    # Effective model settings snapshotted at run time, so a later change to a
    # model's live config (e.g. its temperature in System Config) can't
    # silently rewrite what a historical score measured. Shape varies by
    # run_type: extraction {"source", "requested_model", "temperature",
    # "pass_models"}, workflow {"models_used"}, kb_validation
    # {"requested_model", "judge_model", "answer_temperature"}.
    model_settings: Optional[dict] = None
    num_runs: int = 1
    num_test_cases: int = 0
    num_checks: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    score_breakdown: dict = {}  # raw_score, sample_size_factor, penalty details
    result_snapshot: dict = {}  # Full validation result payload
    extraction_config: dict = {}  # Extraction config used for this run
    config_hash: Optional[str] = None
    user_id: str
    # Provenance tag — distinguishes a user-triggered validation run from an
    # auto-recorded apply event (Phase 4 of loop closure). Values:
    # ``"validation"`` (default), ``"optimizer_apply"``. Optimizer-apply rows
    # are rendered differently on the quality timeline so users can tell
    # "we measured this" from "the optimizer believed this".
    source: Optional[str] = None
    # When source="optimizer_apply", the originating optimization-run uuid.
    # Lets the timeline deep-link an apply row back to its winning trial.
    source_run_uuid: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = "validation_runs"
        indexes = [
            # Per-item history (get_quality_history, get_latest_validation).
            [("item_kind", 1), ("item_id", 1), ("created_at", -1)],
            # By-model rollups and the mgmt API's model filter — previously a
            # full collection scan.
            [("model", 1), ("created_at", -1)],
        ]

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
