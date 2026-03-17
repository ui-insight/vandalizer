"""Audit log models for compliance tracking and admin actions."""

import datetime
from typing import Any, Optional

from beanie import Document
from pydantic import Field


class AuditLog(Document):
    """Append-only audit trail entry. No update/delete operations."""

    uuid: str
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    actor_user_id: str
    actor_type: str = "user"  # user | system | celery
    action: str  # e.g. document.create, extraction.run, workflow.approve
    resource_type: str  # document | workflow | extraction | team | user | config
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    team_id: Optional[str] = None
    organization_id: Optional[str] = None
    detail: dict = {}
    ip_address: Optional[str] = None

    class Settings:
        name = "audit_log"
        indexes = [
            "uuid",
            [("timestamp", -1)],
            [("actor_user_id", 1), ("timestamp", -1)],
            [("resource_type", 1), ("resource_id", 1)],
            [("action", 1), ("timestamp", -1)],
            [("organization_id", 1), ("timestamp", -1)],
        ]


class AdminAuditLog(Document):
    """Records all state-changing admin actions."""

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
