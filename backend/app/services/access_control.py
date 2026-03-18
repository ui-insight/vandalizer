from __future__ import annotations

from dataclasses import dataclass

from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.team import Team, TeamMembership
from app.models.user import User

TEAM_MANAGE_ROLES = frozenset({"owner", "admin"})


@dataclass(slots=True)
class TeamAccessContext:
    team_uuids: set[str]
    roles_by_uuid: dict[str, str]


async def get_team_access_context(user: User) -> TeamAccessContext:
    memberships = await TeamMembership.find(
        TeamMembership.user_id == user.user_id
    ).to_list()
    if not memberships:
        return TeamAccessContext(team_uuids=set(), roles_by_uuid={})

    team_ids = [m.team for m in memberships]
    teams = await Team.find({"_id": {"$in": team_ids}}).to_list()
    role_by_team_id = {m.team: m.role for m in memberships}

    roles_by_uuid: dict[str, str] = {}
    for team in teams:
        role = role_by_team_id.get(team.id)
        if role:
            roles_by_uuid[team.uuid] = role

    return TeamAccessContext(
        team_uuids=set(roles_by_uuid.keys()),
        roles_by_uuid=roles_by_uuid,
    )


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
        return folder.team_id in team_access.team_uuids
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
        return team_access.roles_by_uuid.get(folder.team_id) in TEAM_MANAGE_ROLES
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
    return bool(document.team_id and document.team_id in team_access.team_uuids)


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
        and team_access.roles_by_uuid.get(document.team_id) in TEAM_MANAGE_ROLES
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
    return bool(workflow.team_id and workflow.team_id in team_access.team_uuids)


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
        and team_access.roles_by_uuid.get(workflow.team_id) in TEAM_MANAGE_ROLES
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
    return wf if allowed else None


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
    return ss if allowed else None
