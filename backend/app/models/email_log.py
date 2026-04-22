"""Email send log — one record per send attempt for deliverability analytics."""

import datetime
from typing import Optional

from beanie import Document
from pydantic import Field


class EmailLog(Document):
    recipient: str
    subject: str
    email_type: str  # "activation", "waitlist", "password_reset", "team_invite", etc.
    provider: str  # "smtp" or "resend"
    status: str  # "sent" or "failed"
    error: Optional[str] = None  # failure reason, truncated
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "email_log"
        indexes = [
            "created_at",
            "email_type",
            "status",
            [("created_at", -1), ("status", 1)],
            [("email_type", 1), ("created_at", -1)],
        ]
