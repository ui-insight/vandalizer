"""Telemetry receiver model — one row per known deployment.

This lives on the collector instance (the one with telemetry_collector_enabled).
Each incoming heartbeat upserts the row for its instance_id, so the collection is
a roster of live deployments, not an ever-growing event log: counts and version
distribution fall straight out of it. Stores ONLY the anonymous heartbeat fields
plus the voluntary identity an admin chose to self-declare.
"""

import datetime
from typing import Optional

import pymongo
from beanie import Document
from pydantic import Field


class TelemetryHeartbeat(Document):
    # The anonymous, stable per-install id (uuid4 from the sender). Unique key:
    # repeat heartbeats from the same deployment update this row in place.
    instance_id: str
    version: str = "unknown"
    environment: str = "other"  # coarse: "production" | "other"

    # Coarse usage buckets as sent — e.g. {"users": "11-50", ...}. Never exact.
    metrics: dict[str, str] = Field(default_factory=dict)

    # Voluntary identity — present only if the deployment self-declared it.
    organization: Optional[str] = None
    contact_email: Optional[str] = None

    first_seen: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    last_seen: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    heartbeat_count: int = 0

    class Settings:
        name = "telemetry_heartbeat"
        indexes = [
            pymongo.IndexModel("instance_id", unique=True),
            "last_seen",
        ]
