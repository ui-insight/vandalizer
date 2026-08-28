import datetime
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


class DemoApplication(Document):
    uuid: str
    name: str
    title: str = ""
    email: str
    organization: str
    questionnaire_responses: dict = {}
    status: str = "pending"  # pending | approved | active | expired | completed
    waitlist_position: Optional[int] = None
    user_id: Optional[str] = None
    team_id: Optional[PydanticObjectId] = None
    activated_at: Optional[datetime.datetime] = None
    expires_at: Optional[datetime.datetime] = None
    expired_at: Optional[datetime.datetime] = None
    post_questionnaire_completed: bool = False
    post_questionnaire_token: Optional[str] = None
    admin_released: bool = False
    # The activation (or latest resend) email failed to send — surfaced on the
    # public status page so the applicant knows to hit resend rather than
    # seeing "active" with no way in. Cleared by a successful resend.
    activation_email_failed: bool = False
    # The ~80%-of-budget warning email was sent for the current budget window.
    # Reset by a top-up so the next window warns again.
    budget_warning_sent: bool = False
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    last_notified_position: Optional[int] = None

    # Recapture drip — emails sent to activated users who haven't logged in
    recapture_step: int = 0  # 0=not started, 1-3=sent step N
    recapture_next_at: Optional[datetime.datetime] = None  # when to send next recapture email

    # Self-serve renewals taken from the end-of-trial screen (capped)
    trial_extensions_used: int = 0

    class Settings:
        name = "demo_application"


class PostExperienceResponse(Document):
    uuid: str
    demo_application_id: PydanticObjectId
    responses: dict = {}
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

    class Settings:
        name = "post_experience_response"
