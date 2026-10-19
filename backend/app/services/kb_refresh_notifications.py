"""Bell notifications for scheduled web-source refreshes.

A KB with ``url_refresh_interval`` set re-fetches its web sources on its own
(``kb_url_refresh.refresh_due_sources``). Before this, a page that changed was
re-indexed — and a page that stopped loading kept its old text — with no
signal to anyone: the KB answered differently, or went stale, and the only
trace was the currency fields on one source row (support ticket).

The people responsible for the KB hear about it here: its owner and, for a KB
shared with a team, that team's owners and admins — the same people
``can_manage_knowledge_base`` lets edit it.

* A changed page is announced with a short summary of what changed.
* A failed refresh is announced when the source *starts* failing. A page that
  is gone for good would otherwise ring the bell every day; the source row
  keeps showing the error until a refresh succeeds.
* An unchanged page, and any refresh a person started, stay quiet — whoever
  clicked Refresh is looking at the result.

Repeats for one KB fold into one unread row per person and kind, so a weekly
pass that updates twenty sources is "20 sources updated", not twenty entries.
Never raises.
"""

from __future__ import annotations

import logging
from typing import Any

from app.utils import kb_source_currency as currency

logger = logging.getLogger(__name__)

FAILED_OUTCOMES = frozenset({currency.OUTCOME_RETRIEVAL_FAILED, currency.OUTCOME_INGESTION_FAILED})

# Lands on the knowledge screen. /?kb= would be force-routed into chat mode.
KNOWLEDGE_PAGE = "/?mode=knowledge"

_SNIPPET = 160
_ERROR_SNIPPET = 200


def _lines(text: str | None) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def summarize_change(
    old_text: str | None, new_text: str | None,
    old_title: str | None = None, new_title: str | None = None,
) -> str:
    """One or two sentences on how a page's text changed.

    Line-set arithmetic rather than a diff: a source can be millions of
    characters, and the bell needs a sense of scale and a first example, not
    a patch.
    """
    old_lines, new_lines = _lines(old_text), _lines(new_text)
    old_set, new_set = set(old_lines), set(new_lines)
    added = [line for line in new_lines if line not in old_set]
    removed = sum(1 for line in old_lines if line not in new_set)

    parts: list[str] = []
    if old_title and new_title and old_title != new_title:
        parts.append(f"Title changed from “{old_title}” to “{new_title}”.")
    if added or removed:
        parts.append(
            f"{len(added)} line{'' if len(added) == 1 else 's'} added, "
            f"{removed} removed "
            f"({len(old_text or ''):,} → {len(new_text or ''):,} characters)."
        )
    else:
        # Same lines, different bytes: reordered or re-spaced.
        parts.append("The page's text was reordered or reformatted; no lines were added or removed.")
    if added:
        first = added[0]
        if len(first) > _SNIPPET:
            first = first[:_SNIPPET].rstrip() + "…"
        parts.append(f"New text includes: “{first}”")
    return " ".join(parts)


async def kb_managers(kb: Any) -> list[str]:
    """User ids that can manage the KB: its owner, plus its team's owners and
    admins when it is shared with the team. Examiners' catalog-wide manage
    right over verified KBs is governance, not ownership; they are not told."""
    recipients: list[str] = []
    if getattr(kb, "user_id", None):
        recipients.append(kb.user_id)
    team_id = getattr(kb, "team_id", None)
    if getattr(kb, "shared_with_team", False) and team_id:
        try:
            from beanie import PydanticObjectId

            from app.models.team import Team, TeamMembership
            from app.services.access_control import TEAM_MANAGE_ROLES

            team = await Team.find_one({"uuid": team_id})
            if team is None and PydanticObjectId.is_valid(team_id):
                team = await Team.get(PydanticObjectId(team_id))
            if team is not None:
                memberships = await TeamMembership.find(
                    {"team": team.id, "role": {"$in": sorted(TEAM_MANAGE_ROLES)}},
                ).to_list()
                recipients.extend(await _within_org_scope(kb, [m.user_id for m in memberships]))
        except Exception:
            logger.exception("Could not resolve team managers for KB %s", getattr(kb, "uuid", "?"))
    return list(dict.fromkeys(u for u in recipients if u and u != "system"))


async def _within_org_scope(kb: Any, user_ids: list[str]) -> list[str]:
    """The team managers the KB's organization scope lets see it.

    ``can_manage_knowledge_base`` refuses a team admin outside the KB's
    organizations; telling them about it would show them its title and
    source names all the same.
    """
    org_ids = list(getattr(kb, "organization_ids", None) or [])
    if not org_ids or not user_ids:
        return user_ids
    from app.models.user import User
    from app.services import organization_service
    from app.services.access_control import _org_scope_allows

    kept: list[str] = []
    for user in await User.find({"user_id": {"$in": user_ids}}).to_list():
        ancestry = await organization_service.get_user_org_ancestry(user)
        if _org_scope_allows(org_ids, ancestry):
            kept.append(user.user_id)
    return kept


def _source_name(source: Any) -> str:
    return (
        getattr(source, "custom_name", None) or getattr(source, "url_title", None)
        or getattr(source, "url", None) or "A web source"
    )


async def _notify_managers(kb: Any, **fields: Any) -> None:
    from app.services.notification_service import create_notification

    kb_title = getattr(kb, "title", None) or "Knowledge base"
    for user_id in await kb_managers(kb):
        try:
            await create_notification(
                user_id=user_id,
                link=KNOWLEDGE_PAGE,
                item_kind="knowledge_base",
                item_id=kb.uuid,
                item_name=kb_title,
                **fields,
            )
        except Exception:
            logger.exception("Failed to notify %s about a refresh of KB %s", user_id, kb.uuid)


async def notify_source_changed(kb: Any, source: Any, summary: str) -> None:
    """A scheduled refresh re-indexed a source because its page changed."""
    try:
        kb_title = getattr(kb, "title", None) or "Knowledge base"
        name = _source_name(source)
        await _notify_managers(
            kb,
            kind="kb_source_updated",
            title=f"Web source updated: {kb_title}",
            body=f"“{name}” changed on the web and was re-indexed. {summary}",
            severity="info",
            coalesce_key=f"kb_source_updated:{kb.uuid}",
            group_title=f"{{count}} web sources updated in knowledge base: {kb_title}",
        )
    except Exception:
        logger.exception("Failed to emit KB source-updated notification for %s", getattr(kb, "uuid", "?"))


async def notify_source_refresh_failed(
    kb: Any, source: Any, reason: str | None, *, previous_outcome: str | None,
) -> None:
    """A scheduled refresh could not update a source. Sent only when the
    source was not already failing (see the module docstring)."""
    try:
        if previous_outcome in FAILED_OUTCOMES:
            return
        kb_title = getattr(kb, "title", None) or "Knowledge base"
        name = _source_name(source)
        kept = getattr(source, "status", None) == "ready" and getattr(source, "chunk_count", 0)
        consequence = (
            "Its previous text is still being used, and may be out of date."
            if kept else "It has no indexed text, so the knowledge base cannot answer from it."
        )
        error = str(reason or "").strip()[:_ERROR_SNIPPET] or "No error detail was recorded."
        await _notify_managers(
            kb,
            kind="kb_source_refresh_failed",
            title=f"Web source stopped updating: {kb_title}",
            body=f"The scheduled refresh of “{name}” failed. {consequence} {error}",
            severity="warning",
            coalesce_key=f"kb_source_refresh_failed:{kb.uuid}",
            group_title=f"{{count}} web sources stopped updating in knowledge base: {kb_title}",
        )
    except Exception:
        logger.exception("Failed to emit KB source-refresh-failed notification for %s", getattr(kb, "uuid", "?"))
