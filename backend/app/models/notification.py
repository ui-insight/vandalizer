"""User notifications for verification status changes and quality alerts."""

import datetime
import uuid as uuid_mod
from typing import Optional

from beanie import Document
from pydantic import Field


class Notification(Document):
    uuid: str = Field(default_factory=lambda: uuid_mod.uuid4().hex)
    user_id: str  # recipient
    kind: str  # "verification_approved", "verification_rejected", "verification_returned", "verification_stale"
    title: str
    body: Optional[str] = None
    link: Optional[str] = None  # frontend route to navigate to

    # Related entity
    item_kind: Optional[str] = None  # "workflow", "search_set", "knowledge_base"
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    request_uuid: Optional[str] = None  # verification request UUID

    read: bool = False
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "notification"
        indexes = [
            "user_id",
            "uuid",
            [("user_id", 1), ("read", 1), ("created_at", -1)],
        ]
