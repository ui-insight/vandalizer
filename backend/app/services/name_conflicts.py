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
from app.models.library import LibraryItem
from app.models.search_set import SearchSet
from app.models.workflow import Workflow


class DuplicateNameError(ValueError):
    """A name that must be unique within its visibility scope is already taken."""


def _exact_name(name: str) -> dict:
    return {"$regex": f"^{re.escape(name)}$", "$options": "i"}


def _model_identifier(value: object) -> str:
    """Normalize a model name or tag for comparison."""
    return str(value or "").strip().casefold()


def ensure_model_identity_available(
    *,
    name: str,
    tag: str,
    models: list,
    exclude_index: int | None = None,
) -> None:
    """Reject a model whose name or tag is already in use by another model.

    ``get_llm_model_by_name`` resolves a selector by scanning names first and
    tags second, returning the first match either way, so names and tags form a
    single identifier namespace: two models sharing a tag — or one model whose
    name is another's tag — make a selector ambiguous, and the loser is decided
    by list order. User model preferences are stored as that selector, so the
    ambiguity silently routes requests to a model the user did not choose.

    Unlike the ``ensure_*_available`` helpers above, ``available_models`` is an
    embedded list on ``SystemConfig`` rather than a collection, so this compares
    in memory instead of querying. Matching is case-insensitive on the trimmed
    value, consistent with :func:`_exact_name`. Pass ``exclude_index`` when
    updating so a model does not collide with itself.
    """
    candidates = (("name", str(name or "").strip()), ("tag", str(tag or "").strip()))

    for index, existing in enumerate(models):
        if index == exclude_index or not isinstance(existing, dict):
            continue
        owner = str(existing.get("name") or "").strip() or f"at index {index}"
        taken = (
            ("name", _model_identifier(existing.get("name"))),
            ("tag", _model_identifier(existing.get("tag"))),
        )
        for field, value in candidates:
            if not value:
                continue
            for taken_field, taken_value in taken:
                if taken_value and _model_identifier(value) == taken_value:
                    raise DuplicateNameError(
                        f"Model {field} {value!r} is already used as the "
                        f"{taken_field} of model {owner!r}. Model names and tags "
                        f"must be unique."
                    )


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


def _workflow_conflict_query(
    name: str, user_id: str, team_id: str | None, exclude_id: str | None = None,
) -> dict:
    query: dict = {"$and": [_library_scope(user_id, team_id), {"name": _exact_name(name)}]}
    if exclude_id:
        query["$and"].append({"_id": {"$ne": ObjectId(exclude_id)}})
    return query


async def workflow_name_taken(
    name: str, user_id: str, team_id: str | None, exclude_id: str | None = None,
) -> bool:
    query = _workflow_conflict_query(name, user_id, team_id, exclude_id=exclude_id)
    return await Workflow.find(query).count() > 0


async def describe_workflow_name_conflict(
    name: str, user_id: str, team_id: str | None, exclude_id: str | None = None,
) -> str | None:
    """The duplicate-name message for *name*, or None when the name is free.

    The scope spans more than the user's personal library — a teammate's
    team-shared workflow counts, and so does a workflow whose library bookmark
    was removed while the object (and its name) lives on. The old flat message
    claimed every conflict was "in your library", which read as a bug to a
    user whose library plainly showed no such row (support ticket: an Explore
    import "told her she already had a workflow with the same name even though
    she didn't"). Say where the conflicting workflow actually is, in its exact
    capitalization, so the user can find it — or at least believe us.
    """
    query = _workflow_conflict_query(name, user_id, team_id, exclude_id=exclude_id)
    existing = await Workflow.find_one(query)
    if existing is None:
        return None

    shown_name = existing.name or name
    if team_id and existing.team_id == team_id:
        owned = "your" if existing.user_id == user_id else "a teammate's"
        location = f"in your team's library ({owned} workflow, on the Team tab)"
    else:
        location = "in your library"
        # A workflow with no library bookmark shows up in no listing at all,
        # yet still holds its name. Name the situation instead of pointing the
        # user at a row that is not there.
        bookmarked = await LibraryItem.find_one({"item_id": existing.id}) is not None
        if not bookmarked:
            location = (
                "in your account but is not currently listed in your library "
                "(it was removed from the library list without being deleted, "
                "so its name is still in use)"
            )

    return (
        f'A workflow named "{shown_name}" already exists {location}. '
        "Choose a different name."
    )


async def ensure_workflow_name_available(
    name: str, user_id: str, team_id: str | None, exclude_id: str | None = None,
) -> None:
    message = await describe_workflow_name_conflict(
        name, user_id, team_id, exclude_id=exclude_id
    )
    if message is not None:
        raise DuplicateNameError(message)


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
