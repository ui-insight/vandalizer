"""Bell notifications for optimizer runs — the path back to a tuning suggestion.

Shadow runs (``options.shadow_trigger``) are started by quality signals, not by
a person, so no one is watching a panel when they finish: a candidate or a
failure was visible only on ``/tuning``, and nothing in the app led there for
anyone but an admin (support ticket). The owner hears about a run here, from
the bell they already have — no new nav entry for the many users who never own
a tuned item.

Who hears what mirrors the inbox's membership rule:

* A shadow run is announced only when it leaves something to act on — a
  candidate worth reviewing, or a failure. A run that found nothing better, or
  whose winner was applied, stays quiet.
* A run the user started is announced when it completes or fails; they may
  have left the panel long ago. A cancel is not: they did it themselves.

Repeats for one item fold into a single unread row, so a signal that keeps
firing shows as "3×" rather than three entries. Never raises.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

Surface = Literal["kb", "extraction", "workflow"]

TUNING_PAGE = "/tuning"

# surface -> (notification item_kind, noun used when the item has no name)
_SURFACE_LABELS: dict[str, tuple[str, str]] = {
    "kb": ("knowledge_base", "Knowledge base"),
    "extraction": ("search_set", "Extraction"),
    "workflow": ("workflow", "Workflow"),
}

_ERROR_SNIPPET = 200


def _item_id(surface: Surface, run_doc: Any) -> str:
    if surface == "kb":
        return run_doc.kb_uuid
    if surface == "extraction":
        return run_doc.search_set_uuid
    return run_doc.workflow_id


def _item_link(surface: Surface, item_id: str) -> str:
    if surface == "kb":
        return f"/?mode=knowledge&kb={item_id}"
    if surface == "extraction":
        return f"/?extraction={item_id}"
    return f"/?workflow={item_id}"


async def _item_info(surface: Surface, item_id: str) -> tuple[str | None, str | None]:
    """``(name, owner_user_id)`` of the tuned item; ``(None, None)`` if it is gone."""
    try:
        if surface == "kb":
            from app.models.knowledge import KnowledgeBase
            item = await KnowledgeBase.find_one(KnowledgeBase.uuid == item_id)
            return (item.title, item.user_id) if item else (None, None)
        if surface == "extraction":
            from app.models.search_set import SearchSet
            item = await SearchSet.find_one(SearchSet.uuid == item_id)
            return (item.title, item.user_id) if item else (None, None)
        from beanie import PydanticObjectId

        from app.models.workflow import Workflow
        item = await Workflow.get(PydanticObjectId(item_id))
        return (item.name, item.user_id) if item else (None, None)
    except Exception:
        return None, None


def _is_shadow(run_doc: Any) -> bool:
    options = getattr(run_doc, "options", None)
    return isinstance(options, dict) and bool(options.get("shadow_trigger"))


def _has_suggestion(run_doc: Any) -> bool:
    """A config that beat the current one — the inbox's ``needs_review`` once
    the caller has ruled out that it was applied on finish."""
    return (
        bool(getattr(run_doc, "best_config", None))
        and not getattr(run_doc, "tied_with_baseline", False)
        and getattr(run_doc, "dismissed_at", None) is None
    )


def _score_line(run_doc: Any) -> str:
    optimized = getattr(run_doc, "optimized_score", None)
    baseline = getattr(run_doc, "baseline_default_score", None)
    if optimized is None or baseline is None:
        return ""
    lift = (optimized - baseline) * 100
    return f" Score {baseline * 100:.0f}% → {optimized * 100:.0f}% ({'+' if lift >= 0 else ''}{lift:.0f} pts)."


async def notify_run_terminal(
    surface: Surface, run_doc: Any, *, applied: bool = False, item_name: str | None = None,
) -> None:
    """Tell the run's owner a run finished, when there is something to tell.

    ``applied`` is whether the run's winner was applied on finish — each
    surface records that differently, and the finalizer knows it outright.
    """
    try:
        status = getattr(run_doc, "status", None)
        if status not in ("completed", "failed"):
            return
        shadow = _is_shadow(run_doc)
        suggestion = status == "completed" and not applied and _has_suggestion(run_doc)
        if shadow and status == "completed" and not suggestion:
            return

        item_kind, noun = _SURFACE_LABELS[surface]
        item_id = _item_id(surface, run_doc)
        looked_up_name, owner = await _item_info(surface, item_id)
        name = item_name or looked_up_name or noun
        # A shadow run's user_id is whoever tripped the signal — "system" for
        # the quality sweep, the chat user behind a thumbs-down — not someone
        # who can act on it. The item's owner can; they get it. A run a
        # person started goes to that person.
        user_id = owner if shadow else getattr(run_doc, "user_id", None)
        if not user_id or user_id == "system":
            return
        # A shadow run's only home is the inbox; a run the user started
        # belongs to the item's own panel, which restores it.
        link = TUNING_PAGE if shadow else _item_link(surface, item_id)

        if status == "failed":
            kind = f"{surface}_optimization_failed"
            title = f"Tuning run failed: {name}"
            group_title = f"Tuning run failed {{count}}×: {name}"
            error = str(getattr(run_doc, "error_message", None) or "").strip()
            body = error[:_ERROR_SNIPPET] or "The tuning run failed without recording an error."
            severity = "warning"
        elif shadow:
            kind = "tuning_suggestion"
            title = f"Tuning suggestion: {name}"
            group_title = f"{{count}} tuning suggestions: {name}"
            body = (
                "An automatic tuning run found settings that score better than the "
                f"current ones.{_score_line(run_doc)} Review, apply or dismiss it."
            )
            severity = "info"
        else:
            kind = f"{surface}_optimization_completed"
            title = f"Tuning run complete: {name}"
            group_title = f"Tuning runs complete {{count}}×: {name}"
            if applied:
                body = f"Better settings were found and applied.{_score_line(run_doc)}"
            elif suggestion:
                body = (
                    f"Found settings that score better than the current ones.{_score_line(run_doc)} "
                    f"Review and apply them from the {noun.lower()}."
                )
            else:
                body = "No measurably better settings were found; the current ones stay."
            severity = "info"

        from app.services.notification_service import create_notification

        await create_notification(
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            link=link,
            item_kind=item_kind,
            item_id=item_id,
            item_name=name,
            severity=severity,
            coalesce_key=f"{kind}:{surface}:{item_id}",
            group_title=group_title,
        )
    except Exception:
        logger.exception("Failed to emit optimizer notification for run %s", getattr(run_doc, "uuid", "?"))
