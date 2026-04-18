"""Demo waitlist service — manages applications, activation, expiry, and feedback."""

import datetime
import logging
import secrets
from typing import Optional


from app.config import Settings
from app.models.demo import DemoApplication, PostExperienceResponse
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.services.email_service import (
    send_email,
    test_email,
    waitlist_confirmation_email,
    activation_email,
    expiry_warning_email,
    trial_expired_email,
    recapture_email,
)
from app.utils.security import hash_password
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

MAX_ACTIVE_DEMOS = 50
MAX_PER_ORGANIZATION = 5
TRIAL_DAYS = 14


async def submit_application(
    name: str,
    email: str,
    organization: str,
    questionnaire_responses: dict,
    title: str = "",
    settings: Settings | None = None,
) -> DemoApplication:
    """Create a new demo application and send confirmation email."""
    if settings is None:
        settings = Settings()

    existing = await DemoApplication.find_one(DemoApplication.email == email)
    if existing:
        raise ValueError("An application with this email already exists")

    existing_user = await User.find_one(User.email == email)
    if existing_user:
        raise ValueError("An account with this email already exists")

    # Calculate waitlist position
    pending_count = await DemoApplication.find(
        DemoApplication.status == "pending"
    ).count()
    position = pending_count + 1

    app = DemoApplication(
        uuid=secrets.token_urlsafe(16),
        name=name,
        title=title,
        email=email,
        organization=organization.strip(),
        questionnaire_responses=questionnaire_responses,
        status="pending",
        waitlist_position=position,
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    await app.insert()

    # Send confirmation email
    subject, html = waitlist_confirmation_email(
        name, position, settings.frontend_url, app.uuid
    )
    await send_email(email, subject, html, settings)

    return app


async def get_waitlist_status(uuid: str) -> Optional[DemoApplication]:
    """Return current application status."""
    app = await DemoApplication.find_one(DemoApplication.uuid == uuid)
    if not app:
        return None

    # Recalculate position for pending apps
    if app.status == "pending":
        ahead = await DemoApplication.find(
            DemoApplication.status == "pending",
            DemoApplication.created_at < app.created_at,
        ).count()
        app.waitlist_position = ahead + 1

    return app


async def process_waitlist(settings: Settings | None = None) -> int:
    """Activate eligible waitlisted applications. Returns count activated."""
    if settings is None:
        settings = Settings()

    active_count = await DemoApplication.find(
        DemoApplication.status == "active"
    ).count()

    activated = 0
    while active_count < MAX_ACTIVE_DEMOS:
        # Find next eligible pending application (FIFO)
        pending = await DemoApplication.find(
            DemoApplication.status == "pending"
        ).sort("+created_at").to_list()

        candidate = None
        for p in pending:
            org_active = await DemoApplication.find(
                DemoApplication.organization == p.organization,
                DemoApplication.status == "active",
            ).count()
            if org_active < MAX_PER_ORGANIZATION:
                candidate = p
                break

        if not candidate:
            break

        await _activate_application(candidate, settings)
        active_count += 1
        activated += 1

    if activated:
        logger.info("Activated %d demo accounts", activated)
    return activated


async def _activate_application(app: DemoApplication, settings: Settings) -> None:
    """Create user account + team and mark application as active."""
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = now + datetime.timedelta(days=TRIAL_DAYS)
    password = secrets.token_urlsafe(10)

    # Create user
    user_id = app.email
    user = User(
        user_id=user_id,
        email=app.email,
        name=app.name,
        password_hash=hash_password(password),
        is_demo_user=True,
        demo_expires_at=expires_at,
        demo_status="active",
    )
    await user.insert()

    # Find or create team from org + department
    department = None
    responses = app.questionnaire_responses or {}
    ra_dept = responses.get("ra_department")
    if isinstance(ra_dept, list) and ra_dept:
        # Use the first selected department, skip generic answers
        for d in ra_dept:
            if d not in ("Other", "I'm not in research administration"):
                department = d
                break
    team = await _find_or_create_org_team(app.organization, user.user_id, department)

    # Add membership
    existing_membership = await TeamMembership.find_one(
        TeamMembership.team == team.id,
        TeamMembership.user_id == user.user_id,
    )
    if not existing_membership:
        await TeamMembership(
            team=team.id,
            user_id=user.user_id,
            role="member",
            created_at=now,
        ).insert()

    # Set user's current team
    user.current_team = team.id
    await user.save()

    # Update application
    app.status = "active"
    app.user_id = user.user_id
    app.team_id = team.id
    app.activated_at = now
    app.expires_at = expires_at
    await app.save()

    # Seed recapture drip — first email 24h after activation
    app.recapture_step = 0
    app.recapture_next_at = now + datetime.timedelta(days=_RECAPTURE_SCHEDULE_DAYS[0])
    await app.save()

    # Send activation email
    expires_str = expires_at.strftime("%B %d, %Y")
    subject, html = activation_email(
        app.name, user_id, password, expires_str, settings.frontend_url
    )
    await send_email(app.email, subject, html, settings)


async def _find_or_create_org_team(
    org_name: str, owner_user_id: str, department: str | None = None
) -> Team:
    """Find existing team for org+department or create a new one."""
    team_name = f"{org_name} - {department}" if department else org_name
    team = await Team.find_one(Team.name == team_name)
    if team:
        return team

    now = datetime.datetime.now(datetime.timezone.utc)
    team = Team(
        uuid=secrets.token_urlsafe(12),
        name=team_name,
        owner_user_id=owner_user_id,
        created_at=now,
    )
    await team.insert()

    # Owner membership
    await TeamMembership(
        team=team.id,
        user_id=owner_user_id,
        role="owner",
        created_at=now,
    ).insert()

    return team


async def check_expirations(settings: Settings | None = None) -> int:
    """Lock expired demo accounts and send feedback emails. Returns count expired."""
    if settings is None:
        settings = Settings()

    now = datetime.datetime.now(datetime.timezone.utc)
    expired_apps = await DemoApplication.find(
        DemoApplication.status == "active",
        DemoApplication.expires_at <= now,
    ).to_list()

    count = 0
    for app in expired_apps:
        # Update application
        app.status = "expired"
        app.expired_at = now
        app.post_questionnaire_token = secrets.token_urlsafe(16)
        await app.save()

        # Lock user account
        if app.user_id:
            user = await User.find_one(User.user_id == app.user_id)
            if user:
                user.demo_status = "locked"
                await user.save()

        # Send feedback email
        feedback_url = f"{settings.frontend_url}/demo/feedback?token={app.post_questionnaire_token}"
        subject, html = trial_expired_email(app.name, feedback_url)
        await send_email(app.email, subject, html, settings)
        count += 1

    if count:
        logger.info("Expired %d demo accounts", count)
    return count


async def send_expiry_warnings(settings: Settings | None = None) -> int:
    """Send warning emails to demos expiring in the next 2 days."""
    if settings is None:
        settings = Settings()

    now = datetime.datetime.now(datetime.timezone.utc)
    two_days = now + datetime.timedelta(days=2)

    apps = await DemoApplication.find(
        DemoApplication.status == "active",
        DemoApplication.expires_at <= two_days,
        DemoApplication.expires_at > now,
    ).to_list()

    count = 0
    for app in apps:
        if not app.expires_at:
            continue
        days_left = max(1, (app.expires_at - now).days)
        expires_str = app.expires_at.strftime("%B %d, %Y")
        subject, html = expiry_warning_email(
            app.name, days_left, expires_str, settings.frontend_url
        )
        await send_email(app.email, subject, html, settings)
        count += 1

    return count


async def submit_post_questionnaire(token: str, responses: dict) -> bool:
    """Save post-experience questionnaire response."""
    app = await DemoApplication.find_one(
        DemoApplication.post_questionnaire_token == token
    )
    if not app:
        return False

    await PostExperienceResponse(
        uuid=secrets.token_urlsafe(12),
        demo_application_id=app.id,
        responses=responses,
        created_at=datetime.datetime.now(datetime.timezone.utc),
    ).insert()

    app.post_questionnaire_completed = True
    app.status = "completed"
    await app.save()

    return True


async def get_feedback_application(token: str) -> Optional[DemoApplication]:
    """Validate a feedback token and return the associated application."""
    return await DemoApplication.find_one(
        DemoApplication.post_questionnaire_token == token
    )


async def resend_credentials(uuid: str, settings: Settings | None = None) -> bool:
    """Reset password and resend activation email for an active demo user."""
    if settings is None:
        settings = Settings()

    app = await DemoApplication.find_one(DemoApplication.uuid == uuid)
    if not app or app.status != "active" or not app.user_id:
        return False

    user = await User.find_one(User.user_id == app.user_id)
    if not user:
        return False

    # Generate new password and update
    password = secrets.token_urlsafe(10)
    user.password_hash = hash_password(password)
    await user.save()

    # Resend activation email with new credentials
    expires_str = app.expires_at.strftime("%B %d, %Y") if app.expires_at else "N/A"
    subject, html = activation_email(
        app.name, user.user_id, password, expires_str, settings.frontend_url
    )
    await send_email(app.email, subject, html, settings)

    logger.info("Resent credentials for demo user %s", app.email)
    return True


async def generate_magic_link(uuid: str, settings: Settings) -> str | None:
    """Generate a one-time magic login link for a demo user (24h TTL)."""
    app = await DemoApplication.find_one(DemoApplication.uuid == uuid)
    if not app or app.status != "active" or not app.user_id:
        return None

    user = await User.find_one(User.user_id == app.user_id)
    if not user:
        return None

    token = secrets.token_urlsafe(32)
    r = aioredis.from_url(f"redis://{settings.redis_host}:6379")
    try:
        await r.set(f"magic_login:{token}", user.user_id, ex=86400)  # 24 hours
    finally:
        await r.aclose()

    logger.info("Generated magic link for demo user %s", app.email)
    return f"{settings.frontend_url}/api/auth/magic-login?token={token}"


async def admin_release_user(demo_uuid: str) -> bool:
    """Admin: release an expired demo user so they can log in again."""
    app = await DemoApplication.find_one(DemoApplication.uuid == demo_uuid)
    if not app:
        return False

    app.admin_released = True
    app.status = "completed"
    await app.save()

    if app.user_id:
        user = await User.find_one(User.user_id == app.user_id)
        if user:
            user.demo_status = "active"
            await user.save()

    return True


async def admin_restart_trial(demo_uuid: str) -> bool:
    """Admin: restart the trial for an expired demo user (reset to 14 days)."""
    app = await DemoApplication.find_one(DemoApplication.uuid == demo_uuid)
    if not app or app.status not in ("active", "expired", "completed"):
        return False

    now = datetime.datetime.now(datetime.timezone.utc)
    new_expires = now + datetime.timedelta(days=TRIAL_DAYS)

    app.status = "active"
    app.expires_at = new_expires
    app.expired_at = None
    app.recapture_step = 0
    app.recapture_next_at = now + datetime.timedelta(days=_RECAPTURE_SCHEDULE_DAYS[0])
    await app.save()

    if app.user_id:
        user = await User.find_one(User.user_id == app.user_id)
        if user:
            user.demo_status = "active"
            user.demo_expires_at = new_expires
            await user.save()

    return True


async def admin_add_demo_user(
    first_name: str,
    last_name: str,
    email: str,
    settings: Settings | None = None,
) -> DemoApplication:
    """Admin: create a demo user directly, skipping the application/waitlist flow."""
    if settings is None:
        settings = Settings()

    existing = await DemoApplication.find_one(DemoApplication.email == email)
    if existing:
        raise ValueError("An application with this email already exists")

    existing_user = await User.find_one(User.email == email)
    if existing_user:
        raise ValueError("An account with this email already exists")

    name = f"{first_name} {last_name}"
    app = DemoApplication(
        uuid=secrets.token_urlsafe(16),
        name=name,
        email=email,
        organization="Direct Add",
        questionnaire_responses={},
        status="pending",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    await app.insert()

    await _activate_application(app, settings)
    return app


async def admin_activate_user(demo_uuid: str, settings: Settings | None = None) -> bool:
    """Admin: manually activate a waitlisted user (skip queue)."""
    if settings is None:
        settings = Settings()

    app = await DemoApplication.find_one(DemoApplication.uuid == demo_uuid)
    if not app or app.status != "pending":
        return False

    await _activate_application(app, settings)
    return True


async def admin_get_stats() -> dict:
    """Aggregate demo program statistics."""
    total = await DemoApplication.find().count()
    active = await DemoApplication.find(DemoApplication.status == "active").count()
    pending = await DemoApplication.find(DemoApplication.status == "pending").count()
    expired = await DemoApplication.find(DemoApplication.status == "expired").count()
    completed = await DemoApplication.find(DemoApplication.status == "completed").count()

    # Per-organization breakdown
    pipeline = [
        {"$group": {"_id": "$organization", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    org_results = await DemoApplication.aggregate(pipeline).to_list()
    by_org = [{"organization": r["_id"], "count": r["count"]} for r in org_results]

    return {
        "total_applications": total,
        "active_count": active,
        "waitlist_count": pending,
        "expired_count": expired,
        "completed_count": completed,
        "by_organization": by_org,
    }


async def admin_list_applications(status_filter: Optional[str] = None) -> list[dict]:
    """List all demo applications, optionally filtered by status."""
    query = {}
    if status_filter:
        query = DemoApplication.find(DemoApplication.status == status_filter)
    else:
        query = DemoApplication.find()

    apps = await query.sort("-created_at").to_list()
    return [
        {
            "uuid": a.uuid,
            "name": a.name,
            "email": a.email,
            "organization": a.organization,
            "status": a.status,
            "waitlist_position": a.waitlist_position,
            "activated_at": a.activated_at.isoformat() if a.activated_at else None,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            "post_questionnaire_completed": a.post_questionnaire_completed,
            "admin_released": a.admin_released,
            "created_at": a.created_at.isoformat(),
            "title": a.title or "",
            "questionnaire_responses": a.questionnaire_responses or {},
        }
        for a in apps
    ]


async def admin_list_post_responses() -> list[dict]:
    """List all post-experience responses with associated applicant info."""
    responses = await PostExperienceResponse.find().sort("-created_at").to_list()

    # Build lookup of demo applications by id
    app_ids = [r.demo_application_id for r in responses]
    apps = await DemoApplication.find({"_id": {"$in": app_ids}}).to_list()
    app_map = {a.id: a for a in apps}

    result = []
    for r in responses:
        app = app_map.get(r.demo_application_id)
        result.append({
            "uuid": r.uuid,
            "name": app.name if app else "Unknown",
            "email": app.email if app else "Unknown",
            "organization": app.organization if app else "Unknown",
            "title": app.title if app else "",
            "questionnaire_responses": app.questionnaire_responses if app else {},
            "responses": r.responses,
            "created_at": r.created_at.isoformat(),
        })
    return result


# ---------------------------------------------------------------------------
# Recapture drip — re-engage activated users who haven't logged in
# ---------------------------------------------------------------------------

_RECAPTURE_STEPS = 3
# Days after activation to send each step
_RECAPTURE_SCHEDULE_DAYS = [1, 4, 9]


async def process_recapture_drips(settings: Settings | None = None) -> int:
    """Send recapture emails to activated demo users who haven't logged in.

    Returns count of emails sent.
    """
    if settings is None:
        settings = Settings()

    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0

    # Find active demo apps with a pending recapture email due
    apps = await DemoApplication.find(
        DemoApplication.status == "active",
        DemoApplication.recapture_step < _RECAPTURE_STEPS,
        DemoApplication.recapture_next_at <= now,
    ).to_list()

    for app in apps:
        # Skip if the user has already logged in
        if app.user_id:
            user = await User.find_one(User.user_id == app.user_id)
            if user and user.last_login_at:
                # User logged in — stop the recapture sequence
                app.recapture_next_at = None
                await app.save()
                continue

        step = app.recapture_step + 1  # next step to send (1-indexed)
        resend_url = f"{settings.frontend_url}/demo/resend/{app.uuid}"

        subject, html = recapture_email(
            name=app.name,
            step=step,
            frontend_url=settings.frontend_url,
            resend_url=resend_url,
        )
        success = await send_email(app.email, subject, html, settings)
        if success:
            sent += 1

        # Advance to next step
        app.recapture_step = step
        if step < _RECAPTURE_STEPS:
            next_delay = _RECAPTURE_SCHEDULE_DAYS[step] - _RECAPTURE_SCHEDULE_DAYS[step - 1]
            app.recapture_next_at = now + datetime.timedelta(days=next_delay)
        else:
            app.recapture_next_at = None  # sequence complete
        await app.save()

    if sent:
        logger.info("Sent %d recapture emails", sent)
    return sent


async def enqueue_recapture_all(settings: Settings | None = None) -> int:
    """Admin: reset and enqueue recapture drips for all active demo users
    who have never logged in. Used to backfill after SMTP issues.

    Returns count of users enqueued.
    """
    if settings is None:
        settings = Settings()

    now = datetime.datetime.now(datetime.timezone.utc)
    enqueued = 0

    apps = await DemoApplication.find(
        DemoApplication.status == "active",
        DemoApplication.user_id != None,  # noqa: E711
    ).to_list()

    for app in apps:
        user = await User.find_one(User.user_id == app.user_id)
        if user and user.last_login_at:
            continue  # already logged in, skip

        # Reset the recapture sequence so it starts fresh
        app.recapture_step = 0
        app.recapture_next_at = now  # send first email on next processing cycle
        await app.save()
        enqueued += 1

    if enqueued:
        logger.info("Enqueued recapture drips for %d demo users", enqueued)
    return enqueued


async def send_test_email(to: str, settings: Settings | None = None) -> bool:
    """Send a deliverability test email to verify SMTP/spam-folder status."""
    if settings is None:
        settings = Settings()
    subject, html = test_email(to)
    return await send_email(to, subject, html, settings)


async def bulk_resend_credentials(settings: Settings | None = None) -> dict:
    """Reset passwords and resend activation emails for all active demo users
    who have never logged in. Returns counts of successes and failures."""
    if settings is None:
        settings = Settings()

    apps = await DemoApplication.find(
        DemoApplication.status == "active",
        DemoApplication.user_id != None,  # noqa: E711
    ).to_list()

    sent = 0
    skipped = 0
    failed = 0

    for app in apps:
        user = await User.find_one(User.user_id == app.user_id)
        if not user:
            failed += 1
            continue
        if user.last_login_at:
            skipped += 1
            continue

        # Reset trial expiration to 14 days from now
        now = datetime.datetime.now(datetime.timezone.utc)
        new_expires = now + datetime.timedelta(days=TRIAL_DAYS)
        app.expires_at = new_expires
        # Restart recapture drip so they get reminder emails
        app.recapture_step = 0
        app.recapture_next_at = now + datetime.timedelta(days=_RECAPTURE_SCHEDULE_DAYS[0])
        await app.save()

        # Generate new password and update user
        password = secrets.token_urlsafe(10)
        user.password_hash = hash_password(password)
        user.demo_expires_at = new_expires
        await user.save()

        expires_str = new_expires.strftime("%B %d, %Y")
        subject, html = activation_email(
            app.name, user.user_id, password, expires_str, settings.frontend_url
        )
        success = await send_email(app.email, subject, html, settings)
        if success:
            sent += 1
        else:
            failed += 1

    logger.info("Bulk resend: sent=%d skipped=%d failed=%d", sent, skipped, failed)
    return {"sent": sent, "skipped": skipped, "failed": failed}
