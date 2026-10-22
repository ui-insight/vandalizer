"""Behavioral memory for personalizing chat across sessions.

Records which extraction templates, workflows, and knowledge bases a user
actually exercises, and builds a short natural-language "patterns" block
that the agentic chat injects into the system prompt so the model can
reference the user's habits without having to infer them.

Design:
- Deterministic counts only — no LLM inference over conversation text.
- Per-(user, team) scope so a user's grants-team habits don't leak into
  their compliance-team chat.
- Items that haven't been touched in 60 days are filtered out of the
  prompt (still stored, surfaced again if the user returns to them).
"""

import datetime
import logging
from typing import Optional

from app.models.user_memory import UserMemory

logger = logging.getLogger(__name__)

# How many items per category to surface in the patterns block.
_TOP_N = 3
# Items older than this are ignored when rendering patterns.
_RECENCY_CUTOFF_DAYS = 60


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt: datetime.datetime) -> str:
    return dt.isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        return None


async def _get_or_create(user_id: str, team_id: Optional[str]) -> UserMemory:
    doc = await UserMemory.find_one(
        UserMemory.user_id == user_id,
        UserMemory.team_id == team_id,
    )
    if doc is None:
        doc = UserMemory(user_id=user_id, team_id=team_id)
        await doc.insert()
    return doc


async def _record(
    user_id: str,
    team_id: Optional[str],
    field: str,
    item_id: str,
    title: str,
) -> None:
    """Increment a usage counter for an item in the given field."""
    if not item_id:
        return
    try:
        doc = await _get_or_create(user_id, team_id)
        bucket: dict = getattr(doc, field)
        entry = bucket.get(item_id) or {"title": title, "count": 0}
        entry["title"] = title or entry.get("title") or item_id
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_used"] = _iso(_utcnow())
        bucket[item_id] = entry
        setattr(doc, field, bucket)
        doc.updated_at = _utcnow()
        await doc.save()
    except Exception as e:
        # Memory tracking is best-effort — never break the caller.
        logger.warning("Failed to record %s memory for user %s: %s", field, user_id, e)


async def record_extraction(
    user_id: str, team_id: Optional[str], set_uuid: str, set_title: str
) -> None:
    await _record(user_id, team_id, "extraction_runs", set_uuid, set_title)


async def record_workflow(
    user_id: str, team_id: Optional[str], workflow_id: str, workflow_title: str
) -> None:
    await _record(user_id, team_id, "workflow_runs", workflow_id, workflow_title)


async def record_kb_query(
    user_id: str, team_id: Optional[str], kb_uuid: str, kb_title: str
) -> None:
    await _record(user_id, team_id, "kb_queries", kb_uuid, kb_title)


def _top_recent(bucket: dict, cutoff: datetime.datetime, n: int = _TOP_N) -> list[dict]:
    """Return the top-N entries by count, limited to items used after cutoff."""
    recent: list[dict] = []
    for entry in bucket.values():
        last = _parse_iso(entry.get("last_used"))
        if last is None:
            continue
        if last.tzinfo is None:
            last = last.replace(tzinfo=datetime.timezone.utc)
        if last < cutoff:
            continue
        recent.append(entry)
    recent.sort(key=lambda e: int(e.get("count", 0)), reverse=True)
    return recent[:n]


async def build_patterns_block(user_id: str, team_id: Optional[str]) -> str:
    """Return a markdown block describing the user's habits, or '' if none."""
    doc = await UserMemory.find_one(
        UserMemory.user_id == user_id,
        UserMemory.team_id == team_id,
    )
    if doc is None:
        return ""

    cutoff = _utcnow() - datetime.timedelta(days=_RECENCY_CUTOFF_DAYS)
    top_extractions = _top_recent(doc.extraction_runs, cutoff)
    top_workflows = _top_recent(doc.workflow_runs, cutoff)
    top_kbs = _top_recent(doc.kb_queries, cutoff)

    if not (top_extractions or top_workflows or top_kbs):
        return ""

    lines: list[str] = ["## Your patterns", "This user frequently:"]
    for e in top_extractions:
        lines.append(f'- Runs the "{e["title"]}" extraction template')
    for w in top_workflows:
        lines.append(f'- Executes the "{w["title"]}" workflow')
    for k in top_kbs:
        lines.append(f'- Queries the "{k["title"]}" knowledge base')
    lines.append(
        "Reference these by name when the user's request naturally matches one. "
        "Do not force them — skip if the request is off-topic."
    )
    return "\n".join(lines)


async def get_patterns(user_id: str, team_id: Optional[str]) -> dict:
    """Return top recent items per category as structured data for the UI.

    Mirrors the filtering used by build_patterns_block so the user sees the
    same items the assistant is referencing.
    """
    doc = await UserMemory.find_one(
        UserMemory.user_id == user_id,
        UserMemory.team_id == team_id,
    )
    if doc is None:
        return {"extractions": [], "workflows": [], "kbs": []}

    cutoff = _utcnow() - datetime.timedelta(days=_RECENCY_CUTOFF_DAYS)
    return {
        "extractions": _top_recent(doc.extraction_runs, cutoff),
        "workflows": _top_recent(doc.workflow_runs, cutoff),
        "kbs": _top_recent(doc.kb_queries, cutoff),
    }


async def clear_memory(user_id: str, team_id: Optional[str]) -> bool:
    """Delete this user's memory for the given team. Returns True if removed."""
    doc = await UserMemory.find_one(
        UserMemory.user_id == user_id,
        UserMemory.team_id == team_id,
    )
    if doc is None:
        return False
    await doc.delete()
    return True
