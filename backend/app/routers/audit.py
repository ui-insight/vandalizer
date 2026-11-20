"""Audit log query endpoints."""
from fastapi.responses import StreamingResponse
from app.models.web_search_usage import WebSearchUsage

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.models.user import User
from app.services import audit_service

router = APIRouter()


@router.get("/", response_model=None)
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
) -> dict[str, object]:
    """Query audit log. Admin or staff (analytics role)."""
    if not (user.is_admin or user.is_staff):
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


@router.get("/export", response_model=None)
async def export_audit_log(
    action: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Export audit log as CSV. Admin or staff (analytics role).

    Pass ``actor_user_id`` to scope the export to a single user's trail (used by
    the per-user activity drill-down in the admin console).
    """
    import csv
    import io

    from fastapi.responses import StreamingResponse

    if not (user.is_admin or user.is_staff):
        raise HTTPException(status_code=403, detail="Admin access required")

    parsed_start = None
    parsed_end = None
    if start_time:
        parsed_start = datetime.datetime.fromisoformat(start_time)
    if end_time:
        parsed_end = datetime.datetime.fromisoformat(end_time)

    entries, _ = await audit_service.query_audit_log(
        action=action,
        actor_user_id=actor_user_id,
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


# ---------------------------------------------------------------------------
# Web searches
# ---------------------------------------------------------------------------
# Each query sent to the deployment's web search provider (web_search_usage):
# what left the deployment, from which surface and for whom, and the count to
# reconcile with a paid provider's bill.


def _web_search_filter(
    feature: Optional[str],
    status: Optional[str],
    provider: Optional[str],
    user_id: Optional[str],
    start_time: Optional[str],
    end_time: Optional[str],
) -> dict:
    query: dict = {}
    if feature:
        query["feature"] = feature
    if status:
        query["status"] = status
    if provider:
        query["provider"] = provider
    if user_id:
        query["user_id"] = user_id
    window: dict = {}
    for key, raw in (("$gte", start_time), ("$lte", end_time)):
        if raw:
            try:
                window[key] = datetime.datetime.fromisoformat(raw)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid {'start' if key == '$gte' else 'end'}_time format")
    if window:
        query["timestamp"] = window
    return query


def _web_search_row(e: WebSearchUsage) -> dict:
    return {
        "id": str(e.id),
        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        "feature": e.feature,
        "user_id": e.user_id,
        "team_id": e.team_id,
        "activity_id": e.activity_id,
        "provider": e.provider,
        "query": e.query,
        "result_count": e.result_count,
        "status": e.status,
        "error": e.error,
    }


@router.get("/web-searches", response_model=None)
async def query_web_searches(
    feature: Optional[str] = None,
    status: Optional[str] = None,
    provider: Optional[str] = None,
    user_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Web searches sent to the provider, newest first, with counts by
    feature and status over the same filter. Admin or staff (analytics role)."""
    from app.models.web_search_usage import WebSearchUsage

    if not (user.is_admin or user.is_staff):
        raise HTTPException(status_code=403, detail="Admin access required")

    query = _web_search_filter(feature, status, provider, user_id, start_time, end_time)
    total = await WebSearchUsage.find(query).count()
    entries = await WebSearchUsage.find(query).sort("-timestamp").skip(skip).limit(limit).to_list()

    async def _counts(field: str) -> dict[str, int]:
        pipeline = [{"$match": query}, {"$group": {"_id": f"${field}", "n": {"$sum": 1}}}]
        rows = await WebSearchUsage.get_motor_collection().aggregate(pipeline).to_list(None)
        return {str(r["_id"] or "unknown"): r["n"] for r in rows}

    return {
        "entries": [_web_search_row(e) for e in entries],
        "total": total,
        "skip": skip,
        "limit": limit,
        "by_feature": await _counts("feature"),
        "by_status": await _counts("status"),
    }


@router.get("/web-searches/export", response_model=None)
async def export_web_searches(
    feature: Optional[str] = None,
    status: Optional[str] = None,
    provider: Optional[str] = None,
    user_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Web searches as CSV (up to 10,000, newest first). Admin or staff."""
    import csv
    import io

    from fastapi.responses import StreamingResponse

    from app.models.web_search_usage import WebSearchUsage

    if not (user.is_admin or user.is_staff):
        raise HTTPException(status_code=403, detail="Admin access required")

    query = _web_search_filter(feature, status, provider, user_id, start_time, end_time)
    entries = await WebSearchUsage.find(query).sort("-timestamp").limit(10000).to_list()

    output = io.StringIO()
    writer = csv.writer(output)
    columns = ["timestamp", "feature", "user_id", "team_id", "activity_id", "provider", "query", "result_count", "status", "error"]
    writer.writerow(columns)
    for e in entries:
        row = _web_search_row(e)
        writer.writerow(["" if row[c] is None else row[c] for c in columns])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=web_searches.csv"},
    )
