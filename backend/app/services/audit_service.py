"""Audit trail service — fire-and-forget event logging."""

import datetime
import logging
import uuid
from typing import Optional

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def log_event(
    action: str,
    actor_user_id: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    resource_name: Optional[str] = None,
    actor_type: str = "user",
    team_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    detail: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Log an audit event. Non-blocking — errors are logged, not raised."""
    try:
        entry = AuditLog(
            uuid=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(tz=datetime.timezone.utc),
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            team_id=team_id,
            organization_id=organization_id,
            detail=detail or {},
            ip_address=ip_address,
        )
        await entry.insert()
    except Exception:
        logger.exception("Failed to write audit log entry for action=%s", action)


async def query_audit_log(
    action: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    start_time: Optional[datetime.datetime] = None,
    end_time: Optional[datetime.datetime] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[AuditLog], int]:
    """Query audit log with filters. Returns (entries, total_count)."""
    filters = {}
    if action:
        filters["action"] = action
    if actor_user_id:
        filters["actor_user_id"] = actor_user_id
    if resource_type:
        filters["resource_type"] = resource_type
    if resource_id:
        filters["resource_id"] = resource_id
    if organization_id:
        filters["organization_id"] = organization_id
    if start_time or end_time:
        ts_filter = {}
        if start_time:
            ts_filter["$gte"] = start_time
        if end_time:
            ts_filter["$lte"] = end_time
        filters["timestamp"] = ts_filter

    query = AuditLog.find(filters)
    total = await query.count()
    entries = await query.sort(-AuditLog.timestamp).skip(skip).limit(limit).to_list()
    return entries, total
