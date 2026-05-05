"""Scoped API keys for the management API (/api/mgmt/v1).

Distinct from User.api_token_hash, which is a single per-user token bound
to that user's role. ApiKey supports multiple named, scoped, revocable
keys per issuer — intended for service consumers (dashboards, agentic
tooling) that need bounded blast radius and per-key audit trails.
"""

import datetime
from typing import Optional

from beanie import Document
from pydantic import Field


class ApiKey(Document):
    key_hash: str
    prefix: str
    name: str
    description: Optional[str] = None
    created_by: str
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    scopes: list[str] = Field(default_factory=list)
    expires_at: Optional[datetime.datetime] = None
    revoked_at: Optional[datetime.datetime] = None
    last_used_at: Optional[datetime.datetime] = None
    last_used_ip: Optional[str] = None

    class Settings:
        name = "api_key"
        indexes = [
            "key_hash",
            "created_by",
            [("revoked_at", 1), ("expires_at", 1)],
        ]
