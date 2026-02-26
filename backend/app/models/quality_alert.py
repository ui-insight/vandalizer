"""QualityAlert model - tracks quality regressions, staleness, and config changes."""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document


class QualityAlert(Document):
    """A quality alert for regression, staleness, or config change detection."""

    uuid: str = ""
    alert_type: str  # "regression" | "stale" | "config_changed"
    item_kind: str  # "search_set" | "workflow"
    item_id: str
    item_name: str = ""
    severity: str = "info"  # "info" | "warning" | "critical"
    message: str = ""
    previous_score: Optional[float] = None
    current_score: Optional[float] = None
    previous_tier: Optional[str] = None
    current_tier: Optional[str] = None
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)

    class Settings:
        name = "quality_alerts"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
