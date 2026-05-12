"""Morning Briefing service — daily personalized digest of activity + KB news.

Aggregates the user's last-24h activity, their team's activity, and recently
verified KB items. Caps at 5 items, dedups across days, and falls back to
curated primer content for trial users when nothing real is available.

The same Briefing record powers both surfaces:
  - 8am email (Celery task in engagement_tasks.send_morning_briefings)
  - In-app chat card (router in app/routers/briefings.py)
"""

import datetime
import logging
from collections import Counter
from typing import Optional

from beanie import PydanticObjectId
from beanie.operators import In

from app.config import Settings
from app.models.activity import ActivityEvent, ActivityStatus, ActivityType
from app.models.briefing import Briefing, BriefingItem, BriefingItemCategory
from app.models.library import LibraryItem, LibraryItemKind
from app.models.team import TeamMembership
from app.models.user import User
from app.models.verification import VerifiedItemMetadata
from app.services.briefing_primer_content import select_primer_items
from app.services.email_service import morning_briefing_email, send_email

logger = logging.getLogger(__name__)


MAX_ITEMS = 5
MY_ACTIVITY_TAKE = 2
TEAM_ACTIVITY_TAKE = 2
KB_NEWS_TAKE = 1
TRIAL_PRIMER_MIN_ITEMS = 3
ACTIVITY_LOOKBACK_HOURS = 24
KB_LOOKBACK_DAYS = 7


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _today() -> datetime.date:
    return _utcnow().date()


# ---------------------------------------------------------------------------
# Item selectors
# ---------------------------------------------------------------------------

async def _select_my_activity(user: User) -> list[BriefingItem]:
    since = _utcnow() - datetime.timedelta(hours=ACTIVITY_LOOKBACK_HOURS)

    events = await ActivityEvent.find(
        ActivityEvent.user_id == user.user_id,
        ActivityEvent.started_at >= since,
    ).sort("-last_updated_at").limit(20).to_list()

    items: list[BriefingItem] = []
    seen_keys: set[str] = set()  # dedup by (type, primary artifact)

    for ev in events:
        key = f"{ev.type}:{ev.workflow or ev.search_set_uuid or ev.conversation_id or ev.id}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

        item = _activity_event_to_item(ev, is_team=False, actor_name=None)
        if item:
            items.append(item)
        if len(items) >= MY_ACTIVITY_TAKE:
            break

    return items


TEAM_DIGEST_THRESHOLD = 3  # 3+ teammate events → collapse to one digest item


def _render_team_digest(
    events: list[ActivityEvent],
    actor_info: dict[str, tuple[str, Optional[str]]],
) -> BriefingItem:
    """Collapse 3+ team events into a single digest item.

    Frees up briefing slots for other categories while preserving the
    "your team is active" signal. Date-keyed source_id so the digest is
    correctly deduped within a day but doesn't collide across days.
    """
    type_counts: Counter = Counter()
    for ev in events:
        if ev.type == ActivityType.WORKFLOW_RUN.value:
            type_counts["workflows"] += 1
        elif ev.type == ActivityType.SEARCH_SET_RUN.value:
            type_counts["extractions"] += 1
        elif ev.type == ActivityType.CONVERSATION.value:
            type_counts["chats"] += 1

    if type_counts:
        summary = ", ".join(f"{n} {label}" for label, n in type_counts.most_common())
    else:
        summary = f"{len(events)} actions"

    distinct_actor_ids: list[str] = []
    distinct_names: list[str] = []
    for ev in events:
        if ev.user_id not in distinct_actor_ids:
            distinct_actor_ids.append(ev.user_id)
            distinct_names.append(actor_info[ev.user_id][0])

    actor_count = len(distinct_actor_ids)
    actor_part = "Your team" if actor_count == 1 else f"{actor_count} teammates"

    sample = ", ".join(distinct_names[:3])
    if len(distinct_names) > 3:
        sample = f"{sample} and {len(distinct_names) - 3} more"

    return BriefingItem(
        category=BriefingItemCategory.TEAM_ACTIVITY.value,
        headline=f"{actor_part} were active: {summary}",
        body=f"Including {sample}. Open Activity to see what they ran.",
        deep_link="/activity",
        source_id=f"team-digest:{_today().isoformat()}",
        urgency=1,
    )


async def _select_team_activity(user: User) -> list[BriefingItem]:
    since = _utcnow() - datetime.timedelta(hours=ACTIVITY_LOOKBACK_HOURS)

    memberships = await TeamMembership.find(
        TeamMembership.user_id == user.user_id
    ).to_list()
    team_ids = [str(m.team) for m in memberships]
    if not team_ids:
        return []

    events = await ActivityEvent.find(
        In(ActivityEvent.team_id, team_ids),
        ActivityEvent.user_id != user.user_id,
        ActivityEvent.started_at >= since,
        ActivityEvent.status == ActivityStatus.COMPLETED.value,
    ).sort("-last_updated_at").limit(20).to_list()

    if not events:
        return []

    # Resolve actor name + role_segment per distinct actor. One DB hit each;
    # bounded by event count (limit 20 above).
    actor_info: dict[str, tuple[str, Optional[str]]] = {}
    for ev in events:
        if ev.user_id not in actor_info:
            actor_user = await User.find_one(User.user_id == ev.user_id)
            name = (actor_user.name or actor_user.user_id) if actor_user else "A teammate"
            role = actor_user.role_segment if actor_user else None
            actor_info[ev.user_id] = (name, role)

    # Render each event to a BriefingItem; track whether the actor's role
    # matches the viewer's role (used for ranking individual items).
    candidates: list[tuple[BriefingItem, bool]] = []
    for ev in events:
        actor_name, actor_role = actor_info[ev.user_id]
        item = _activity_event_to_item(ev, is_team=True, actor_name=actor_name)
        if not item:
            continue
        role_matches = bool(
            user.role_segment and actor_role and user.role_segment == actor_role
        )
        candidates.append((item, role_matches))

    if not candidates:
        return []

    # 3+ events → single digest item, frees other briefing slots.
    if len(candidates) >= TEAM_DIGEST_THRESHOLD:
        return [_render_team_digest(events, actor_info)]

    # 1-2 events → individual items, sorted by role-match first (stable so
    # recency from the DB sort survives within each match bucket).
    candidates.sort(key=lambda c: 0 if c[1] else 1)
    return [c[0] for c in candidates[:TEAM_ACTIVITY_TAKE]]


async def _select_kb_news(user: User) -> list[BriefingItem]:
    since = _utcnow() - datetime.timedelta(days=KB_LOOKBACK_DAYS)

    items_seen = set(user.briefing_items_shown_ids or [])
    # Bump the candidate pool to absorb post-filter drop-off when role_tags
    # narrow the field. Final cap is still KB_NEWS_TAKE.
    library_items = await LibraryItem.find(
        LibraryItem.verified == True,  # noqa: E712
        LibraryItem.created_at >= since,
    ).sort("-created_at").limit(30).to_list()

    selected: list[BriefingItem] = []
    for li in library_items:
        source_id = f"libraryitem:{li.id}"
        if source_id in items_seen:
            continue

        if not await _item_matches_user_role(li, user):
            continue

        name = await _resolve_library_item_name(li)
        if not name:
            continue

        kind_label = li.kind.value.replace("_", " ") if hasattr(li.kind, "value") else str(li.kind).replace("_", " ")
        selected.append(BriefingItem(
            category=BriefingItemCategory.KB_NEWS.value,
            headline=f"New verified {kind_label}: {name}",
            body="Added to the catalog this week. Try it on your next chat task.",
            deep_link=f"/library?tab=catalog&item={li.item_id}",
            source_id=source_id,
            urgency=1,
        ))
        if len(selected) >= KB_NEWS_TAKE:
            break

    return selected


async def _item_matches_user_role(li: LibraryItem, user: User) -> bool:
    """Return True if this library item should be shown to this user based on role.

    Rule: items with empty role_tags are universal (visible to everyone).
    Items with non-empty role_tags only match users whose role_segment is in
    the list. Users with no role_segment see only universal items.
    """
    kind = li.kind.value if hasattr(li.kind, "value") else str(li.kind)
    meta = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == kind,
        VerifiedItemMetadata.item_id == str(li.item_id),
    )
    if not meta or not meta.role_tags:
        return True  # universal
    if not user.role_segment:
        return False  # role-tagged item, user has no role → not a match
    return user.role_segment in meta.role_tags


def _activity_event_to_item(
    ev: ActivityEvent,
    *,
    is_team: bool,
    actor_name: Optional[str],
) -> Optional[BriefingItem]:
    """Render an ActivityEvent as a BriefingItem, or None to skip."""
    actor_prefix = f"{actor_name} " if is_team and actor_name else ("Your " if not is_team else "")
    category = (
        BriefingItemCategory.TEAM_ACTIVITY.value if is_team else BriefingItemCategory.MY_ACTIVITY.value
    )

    if ev.type == ActivityType.WORKFLOW_RUN.value:
        verb = "ran" if is_team else "finished running"
        title = ev.title or "a workflow"
        body_pieces = []
        if ev.documents_touched:
            body_pieces.append(f"{ev.documents_touched} documents")
        if ev.steps_completed and ev.steps_total:
            body_pieces.append(f"{ev.steps_completed}/{ev.steps_total} steps")
        body = " • ".join(body_pieces) or "Open it to see the result."
        urgency = 2 if ev.status == ActivityStatus.FAILED.value else 1
        headline = f"{actor_prefix.strip() or 'Your'} workflow `{title}` {verb}".strip()
        if ev.status == ActivityStatus.FAILED.value:
            headline = f"{headline} — failed, needs attention"
            urgency = 3
        return BriefingItem(
            category=category,
            headline=headline,
            body=body,
            deep_link=f"/workflows/results/{ev.workflow_result}" if ev.workflow_result else "/activity",
            source_id=f"activity:{ev.id}",
            urgency=urgency,
        )

    if ev.type == ActivityType.SEARCH_SET_RUN.value:
        title = ev.title or "a saved search"
        verb = "ran" if is_team else "ran"
        return BriefingItem(
            category=category,
            headline=f"{actor_prefix.strip() or 'Your'} search `{title}` {verb}".strip(),
            body=(
                f"{ev.documents_touched} documents matched."
                if ev.documents_touched
                else "Results are ready to review."
            ),
            deep_link=f"/search/{ev.search_set_uuid}" if ev.search_set_uuid else "/activity",
            source_id=f"activity:{ev.id}",
            urgency=1,
        )

    if ev.type == ActivityType.QUALITY_ALERT.value:
        return BriefingItem(
            category=category,
            headline=f"Quality alert on {ev.title or 'a recent answer'} — confidence dropped",
            body="Worth a second look before you act on it.",
            deep_link="/activity",
            source_id=f"activity:{ev.id}",
            urgency=3,
        )

    if ev.type == ActivityType.CONVERSATION.value and ev.is_running and not is_team:
        # Open chat thread — continuity hook.
        return BriefingItem(
            category=category,
            headline=f"You left a chat thread open: {ev.title or 'untitled'}",
            body="Pick up where you stopped — your context is saved.",
            deep_link=f"/chat/{ev.conversation_id}" if ev.conversation_id else "/chat",
            source_id=f"activity:{ev.id}",
            urgency=0,
        )

    return None


async def _select_suggested_action(user: User) -> list[BriefingItem]:
    """Return one 'try this next' item from the role-tailored seed-task pool.

    Distinct from the trial primer (which fires only when real items are scarce):
    this is a discovery-leaning item that appears for any user, picked from the
    seed-tasks pool with dedup against previously-shown primers so the user
    doesn't see the same suggestion repeatedly.
    """
    picks = select_primer_items(
        user.role_segment,
        user.briefing_primer_shown_ids or [],
        count=1,
    )
    if not picks:
        return []
    p = picks[0]
    return [BriefingItem(
        category=BriefingItemCategory.SUGGESTED_ACTION.value,
        headline=p["headline"],
        body=p["body"],
        deep_link=p.get("deep_link"),
        source_id=f"primer:{p['id']}",
        urgency=0,
    )]


_ACHIEVEMENTS_PER_BRIEFING = 2  # cap so a flurry of milestones doesn't crowd everything else


async def _select_achievements(user: User) -> list[BriefingItem]:
    """Surface unacknowledged first-time milestones as briefing items.

    Each achievement appears in exactly one briefing — once the source_id
    lands in `briefing_items_shown_ids` (which happens at briefing-write time),
    it won't show again. Capped at 2 per briefing so a user who crosses
    several thresholds at once doesn't lose the rest of the briefing's slots.
    """
    from app.services.achievements import milestone_def

    unlocked = user.achievements_unlocked or []
    if not unlocked:
        return []

    items_seen = set(user.briefing_items_shown_ids or [])
    items: list[BriefingItem] = []
    for milestone_id in unlocked:
        source_id = f"achievement:{milestone_id}"
        if source_id in items_seen:
            continue
        defn = milestone_def(milestone_id)
        if not defn:
            continue  # legacy / removed milestone IDs are silently skipped
        items.append(BriefingItem(
            category=BriefingItemCategory.ACHIEVEMENT.value,
            headline=defn["headline"],
            body=defn["body"],
            deep_link=defn.get("deep_link"),
            source_id=source_id,
            urgency=2,  # above suggested-action (0) and kb-news (1), below quality alerts (3)
        ))
        if len(items) >= _ACHIEVEMENTS_PER_BRIEFING:
            break
    return items


async def _select_deadlines(user: User) -> list[BriefingItem]:
    """Reserved for future implementation.

    Deadlines should ideally come from sponsor-portal scrapes or extracted
    due-date metadata on documents. v0 has no clean data source, so this
    returns an empty list; the category remains in the dispatch so the
    selector slots in cleanly once a source exists.
    """
    return []


async def _get_yesterday_category_set(user_id: str) -> set[str]:
    """Return the set of categories that appeared in yesterday's briefing.

    Used to deprioritize repeat-categories so consecutive briefings vary.
    Returns empty set when there is no yesterday's briefing (first day,
    weekend gap, etc.)."""
    yesterday = _today() - datetime.timedelta(days=1)
    prev = await Briefing.find_one(
        Briefing.user_id == user_id,
        Briefing.date == yesterday,
    )
    if not prev or not prev.items:
        return set()
    return {it.category for it in prev.items}


_ROTATION_PENALTY = 10  # larger than the category-priority range (0-5) so a
                        # yesterday-category sorts AFTER fresh categories at the
                        # same urgency tier. Relative order within yesterday's
                        # categories is preserved (they all get the same bump).


async def _resolve_library_item_name(li: LibraryItem) -> Optional[str]:
    """Resolve the human-readable name for a LibraryItem by following its kind."""
    try:
        from app.models.workflow import Workflow
        from app.models.search_set import SearchSet
        from app.models.knowledge import KnowledgeBase

        kind = li.kind.value if hasattr(li.kind, "value") else str(li.kind)
        obj_id = PydanticObjectId(str(li.item_id))

        if kind == LibraryItemKind.WORKFLOW.value:
            wf = await Workflow.get(obj_id)
            return wf.name if wf else None
        if kind == LibraryItemKind.SEARCH_SET.value:
            ss = await SearchSet.get(obj_id)
            return ss.title if ss else None
        if kind == LibraryItemKind.KNOWLEDGE_BASE.value:
            kb = await KnowledgeBase.get(obj_id)
            return kb.name if kb else None
    except Exception as exc:
        logger.debug("Failed to resolve library item name: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def compute_daily_briefing(user: User, *, force_recompute: bool = False) -> Briefing:
    """Compute (or fetch) today's briefing for a user. Idempotent for the same date.

    If a briefing for today already exists, returns it (unless force_recompute).
    Otherwise computes a new one, persists it, and returns it.
    """
    today = _today()

    if not force_recompute:
        existing = await Briefing.find_one(
            Briefing.user_id == user.user_id,
            Briefing.date == today,
        )
        if existing:
            return existing

    my_items = await _select_my_activity(user)
    team_items = await _select_team_activity(user)
    kb_items = await _select_kb_news(user)
    deadline_items = await _select_deadlines(user)
    suggested_items = await _select_suggested_action(user)
    achievement_items = await _select_achievements(user)

    real_items = my_items + team_items + kb_items + deadline_items + suggested_items + achievement_items
    primer_padded = False

    in_trial = user.demo_status == "active"
    needs_padding = in_trial and len(real_items) < TRIAL_PRIMER_MIN_ITEMS

    if needs_padding:
        primer_count = TRIAL_PRIMER_MIN_ITEMS - len(real_items)
        # Exclude primer IDs already used by suggested-action this turn so we
        # don't double-render the same seed-task as both a primer and a
        # suggested-action.
        seen_primer_ids: list[str] = list(user.briefing_primer_shown_ids or [])
        for it in suggested_items:
            if it.source_id and it.source_id.startswith("primer:"):
                seen_primer_ids.append(it.source_id.split(":", 1)[1])
        primer_picks = select_primer_items(
            user.role_segment,
            seen_primer_ids,
            primer_count,
        )
        for p in primer_picks:
            real_items.append(BriefingItem(
                category=BriefingItemCategory.PRIMER.value,
                headline=p["headline"],
                body=p["body"],
                deep_link=p.get("deep_link"),
                source_id=f"primer:{p['id']}",
                urgency=0,
            ))
        primer_padded = bool(primer_picks)

    # Order by urgency desc, then by category priority, with a rotation tweak
    # that gently deprioritizes categories that appeared yesterday — so
    # consecutive briefings don't feel like the same dashboard.
    category_priority = {
        BriefingItemCategory.DEADLINE.value: 0,  # reserved; sorts highest when added
        BriefingItemCategory.MY_ACTIVITY.value: 1,
        BriefingItemCategory.ACHIEVEMENT.value: 2,  # personal acknowledgment; above social/discovery
        BriefingItemCategory.TEAM_ACTIVITY.value: 3,
        BriefingItemCategory.KB_NEWS.value: 4,
        BriefingItemCategory.SUGGESTED_ACTION.value: 5,
        BriefingItemCategory.PRIMER.value: 6,
    }
    yesterday_cats = await _get_yesterday_category_set(user.user_id)

    def _sort_key(it: BriefingItem) -> tuple:
        base_priority = category_priority.get(it.category, 99)
        rotation = _ROTATION_PENALTY if it.category in yesterday_cats else 0
        return (-it.urgency, base_priority + rotation)

    real_items.sort(key=_sort_key)
    final_items = real_items[:MAX_ITEMS]

    briefing = Briefing(
        user_id=user.user_id,
        date=today,
        items=final_items,
        primer_padded=primer_padded,
    )
    await briefing.insert()

    # Track shown source_ids so they don't repeat tomorrow.
    new_source_ids = [it.source_id for it in final_items if it.source_id]
    if new_source_ids:
        user.briefing_items_shown_ids = (user.briefing_items_shown_ids or []) + new_source_ids
        # Cap the list to last 500 to bound storage.
        if len(user.briefing_items_shown_ids) > 500:
            user.briefing_items_shown_ids = user.briefing_items_shown_ids[-500:]
    primer_ids = [
        it.source_id.split(":", 1)[1] for it in final_items
        if it.source_id and it.source_id.startswith("primer:")
    ]
    if primer_ids:
        user.briefing_primer_shown_ids = (user.briefing_primer_shown_ids or []) + primer_ids
        if len(user.briefing_primer_shown_ids) > 100:
            user.briefing_primer_shown_ids = user.briefing_primer_shown_ids[-100:]
    if new_source_ids or primer_ids:
        await user.save()

    return briefing


async def get_or_create_today_briefing(user: User) -> Briefing:
    """Idempotent fetch for the in-app chat surface."""
    return await compute_daily_briefing(user, force_recompute=False)


async def mark_briefing_opened(briefing: Briefing, user: User) -> None:
    """Mark a briefing as opened. Appends to user.briefing_opened_dates for engagement analytics."""
    now = _utcnow()
    briefing.opened_at = briefing.opened_at or now
    await briefing.save()

    user.last_briefing_opened_at = now
    if briefing.date not in (user.briefing_opened_dates or []):
        user.briefing_opened_dates = (user.briefing_opened_dates or []) + [briefing.date]
        if len(user.briefing_opened_dates) > 120:
            user.briefing_opened_dates = user.briefing_opened_dates[-120:]
    await user.save()


async def send_morning_briefings(settings: Settings | None = None) -> int:
    """Compute + email today's briefing to eligible users. Returns count sent.

    Eligibility:
      - User has an email
      - email_preferences.briefings is not explicitly False
      - For paid users with an empty briefing, the email is skipped (in-app only)
      - For trial users (demo_status=active), primer-padded briefing is always sent
    """
    if settings is None:
        settings = Settings()

    sent = 0
    now = _utcnow()

    # Pull only users that haven't been sent a briefing today, to keep this idempotent
    # if the beat fires twice in a day for any reason.
    start_of_today_utc = datetime.datetime.combine(_today(), datetime.time.min, tzinfo=datetime.timezone.utc)

    candidates = await User.find(
        User.email != None,  # noqa: E711
    ).to_list()

    for user in candidates:
        if not user.email:
            continue
        prefs = user.email_preferences or {}
        if prefs.get("briefings") is False:
            continue
        if user.last_briefing_sent_at and user.last_briefing_sent_at >= start_of_today_utc:
            continue  # already sent today

        briefing = await compute_daily_briefing(user)

        in_trial = user.demo_status == "active"
        has_real_items = any(
            it.category not in (BriefingItemCategory.PRIMER.value,) for it in briefing.items
        )

        if not briefing.items:
            briefing.email_skipped_reason = "empty"
            await briefing.save()
            continue
        if not has_real_items and not in_trial:
            briefing.email_skipped_reason = "empty_paid_user"
            await briefing.save()
            continue

        subject, html = morning_briefing_email(
            name=user.name or user.user_id,
            briefing_items=[it.model_dump() for it in briefing.items],
            frontend_url=settings.frontend_url,
            primer_padded=briefing.primer_padded,
        )
        success = await send_email(
            user.email, subject, html, settings, email_type="morning_briefing"
        )
        if success:
            briefing.sent_via_email = True
            await briefing.save()
            user.last_briefing_sent_at = now
            await user.save()
            sent += 1
        else:
            briefing.email_skipped_reason = "send_failed"
            await briefing.save()

    if sent:
        logger.info("Sent %d morning briefings", sent)
    return sent
