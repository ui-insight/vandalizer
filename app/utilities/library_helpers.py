from datetime import datetime, timezone
from typing import Literal, Optional, Sequence, Tuple

from mongoengine import Q

from app.models import (
    Library,
    LibraryItem,
    LibraryScope,
    SearchSet,
    Team,
    TeamMembership,
    User,
    Workflow,
)


def get_or_create_personal_library(user_id: str) -> Library:
    lib = Library.objects(scope=LibraryScope.PERSONAL, owner_user_id=user_id).first()
    if lib:
        return lib
    return Library(
        scope=LibraryScope.PERSONAL,
        owner_user_id=user_id,
        title="My Library",
        description="Personal collection of workflows and search sets.",
    ).save()


def get_or_create_team_library(team: Team) -> Library:
    lib = Library.objects(scope=LibraryScope.TEAM, team=team).first()
    if lib:
        return lib
    return Library(
        scope=LibraryScope.TEAM,
        team=team,
        title=f"{team.name} Library",
        description=f"Shared library for team {team.name}.",
    ).save()


def get_or_create_verified_library() -> Library:
    lib = Library.objects(scope=LibraryScope.VERIFIED).first()
    if lib:
        return lib
    return Library(
        scope=LibraryScope.VERIFIED,
        title="Verified Catalog",
        description="Curated, verified workflows and search sets.",
    ).save()


def _mk_library_item(obj, added_by_user_id: str) -> LibraryItem:
    # Detect type
    kind = None
    from_path = f"{obj.__class__.__module__}.{obj.__class__.__name__}"
    if obj.__class__.__name__ == "Workflow":
        kind = "workflow"
        verified = bool(getattr(obj, "verified", False))
    elif obj.__class__.__name__ == "SearchSet":
        kind = "searchset"
        verified = bool(getattr(obj, "verified", False))
    elif obj.__class__.__name__ == "SearchSetItem" and obj.searchtype == "prompt":
        kind = "prompt"
        verified = False
    elif obj.__class__.__name__ == "SearchSetItem" and obj.searchtype == "formatter":
        kind = "formatter"
        verified = False
    else:
        raise ValueError(f"Unsupported library object type: {from_path}")

    li = LibraryItem(
        obj=obj,
        kind=kind,
        added_by_user_id=added_by_user_id,
        verified=verified,
        verified_at=datetime.now() if verified else None,
        verified_by_user_id=None,
    ).save()
    return li


def add_object_to_library(obj, library: Library, added_by_user_id: str) -> LibraryItem:
    # Avoid duplicate entries pointing to the same object in the same library
    existing = [it for it in library.items if it.obj == obj]
    if existing:
        return existing[0]

    li = _mk_library_item(obj, added_by_user_id)
    library.items.append(li)
    library.updated_at = datetime.now()
    library.save()
    return li


def add_verified_to_personal(user_id: str, obj):
    if not getattr(obj, "verified", False):
        raise ValueError("Object is not verified.")
    lib = get_or_create_personal_library(user_id)
    return add_object_to_library(obj, lib, added_by_user_id=user_id)


def add_verified_to_team(team: Team, added_by_user_id: str, obj):
    if not getattr(obj, "verified", False):
        raise ValueError("Object is not verified.")
    lib = get_or_create_team_library(team)
    return add_object_to_library(obj, lib, added_by_user_id=added_by_user_id)


def promote_personal_item_to_team(user_id: str, team: Team, obj):
    # Ensure it exists in personal library (optional guard)
    personal = get_or_create_personal_library(user_id)
    if not any(it.obj == obj for it in personal.items):
        # Not strictly required, but keeps semantics explicit
        add_object_to_library(obj, personal, added_by_user_id=user_id)

    team_lib = get_or_create_team_library(team)
    return add_object_to_library(obj, team_lib, added_by_user_id=user_id)


def sync_verification_flags_for_object(obj, verified_by_user_id: str | None = None):
    now = datetime.now()
    is_verified = bool(getattr(obj, "verified", False))
    for li in LibraryItem.objects(obj=obj):
        li.verified = is_verified
        li.verified_at = now if is_verified else None
        li.verified_by_user_id = verified_by_user_id if is_verified else None
        li.save()


# ---- Quick accessors for libraries by scope ----


def get_personal_library(user_id: str) -> Optional[Library]:
    return Library.objects(scope=LibraryScope.PERSONAL, owner_user_id=user_id).first()


def get_team_library(team: Team) -> Optional[Library]:
    return Library.objects(scope=LibraryScope.TEAM, team=team).first()


def get_verified_library() -> Optional[Library]:
    return Library.objects(scope=LibraryScope.VERIFIED).first()


def _items_of_kind(
    lib: Optional[Library], kind: Literal["workflow", "searchset"]
) -> list:
    if not lib:
        return []
    # Filter LibraryItems by kind, then return the underlying object
    return [li.obj for li in lib.items if li.kind == kind and li.obj is not None]


def _dedup_by_id(objs: Sequence) -> list:
    seen = set()
    out = []
    for o in objs:
        oid = str(o.id)
        if oid not in seen:
            seen.add(oid)
            out.append(o)
    return out


def workflows_from_personal_library(user_id: str) -> list[Workflow]:
    return _items_of_kind(get_personal_library(user_id), "workflow")


def workflows_from_team_library(team: Team) -> list[Workflow]:
    return _items_of_kind(get_team_library(team), "workflow")


def workflows_from_verified_library() -> list[Workflow]:
    return _items_of_kind(get_verified_library(), "workflow")


def workflows_by_scope(
    user_id: Optional[str] = None,
    team: Optional[Team] = None,
    include_verified: bool = True,
) -> dict[str, list[Workflow]]:
    out = {}
    if user_id:
        out["personal"] = workflows_from_personal_library(user_id)
    if team:
        out["team"] = workflows_from_team_library(team)
    if include_verified:
        out["verified"] = workflows_from_verified_library()
    return out


def searchsets_from_personal_library(
    user_id: str, set_type: Optional[str] = None
) -> list[SearchSet]:
    sets_ = _items_of_kind(get_personal_library(user_id), "searchset")
    return [
        s
        for s in sets_
        if (set_type is None or getattr(s, "set_type", None) == set_type)
    ]


def searchsets_from_team_library(
    team: Team, set_type: Optional[str] = None
) -> list[SearchSet]:
    sets_ = _items_of_kind(get_team_library(team), "searchset")
    return [
        s
        for s in sets_
        if (set_type is None or getattr(s, "set_type", None) == set_type)
    ]


def searchsets_from_verified_library(set_type: Optional[str] = None) -> list[SearchSet]:
    sets_ = _items_of_kind(get_verified_library(), "searchset")
    return [
        s
        for s in sets_
        if (set_type is None or getattr(s, "set_type", None) == set_type)
    ]


def searchsets_by_scope(
    user_id: Optional[str] = None,
    team: Optional[Team] = None,
    include_verified: bool = True,
    set_type: Optional[str] = None,
) -> dict[str, list[SearchSet]]:
    out = {}
    if user_id:
        out["personal"] = searchsets_from_personal_library(user_id, set_type=set_type)
    if team:
        out["team"] = searchsets_from_team_library(team, set_type=set_type)
    if include_verified:
        out["verified"] = searchsets_from_verified_library(set_type=set_type)
    return out


ScopeStr = Literal["personal", "team", "verified"]
KindStr = Literal["workflow", "searchset", "all"]


def _collect_libraries(
    scopes: Sequence[ScopeStr], user_id: Optional[str], team: Optional[Team]
) -> list[Library]:
    libs: list[Library] = []
    for s in scopes:
        if s == "personal":
            if not user_id:
                continue
            lib = get_personal_library(user_id)
            if lib:
                libs.append(lib)
        elif s == "team":
            if not team:
                continue
            lib = get_team_library(team)
            if lib:
                libs.append(lib)
        elif s == "verified":
            lib = get_verified_library()
            if lib:
                libs.append(lib)
    return libs


def _li_passes_tag_filter(li: LibraryItem, tags: Optional[Sequence[str]]) -> bool:
    if not tags:
        return True
    # require ALL tags present
    s = set(li.tags or [])
    return all(t in s for t in tags)


def _text_match(obj, q: Optional[str]) -> bool:
    if not q:
        return True
    ql = q.lower()

    if isinstance(obj, Workflow):
        name = (obj.name or "").lower()
        desc = (obj.description or "").lower()
        return (ql in name) or (ql in desc)
    if isinstance(obj, SearchSet):
        title = (obj.title or "").lower()
        return ql in title
    return False


def search_libraries(
    *,
    scopes: Sequence[ScopeStr],  # e.g., ["personal", "team", "verified"]
    user_id: Optional[str] = None,
    team: Optional[Team] = None,
    kind: KindStr = "all",  # "workflow" | "searchset" | "all"
    set_type: Optional[str] = None,  # only applies to searchsets
    q: Optional[str] = None,  # free-text in titles/desc
    tags: Optional[Sequence[str]] = None,  # match ALL tags on LibraryItem
    verified_only: bool = False,  # filter on LibraryItem.verified mirror
    offset: int = 0,
    limit: Optional[int] = None,
) -> Tuple[list, int]:
    """
    Returns (results, total_count). `results` is a list of underlying objects (Workflow or SearchSet).
    """
    libs = _collect_libraries(scopes, user_id, team)
    if not libs:
        return ([], 0)

    # Build candidate LibraryItems based on kind & optional tag/verified filters
    li_candidates: list[Tuple[LibraryItem, object]] = []
    allowed_kinds = {"workflow", "searchset"} if kind == "all" else {kind}

    for lib in libs:
        for li in lib.items:
            if li.kind not in allowed_kinds:
                continue
            if verified_only and not li.verified:
                continue
            if not _li_passes_tag_filter(li, tags):
                continue
            obj = li.obj
            if obj is None:
                continue

            # SearchSet set_type filter (when relevant)
            if li.kind == "searchset" and set_type is not None:
                if getattr(obj, "set_type", None) != set_type:
                    continue

            # text filter
            if not _text_match(obj, q):
                continue

            li_candidates.append((li, obj))

    # Dedup by underlying object id, preserving first-seen ordering
    objs = _dedup_by_id([obj for _, obj in li_candidates])
    total = len(objs)

    # Pagination
    if offset < 0:
        offset = 0
    if limit is None or limit <= 0:
        paged = objs[offset:]
    else:
        paged = objs[offset : offset + limit]

    return (paged, total)


def _get_or_create_personal_library(user_id: str) -> Library:
    lib = Library.objects(scope=LibraryScope.PERSONAL, owner_user_id=user_id).first()
    if lib:
        return lib
    return Library(
        scope=LibraryScope.PERSONAL,
        title="My Library",
        description="Personal library",
        owner_user_id=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ).save()


def _get_or_create_team_library(team: Team) -> Library:
    lib = Library.objects(scope=LibraryScope.TEAM, team=team).first()
    if lib:
        return lib
    return Library(
        scope=LibraryScope.TEAM,
        title=f"{team.name} Library",
        description=f"Shared library for team: {team.name}",
        team=team,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ).save()


def _owner_id_for(obj) -> str | None:
    """
    Decide which field reflects 'ownership' for backfill.
    Prefer created_by_user_id when present; otherwise user_id.
    """
    uid = getattr(obj, "created_by_user_id", None) or getattr(obj, "user_id", None)
    return uid or None


def _ensure_library_item(lib: Library, obj, kind: str) -> LibraryItem:
    """
    Create-or-get a LibraryItem pointing to obj (Workflow or SearchSet) and
    attach to lib.items if missing. Idempotent.
    """
    # Look for any LibraryItem that already points at this obj/kind.
    # We keep a single item globally (not per library) to avoid duplication.
    li = LibraryItem.objects(obj=obj, kind=kind).first()
    if not li:
        # mirror verified if source has it
        verified_flag = bool(getattr(obj, "verified", False))
        li = LibraryItem(
            obj=obj,
            kind=kind,
            added_by_user_id=_owner_id_for(obj) or "",
            added_at=datetime.now(timezone.utc),
            verified=verified_flag,
            verified_at=datetime.now(timezone.utc) if verified_flag else None,
        ).save()

    # Attach to the target library if not already attached
    if li.id not in [x.id for x in lib.items]:
        lib.items.append(li)
        lib.updated_at = datetime.now(timezone.utc)
        lib.save()

    return li


def ensure_user_team_libraries(user: User) -> list[Library]:
    """
    Ensure a team library exists for every team the user belongs to.
    Returns the list of libraries (created or found).
    """
    libs = []
    memberships = TeamMembership.objects(user_id=user.user_id)
    for m in memberships:
        libs.append(_get_or_create_team_library(m.team))
    return libs


def backfill_personal_library(user: User) -> Library:
    """
    Ensure user’s personal library exists and backfill it with all of their
    Workflows and SearchSets.
    """
    lib = _get_or_create_personal_library(user.user_id)

    # Find objects "owned" by the user
    # Ownership rule: created_by_user_id == user.user_id OR user_id == user.user_id
    user_q = Q(created_by_user_id=user.user_id) | Q(user_id=user.user_id)

    # SearchSets
    for ss in SearchSet.objects(user_q):
        _ensure_library_item(lib, ss, "searchset")

    # Workflows
    for wf in Workflow.objects(user_q):
        _ensure_library_item(lib, wf, "workflow")

    return lib


# ---------- batch utilities ----------


def ensure_everyone_has_libraries_and_backfill(personal_only: bool = False) -> None:
    """
    Run once or on a schedule. Safe to re-run.
    - Ensures each user has a personal library and backfills it.
    - If personal_only=False, also ensures a team library for every team they belong to.
    """
    for user in User.objects():
        backfill_personal_library(user)
        if not personal_only:
            ensure_user_team_libraries(user)


# ---------- optional signal hooks (auto-create on demand) ----------


def _user_post_save(sender, document: User, **kwargs):
    # Ensure the personal library exists for new/updated users
    _get_or_create_personal_library(document.user_id)


# If you want this behavior automatically:
# signals.post_save.connect(_user_post_save, sender=User)
