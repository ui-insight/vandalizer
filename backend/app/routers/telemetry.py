"""Telemetry receiver — runs only on the collector instance.

This router is registered ONLY when telemetry_collector_enabled is True (see
app/main.py), so on every other deployment of this codebase both the public
ingest endpoint and the admin analytics endpoint simply do not exist.

Two endpoints:
  - POST /api/telemetry/heartbeat — public, unauthenticated (pings come from
    arbitrary deployments we have no shared secret with), strictly validated,
    rate-limited, and write-only. It upserts the sender's roster row.
  - GET  /api/telemetry/analytics — admin/staff only, the data behind the
    in-app fleet dashboard.
"""

from __future__ import annotations

import datetime
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from starlette.requests import Request

from app.dependencies import get_current_user
from app.models.telemetry import TelemetryHeartbeat
from app.models.user import User
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

ACTIVE_WINDOW_DAYS = 30

# Bounded strings so a malformed/hostile sender can't write unbounded blobs into
# the collection. The values we expect are short (bucket labels, a version tag,
# an org name), so these caps are generous.
ShortStr = Annotated[str, StringConstraints(max_length=32)]
LabelStr = Annotated[str, StringConstraints(max_length=200)]


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _as_utc(dt: datetime.datetime) -> datetime.datetime:
    """Coerce a possibly-naive datetime to aware UTC.

    Datetimes read back from Mongo are naive (the Motor client isn't tz_aware),
    so comparing ``last_seen`` against a tz-aware cutoff raises ``TypeError:
    can't compare offset-naive and offset-aware datetimes`` — a 500 that only
    appears once the roster has at least one row. Naive values are already UTC,
    so just attach the tzinfo.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=datetime.timezone.utc)


# ---------------------------------------------------------------------------
# Ingest payload validation — mirrors the client's build_heartbeat_payload.
# extra="ignore" lets future schema additions arrive without 422-ing old
# collectors; unknown fields are simply dropped.
# ---------------------------------------------------------------------------


class HeartbeatMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    users: ShortStr = ""
    active_users_30d: ShortStr = ""
    teams: ShortStr = ""
    documents: ShortStr = ""
    workflows: ShortStr = ""


class HeartbeatIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    organization: LabelStr = ""
    contact_email: LabelStr = ""


class HeartbeatIn(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schema_version: int = Field(1, alias="schema")
    instance_id: Annotated[str, StringConstraints(min_length=8, max_length=64)]
    version: ShortStr = "unknown"
    environment: ShortStr = "other"
    metrics: HeartbeatMetrics = Field(default_factory=HeartbeatMetrics)
    identity: Optional[HeartbeatIdentity] = None


@router.post("/heartbeat")
@limiter.limit("30/hour")
async def receive_heartbeat(request: Request, payload: HeartbeatIn) -> dict:
    """Record one deployment heartbeat. Write-only: never echoes data back."""
    # Coarse environment only — anything we don't recognize collapses to "other"
    # rather than being stored verbatim.
    environment = payload.environment if payload.environment == "production" else "other"

    organization = None
    contact_email = None
    if payload.identity and payload.identity.organization.strip():
        organization = payload.identity.organization.strip()
        contact_email = payload.identity.contact_email.strip() or None

    now = _utcnow()
    existing = await TelemetryHeartbeat.find_one(
        TelemetryHeartbeat.instance_id == payload.instance_id
    )
    if existing is not None:
        existing.version = payload.version
        existing.environment = environment
        existing.metrics = payload.metrics.model_dump()
        existing.organization = organization
        existing.contact_email = contact_email
        existing.last_seen = now
        existing.heartbeat_count += 1
        await existing.save()
    else:
        await TelemetryHeartbeat(
            instance_id=payload.instance_id,
            version=payload.version,
            environment=environment,
            metrics=payload.metrics.model_dump(),
            organization=organization,
            contact_email=contact_email,
            first_seen=now,
            last_seen=now,
            heartbeat_count=1,
        ).insert()

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Analytics — the in-app fleet dashboard data (admin/staff only).
# ---------------------------------------------------------------------------


def _tally(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        key = v or "unknown"
        out[key] = out.get(key, 0) + 1
    return out


@router.get("/analytics")
async def telemetry_analytics(user: User = Depends(get_current_user)) -> dict:
    """Aggregate fleet stats for the admin dashboard."""
    if not (user.is_admin or user.is_staff):
        raise HTTPException(status_code=403, detail="Admin access required")

    active_cutoff = _utcnow() - datetime.timedelta(days=ACTIVE_WINDOW_DAYS)

    # The roster is one row per deployment — small enough to scan and aggregate
    # in-process rather than maintaining a pipeline.
    rows = await TelemetryHeartbeat.find_all().to_list()

    total = len(rows)
    active = [r for r in rows if _as_utc(r.last_seen) >= active_cutoff]

    named = [
        {
            "organization": r.organization,
            "version": r.version,
            "environment": r.environment,
            "last_seen": _as_utc(r.last_seen).isoformat(),
            "active": _as_utc(r.last_seen) >= active_cutoff,
        }
        for r in rows
        if r.organization
    ]
    named.sort(key=lambda d: d["last_seen"], reverse=True)

    return {
        "total_instances": total,
        "active_instances_30d": len(active),
        "named_instances": len(named),
        "anonymous_instances": total - len(named),
        "by_version": _tally([r.version for r in active]),
        "by_environment": _tally([r.environment for r in active]),
        "users_buckets": _tally([r.metrics.get("users", "") for r in active]),
        "named_deployments": named,
    }
