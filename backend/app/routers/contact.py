"""Public contact endpoints — always-on, independent of the trial system.

Split out from ``demo.py`` so the landing-page demo-request form works on
self-hosted installs that have the trial system disabled.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.config import Settings
from app.dependencies import get_settings
from app.services import email_service

logger = logging.getLogger(__name__)
router = APIRouter()


class DemoRequestContactRequest(BaseModel):
    """Payload for the public demo-request form on the landing page."""

    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    institution: str = Field(min_length=1, max_length=300)
    role: str = Field(min_length=1, max_length=100)
    message: str = Field(default="", max_length=5000)

    @field_validator("email")
    @classmethod
    def _has_at_sign(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Not a valid email address")
        return v


@router.post("/request-contact", status_code=status.HTTP_202_ACCEPTED)
async def request_contact(
    body: DemoRequestContactRequest,
    settings: Settings = Depends(get_settings),
):
    """Submit a landing-page demo request. Emails requester and admin notification."""
    admin_to = (
        settings.demo_request_to_email
        or settings.resend_from_email
        or settings.smtp_from_email
    )
    if not admin_to:
        logger.error("Demo-request submitted but no admin recipient configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo requests are temporarily unavailable. Please email us directly.",
        )

    admin_subject, admin_html = email_service.demo_request_admin_notification_email(
        name=body.name,
        email=body.email,
        institution=body.institution,
        role=body.role,
        message=body.message,
    )
    await email_service.send_email(
        to=admin_to,
        subject=admin_subject,
        html_body=admin_html,
        settings=settings,
        email_type="demo_request_admin",
    )

    conf_subject, conf_html = email_service.demo_request_confirmation_email(name=body.name)
    await email_service.send_email(
        to=body.email,
        subject=conf_subject,
        html_body=conf_html,
        settings=settings,
        email_type="demo_request_confirmation",
    )

    return {"ok": True}
