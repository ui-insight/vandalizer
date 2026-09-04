"""RegressionSuiteRun - a persisted catalog-wide validation sweep."""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document
from pydantic import Field


class RegressionSuiteRun(Document):
    """One admin-triggered validation sweep over all verified catalog items.

    Persisted so a sweep survives the request that started it and so two
    sweeps (e.g. under two different models) can be compared after the fact —
    the previous implementation ran inside the HTTP request and returned its
    results into component state, keeping nothing.
    """

    uuid: str = ""
    status: str = "running"  # running | completed | failed
    # The model explicitly requested for the sweep; None = each item's own
    # default resolution. The per-item ground truth of what actually executed
    # is on the individual ValidationRun rows this sweep produced.
    model: Optional[str] = None
    user_id: str = ""
    total_items: int = 0
    completed_items: int = 0
    succeeded: int = 0
    failed: int = 0
    # Mean of per-item scores across items that validated successfully — the
    # one catalog-wide number "is this model good?" asks for.
    mean_score: Optional[float] = None
    # Per-item rows: {item_id, kind, name, score, grade, prev_score, delta, status}
    results: list[dict] = []
    error: Optional[str] = None
    started_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    finished_at: Optional[datetime.datetime] = None

    class Settings:
        name = "regression_suite_runs"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex

    def summary_dict(self) -> dict:
        return {
            "run_uuid": self.uuid,
            "status": self.status,
            "model": self.model,
            "total_items": self.total_items,
            "completed_items": self.completed_items,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "mean_score": self.mean_score,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
