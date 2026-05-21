"""Support ticket models."""

import datetime
import uuid as uuid_mod
from enum import Enum
from typing import Optional

from beanie import Document
from pydantic import BaseModel, Field


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class SupportMessage(BaseModel):
    """Embedded message within a ticket conversation."""

    uuid: str = Field(default_factory=lambda: uuid_mod.uuid4().hex)
    user_id: str
    user_name: Optional[str] = None
    content: str
    is_support_reply: bool = False
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    edited_at: Optional[datetime.datetime] = None


class SupportAttachment(BaseModel):
    """File attached to a support ticket."""

    uuid: str = Field(default_factory=lambda: uuid_mod.uuid4().hex)
    filename: str
    file_type: Optional[str] = None
    file_data: str = ""  # base64 encoded (legacy, prefer file_path)
    file_path: Optional[str] = None  # on-disk path (preferred)
    uploaded_by: str
    message_uuid: Optional[str] = None  # linked to a specific message
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class SupportTicket(Document):
    uuid: str = Field(default_factory=lambda: uuid_mod.uuid4().hex)
    # Human-friendly sequential id (e.g. 1024). Assigned at insert time via an
    # atomic counter; legacy tickets created before this feature get backfilled
    # on first read. Optional only so older docs deserialize cleanly.
    ticket_number: Optional[int] = None
    subject: str
    status: TicketStatus = TicketStatus.OPEN
    priority: TicketPriority = TicketPriority.NORMAL

    # Creator
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    team_id: Optional[str] = None

    # Conversation
    messages: list[SupportMessage] = []
    attachments: list[SupportAttachment] = []

    # Category (None for regular tickets, "feedback_prompt" for check-in prompts)
    category: Optional[str] = None

    # Assignment
    assigned_to: Optional[str] = None  # user_id of support person

    # Read tracking — user_ids who have viewed the ticket since the last message
    read_by: list[str] = []

    # Tags applied by support agents — internal-only; never returned to the
    # ticket owner or other non-support users.
    tags: list[str] = []

    # Users (by user_id) the requester or an agent has looped in on this
    # ticket. Watchers can view the ticket, get notified on new messages
    # and status changes, and reply to it. Distinct from `tags` (which are
    # support-internal labels) — watchers are always visible to everyone
    # who can see the ticket.
    watchers: list[str] = []

    # Timestamps
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    closed_at: Optional[datetime.datetime] = None

    class Settings:
        name = "support_ticket"
        indexes = [
            "uuid",
            "ticket_number",
            "user_id",
            "status",
            "assigned_to",
            "tags",
            "watchers",
            [("status", 1), ("created_at", -1)],
            [("user_id", 1), ("created_at", -1)],
        ]


class SupportCounter(Document):
    """Atomic counter for sequential ticket numbers.

    One singleton document keyed by `name` (always "support_ticket"). Mongo's
    findOneAndUpdate with $inc + upsert guarantees each create_ticket call
    gets a unique increasing value, even under concurrent inserts.
    """

    name: str
    value: int = 0

    class Settings:
        name = "support_counter"
        indexes = ["name"]
