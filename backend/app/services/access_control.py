from __future__ import annotations

from dataclasses import dataclass, field

from beanie import PydanticObjectId

from app.models.automation import Automation
from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.knowledge import KnowledgeBase
from app.models.library import Library, LibraryFolder, LibraryItem, LibraryItemKind, LibraryScope
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.models.verification import VerifiedItemMetadata

TEAM_MANAGE_ROLES = frozenset({"owner", "admin"})


@dataclass(slots=True)
class TeamAccessContext:
    team_uuids: set[str] = field(default_factory=set)
    team_object_ids: set[str] = field(default_factory=set)
    roles_by_uuid: dict[str, str] = field(default_factory=dict)
    roles_by_object_id: dict[str, str] = field(default_factory=dict)


def _has_team_membership(team_id: str | None, team_access: TeamAccessContext) -> bool:
    if not team_id:
        return False
    return team_id in team_access.team_uuids or team_id in team_access.team_object_ids


def _team_role(team_id: str | None, team_access: TeamAccessContext) -> str | None:
    if not team_id:
        return None
    return (
        team_access.roles_by_uuid.get(team_id)
        or team_access.roles_by_object_id.get(team_id)
    )


def _org_scope_allows(
    organization_ids: list[str] | None,
    user_org_ancestry: list[str] | None,
) -> bool:
    if not organization_ids:
        return True
    if user_org_ancestry is None:
        return False
    return bool(set(organization_ids) & set(user_org_ancestry))


async def _load_user_org_ancestry(
    user: User,
    user_org_ancestry: list[str] | None,
    organization_ids: list[str] | None,
) -> list[str] | None:
    if user_org_ancestry is not None or not organization_ids:
        return user_org_ancestry
    from app.services import organization_service

    return await organization_service.get_user_org_ancestry(user)


async def get_team_access_context(user: User) -> TeamAccessContext:
    memberships = await TeamMembership.find(
        TeamMembership.user_id == user.user_id
    ).to_list()
    if not memberships:
        return TeamAccessContext()

    team_ids = [m.team for m in memberships]
    teams = await Team.find({"_id": {"$in": team_ids}}).to_list()
    role_by_team_id = {m.team: m.role for m in memberships}

    roles_by_uuid: dict[str, str] = {}
    roles_by_object_id: dict[str, str] = {}
    for team in teams:
        role = role_by_team_id.get(team.id)
        if role:
            roles_by_uuid[team.uuid] = role
            roles_by_object_id[str(team.id)] = role

    return TeamAccessContext(
        team_uuids=set(roles_by_uuid.keys()),
        team_object_ids=set(roles_by_object_id.keys()),
        roles_by_uuid=roles_by_uuid,
        roles_by_object_id=roles_by_object_id,
    )


def can_view_team(team_id: str | None, team_access: TeamAccessContext) -> bool:
    return _has_team_membership(team_id, team_access)


def can_manage_team(team_id: str | None, team_access: TeamAccessContext) -> bool:
    return _team_role(team_id, team_access) in TEAM_MANAGE_ROLES


def can_view_folder(
    folder: SmartFolder,
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if folder.team_id:
        return _has_team_membership(folder.team_id, team_access)
    return folder.user_id == user.user_id


def can_manage_folder(
    folder: SmartFolder,
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if folder.team_id:
        return _team_role(folder.team_id, team_access) in TEAM_MANAGE_ROLES
    return folder.user_id == user.user_id


def can_view_document(
    document: SmartDocument,
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if document.user_id == user.user_id:
        return True
    return _has_team_membership(document.team_id, team_access)


def can_manage_document(
    document: SmartDocument,
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if document.user_id == user.user_id:
        return True
    return bool(
        document.team_id
        and _team_role(document.team_id, team_access) in TEAM_MANAGE_ROLES
    )


async def get_authorized_folder(
    folder_uuid: str,
    user: User,
    *,
    manage: bool = False,
    allow_admin: bool = False,
    team_access: TeamAccessContext | None = None,
) -> SmartFolder | None:
    folder = await SmartFolder.find_one(SmartFolder.uuid == folder_uuid)
    if not folder:
        return None

    access = team_access or await get_team_access_context(user)
    allowed = (
        can_manage_folder(folder, user, access, allow_admin=allow_admin)
        if manage
        else can_view_folder(folder, user, access, allow_admin=allow_admin)
    )
    return folder if allowed else None


async def get_authorized_document(
    document_uuid: str,
    user: User,
    *,
    manage: bool = False,
    allow_admin: bool = False,
    team_access: TeamAccessContext | None = None,
) -> SmartDocument | None:
    document = await SmartDocument.find_one(SmartDocument.uuid == document_uuid)
    if not document:
        return None

    access = team_access or await get_team_access_context(user)
    allowed = (
        can_manage_document(document, user, access, allow_admin=allow_admin)
        if manage
        else can_view_document(document, user, access, allow_admin=allow_admin)
    )
    return document if allowed else None


# ---------------------------------------------------------------------------
# Library helpers
# ---------------------------------------------------------------------------


def can_view_library(
    library: Library,
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if library.scope == LibraryScope.PERSONAL:
        return library.owner_user_id == user.user_id
    if library.scope == LibraryScope.TEAM:
        return _has_team_membership(str(library.team) if library.team else None, team_access)
    return True


def can_manage_library(
    library: Library,
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if library.scope == LibraryScope.PERSONAL:
        return library.owner_user_id == user.user_id
    if library.scope == LibraryScope.TEAM:
        return _team_role(str(library.team) if library.team else None, team_access) in TEAM_MANAGE_ROLES
    return False


def can_view_library_folder(
    folder: LibraryFolder,
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if folder.scope == LibraryScope.PERSONAL:
        return folder.owner_user_id == user.user_id
    if folder.scope == LibraryScope.TEAM:
        return _has_team_membership(str(folder.team) if folder.team else None, team_access)
    return True


def can_manage_library_folder(
    folder: LibraryFolder,
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if folder.scope == LibraryScope.PERSONAL:
        return folder.owner_user_id == user.user_id
    if folder.scope == LibraryScope.TEAM:
        return (
            folder.owner_user_id == user.user_id
            or _team_role(str(folder.team) if folder.team else None, team_access) in TEAM_MANAGE_ROLES
        )
    return False


async def get_authorized_library(
    library_id: str,
    user: User,
    *,
    manage: bool = False,
    allow_admin: bool = False,
    team_access: TeamAccessContext | None = None,
) -> Library | None:
    try:
        library = await Library.get(PydanticObjectId(library_id))
    except Exception:
        return None
    if not library:
        return None

    access = team_access or await get_team_access_context(user)
    allowed = (
        can_manage_library(library, user, access, allow_admin=allow_admin)
        if manage
        else can_view_library(library, user, access, allow_admin=allow_admin)
    )
    return library if allowed else None


async def get_authorized_library_folder(
    folder_uuid: str,
    user: User,
    *,
    manage: bool = False,
    allow_admin: bool = False,
    team_access: TeamAccessContext | None = None,
) -> LibraryFolder | None:
    folder = await LibraryFolder.find_one(LibraryFolder.uuid == folder_uuid)
    if not folder:
        return None

    access = team_access or await get_team_access_context(user)
    allowed = (
        can_manage_library_folder(folder, user, access, allow_admin=allow_admin)
        if manage
        else can_view_library_folder(folder, user, access, allow_admin=allow_admin)
    )
    return folder if allowed else None


async def _verified_library_item_visible(
    item: LibraryItem,
    user: User,
    *,
    user_org_ancestry: list[str] | None = None,
) -> bool:
    meta = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == item.kind.value,
        VerifiedItemMetadata.item_id == str(item.item_id),
    )
    org_ancestry = await _load_user_org_ancestry(
        user,
        user_org_ancestry,
        meta.organization_ids if meta else None,
    )
    return _org_scope_allows(meta.organization_ids if meta else None, org_ancestry)


async def has_library_backed_object_access(
    item_kind: str,
    object_id: str,
    user: User,
    team_access: TeamAccessContext,
    *,
    manage: bool = False,
    user_org_ancestry: list[str] | None = None,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True

    try:
        object_oid = PydanticObjectId(object_id)
    except Exception:
        return False

    try:
        kind = LibraryItemKind(item_kind)
    except ValueError:
        return False

    library_items = await LibraryItem.find(
        LibraryItem.item_id == object_oid,
        LibraryItem.kind == kind,
    ).to_list()
    if not library_items:
        return False

    for item in library_items:
        parent_libraries = await Library.find({"items": item.id}).to_list()
        for library in parent_libraries:
            allowed = (
                can_manage_library(library, user, team_access, allow_admin=allow_admin)
                if manage
                else can_view_library(library, user, team_access, allow_admin=allow_admin)
            )
            if not allowed:
                continue
            if library.scope == LibraryScope.VERIFIED and not await _verified_library_item_visible(
                item,
                user,
                user_org_ancestry=user_org_ancestry,
            ):
                continue
            return True

    return False


async def get_authorized_library_item(
    item_id: str,
    user: User,
    *,
    manage: bool = False,
    user_org_ancestry: list[str] | None = None,
    allow_admin: bool = False,
    team_access: TeamAccessContext | None = None,
) -> LibraryItem | None:
    try:
        item = await LibraryItem.get(PydanticObjectId(item_id))
    except Exception:
        return None
    if not item:
        return None

    access = team_access or await get_team_access_context(user)
    parent_libraries = await Library.find({"items": item.id}).to_list()
    for library in parent_libraries:
        allowed = (
            can_manage_library(library, user, access, allow_admin=allow_admin)
            if manage
            else can_view_library(library, user, access, allow_admin=allow_admin)
        )
        if not allowed:
            continue
        if library.scope == LibraryScope.VERIFIED and not await _verified_library_item_visible(
            item,
            user,
            user_org_ancestry=user_org_ancestry,
        ):
            continue
        return item
    return None


# ---------------------------------------------------------------------------
# Workflow helpers
# ---------------------------------------------------------------------------


def can_view_workflow(
    workflow: "Workflow",
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if workflow.user_id == user.user_id:
        return True
    return _has_team_membership(workflow.team_id, team_access)


def can_manage_workflow(
    workflow: "Workflow",
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if workflow.user_id == user.user_id:
        return True
    return bool(
        workflow.team_id
        and _team_role(workflow.team_id, team_access) in TEAM_MANAGE_ROLES
    )


async def get_authorized_workflow(
    workflow_id: str,
    user: User,
    *,
    manage: bool = False,
    allow_admin: bool = False,
    team_access: TeamAccessContext | None = None,
) -> "Workflow | None":
    from app.models.workflow import Workflow
    from beanie import PydanticObjectId

    try:
        wf = await Workflow.get(PydanticObjectId(workflow_id))
    except Exception:
        return None
    if not wf:
        return None

    access = team_access or await get_team_access_context(user)
    allowed = (
        can_manage_workflow(wf, user, access, allow_admin=allow_admin)
        if manage
        else can_view_workflow(wf, user, access, allow_admin=allow_admin)
    )
    if not allowed:
        allowed = await has_library_backed_object_access(
            "workflow",
            str(wf.id),
            user,
            access,
            manage=manage,
            allow_admin=allow_admin,
        )
    return wf if allowed else None


# ---------------------------------------------------------------------------
# Automation helpers
# ---------------------------------------------------------------------------


def can_view_automation(
    automation: Automation,
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if automation.user_id == user.user_id:
        return True
    return bool(
        automation.shared_with_team
        and _has_team_membership(automation.team_id, team_access)
    )


def can_manage_automation(
    automation: Automation,
    user: User,
    team_access: TeamAccessContext,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if automation.user_id == user.user_id:
        return True
    return bool(
        automation.shared_with_team
        and _team_role(automation.team_id, team_access) in TEAM_MANAGE_ROLES
    )


async def get_authorized_automation(
    automation_id: str,
    user: User,
    *,
    manage: bool = False,
    allow_admin: bool = False,
    team_access: TeamAccessContext | None = None,
) -> Automation | None:
    from beanie import PydanticObjectId

    try:
        automation = await Automation.get(PydanticObjectId(automation_id))
    except Exception:
        return None
    if not automation:
        return None

    access = team_access or await get_team_access_context(user)
    allowed = (
        can_manage_automation(automation, user, access, allow_admin=allow_admin)
        if manage
        else can_view_automation(automation, user, access, allow_admin=allow_admin)
    )
    return automation if allowed else None


# ---------------------------------------------------------------------------
# Knowledge base helpers
# ---------------------------------------------------------------------------


def can_view_knowledge_base(
    knowledge_base: KnowledgeBase,
    user: User,
    team_access: TeamAccessContext,
    *,
    user_org_ancestry: list[str] | None = None,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if knowledge_base.user_id == user.user_id:
        return True
    if not _org_scope_allows(knowledge_base.organization_ids, user_org_ancestry):
        return False
    if knowledge_base.verified:
        return True
    return bool(
        knowledge_base.shared_with_team
        and _has_team_membership(knowledge_base.team_id, team_access)
    )


def can_manage_knowledge_base(
    knowledge_base: KnowledgeBase,
    user: User,
    team_access: TeamAccessContext,
    *,
    user_org_ancestry: list[str] | None = None,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if knowledge_base.user_id == user.user_id:
        return True
    if not _org_scope_allows(knowledge_base.organization_ids, user_org_ancestry):
        return False
    return bool(
        knowledge_base.shared_with_team
        and _team_role(knowledge_base.team_id, team_access) in TEAM_MANAGE_ROLES
    )


async def get_authorized_knowledge_base(
    knowledge_base_uuid: str,
    user: User,
    *,
    manage: bool = False,
    user_org_ancestry: list[str] | None = None,
    allow_admin: bool = False,
    team_access: TeamAccessContext | None = None,
) -> KnowledgeBase | None:
    kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == knowledge_base_uuid)
    if not kb:
        return None

    access = team_access or await get_team_access_context(user)
    allowed = (
        can_manage_knowledge_base(
            kb,
            user,
            access,
            user_org_ancestry=user_org_ancestry,
            allow_admin=allow_admin,
        )
        if manage
        else can_view_knowledge_base(
            kb,
            user,
            access,
            user_org_ancestry=user_org_ancestry,
            allow_admin=allow_admin,
        )
    )
    return kb if allowed else None


async def get_authorized_knowledge_base_by_id(
    knowledge_base_id: str,
    user: User,
    *,
    manage: bool = False,
    user_org_ancestry: list[str] | None = None,
    allow_admin: bool = False,
    team_access: TeamAccessContext | None = None,
) -> KnowledgeBase | None:
    try:
        kb = await KnowledgeBase.get(PydanticObjectId(knowledge_base_id))
    except Exception:
        return None
    if not kb:
        return None

    access = team_access or await get_team_access_context(user)
    ancestry = await _load_user_org_ancestry(user, user_org_ancestry, kb.organization_ids)
    allowed = (
        can_manage_knowledge_base(
            kb,
            user,
            access,
            user_org_ancestry=ancestry,
            allow_admin=allow_admin,
        )
        if manage
        else can_view_knowledge_base(
            kb,
            user,
            access,
            user_org_ancestry=ancestry,
            allow_admin=allow_admin,
        )
    )
    return kb if allowed else None


# ---------------------------------------------------------------------------
# SearchSet helpers
# ---------------------------------------------------------------------------


def can_view_search_set(
    search_set: "SearchSet",
    user: User,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    if search_set.user_id == user.user_id:
        return True
    return bool(search_set.is_global)


def can_manage_search_set(
    search_set: "SearchSet",
    user: User,
    *,
    allow_admin: bool = False,
) -> bool:
    if allow_admin and user.is_admin:
        return True
    return search_set.user_id == user.user_id


async def get_authorized_search_set(
    search_set_uuid: str,
    user: User,
    *,
    manage: bool = False,
    allow_admin: bool = False,
) -> "SearchSet | None":
    from app.models.search_set import SearchSet

    ss = await SearchSet.find_one(SearchSet.uuid == search_set_uuid)
    if not ss:
        return None

    allowed = (
        can_manage_search_set(ss, user, allow_admin=allow_admin)
        if manage
        else can_view_search_set(ss, user, allow_admin=allow_admin)
    )
    if not allowed:
        team_access = await get_team_access_context(user)
        allowed = await has_library_backed_object_access(
            "search_set",
            str(ss.id),
            user,
            team_access,
            manage=manage,
            allow_admin=allow_admin,
        )
    return ss if allowed else None


async def get_authorized_search_set_by_id(
    search_set_id: str,
    user: User,
    *,
    manage: bool = False,
    allow_admin: bool = False,
) -> "SearchSet | None":
    from app.models.search_set import SearchSet

    try:
        ss = await SearchSet.get(PydanticObjectId(search_set_id))
    except Exception:
        return None
    if not ss:
        return None

    allowed = (
        can_manage_search_set(ss, user, allow_admin=allow_admin)
        if manage
        else can_view_search_set(ss, user, allow_admin=allow_admin)
    )
    if not allowed:
        team_access = await get_team_access_context(user)
        allowed = await has_library_backed_object_access(
            "search_set",
            str(ss.id),
            user,
            team_access,
            manage=manage,
            allow_admin=allow_admin,
        )
    return ss if allowed else None
