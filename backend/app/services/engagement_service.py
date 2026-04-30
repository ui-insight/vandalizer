"""User engagement service — onboarding drip + inactivity nudges + v5 launch funnel."""

import datetime
import logging

from app.config import Settings
from app.models.certification import CertificationProgress
from app.models.user import User
from app.services.email_service import (
    send_email,
    onboarding_drip_email,
    inactivity_nudge_email,
    v5_launch_announcement_email,
    agentic_chat_drip_email,
    certification_complete_email,
    powerup_milestone_email,
)

logger = logging.getLogger(__name__)

# Module IDs in certification order — used for the drip sequence
_DRIP_MODULES = [
    {
        "id": "ai_literacy",
        "title": "AI Literacy",
        "description": "start with the fundamentals: what AI actually is, what it's good and bad at, and how it applies to research administration.",
    },
    {
        "id": "foundations",
        "title": "Foundations: Your First Extraction",
        "description": "it's time to get hands-on. This module walks you through uploading a document and building your first extraction workflow.",
    },
    {
        "id": "process_mapping",
        "title": "Process Mapping",
        "description": "learn to identify which parts of your daily work are good candidates for automation and how to break them into workflow steps.",
    },
    {
        "id": "workflow_design",
        "title": "Workflow Design",
        "description": "build a multi-step workflow with extraction, prompt, and formatting tasks working together.",
    },
]

INACTIVITY_THRESHOLD_DAYS = 30
NUDGE_COOLDOWN_DAYS = 30  # don't nudge the same person more than once a month

# Drip schedule: days after first login to send each step
_DRIP_SCHEDULE_DAYS = [0, 3, 7, 14]


async def process_onboarding_drips(settings: Settings | None = None) -> int:
    """Send due onboarding drip emails. Returns count sent."""
    if settings is None:
        settings = Settings()

    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0

    # Find users with a pending drip (includes demo/trial users)
    users = await User.find(
        User.onboarding_drip_step < len(_DRIP_MODULES),
        User.onboarding_drip_next_at <= now,
    ).to_list()

    for user in users:
        if not user.email:
            continue
        prefs = user.email_preferences or {}
        if not prefs.get("onboarding", True):
            continue

        step = user.onboarding_drip_step  # 0-indexed, next step to send
        module = _DRIP_MODULES[step]

        # Skip if user already completed this module in certification
        cert = await CertificationProgress.find_one(
            CertificationProgress.user_id == user.user_id
        )
        if cert:
            module_data = cert.modules.get(module["id"], {})
            if module_data.get("completed"):
                # Skip ahead — find next incomplete module
                user.onboarding_drip_step = step + 1
                if step + 1 < len(_DRIP_MODULES):
                    user.onboarding_drip_next_at = now  # check again immediately
                else:
                    user.onboarding_drip_next_at = None
                await user.save()
                continue

        subject, html = onboarding_drip_email(
            name=user.name or user.user_id,
            step=step + 1,
            module_title=module["title"],
            module_description=module["description"],
            frontend_url=settings.frontend_url,
        )
        success = await send_email(user.email, subject, html, settings, email_type="onboarding_drip")
        if success:
            sent += 1

        # Advance to next step
        user.onboarding_drip_step = step + 1
        if step + 1 < len(_DRIP_MODULES):
            days_until_next = _DRIP_SCHEDULE_DAYS[step + 1] - _DRIP_SCHEDULE_DAYS[step]
            user.onboarding_drip_next_at = now + datetime.timedelta(days=days_until_next)
        else:
            user.onboarding_drip_next_at = None  # drip complete
        await user.save()

    if sent:
        logger.info("Sent %d onboarding drip emails", sent)
    return sent


async def process_inactivity_nudges(settings: Settings | None = None) -> int:
    """Send inactivity nudges to users who haven't logged in for 30+ days.

    Only sends if there are new verified catalog items since their last visit.
    Returns count sent.
    """
    if settings is None:
        settings = Settings()

    now = datetime.datetime.now(datetime.timezone.utc)
    threshold = now - datetime.timedelta(days=INACTIVITY_THRESHOLD_DAYS)
    sent = 0

    # Find inactive users who haven't been nudged recently
    nudge_cutoff = now - datetime.timedelta(days=NUDGE_COOLDOWN_DAYS)
    users = await User.find(
        User.last_login_at != None,  # noqa: E711
        User.last_login_at <= threshold,
        User.is_demo_user != True,  # noqa: E712
    ).to_list()

    for user in users:
        if not user.email:
            continue
        prefs = user.email_preferences or {}
        if not prefs.get("nudges", True):
            continue
        # Cooldown check
        if user.last_nudge_sent_at and user.last_nudge_sent_at > nudge_cutoff:
            continue

        # Find new verified items since their last login
        new_items = await _get_new_catalog_items_since(user.last_login_at)
        if not new_items:
            continue  # nothing new — don't send an empty nudge

        days_inactive = (now - user.last_login_at).days

        subject, html = inactivity_nudge_email(
            name=user.name or user.user_id,
            days_inactive=days_inactive,
            new_items=new_items,
            frontend_url=settings.frontend_url,
        )
        success = await send_email(user.email, subject, html, settings, email_type="inactivity_nudge")
        if success:
            sent += 1

        user.last_nudge_sent_at = now
        await user.save()

    if sent:
        logger.info("Sent %d inactivity nudge emails", sent)
    return sent


async def _get_new_catalog_items_since(
    since: datetime.datetime,
) -> list[dict]:
    """Return verified catalog items added since the given date."""
    from app.models.verification import VerificationRequest

    approved = await VerificationRequest.find(
        VerificationRequest.status == "approved",
        VerificationRequest.reviewed_at >= since,
    ).sort("-reviewed_at").limit(10).to_list()

    items = []
    for req in approved:
        name = await _get_item_name(req.item_kind, req.item_id)
        items.append({
            "name": name or "Untitled",
            "kind": req.item_kind,
        })
    return items


async def _get_item_name(item_kind: str, item_id) -> str | None:
    """Resolve a human-readable name for a catalog item."""
    from beanie import PydanticObjectId
    from app.models.workflow import Workflow
    from app.models.search_set import SearchSet
    from app.models.knowledge import KnowledgeBase

    try:
        obj_id = PydanticObjectId(str(item_id))
    except Exception:
        return None

    if item_kind == "workflow":
        obj = await Workflow.get(obj_id)
        return obj.name if obj else None
    elif item_kind == "search_set":
        obj = await SearchSet.get(obj_id)
        return obj.title if obj else None
    elif item_kind == "knowledge_base":
        obj = await KnowledgeBase.get(obj_id)
        return obj.name if obj else None
    return None


# ---------------------------------------------------------------------------
# v5.0 launch announcement — one-time send to existing users
# ---------------------------------------------------------------------------


async def process_v5_launch_announcement(
    settings: Settings | None = None, batch_size: int = 200,
) -> int:
    """Send the v5.0 launch email to each eligible user once. Returns count sent.

    Idempotent: records `v5_announcement_sent_at` on the user after a successful
    send so repeat runs skip users who already received it.
    """
    if settings is None:
        settings = Settings()

    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0

    users = await User.find(
        User.v5_announcement_sent_at == None,  # noqa: E711
        User.is_demo_user != True,  # noqa: E712
    ).limit(batch_size).to_list()

    for user in users:
        if not user.email:
            continue
        prefs = user.email_preferences or {}
        # Respect announcement opt-out if set; default to opted-in
        if prefs.get("announcements") is False:
            continue

        subject, html = v5_launch_announcement_email(
            name=user.name or user.user_id,
            frontend_url=settings.frontend_url,
        )
        success = await send_email(
            user.email, subject, html, settings, email_type="v5_announcement",
        )
        if success:
            user.v5_announcement_sent_at = now
            await user.save()
            sent += 1

    if sent:
        logger.info("Sent %d v5.0 launch announcement emails", sent)
    return sent


# ---------------------------------------------------------------------------
# Agentic-chat tutorial drip (5-step) — a product-feature drip parallel to
# the cert-module onboarding drip
# ---------------------------------------------------------------------------

_AGENTIC_DRIP_TOTAL_STEPS = 5
_AGENTIC_DRIP_SCHEDULE_DAYS = [0, 2, 5, 9, 14]


async def process_agentic_chat_drip(settings: Settings | None = None) -> int:
    """Send due agentic-chat tutorial emails. Returns count sent."""
    if settings is None:
        settings = Settings()

    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0

    users = await User.find(
        User.agentic_drip_step < _AGENTIC_DRIP_TOTAL_STEPS,
        User.agentic_drip_next_at <= now,
    ).to_list()

    for user in users:
        if not user.email:
            continue
        prefs = user.email_preferences or {}
        if not prefs.get("onboarding", True):
            continue

        step = user.agentic_drip_step  # 0-indexed; next step to send
        subject, html = agentic_chat_drip_email(
            name=user.name or user.user_id,
            step=step + 1,
            frontend_url=settings.frontend_url,
            role=user.role_segment,
        )
        success = await send_email(
            user.email, subject, html, settings, email_type="agentic_chat_drip",
        )
        if success:
            sent += 1

        user.agentic_drip_step = step + 1
        if step + 1 < _AGENTIC_DRIP_TOTAL_STEPS:
            days_until_next = (
                _AGENTIC_DRIP_SCHEDULE_DAYS[step + 1] - _AGENTIC_DRIP_SCHEDULE_DAYS[step]
            )
            user.agentic_drip_next_at = now + datetime.timedelta(days=days_until_next)
        else:
            user.agentic_drip_next_at = None
        await user.save()

    if sent:
        logger.info("Sent %d agentic-chat drip emails", sent)
    return sent


def start_agentic_chat_drip(user: User) -> None:
    """Enroll a user in the agentic-chat drip if they haven't been enrolled yet.

    Call this from registration / first-login hooks. Does not persist — caller
    must save the user.
    """
    if user.agentic_drip_next_at is None and user.agentic_drip_step == 0:
        user.agentic_drip_next_at = datetime.datetime.now(datetime.timezone.utc)


async def backfill_agentic_chat_drip(
    settings: Settings | None = None, batch_size: int = 500,
) -> int:
    """Enroll existing users into the agentic-chat drip (one-shot backfill).

    Skips users who are demo-only, already enrolled, or have opted out of
    onboarding emails. Returns count enrolled.
    """
    if settings is None:
        settings = Settings()

    now = datetime.datetime.now(datetime.timezone.utc)
    users = await User.find(
        User.agentic_drip_next_at == None,  # noqa: E711
        User.agentic_drip_step == 0,
        User.is_demo_user != True,  # noqa: E712
    ).limit(batch_size).to_list()

    enrolled = 0
    for user in users:
        prefs = user.email_preferences or {}
        if prefs.get("onboarding") is False:
            continue
        if not user.email:
            continue
        user.agentic_drip_next_at = now
        await user.save()
        enrolled += 1

    if enrolled:
        logger.info("Backfilled %d users into agentic-chat drip", enrolled)
    return enrolled


# ---------------------------------------------------------------------------
# Certification-complete notification
# ---------------------------------------------------------------------------


async def send_certification_complete_email_for(
    user: User, settings: Settings | None = None,
) -> bool:
    """Send a certification-complete celebration email. Idempotent per user."""
    if not user.email:
        return False
    if user.certification_complete_sent_at is not None:
        return False

    if settings is None:
        settings = Settings()

    subject, html = certification_complete_email(
        name=user.name or user.user_id,
        frontend_url=settings.frontend_url,
    )
    success = await send_email(
        user.email, subject, html, settings, email_type="certification_complete",
    )
    if success:
        user.certification_complete_sent_at = datetime.datetime.now(datetime.timezone.utc)
        await user.save()
    return success


# ---------------------------------------------------------------------------
# Chat-workflow milestone tracking (P2-13 trigger)
# ---------------------------------------------------------------------------

POWERUP_MILESTONE_THRESHOLD = 30


async def record_chat_workflow_run(user_id: str) -> None:
    """Increment a user's chat-workflow counter, recording first-run timestamp.

    Called from the agentic chat tool layer whenever `run_workflow` succeeds.
    Safe to call opportunistically — failures are logged but never raised.
    """
    try:
        user = await User.find_one(User.user_id == user_id)
        if not user:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        if user.first_chat_workflow_at is None:
            user.first_chat_workflow_at = now
        user.chat_workflow_count = (user.chat_workflow_count or 0) + 1
        await user.save()
    except Exception:
        logger.exception("Failed to record chat workflow run for %s", user_id)


async def process_powerup_milestones(settings: Settings | None = None) -> int:
    """Send the power-user upsell email to users who crossed the threshold.

    Idempotent per user via `powerup_milestone_sent_at`.
    """
    if settings is None:
        settings = Settings()

    users = await User.find(
        User.chat_workflow_count >= POWERUP_MILESTONE_THRESHOLD,
        User.powerup_milestone_sent_at == None,  # noqa: E711
    ).to_list()

    sent = 0
    now = datetime.datetime.now(datetime.timezone.utc)
    for user in users:
        if not user.email:
            continue
        prefs = user.email_preferences or {}
        if prefs.get("announcements") is False:
            continue
        subject, html = powerup_milestone_email(
            name=user.name or user.user_id,
            workflow_count=user.chat_workflow_count,
            frontend_url=settings.frontend_url,
        )
        success = await send_email(
            user.email, subject, html, settings, email_type="powerup_milestone",
        )
        if success:
            user.powerup_milestone_sent_at = now
            await user.save()
            sent += 1

    if sent:
        logger.info("Sent %d power-user milestone emails", sent)
    return sent
