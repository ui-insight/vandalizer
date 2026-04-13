"""User engagement service — onboarding drip + inactivity nudges."""

import datetime
import logging

from app.config import Settings
from app.models.certification import CertificationProgress
from app.models.user import User
from app.services.email_service import (
    send_email,
    onboarding_drip_email,
    inactivity_nudge_email,
)

logger = logging.getLogger(__name__)

# Module IDs in certification order — used for the drip sequence
_DRIP_MODULES = [
    {
        "id": "ai_literacy",
        "title": "AI Literacy",
        "description": "start with the fundamentals — what AI actually is, what it's good and bad at, and how it applies to research administration.",
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
        success = await send_email(user.email, subject, html, settings)
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
        success = await send_email(user.email, subject, html, settings)
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
