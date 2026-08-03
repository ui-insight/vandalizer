import datetime
from typing import Optional

from beanie import Document
from beanie import PydanticObjectId


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
    # Set ("oauth"/"saml") whenever the account signs in via an identity
    # provider. Once set, the provider owns the email: profile edits to it are
    # blocked, because every SSO login syncs the address back from the IdP.
    # password_hash alone can't tell — SSO users may also set a local password.
    sso_provider: Optional[str] = None
    # Incremented to invalidate all outstanding access/refresh tokens (e.g. on
    # password reset, email change, or account recovery). Tokens embed the value
    # they were minted with; get_current_user/refresh reject any token whose
    # version is stale.
    token_version: int = 0
    is_demo_user: bool = False
    demo_expires_at: Optional[datetime.datetime] = None
    demo_status: Optional[str] = None  # active | expired | locked
    organization_id: Optional[str] = None  # org uuid for university hierarchy

    # Engagement tracking
    last_login_at: Optional[datetime.datetime] = None
    first_session_completed: bool = False
    onboarding_drip_step: int = 0  # 0=not started, 1-4=sent step N
    onboarding_drip_next_at: Optional[datetime.datetime] = None  # when to send next drip
    last_nudge_sent_at: Optional[datetime.datetime] = None
    email_preferences: dict = {}  # {"onboarding": True, "nudges": True, "announcements": True}

    # v5.0 launch — one-time announcement send tracking
    v5_announcement_sent_at: Optional[datetime.datetime] = None

    # Agentic chat tutorial drip (separate from the cert-module onboarding drip)
    agentic_drip_step: int = 0  # 0=not started, 1-5=sent step N
    agentic_drip_next_at: Optional[datetime.datetime] = None

    # Chat-milestone tracking (powers post-launch engagement nudges)
    first_chat_workflow_at: Optional[datetime.datetime] = None
    chat_workflow_count: int = 0
    powerup_milestone_sent_at: Optional[datetime.datetime] = None  # 30-workflow upsell
    certification_complete_sent_at: Optional[datetime.datetime] = None

    # Role segmentation for drips (optional — set at registration or by admin)
    # Values: "research_admin", "pi", "sponsored_programs", "compliance", "it", "other"
    role_segment: Optional[str] = None

    class Settings:
        name = "user"
        indexes = [
            "user_id",
            "email",
            "api_token_hash",
        ]
