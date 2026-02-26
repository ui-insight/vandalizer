from typing import Optional
from pydantic import BaseModel


class DemoSignupRequest(BaseModel):
    name: str
    title: str = ""
    email: str
    organization: str
    questionnaire_responses: dict = {}


class DemoSignupResponse(BaseModel):
    uuid: str
    waitlist_position: int
    message: str


class WaitlistStatusResponse(BaseModel):
    uuid: str
    status: str
    waitlist_position: Optional[int] = None
    estimated_wait: Optional[str] = None


class PostExperienceRequest(BaseModel):
    responses: dict


class PostExperienceResponseSchema(BaseModel):
    message: str


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
