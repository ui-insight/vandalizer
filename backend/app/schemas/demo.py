from typing import Optional
from pydantic import BaseModel


class ResendCredentialsResponse(BaseModel):
    ok: bool
    # sent | send_failed | pending | exhausted | not_found
    status: str
    message: str
    email: Optional[str] = None
    feedback_token: Optional[str] = None


class PostExperienceRequest(BaseModel):
    responses: dict


class PostExperienceResponseSchema(BaseModel):
    message: str


class TrialEndInfoResponse(BaseModel):
    name: str
    organization: str
    engagement: str  # "low" | "engaged"
    extensions_used: int
    max_extensions: int
    can_self_extend: bool
    already_extended: bool
    # Token balance when the screen was opened, and what a top-up adds.
    tokens_used: int = 0
    tokens_budget: int = 0
    topup_tokens: int = 0


class TrialUsageResponse(BaseModel):
    """Trial token balance for the signed-in user.

    ``enabled`` is False for non-trial users and cap-disabled deployments; the
    other fields are zero then and must not be rendered.
    """

    enabled: bool
    budget: int
    used: int
    remaining: int
    percent: int
    # False means AI features are gated until the address is confirmed.
    email_verified: bool = True


class TrialExtensionRequest(BaseModel):
    notes: Optional[dict] = None


class TrialExtensionResponse(BaseModel):
    ok: bool
    message: str
    # Tokens added by this top-up, and the account's new lifetime ceiling.
    tokens_granted: Optional[int] = None
    tokens_budget: Optional[int] = None
    # One-time magic sign-in URL for the top-up screen's "Enter" button —
    # trial accounts have no known password, so this is their way back in.
    login_url: Optional[str] = None


class DemoApplicationResponse(BaseModel):
    uuid: str
    name: str
    email: str
    organization: str
    status: str
    waitlist_position: Optional[int] = None
    activated_at: Optional[str] = None
    expires_at: Optional[str] = None
    post_questionnaire_completed: bool = False
    admin_released: bool = False
    created_at: str


class AdminAddDemoUserRequest(BaseModel):
    first_name: str
    last_name: str
    email: str


class DemoAdminStatsResponse(BaseModel):
    total_applications: int
    active_count: int
    waitlist_count: int
    expired_count: int
    completed_count: int
    by_organization: list[dict]


class PostExperienceResponseDetail(BaseModel):
    uuid: str
    name: str
    email: str
    organization: str
    title: str = ""
    questionnaire_responses: dict = {}
    responses: dict
    created_at: str
