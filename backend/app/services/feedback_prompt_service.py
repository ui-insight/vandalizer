"""Service for trial feedback prompt evaluation and delivery."""

import datetime
import logging
from typing import Optional

from app.models.feedback_prompt import FeedbackPrompt, FeedbackPromptResponse, TriggerRules
from app.models.support import SupportMessage, SupportTicket
from app.models.user import User

logger = logging.getLogger(__name__)

SYSTEM_USER_ID = "__vandalizer_team__"
SYSTEM_USER_NAME = "Vandalizer Team"

# Trial duration matches demo_service.TRIAL_DAYS
TRIAL_DAYS = 14


# ------------------------------------------------------------------
# Evaluate which prompt (if any) should be shown
# ------------------------------------------------------------------

async def evaluate_eligible_prompt(
    user: User,
    onboarding_status: dict,
) -> Optional[dict]:
    """Return the single highest-priority eligible prompt for this user, or None."""
    if not user.is_demo_user or not user.demo_expires_at:
        return None

    expires_at = user.demo_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
    activation_date = expires_at - datetime.timedelta(days=TRIAL_DAYS)
    now = datetime.datetime.now(datetime.timezone.utc)
    trial_day = max(0, (now - activation_date).days)

    # Load all enabled prompts, ordered by priority
    prompts = await FeedbackPrompt.find(
        FeedbackPrompt.enabled == True,  # noqa: E712
    ).sort("+priority").to_list()

    if not prompts:
        return None

    # Load all existing responses for this user
    existing = await FeedbackPromptResponse.find(
        FeedbackPromptResponse.user_id == user.user_id,
    ).to_list()
    existing_by_slug = {r.prompt_slug: r for r in existing}

    # Find the most recent shown_at across all prompts for cooldown
    last_shown_at: Optional[datetime.datetime] = None
    for r in existing:
        shown = r.shown_at
        if shown is None:
            continue
        if shown.tzinfo is None:
            shown = shown.replace(tzinfo=datetime.timezone.utc)
        if last_shown_at is None or shown > last_shown_at:
            last_shown_at = shown

    for prompt in prompts:
        # Skip if already processed
        resp = existing_by_slug.get(prompt.slug)
        if resp and resp.status in ("shown", "responded", "dismissed"):
            continue

        # Evaluate trigger rules
        if not _check_rules(prompt.trigger_rules, trial_day, onboarding_status, last_shown_at, now):
            continue

        return {
            "slug": prompt.slug,
            "question_text": prompt.question_text,
            "subject": prompt.subject,
            "stage": prompt.stage,
        }

    return None


def _check_rules(
    rules: TriggerRules,
    trial_day: int,
    onboarding: dict,
    last_shown_at: Optional[datetime.datetime],
    now: datetime.datetime,
) -> bool:
    """Return True if all trigger conditions are met."""
    if trial_day < rules.min_trial_day or trial_day > rules.max_trial_day:
        return False

    for milestone in rules.required_milestones:
        if not onboarding.get(milestone, False):
            return False

    for milestone in rules.forbidden_milestones:
        if onboarding.get(milestone, False):
            return False

    if rules.cooldown_hours > 0 and last_shown_at:
        hours_since = (now - last_shown_at).total_seconds() / 3600
        if hours_since < rules.cooldown_hours:
            return False

    return True


# ------------------------------------------------------------------
# Show / dismiss / respond
# ------------------------------------------------------------------

async def show_prompt(user: User, slug: str) -> Optional[dict]:
    """Create a support ticket for the prompt and record that it was shown.

    Returns ``{"ticket_uuid": ..., "response_uuid": ...}`` or None if the
    prompt doesn't exist.  Idempotent — if already shown, returns the
    existing ticket.
    """
    prompt = await FeedbackPrompt.find_one(FeedbackPrompt.slug == slug)
    if not prompt:
        return None

    # Check for existing response (idempotent)
    existing = await FeedbackPromptResponse.find_one(
        FeedbackPromptResponse.user_id == user.user_id,
        FeedbackPromptResponse.prompt_slug == slug,
    )
    if existing and existing.ticket_uuid:
        return {"ticket_uuid": existing.ticket_uuid, "response_uuid": existing.uuid}

    now = datetime.datetime.now(datetime.timezone.utc)

    # Create the support ticket
    ticket = SupportTicket(
        subject=f"[Check-in] {prompt.subject}",
        user_id=user.user_id,
        user_name=user.name or user.user_id,
        user_email=user.email,
        team_id=str(user.current_team) if user.current_team else None,
        category="feedback_prompt",
        messages=[
            SupportMessage(
                user_id=SYSTEM_USER_ID,
                user_name=SYSTEM_USER_NAME,
                content=prompt.question_text,
                is_support_reply=True,
            ),
        ],
    )
    await ticket.insert()

    # Create or update the response record
    if existing:
        existing.status = "shown"
        existing.ticket_uuid = ticket.uuid
        existing.shown_at = now
        await existing.save()
        response_uuid = existing.uuid
    else:
        resp = FeedbackPromptResponse(
            user_id=user.user_id,
            prompt_slug=slug,
            status="shown",
            ticket_uuid=ticket.uuid,
            shown_at=now,
        )
        await resp.insert()
        response_uuid = resp.uuid

    return {"ticket_uuid": ticket.uuid, "response_uuid": response_uuid}


async def dismiss_prompt(user: User, slug: str) -> bool:
    """Mark a prompt as dismissed. Returns True on success."""
    resp = await FeedbackPromptResponse.find_one(
        FeedbackPromptResponse.user_id == user.user_id,
        FeedbackPromptResponse.prompt_slug == slug,
    )
    if not resp:
        return False

    resp.status = "dismissed"
    resp.dismissed_at = datetime.datetime.now(datetime.timezone.utc)
    await resp.save()
    return True


async def mark_responded(ticket_uuid: str) -> None:
    """Called when a user replies to a feedback prompt ticket."""
    resp = await FeedbackPromptResponse.find_one(
        FeedbackPromptResponse.ticket_uuid == ticket_uuid,
        FeedbackPromptResponse.status == "shown",
    )
    if resp:
        resp.status = "responded"
        resp.responded_at = datetime.datetime.now(datetime.timezone.utc)
        await resp.save()


# ------------------------------------------------------------------
# Admin helpers
# ------------------------------------------------------------------

async def get_admin_overview() -> list[dict]:
    """Return per-prompt stats for the admin dashboard."""
    prompts = await FeedbackPrompt.find().sort("+priority").to_list()
    all_responses = await FeedbackPromptResponse.find().to_list()

    # Group responses by slug
    by_slug: dict[str, list[FeedbackPromptResponse]] = {}
    for r in all_responses:
        by_slug.setdefault(r.prompt_slug, []).append(r)

    result = []
    for p in prompts:
        responses = by_slug.get(p.slug, [])
        shown = sum(1 for r in responses if r.status in ("shown", "responded"))
        responded = sum(1 for r in responses if r.status == "responded")
        dismissed = sum(1 for r in responses if r.status == "dismissed")
        result.append({
            "slug": p.slug,
            "stage": p.stage,
            "subject": p.subject,
            "question_text": p.question_text,
            "enabled": p.enabled,
            "priority": p.priority,
            "trigger_rules": p.trigger_rules.model_dump(),
            "stats": {
                "shown": shown,
                "responded": responded,
                "dismissed": dismissed,
                "response_rate": round(responded / shown, 2) if shown > 0 else 0,
            },
        })
    return result


async def admin_update_prompt(slug: str, updates: dict) -> Optional[dict]:
    """Update a prompt's editable fields. Returns updated prompt or None."""
    prompt = await FeedbackPrompt.find_one(FeedbackPrompt.slug == slug)
    if not prompt:
        return None

    allowed = {"question_text", "subject", "enabled", "priority", "trigger_rules"}
    for key, value in updates.items():
        if key not in allowed:
            continue
        if key == "trigger_rules" and isinstance(value, dict):
            prompt.trigger_rules = TriggerRules(**value)
        else:
            setattr(prompt, key, value)

    prompt.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await prompt.save()
    return {
        "slug": prompt.slug,
        "stage": prompt.stage,
        "subject": prompt.subject,
        "question_text": prompt.question_text,
        "enabled": prompt.enabled,
        "priority": prompt.priority,
        "trigger_rules": prompt.trigger_rules.model_dump(),
    }


# ------------------------------------------------------------------
# Seed defaults
# ------------------------------------------------------------------

DEFAULT_PROMPTS = [
    {
        "slug": "welcome_checkin",
        "stage": "early",
        "subject": "Welcome Check-in",
        "question_text": (
            "Welcome to Vandalizer! We're glad you're here. "
            "What's the first task or problem you're hoping to solve with this tool? "
            "Understanding your goals will help us support you better."
        ),
        "trigger_rules": TriggerRules(min_trial_day=1, max_trial_day=2, cooldown_hours=0),
        "priority": 10,
    },
    {
        "slug": "first_upload",
        "stage": "early",
        "subject": "First Upload",
        "question_text": (
            "You've uploaded your first document \u2014 nice! "
            "How easy was it to find what you needed in the interface? "
            "Was anything confusing or hard to locate?"
        ),
        "trigger_rules": TriggerRules(
            min_trial_day=2, max_trial_day=4, cooldown_hours=24,
            required_milestones=["has_documents"],
        ),
        "priority": 20,
    },
    {
        "slug": "stuck_check",
        "stage": "early",
        "subject": "Need a Hand?",
        "question_text": (
            "It looks like you haven't tried workflows or extraction sets yet. "
            "Is there something you're having trouble with, or would you like "
            "a quick walkthrough of these features?"
        ),
        "trigger_rules": TriggerRules(
            min_trial_day=3, max_trial_day=5, cooldown_hours=24,
            forbidden_milestones=["has_workflows", "has_extraction_sets"],
        ),
        "priority": 30,
    },
    {
        "slug": "workflow_feedback",
        "stage": "mid",
        "subject": "Workflow Feedback",
        "question_text": (
            "You've run a workflow \u2014 great! How well did the results "
            "match what you expected? Is there anything about the workflow "
            "experience you'd change?"
        ),
        "trigger_rules": TriggerRules(
            min_trial_day=4, max_trial_day=9, cooldown_hours=48,
            required_milestones=["has_run_workflow"],
        ),
        "priority": 40,
    },
    {
        "slug": "extraction_feedback",
        "stage": "mid",
        "subject": "Extraction Feedback",
        "question_text": (
            "You've set up an extraction set. How accurate were the extracted "
            "results? Were there any fields that were tricky to define or that "
            "didn't extract well?"
        ),
        "trigger_rules": TriggerRules(
            min_trial_day=4, max_trial_day=9, cooldown_hours=48,
            required_milestones=["has_extraction_sets"],
        ),
        "priority": 50,
    },
    {
        "slug": "midtrial_checkin",
        "stage": "mid",
        "subject": "Mid-Trial Check-in",
        "question_text": (
            "You're about halfway through your trial. How's it going so far? "
            "Is there a feature you wish Vandalizer had, or something you "
            "expected that isn't here?"
        ),
        "trigger_rules": TriggerRules(min_trial_day=6, max_trial_day=9, cooldown_hours=72),
        "priority": 60,
    },
    {
        "slug": "value_assessment",
        "stage": "late",
        "subject": "Value Assessment",
        "question_text": (
            "Your trial wraps up soon. Has Vandalizer helped you accomplish "
            "what you set out to do? If you could keep using it, how would "
            "it fit into your regular work?"
        ),
        "trigger_rules": TriggerRules(min_trial_day=10, max_trial_day=12, cooldown_hours=72),
        "priority": 70,
    },
    {
        "slug": "recommendation",
        "stage": "late",
        "subject": "Recommendation",
        "question_text": (
            "One last question: On a scale from 1\u201310, how likely would you "
            "be to recommend Vandalizer to a colleague? What's the main reason "
            "for your score?"
        ),
        "trigger_rules": TriggerRules(min_trial_day=12, max_trial_day=14, cooldown_hours=48),
        "priority": 80,
    },
]


async def seed_default_prompts() -> int:
    """Insert default prompts that don't already exist. Returns count inserted."""
    inserted = 0
    for defn in DEFAULT_PROMPTS:
        existing = await FeedbackPrompt.find_one(FeedbackPrompt.slug == defn["slug"])
        if existing:
            continue
        prompt = FeedbackPrompt(**defn)
        await prompt.insert()
        inserted += 1

    if inserted:
        logger.info("Seeded %d default feedback prompts", inserted)
    return inserted
