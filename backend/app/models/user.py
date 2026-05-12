import datetime
from typing import Optional

from beanie import Document
from beanie import PydanticObjectId
from pydantic import Field


class User(Document):
    user_id: str
    email: Optional[str] = None
    is_admin: bool = False
    is_staff: bool = False
    is_examiner: bool = False
    name: Optional[str] = None
    current_team: Optional[PydanticObjectId] = None
    api_token_hash: Optional[str] = None
    api_token_created_at: Optional[datetime.datetime] = None
    api_token_expires_at: Optional[datetime.datetime] = None
    browser_automation_session_id: Optional[str] = None
    m365_enabled: bool = False
    m365_connected_at: Optional[datetime.datetime] = None
    password_hash: Optional[str] = None
    is_demo_user: bool = False
    demo_expires_at: Optional[datetime.datetime] = None
    demo_status: Optional[str] = None  # active | expired | locked
    organization_id: Optional[str] = None  # org uuid for university hierarchy
    role_segment: Optional[str] = None  # research_admin | pi | sponsored_programs | compliance | it | other

    # Engagement tracking
    last_login_at: Optional[datetime.datetime] = None
    first_session_completed: bool = False
    onboarding_drip_step: int = 0  # 0=not started, 1-4=sent step N
    onboarding_drip_next_at: Optional[datetime.datetime] = None  # when to send next drip
    last_nudge_sent_at: Optional[datetime.datetime] = None
    email_preferences: dict = {}  # {"onboarding": True, "nudges": True, "briefings": True}

    # Morning Briefing tracking
    last_briefing_sent_at: Optional[datetime.datetime] = None
    last_briefing_opened_at: Optional[datetime.datetime] = None
    briefing_opened_dates: list[datetime.date] = Field(default_factory=list)
    briefing_items_shown_ids: list[str] = Field(default_factory=list)
    briefing_primer_shown_ids: list[str] = Field(default_factory=list)

    class Settings:
        name = "user"
        indexes = [
            "user_id",
            "email",
            "api_token_hash",
        ]
