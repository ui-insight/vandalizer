"""Demo/trial service — a token-metered free tier.

The trial is a *budget*, not a clock: an account is included up to
``TRIAL_TOKEN_BUDGET`` LLM tokens (enforced live at the metering chokepoint in
``trial_budget.py``), tops up in ``TRIAL_TOPUP_TOKENS`` increments priced in
feedback, and never expires on a date. Running out is soft — the workspace
stays browsable and only LLM spend is gated — so there is no lockout and
nothing to rescue the user from.

This module owns application records, activation, the budget lifecycle sweep
(warning → exhausted → top-up), and the feedback loop around them.
"""

import datetime
import logging
import secrets
from typing import Optional


from app.config import Settings
from app.models.chat import ChatConversation
from app.models.demo import DemoApplication, PostExperienceResponse
from app.models.document import SmartDocument
from app.models.email_log import EmailLog
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.models.workflow import Workflow, WorkflowResult
from app.services.email_service import (
    send_email,
    test_email,
    activation_email,
    budget_warning_email,
    trial_exhausted_email,
    trial_topup_email,
    verify_email_email,
    recapture_email,
)
from app.services import trial_budget
from app.utils.security import hash_password
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Fraction of the budget that triggers the one-time "running low" email.
BUDGET_WARNING_THRESHOLD = 0.8

# Self-serve top-ups from the trial-end screen are unlimited; the counter is
# analytics only (kept under its historical name for stored records).
MAX_SELF_EXTENSIONS = 2
# A trial user who logged in but produced fewer than this many meaningful
# artifacts (documents + workflow runs + chats) "didn't really get a chance to
# try it" — the end screen offers them a frictionless one-click top-up.
LOW_ENGAGEMENT_MAX_ARTIFACTS = 3

# Magic sign-in links double as the primary credential for trial users, so they
# need to outlive a vacation, not expire in 48h.
MAGIC_LINK_TTL_SECONDS = 14 * 24 * 60 * 60

# Excludes look-alikes (I, O, i, l, o, 0, 1) so copied/typed passwords don't fail silently.
_UNAMBIGUOUS_ALPHABET = (
    "ABCDEFGHJKLMNPQRSTUVWXYZ"
    "abcdefghjkmnpqrstuvwxyz"
    "23456789"
)
_DEMO_PASSWORD_LENGTH = 14


def _generate_demo_password() -> str:
    """Generate a demo password using an alphabet free of look-alike characters."""
    return "".join(
        secrets.choice(_UNAMBIGUOUS_ALPHABET) for _ in range(_DEMO_PASSWORD_LENGTH)
    )


async def _create_magic_login_token(user_id: str, settings: Settings) -> str:
    """Create a one-time magic login URL (TTL = MAGIC_LINK_TTL_SECONDS)."""
    token = secrets.token_urlsafe(32)
    r = aioredis.from_url(f"redis://{settings.redis_host}:6379")
    try:
        await r.set(f"magic_login:{token}", user_id, ex=MAGIC_LINK_TTL_SECONDS)
    finally:
        await r.aclose()
    return f"{settings.frontend_url}/api/auth/magic-login?token={token}"


def _email_domain(email: str) -> str:
    """Bucket signups by email domain, so per-institution uptake is visible."""
    domain = (email or "").rsplit("@", 1)[-1].strip().lower()
    return domain or "self-registered"


async def begin_self_serve_trial(
    user: User, settings: Settings | None = None
) -> DemoApplication:
    """Start the token-metered trial for a user who registered directly.

    Marks the User as a trial account with the deployment's default token
    budget and mints — or adopts, for a *pending* application an admin created
    but never sent — an active DemoApplication. The application record is
    what the rest of the lifecycle keys on (the budget sweep, the trial-end
    screen, engagement scoring, the admin dashboard).

    Only a pending application is adopted. An exhausted or completed one
    belongs to a finished run: reviving it would silently hand a fresh budget
    to someone who already used theirs, so those keep their record and get a
    new one.
    """
    if settings is None:
        settings = Settings()

    now = datetime.datetime.now(datetime.timezone.utc)

    user.is_demo_user = True
    user.demo_status = "active"
    # Token-metered: no clock. The legacy field stays None for new trials.
    user.demo_expires_at = None
    user.trial_token_budget = settings.trial_token_budget
    await user.save()

    email = (user.email or user.user_id or "").strip().lower()
    existing = await DemoApplication.find_one(DemoApplication.email == email)
    if existing is not None and existing.status == "pending":
        existing.status = "active"
        existing.user_id = user.user_id
        existing.activated_at = now
        existing.expires_at = None
        existing.budget_warning_sent = False
        await existing.save()
        # Same gate as a fresh signup: adopting a pending record is still a
        # first sign-in, and without this the account is unverified with no
        # link ever sent — AI gated with nothing to click.
        await send_verification_email(user, existing, settings)
        return existing

    app = DemoApplication(
        uuid=secrets.token_urlsafe(16),
        name=user.name or email,
        email=email,
        organization=_email_domain(email),
        status="active",
        user_id=user.user_id,
        activated_at=now,
        created_at=now,
    )
    await app.insert()
    await send_verification_email(user, app, settings)
    return app


async def send_verification_email(
    user: User, app: DemoApplication, settings: Settings | None = None
) -> bool:
    """Email a new signup the link that confirms their address.

    Self-registration hands out a session immediately, so this is the only
    thing standing between "anyone can type an address" and unmetered spend on
    the deployment's keys — clicking the link both verifies the address and
    signs them in. SSO users never see this (the IdP asserts the address), and
    neither does anyone on a deployment with the trial system off.
    """
    if settings is None:
        settings = Settings()
    if user.email_verified:
        return True

    magic_link = await _create_magic_login_token(user.user_id, settings)
    subject, html = verify_email_email(
        user.name or app.name,
        magic_link,
        budget_tokens=settings.trial_token_budget,
    )
    sent = await send_email(
        app.email, subject, html, settings, email_type="verify_email"
    )
    if not sent:
        logger.error(
            "Verification email FAILED to send for trial user %s — they cannot "
            "use AI features until it is resent",
            app.email,
        )
    if app.activation_email_failed != (not sent):
        app.activation_email_failed = not sent
        await app.save()
    return sent


async def _activate_application(app: DemoApplication, settings: Settings) -> None:
    """Create user account + team and mark application as active."""
    now = datetime.datetime.now(datetime.timezone.utc)
    password = _generate_demo_password()

    # Create user. Normalize the identity to lowercase to match register()'s
    # convention — login lowercases the typed identity before a case-sensitive
    # lookup, so a mixed-case stored email would never be found.
    user_id = app.email.strip().lower()
    user = User(
        user_id=user_id,
        email=user_id,
        name=app.name,
        password_hash=hash_password(password),
        is_demo_user=True,
        demo_status="active",
        trial_token_budget=settings.trial_token_budget,
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
    team = await _find_or_create_org_team(
        app.organization, user.user_id, department, applicant_email=app.email
    )

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
    app.budget_warning_sent = False
    await app.save()

    # Seed recapture drip — first email 24h after activation
    app.recapture_step = 0
    app.recapture_next_at = now + datetime.timedelta(days=_RECAPTURE_SCHEDULE_DAYS[0])
    await app.save()

    # Send activation email. The account password is a random hash the user never
    # sees — sign-in is via the magic link (or a password they set later). Surface
    # send failures loudly: a silent failure leaves an active account whose owner
    # never got a way in.
    magic_link = await _create_magic_login_token(user_id, settings)
    subject, html = activation_email(
        app.name, user_id, settings.frontend_url,
        magic_link=magic_link,
        budget_tokens=settings.trial_token_budget,
    )
    sent = await send_email(
        app.email, subject, html, settings, email_type="demo_activation"
    )
    if not sent:
        logger.error(
            "Activation email FAILED to send for demo user %s (account is active "
            "but they have no way in — needs a resend)",
            app.email,
        )
    # Persisted so the public status page can tell the applicant the email
    # didn't go out and offer the resend button, instead of showing "active"
    # with no way in. Cleared by a successful resend.
    app.activation_email_failed = not sent
    await app.save()


def _login_domain(identity: str) -> str:
    """The email domain of a login identity, lowercased ('' when not an email)."""
    identity = (identity or "").strip().lower()
    return identity.rsplit("@", 1)[-1] if "@" in identity else ""


async def _can_join_demo_team(team: Team, applicant_email: str) -> bool:
    """Whether a demo applicant may be added to an existing team.

    Two gates, both required. The team must be demo-created — the org name on
    an application is self-asserted free text, and matching it against *any*
    team let an applicant type a real team's name and read its shared
    documents. And the applicant's email domain must match the team owner's:
    the domain is the one piece of the org claim the applicant actually
    demonstrated control of (they hold the magic-link inbox), so it, not the
    typed string, is what earns cohort membership.
    """
    if not team.is_demo_team:
        return False
    applicant_domain = _login_domain(applicant_email)
    if not applicant_domain:
        return False
    owner = await User.find_one(User.user_id == team.owner_user_id)
    owner_identity = (owner.email if owner and owner.email else team.owner_user_id)
    return _login_domain(owner_identity) == applicant_domain


async def _find_or_create_org_team(
    org_name: str,
    owner_user_id: str,
    department: str | None = None,
    applicant_email: str | None = None,
) -> Team:
    """Find a joinable demo cohort team for org+department, or create one.

    Only demo-created teams whose owner shares the applicant's email domain are
    ever joined (see _can_join_demo_team); anything else gets a fresh team,
    with a suffixed name if the plain one is already taken by a team the
    applicant may not join.
    """
    team_name = f"{org_name} - {department}" if department else org_name
    team = await Team.find_one(Team.name == team_name)
    if team and await _can_join_demo_team(team, applicant_email or owner_user_id):
        return team
    if team:
        # The name belongs to a team this applicant may not join — a real
        # (non-demo) team, or another domain's cohort. Keep names distinct so
        # members can tell the two workspaces apart.
        team_name = f"{team_name} ({secrets.token_hex(3)})"

    now = datetime.datetime.now(datetime.timezone.utc)
    team = Team(
        uuid=secrets.token_urlsafe(12),
        name=team_name,
        owner_user_id=owner_user_id,
        is_demo_team=True,
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


async def _adopt_clock_era_trial_users(now: datetime.datetime) -> int:
    """Migrate trial users from the 14-day-clock era onto token budgets.

    Two populations, both handled in place so no manual migration is needed:

    * users with no DemoApplication at all (registration once set only the User
      flags) get one minted;
    * users still carrying ``demo_expires_at`` get it cleared and a budget set,
      so a clock that already lapsed can never lock them.

    Already-``locked`` accounts are deliberately left locked: their unlock path
    is the trial-end screen, which now grants tokens.
    """
    users = await User.find(
        User.is_demo_user == True,  # noqa: E712 — Beanie query expression
        User.demo_status == "active",
    ).to_list()
    if not users:
        return 0

    settings_budget = trial_budget._budget()
    linked_user_ids = {
        app.user_id
        for app in await DemoApplication.find(
            DemoApplication.user_id != None  # noqa: E711 — Beanie query expression
        ).to_list()
    }

    migrated = 0
    for user in users:
        touched = False

        # Who predates the token model, decided before anything is rewritten:
        # a clock-era account still carries an expiry, or never got a
        # DemoApplication at all. A signup made under the token model has
        # neither property — begin_self_serve_trial leaves demo_expires_at
        # None and always mints a linked application.
        clock_era = (
            user.demo_expires_at is not None or user.user_id not in linked_user_ids
        )

        # Retire the clock; give anyone without one the deployment default.
        if user.demo_expires_at is not None:
            user.demo_expires_at = None
            touched = True
        if user.trial_token_budget is None and settings_budget:
            user.trial_token_budget = settings_budget
            touched = True
        # Grandfather clock-era trials past the new verification gate. They
        # signed up before it existed — most reached the product through an
        # emailed magic link anyway — and retroactively cutting off AI for
        # people mid-trial would be a far worse failure than the narrow abuse
        # the gate exists to stop.
        #
        # It must not reach anyone else. This sweep runs hourly, not once at
        # deploy, so an unbounded version verifies every new signup at the
        # next tick — the gate would disarm itself within the hour and the
        # feature would be decorative.
        if clock_era and not user.email_verified:
            user.email_verified = True
            touched = True
        if touched:
            await user.save()

        if user.user_id not in linked_user_ids:
            email = (user.email or user.user_id or "").strip().lower()
            app = await DemoApplication.find_one(DemoApplication.email == email)
            if app is None:
                await DemoApplication(
                    uuid=secrets.token_urlsafe(16),
                    name=user.name or email,
                    email=email,
                    organization=_email_domain(email),
                    status="active",
                    user_id=user.user_id,
                    activated_at=now,
                    created_at=now,
                ).insert()
            else:
                app.status = "active"
                app.user_id = user.user_id
                app.activated_at = app.activated_at or now
                app.expires_at = None
                await app.save()
            touched = True

        if touched:
            migrated += 1

    if migrated:
        logger.info("Migrated %d clock-era trial users to token budgets", migrated)
    return migrated


async def sweep_trial_budgets(settings: Settings | None = None) -> dict:
    """Walk active trial accounts and advance the token lifecycle.

    Two transitions, both driven by the ``llm_usage`` ledger:

    * crossing ``BUDGET_WARNING_THRESHOLD`` sends the one-time "running low"
      email (``budget_warning_sent`` keeps it one-time per budget window);
    * reaching the budget marks the application ``exhausted`` and emails the
      trial-end/top-up link.

    Exhaustion is deliberately *soft*: ``demo_status`` becomes ``exhausted``,
    not ``locked``. The user keeps full read access to everything they built —
    only LLM spend is gated, and that gate is already enforced live at the
    metering chokepoint. Returns {"warned": n, "exhausted": n}.
    """
    if settings is None:
        settings = Settings()

    now = datetime.datetime.now(datetime.timezone.utc)
    await _adopt_clock_era_trial_users(now)
    # Recompute the fleet-wide monthly ceiling; the hot path reads the cached
    # flag this writes (per-account budgets stay exact in between).
    await trial_budget.refresh_fleet_pause(settings)

    apps = await DemoApplication.find(DemoApplication.status == "active").to_list()
    warned = 0
    exhausted = 0

    for app in apps:
        if not app.user_id:
            continue
        user = await User.find_one(User.user_id == app.user_id)
        if not user or not user.is_demo_user:
            continue

        usage = await trial_budget.get_trial_usage(user)
        if not usage["enabled"]:
            continue

        if usage["remaining"] <= 0:
            app.status = "exhausted"
            app.expired_at = now
            app.post_questionnaire_token = (
                app.post_questionnaire_token or secrets.token_urlsafe(16)
            )
            await app.save()

            user.demo_status = "exhausted"
            await user.save()

            trial_end_url = (
                f"{settings.frontend_url}/demo/trial-end"
                f"?token={app.post_questionnaire_token}"
            )
            subject, html = trial_exhausted_email(app.name, trial_end_url)
            await send_email(
                app.email, subject, html, settings, email_type="trial_exhausted"
            )
            exhausted += 1
            continue

        if (
            not app.budget_warning_sent
            and usage["used"] >= usage["budget"] * BUDGET_WARNING_THRESHOLD
        ):
            subject, html = budget_warning_email(
                app.name, usage["used"], usage["budget"], settings.frontend_url
            )
            sent = await send_email(
                app.email, subject, html, settings, email_type="budget_warning"
            )
            if sent:
                app.budget_warning_sent = True
                await app.save()
                warned += 1

    if warned or exhausted:
        logger.info(
            "Trial budget sweep: %d warned, %d exhausted", warned, exhausted
        )
    return {"warned": warned, "exhausted": exhausted}


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


async def resend_credentials(uuid: str, settings: Settings | None = None) -> dict:
    """Resend a fresh sign-in link for a demo application.

    Returns a status dict the caller maps to UI/HTTP. Crucially this no longer
    rotates the user's password — every send was minting a new password and
    silently invalidating older emails, which is the root of "the password in
    this email doesn't work." Sign-in is via a fresh magic link instead.

    Status values:
      - "sent"        active trial → a new sign-in link was emailed
      - "send_failed" active trial but the email failed to send
      - "pending"     not yet activated; no credentials exist yet
      - "exhausted"   tokens used up → caller should route to the top-up screen
                      (feedback_token included)
      - "not_found"   no such application
    """
    if settings is None:
        settings = Settings()

    app = await DemoApplication.find_one(DemoApplication.uuid == uuid)
    if not app:
        return {"status": "not_found"}

    # Not yet activated → there are no credentials to resend.
    if app.status == "pending" or not app.user_id:
        return {"status": "pending"}

    # Out of tokens → point at the top-up screen rather than a sign-in link
    # (they can still sign in, but the thing they want is more tokens).
    # "expired" is the legacy clock-era status; treat it the same.
    if app.status in ("exhausted", "expired", "completed"):
        return {"status": "exhausted", "feedback_token": app.post_questionnaire_token}

    user = await User.find_one(User.user_id == app.user_id)
    if not user:
        return {"status": "not_found"}

    # Active → mint a fresh magic sign-in link (no password rotation). No token
    # figure here: this is a "here's your way back in" email, and quoting the
    # original allowance to someone mid-trial would misstate what's left.
    magic_link = await _create_magic_login_token(user.user_id, settings)
    subject, html = activation_email(
        app.name, user.user_id, settings.frontend_url, magic_link=magic_link
    )
    sent = await send_email(
        app.email, subject, html, settings, email_type="credentials_resend"
    )
    if not sent:
        logger.error("Resend sign-in link FAILED to send for demo user %s", app.email)
        app.activation_email_failed = True
        await app.save()
        return {"status": "send_failed", "email": app.email}

    logger.info("Resent sign-in link for demo user %s", app.email)
    if app.activation_email_failed:
        app.activation_email_failed = False
        await app.save()
    return {"status": "sent", "email": app.email}


async def generate_magic_link(uuid: str, settings: Settings) -> str | None:
    """Generate a one-time magic login link (TTL = MAGIC_LINK_TTL_SECONDS)."""
    app = await DemoApplication.find_one(DemoApplication.uuid == uuid)
    if not app or app.status != "active" or not app.user_id:
        return None

    user = await User.find_one(User.user_id == app.user_id)
    if not user:
        return None

    url = await _create_magic_login_token(user.user_id, settings)
    logger.info("Generated magic link for demo user %s", app.email)
    return url


async def admin_release_user(demo_uuid: str) -> bool:
    """Admin: release a finished trial user so they can use AI again.

    Clears the per-account budget cap (``trial_token_budget = 0``) rather than
    granting a fixed number of tokens — an admin release is "stop metering this
    person", not "give them one more helping".
    """
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
            user.demo_expires_at = None
            user.trial_token_budget = 0
            await user.save()

    return True


async def admin_promote_user(demo_uuid: str) -> bool:
    """Admin: convert a demo/trial user into a permanent full user.

    Clears the demo flags on the underlying User so the auth dependency stops
    gating them, and marks the DemoApplication as completed + released so it
    drops out of the active trial lifecycle (no expiry warnings, no recapture).
    """
    app = await DemoApplication.find_one(DemoApplication.uuid == demo_uuid)
    if not app:
        return False

    app.status = "completed"
    app.admin_released = True
    app.expired_at = None
    app.recapture_step = 0
    app.recapture_next_at = None
    await app.save()

    if app.user_id:
        user = await User.find_one(User.user_id == app.user_id)
        if user:
            user.is_demo_user = False
            user.demo_expires_at = None
            user.demo_status = None
            # Not a trial account any more — the budget must not follow them.
            user.trial_token_budget = None
            await user.save()

    return True


async def grant_tokens(user: User, amount: int) -> int:
    """Give a trial user `amount` more usable tokens; returns the new budget.

    Ledger usage is lifetime and never resets, so a grant raises the *budget*.
    Anchoring on ``max(budget, used)`` means the grant is worth exactly
    ``amount`` even when the last operation overshot the previous ceiling.
    """
    used = await trial_budget.tokens_used_async(user.user_id)
    current = user.trial_token_budget
    if current is None:
        current = trial_budget._budget()
    user.trial_token_budget = max(current, used) + amount
    user.demo_status = "active"
    user.demo_expires_at = None
    await user.save()
    return user.trial_token_budget


async def admin_restart_trial(demo_uuid: str) -> bool:
    """Admin: give a finished trial user a fresh full allowance of tokens."""
    app = await DemoApplication.find_one(DemoApplication.uuid == demo_uuid)
    if not app or app.status not in ("active", "exhausted", "expired", "completed"):
        return False

    now = datetime.datetime.now(datetime.timezone.utc)

    app.status = "active"
    app.expires_at = None
    app.expired_at = None
    app.budget_warning_sent = False
    app.recapture_step = 0
    app.recapture_next_at = now + datetime.timedelta(days=_RECAPTURE_SCHEDULE_DAYS[0])
    # A restart is a clean slate, including the self-serve top-up counter.
    app.trial_extensions_used = 0
    await app.save()

    if app.user_id:
        user = await User.find_one(User.user_id == app.user_id)
        if user:
            settings = Settings()
            await grant_tokens(user, settings.trial_token_budget)

    return True


async def compute_trial_engagement(user_id: str | None) -> str:
    """Classify how much a trial user actually used the product.

    Returns "low" if they never logged in or produced fewer than
    LOW_ENGAGEMENT_MAX_ARTIFACTS meaningful artifacts (documents + workflow runs
    + chats with messages), else "engaged".
    """
    if not user_id:
        return "low"

    user = await User.find_one(User.user_id == user_id)
    if not user or user.last_login_at is None:
        return "low"

    docs = await SmartDocument.find(SmartDocument.user_id == user_id).count()

    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    workflow_ids = [w.id for w in workflows]
    runs = (
        await WorkflowResult.find({"workflow": {"$in": workflow_ids}}).count()
        if workflow_ids
        else 0
    )

    chats = await ChatConversation.find(
        {"user_id": user_id, "messages": {"$ne": []}}
    ).count()

    total = docs + runs + chats
    return "low" if total < LOW_ENGAGEMENT_MAX_ARTIFACTS else "engaged"


async def get_trial_end_info(token: str) -> Optional[dict]:
    """Validate a trial-end token and return the data the top-up screen needs."""
    app = await DemoApplication.find_one(
        DemoApplication.post_questionnaire_token == token
    )
    if not app:
        return None

    engagement = await compute_trial_engagement(app.user_id)
    usage = {"enabled": False, "budget": 0, "used": 0, "remaining": 0, "percent": 0}
    if app.user_id:
        user = await User.find_one(User.user_id == app.user_id)
        if user:
            usage = await trial_budget.get_trial_usage(user)

    settings = Settings()
    return {
        "name": app.name,
        "organization": app.organization,
        "engagement": engagement,
        "extensions_used": app.trial_extensions_used,
        "max_extensions": MAX_SELF_EXTENSIONS,
        # Top-ups are unlimited — trial users can always keep going (engaged
        # users in exchange for a few notes). extensions_used is analytics only.
        "can_self_extend": True,
        "already_extended": app.trial_extensions_used > 0,
        "tokens_used": usage["used"],
        "tokens_budget": usage["budget"],
        "topup_tokens": settings.trial_topup_tokens,
    }


async def self_topup_trial(
    token: str, notes: dict | None = None, settings: Settings | None = None
) -> dict:
    """Self-serve token top-up from the trial-end screen.

    Grants ``TRIAL_TOPUP_TOKENS`` more usable tokens and returns the account to
    active. Top-ups are unlimited — low-engagement users take one with a click,
    engaged users in exchange for a few notes — and ``trial_extensions_used``
    is incremented for analytics only. Optional notes are persisted as a
    PostExperienceResponse. Returns {"ok": bool, ...}.
    """
    if settings is None:
        settings = Settings()

    app = await DemoApplication.find_one(
        DemoApplication.post_questionnaire_token == token
    )
    if not app:
        return {"ok": False, "reason": "invalid"}

    # Persist any notes the user left (reuses the feedback model).
    if notes:
        await PostExperienceResponse(
            uuid=secrets.token_urlsafe(12),
            demo_application_id=app.id,
            responses={"kind": "renewal_notes", **notes},
            created_at=datetime.datetime.now(datetime.timezone.utc),
        ).insert()

    now = datetime.datetime.now(datetime.timezone.utc)

    app.status = "active"
    app.expires_at = None
    app.expired_at = None
    app.trial_extensions_used += 1
    # Burn the link. This endpoint is unauthenticated by design — the token in
    # the out-of-tokens email *is* the credential — so a token that survived
    # its own use could be replayed to mint another grant on every call, which
    # is an unbounded spend budget wearing a top-up button. Rotating rather
    # than clearing keeps the field populated for the exhausted-user paths
    # that hand it back out; the next out-of-tokens email carries the new one,
    # and this run's own email gets the user back in by magic link anyway.
    app.post_questionnaire_token = secrets.token_urlsafe(16)
    # A fresh budget window gets a fresh "running low" warning, and a working
    # account shouldn't keep a stale delivery-failure flag.
    app.budget_warning_sent = False
    app.activation_email_failed = False
    app.recapture_step = 0
    app.recapture_next_at = now + datetime.timedelta(days=_RECAPTURE_SCHEDULE_DAYS[0])
    await app.save()

    new_budget = None
    if app.user_id:
        user = await User.find_one(User.user_id == app.user_id)
        if user:
            new_budget = await grant_tokens(user, settings.trial_topup_tokens)

    # Trial accounts have a random password the user never saw — a magic link
    # is their way back in, so the confirmation email and the screen's "Enter"
    # button both carry one instead of pointing at /login. Two separate tokens:
    # magic-login is one-time, and either path must survive the other being
    # used first.
    email_link = None
    screen_link = None
    if app.user_id:
        email_link = await _create_magic_login_token(app.user_id, settings)
        screen_link = await _create_magic_login_token(app.user_id, settings)

    # Confirmation email
    subject, html = trial_topup_email(
        app.name,
        new_budget or settings.trial_topup_tokens,
        settings.frontend_url,
        magic_link=email_link,
    )
    await send_email(app.email, subject, html, settings, email_type="trial_topup")

    logger.info(
        "Self-serve token top-up for %s (#%d, new budget %s)",
        app.email,
        app.trial_extensions_used,
        new_budget,
    )
    return {
        "ok": True,
        "tokens_granted": settings.trial_topup_tokens,
        "tokens_budget": new_budget,
        "login_url": screen_link,
    }


async def admin_add_demo_user(
    first_name: str,
    last_name: str,
    email: str,
    settings: Settings | None = None,
) -> DemoApplication:
    """Admin: create a trial user directly and send them a sign-in link."""
    if settings is None:
        settings = Settings()

    email = email.strip().lower()
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
    """Admin: activate an application an admin created but never sent."""
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
    # "expired" is the legacy clock-era status; count it alongside "exhausted"
    # so the dashboard total stays continuous across the migration.
    exhausted = await DemoApplication.find(
        {"status": {"$in": ["exhausted", "expired"]}}
    ).count()
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
        "expired_count": exhausted,
        "completed_count": completed,
        "by_organization": by_org,
    }


# Email types that deliver login credentials to a demo user. Used to compute
# the most recent "credentials sent" timestamp for the admin dashboard.
_CREDENTIAL_EMAIL_TYPES = (
    "demo_activation",
    "credentials_resend",
    "bulk_credentials_resend",
)


async def admin_list_applications(status_filter: Optional[str] = None) -> list[dict]:
    """List all demo applications, optionally filtered by status."""
    query = {}
    if status_filter:
        query = DemoApplication.find(DemoApplication.status == status_filter)
    else:
        query = DemoApplication.find()

    apps = await query.sort("-created_at").to_list()

    # Bulk-load login + credential-send timestamps so we don't issue 3 queries
    # per row on a list that may have hundreds of entries.
    user_ids = [a.user_id for a in apps if a.user_id]
    last_login_by_user: dict[str, datetime.datetime] = {}
    is_demo_by_user: dict[str, bool] = {}
    budget_by_user: dict[str, int] = {}
    tokens_by_user: dict[str, int] = {}
    if user_ids:
        users = await User.find({"user_id": {"$in": user_ids}}).to_list()
        last_login_by_user = {
            u.user_id: u.last_login_at for u in users if u.last_login_at
        }
        is_demo_by_user = {u.user_id: u.is_demo_user for u in users}
        budget_by_user = {
            u.user_id: trial_budget.effective_budget(u.trial_token_budget)
            for u in users
        }
        # One grouped pass over the ledger rather than a query per row.
        from app.models.llm_usage import LlmUsageRecord

        usage_rows = await LlmUsageRecord.find(
            {"user_id": {"$in": user_ids}}
        ).aggregate(
            [{"$group": {"_id": "$user_id", "total": {"$sum": "$total_tokens"}}}]
        ).to_list()
        tokens_by_user = {r["_id"]: int(r["total"]) for r in usage_rows}

    emails = [a.email for a in apps if a.email]
    creds_sent_by_email: dict[str, datetime.datetime] = {}
    if emails:
        cred_logs = await EmailLog.find(
            {
                "recipient": {"$in": emails},
                "email_type": {"$in": list(_CREDENTIAL_EMAIL_TYPES)},
                "status": "sent",
            }
        ).sort("-created_at").to_list()
        for log in cred_logs:
            # First (most recent) hit per recipient wins because of the sort.
            if log.recipient not in creds_sent_by_email:
                creds_sent_by_email[log.recipient] = log.created_at

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
            "tokens_used": tokens_by_user.get(a.user_id or "", 0),
            "tokens_budget": budget_by_user.get(a.user_id or "", 0),
            "post_questionnaire_completed": a.post_questionnaire_completed,
            "admin_released": a.admin_released,
            "created_at": a.created_at.isoformat(),
            "title": a.title or "",
            "questionnaire_responses": a.questionnaire_responses or {},
            "credentials_sent_at": (
                creds_sent_by_email[a.email].isoformat()
                if a.email in creds_sent_by_email
                else None
            ),
            "last_login_at": (
                last_login_by_user[a.user_id].isoformat()
                if a.user_id and a.user_id in last_login_by_user
                else None
            ),
            "user_is_demo": (
                is_demo_by_user.get(a.user_id, True) if a.user_id else True
            ),
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

    if not settings.promotional_emails_enabled:
        logger.info("Promotional email disabled — skipping recapture drips")
        return 0

    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0

    # Find active demo apps with a pending recapture email due
    apps = await DemoApplication.find(
        DemoApplication.status == "active",
        DemoApplication.recapture_step < _RECAPTURE_STEPS,
        DemoApplication.recapture_next_at <= now,
    ).to_list()

    for app in apps:
        if app.user_id:
            user = await User.find_one(User.user_id == app.user_id)
            if user and user.last_login_at:
                # User logged in — stop the recapture sequence
                app.recapture_next_at = None
                await app.save()
                continue
            # Honor the same opt-out the other nudge campaigns respect. Opting
            # out ends the sequence rather than deferring it, so the app stops
            # coming back as due on every daily run.
            prefs = (user.email_preferences or {}) if user else {}
            if not prefs.get("nudges", True):
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
        success = await send_email(app.email, subject, html, settings, email_type="recapture")
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
    return await send_email(to, subject, html, settings, email_type="deliverability_test")


async def bulk_resend_credentials(settings: Settings | None = None) -> dict:
    """Resend fresh magic sign-in links to all active demo users who have
    never logged in (no password rotation). Returns success/failure counts."""
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

        # These users never got in, so their budget is untouched — there is
        # nothing to top up. Just restart the recapture drip so they get
        # reminder emails alongside the fresh sign-in link.
        now = datetime.datetime.now(datetime.timezone.utc)
        app.recapture_step = 0
        app.recapture_next_at = now + datetime.timedelta(days=_RECAPTURE_SCHEDULE_DAYS[0])
        await app.save()

        # Do NOT rotate the password — rotating here was invalidating the
        # sign-in details users already had. A fresh magic link is all they need.
        magic_link = await _create_magic_login_token(user.user_id, settings)
        usage = await trial_budget.get_trial_usage(user)
        subject, html = activation_email(
            app.name, user.user_id, settings.frontend_url,
            magic_link=magic_link,
            budget_tokens=usage["remaining"] if usage["enabled"] else None,
        )
        success = await send_email(app.email, subject, html, settings, email_type="bulk_credentials_resend")
        # Same contract as the public resend: the status page shows the
        # delivery-failed alert while this flag is set, so a bulk resend after
        # fixing deliverability must clear it (and a failed one must set it).
        if app.activation_email_failed != (not success):
            app.activation_email_failed = not success
            await app.save()
        if success:
            sent += 1
        else:
            failed += 1

    logger.info("Bulk resend: sent=%d skipped=%d failed=%d", sent, skipped, failed)
    return {"sent": sent, "skipped": skipped, "failed": failed}
