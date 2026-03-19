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
    model: Optional[str] = None
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
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = "validation_runs"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
