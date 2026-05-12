"""Credential model — team-scoped secret store referenced by API Node and other integration surfaces."""

import datetime
from typing import Optional

from beanie import Document
from pydantic import Field


CREDENTIAL_TYPES = ("static_header", "oauth_client_credentials")


class Credential(Document):
    """A stored credential, referenced by ID from workflow nodes.

    The `payload` dict holds type-specific fields (each secret value is
    individually Fernet-encrypted via app.utils.encryption.encrypt_value).
    Routers must never echo `payload` back to clients — only metadata.
    """

    name: str
    type: str  # one of CREDENTIAL_TYPES
    description: Optional[str] = None
    team_id: Optional[str] = None
    user_id: str
    payload: dict = {}
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = "credential"
        indexes = [
            "team_id",
            "user_id",
            [("team_id", 1), ("name", 1)],
        ]
