"""Scoped name-uniqueness checks for user-named entities.

Workflows, extractions, prompts, formatters and knowledge bases share the same
library / picker surfaces, so two entries with the same name in the same
visibility scope are indistinguishable rows. Names the user typed themselves
(create / rename) are rejected with :class:`DuplicateNameError`, which routers
translate to HTTP 409. Machine-generated names (clone / duplicate / import)
are never rejected — callers route them through :func:`next_available_name`
to get an auto-suffixed variant ("Budget Analyzer (Copy 2)") instead.

"Same scope" mirrors what the default library listings show together:
the creator's own items plus their team's items (see ``list_workflows`` /
``list_search_sets``), and for knowledge bases the owner's own plus
team-shared KBs (see ``build_kb_list_query``). Matching is case-insensitive
on the already-normalized name.
"""

from __future__ import annotations

import re
from typing import Awaitable, Callable

from bson import ObjectId

from app.models.knowledge import KnowledgeBase
from app.models.search_set import SearchSet
from app.models.workflow import Workflow


class DuplicateNameError(ValueError):
    """A name that must be unique within its visibility scope is already taken."""


def _exact_name(name: str) -> dict:
    return {"$regex": f"^{re.escape(name)}$", "$options": "i"}


def _library_scope(user_id: str, team_id: str | None) -> dict:
    # Mirrors the default (no-scope) query in workflow_service.list_workflows
    # and search_set_service.list_search_sets: own items + current team items.
    if team_id:
        return {"$or": [
            {"user_id": user_id, "team_id": {"$in": [team_id, None]}},
            {"team_id": team_id},
        ]}
    return {"user_id": user_id}


def _kb_scope(user_id: str, team_id: str | None) -> dict:
    # Mirrors build_kb_list_query's own + team-shared clauses. Verified catalog
    # KBs are deliberately excluded — users can't rename the catalog, so a
    # catalog collision shouldn't block their own naming. Implicit
    # (project-owned) KBs never surface in KB lists, so they don't count.
    or_clauses: list[dict] = [{"user_id": user_id, "team_owned": {"$ne": True}}]
    if team_id:
        or_clauses.append({"shared_with_team": True, "team_id": team_id})
    return {"$and": [{"$or": or_clauses}, {"implicit": {"$ne": True}}]}


async def workflow_name_taken(
    name: str, user_id: str, team_id: str | None, exclude_id: str | None = None,
) -> bool:
    query: dict = {"$and": [_library_scope(user_id, team_id), {"name": _exact_name(name)}]}
    if exclude_id:
        query["$and"].append({"_id": {"$ne": ObjectId(exclude_id)}})
    return await Workflow.find(query).count() > 0


async def ensure_workflow_name_available(
    name: str, user_id: str, team_id: str | None, exclude_id: str | None = None,
) -> None:
    if await workflow_name_taken(name, user_id, team_id, exclude_id=exclude_id):
        raise DuplicateNameError(
            f'A workflow named "{name}" already exists in your library. '
            "Choose a different name.",
        )


async def search_set_title_taken(
    title: str, set_type: str, user_id: str, team_id: str | None,
    exclude_uuid: str | None = None,
) -> bool:
    query: dict = {"$and": [
        _library_scope(user_id, team_id),
        {"set_type": set_type, "title": _exact_name(title)},
    ]}
    if exclude_uuid:
        query["$and"].append({"uuid": {"$ne": exclude_uuid}})
    return await SearchSet.find(query).count() > 0


async def ensure_search_set_title_available(
    title: str, set_type: str, user_id: str, team_id: str | None,
    exclude_uuid: str | None = None,
) -> None:
    if await search_set_title_taken(title, set_type, user_id, team_id, exclude_uuid=exclude_uuid):
        label = set_type if set_type in ("extraction", "prompt", "formatter") else "item"
        raise DuplicateNameError(
            f'{label.capitalize()} "{title}" already exists in your library. '
            "Choose a different name.",
        )


async def kb_title_taken(
    title: str, user_id: str, team_id: str | None, exclude_uuid: str | None = None,
) -> bool:
    query: dict = {"$and": [_kb_scope(user_id, team_id), {"title": _exact_name(title)}]}
    if exclude_uuid:
        query["$and"].append({"uuid": {"$ne": exclude_uuid}})
    return await KnowledgeBase.find(query).count() > 0


async def ensure_kb_title_available(
    title: str, user_id: str, team_id: str | None, exclude_uuid: str | None = None,
) -> None:
    if await kb_title_taken(title, user_id, team_id, exclude_uuid=exclude_uuid):
        raise DuplicateNameError(
            f'A knowledge base named "{title}" already exists. '
            "Choose a different name.",
        )


def _variant(base: str, n: int) -> str:
    # "Budget Analyzer (Copy)" → "Budget Analyzer (Copy 2)";
    # "Budget Analyzer" → "Budget Analyzer (2)".
    if base.endswith(")") and "(" in base:
        return f"{base[:-1]} {n})"
    return f"{base} ({n})"


async def next_available_name(
    base: str,
    is_taken: Callable[[str], Awaitable[bool]],
    max_length: int = 100,
) -> str:
    """First name derived from *base* that ``is_taken`` reports free.

    Used by clone / duplicate / import flows, which must never fail on a name
    collision. Falls back to *base* (allowing the duplicate) rather than
    erroring if every numbered variant is somehow taken.
    """
    base = base[:max_length].strip()
    if not await is_taken(base):
        return base
    for n in range(2, 100):
        candidate = _variant(base, n)
        if len(candidate) > max_length:
            cut = len(candidate) - max_length
            candidate = _variant(base[:-cut].strip(), n) if cut < len(base) else base
        if not await is_taken(candidate):
            return candidate
    return base
