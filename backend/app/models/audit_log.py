"""Admin audit log — records all state-changing admin actions."""

import datetime
from typing import Any, Optional

from beanie import Document
from pydantic import Field


class AdminAuditLog(Document):
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    user_id: str
    action: str          # e.g. "update_config", "add_model", "delete_oauth_provider"
    detail: Optional[str] = None   # human-readable description
    payload: Optional[dict[str, Any]] = None  # redacted copy of request body

    class Settings:
        name = "admin_audit_log"
        indexes = [
            "user_id",
            "action",
            "timestamp",
            [("timestamp", -1)],
        ]
