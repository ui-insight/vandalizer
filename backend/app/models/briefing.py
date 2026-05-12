"""Morning Briefing models — daily personalized digest delivered via email + chat surface."""

import datetime
from enum import Enum
from typing import Optional

from beanie import Document
from pydantic import BaseModel, Field


class BriefingItemCategory(str, Enum):
    MY_ACTIVITY = "my-activity"
    TEAM_ACTIVITY = "team-activity"
    KB_NEWS = "kb-news"
    DEADLINE = "deadline"  # reserved for v1
    SUGGESTED_ACTION = "suggested-action"  # reserved for v1
    PRIMER = "primer"  # curated content shown when real items are scarce


class BriefingItem(BaseModel):
    category: str  # BriefingItemCategory value
    headline: str
    body: str
    deep_link: Optional[str] = None  # URL path the CTA should target
    source_id: Optional[str] = None  # ActivityEvent id, LibraryItem id, or primer slug
    urgency: int = 0  # higher = more urgent; used for ordering


class Briefing(Document):
    user_id: str
    date: datetime.date
    items: list[BriefingItem] = Field(default_factory=list)
    primer_padded: bool = False  # true when fallback primer items filled an otherwise-empty briefing
    sent_via_email: bool = False
    email_skipped_reason: Optional[str] = None  # "empty_paid_user" | "no_email" | "prefs_opt_out"
    opened_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "briefing"
        indexes = [
            "user_id",
            [("user_id", 1), ("date", -1)],
        ]
