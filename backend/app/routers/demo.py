"""Demo waitlist API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models.user import User
from app.schemas.demo import (
    DemoSignupRequest,
    DemoSignupResponse,
    WaitlistStatusResponse,
    PostExperienceRequest,
    PostExperienceResponseSchema,
    DemoAdminStatsResponse,
)
from app.services import demo_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Public endpoints (no auth required)
# ---------------------------------------------------------------------------


@router.post("/apply", response_model=DemoSignupResponse)
async def apply(body: DemoSignupRequest, settings: Settings = Depends(get_settings)):
    """Submit a demo application."""
    try:
        app = await demo_service.submit_application(
            name=body.name,
            email=body.email,
            organization=body.organization,
            questionnaire_responses=body.questionnaire_responses,
            title=body.title,
            settings=settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return DemoSignupResponse(
        uuid=app.uuid,
        waitlist_position=app.waitlist_position or 1,
        message="Application received! Check your email for confirmation.",
    )


@router.get("/status/{uuid}", response_model=WaitlistStatusResponse)
async def waitlist_status(uuid: str):
    """Check demo waitlist status."""
    app = await demo_service.get_waitlist_status(uuid)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )

    estimated = None
    if app.status == "pending" and app.waitlist_position:
        # Rough estimate: ~5 activations per processing cycle
        estimated = f"Approximately {app.waitlist_position * 1} day(s)"

    return WaitlistStatusResponse(
        uuid=app.uuid,
        status=app.status,
        waitlist_position=app.waitlist_position if app.status == "pending" else None,
        estimated_wait=estimated,
    )


@router.get("/feedback/{token}")
async def get_feedback(token: str):
    """Validate a feedback token and return application info."""
    app = await demo_service.get_feedback_application(token)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid feedback token"
        )
    return {
        "name": app.name,
        "organization": app.organization,
        "already_completed": app.post_questionnaire_completed,
    }


@router.post("/resend-credentials/{uuid}")
async def resend_credentials(uuid: str, settings: Settings = Depends(get_settings)):
    """Resend login credentials to the email on file for an active demo user."""
    success = await demo_service.resend_credentials(uuid, settings)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found or not in active status",
        )
    return {"ok": True, "message": "New credentials sent to your email on file."}


@router.post("/feedback/{token}", response_model=PostExperienceResponseSchema)
async def submit_feedback(token: str, body: PostExperienceRequest):
    """Submit post-experience questionnaire."""
    success = await demo_service.submit_post_questionnaire(token, body.responses)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid feedback token"
        )
    return PostExperienceResponseSchema(
        message="Thank you for your feedback!"
    )


# ---------------------------------------------------------------------------
# Admin endpoints (require auth + is_admin)
# ---------------------------------------------------------------------------


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )


@router.get("/admin/stats", response_model=DemoAdminStatsResponse)
async def admin_stats(user: User = Depends(get_current_user)):
    """Get demo program statistics."""
    _require_admin(user)
    stats = await demo_service.admin_get_stats()
    return DemoAdminStatsResponse(**stats)


@router.get("/admin/responses")
async def admin_responses(user: User = Depends(get_current_user)):
    """List all post-experience responses with applicant info."""
    _require_admin(user)
    return await demo_service.admin_list_post_responses()


@router.get("/admin/applications")
async def admin_applications(
    status_filter: str | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
):
    """List all demo applications."""
    _require_admin(user)
    return await demo_service.admin_list_applications(status_filter)


@router.post("/admin/release/{demo_uuid}")
async def admin_release(demo_uuid: str, user: User = Depends(get_current_user)):
    """Manually release an expired demo user."""
    _require_admin(user)
    success = await demo_service.admin_release_user(demo_uuid)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )
    return {"ok": True}


@router.post("/admin/activate/{demo_uuid}")
async def admin_activate(
    demo_uuid: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Manually activate a waitlisted user (skip queue)."""
    _require_admin(user)
    success = await demo_service.admin_activate_user(demo_uuid, settings)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Application not found or not in pending status",
        )
    return {"ok": True}


@router.post("/admin/recapture")
async def admin_trigger_recapture(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Enqueue recapture drips for all active demo users who haven't logged in.

    Use this after fixing SMTP issues to re-engage users who missed emails.
    """
    _require_admin(user)
    count = await demo_service.enqueue_recapture_all(settings)
    return {"ok": True, "enqueued": count}
