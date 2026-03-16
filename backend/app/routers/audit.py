"""Audit log query endpoints."""

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.models.user import User
from app.services import audit_service

router = APIRouter()


@router.get("/")
async def query_audit_log(
    action: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    """Query audit log. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    parsed_start = None
    parsed_end = None
    if start_time:
        try:
            parsed_start = datetime.datetime.fromisoformat(start_time)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_time format")
    if end_time:
        try:
            parsed_end = datetime.datetime.fromisoformat(end_time)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_time format")

    entries, total = await audit_service.query_audit_log(
        action=action,
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        organization_id=organization_id,
        start_time=parsed_start,
        end_time=parsed_end,
        skip=skip,
        limit=limit,
    )

    return {
        "entries": [
            {
                "uuid": e.uuid,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "actor_user_id": e.actor_user_id,
                "actor_type": e.actor_type,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "resource_name": e.resource_name,
                "team_id": e.team_id,
                "organization_id": e.organization_id,
                "detail": e.detail,
                "ip_address": e.ip_address,
            }
            for e in entries
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/export")
async def export_audit_log(
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """Export audit log as CSV. Admin only."""
    import csv
    import io

    from fastapi.responses import StreamingResponse

    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    parsed_start = None
    parsed_end = None
    if start_time:
        parsed_start = datetime.datetime.fromisoformat(start_time)
    if end_time:
        parsed_end = datetime.datetime.fromisoformat(end_time)

    entries, _ = await audit_service.query_audit_log(
        action=action,
        resource_type=resource_type,
        start_time=parsed_start,
        end_time=parsed_end,
        limit=10000,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "actor_user_id", "actor_type", "action", "resource_type", "resource_id", "resource_name", "detail"])
    for e in entries:
        writer.writerow([
            e.timestamp.isoformat() if e.timestamp else "",
            e.actor_user_id,
            e.actor_type,
            e.action,
            e.resource_type,
            e.resource_id or "",
            e.resource_name or "",
            str(e.detail),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )
