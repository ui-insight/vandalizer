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


class SupportAttachment(BaseModel):
    """File attached to a support ticket."""

    uuid: str = Field(default_factory=lambda: uuid_mod.uuid4().hex)
    filename: str
    file_type: Optional[str] = None
    file_data: str = ""  # base64 encoded
    uploaded_by: str
    message_uuid: Optional[str] = None  # linked to a specific message
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class SupportTicket(Document):
    uuid: str = Field(default_factory=lambda: uuid_mod.uuid4().hex)
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

    # Assignment
    assigned_to: Optional[str] = None  # user_id of support person

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
            "user_id",
            "status",
            "assigned_to",
            [("status", 1), ("created_at", -1)],
            [("user_id", 1), ("created_at", -1)],
        ]
