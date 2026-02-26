"""Demo waitlist service — manages applications, activation, expiry, and feedback."""

import datetime
import logging
import secrets
from typing import Optional

from beanie import PydanticObjectId

from app.config import Settings
from app.models.demo import DemoApplication, PostExperienceResponse
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.services.email_service import (
    send_email,
    waitlist_confirmation_email,
    activation_email,
    expiry_warning_email,
    trial_expired_email,
)
from app.utils.security import hash_password

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

    # Find or create org team
    team = await _find_or_create_org_team(app.organization, user.user_id)

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

    # Send activation email
    expires_str = expires_at.strftime("%B %d, %Y")
    subject, html = activation_email(
        app.name, user_id, password, expires_str, settings.frontend_url
    )
    await send_email(app.email, subject, html, settings)


async def _find_or_create_org_team(org_name: str, owner_user_id: str) -> Team:
    """Find existing Demo team for org or create a new one."""
    team_name = f"Demo - {org_name}"
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
