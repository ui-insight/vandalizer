"""User notifications for verification status changes, quality alerts, and failures."""

import datetime
import uuid as uuid_mod
from typing import Optional

from beanie import Document
from pydantic import Field


class Notification(Document):
    uuid: str = Field(default_factory=lambda: uuid_mod.uuid4().hex)
    user_id: str  # recipient
    kind: str  # "verification_approved", "workflow_failed", "document_failed", ...
    title: str
    body: Optional[str] = None
    link: Optional[str] = None  # frontend route to navigate to

    # "info" for the ordinary event stream, "error" for failures. The bell
    # styles these differently, and it lets a failures-only view filter without
    # having to enumerate every failure kind.
    severity: str = "info"

    # Related entity
    item_kind: Optional[str] = None  # "workflow", "search_set", "knowledge_base"
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    request_uuid: Optional[str] = None  # verification request UUID

    # Repeated occurrences of the same event fold into one unread row keyed by
    # coalesce_key rather than filling the bell. A weekly automation that has
    # failed nine times is one entry with occurrences=9, not nine entries.
    # (Named `occurrences`, not `count`, which would shadow Document.count.)
    coalesce_key: Optional[str] = None
    occurrences: int = 1

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
            [("user_id", 1), ("coalesce_key", 1), ("read", 1)],
        ]
