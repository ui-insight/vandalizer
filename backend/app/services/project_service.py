import datetime
import secrets
import uuid as uuid_lib

from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.project import (
    Project,
    ProjectJoinLink,
    ProjectMembership,
    ProjectPin,
)
from app.models.team import Team
from app.models.user import User
from app.services import access_control

PROJECT_INVITE_DEFAULT_EXPIRY_HOURS = 24 * 30  # 30 days
PROJECT_INVITE_MAX_EXPIRY_HOURS = 24 * 90


async def _project_folder_uuids(root_folder_uuid: str) -> list[str]:
    """Return the project's root folder plus all descendant folder uuids."""
    uuids = [root_folder_uuid]
    frontier = [root_folder_uuid]
    while frontier:
        children = await SmartFolder.find(
            {"parent_id": {"$in": frontier}}
        ).to_list()
        frontier = [child.uuid for child in children]
        uuids.extend(frontier)
    return uuids


async def _resolve_team_uuid(user: User) -> str | None:
    """The current team's UUID (folders/documents key on UUID, not ObjectId)."""
    if not user.current_team:
        return None
    team = await Team.get(user.current_team)
    return team.uuid if team else None


async def can_view_project(project: Project, user: User) -> bool:
    if project.owner_user_id == user.user_id or user.is_admin:
        return True
    if project.team_id:
        access = await access_control.get_team_access_context(user)
        if project.team_id in access.team_uuids or project.team_id in access.team_object_ids:
            return True
    membership = await ProjectMembership.find_one(
        ProjectMembership.project_uuid == project.uuid,
        ProjectMembership.user_id == user.user_id,
    )
    return membership is not None


async def get_authorized_project(project_uuid: str, user: User) -> Project | None:
    project = await Project.find_one(Project.uuid == project_uuid)
    if not project:
        return None
    return project if await can_view_project(project, user) else None


async def create_project(
    title: str,
    description: str | None,
    user: User,
) -> Project:
    """Create a project, allocating its root folder and implicit-KB name.

    When the user is on a team, the project (and its root folder) is team
    scoped so it's shared with the team; otherwise it's personal.
    """
    from app.services import knowledge_service

    team_uuid = await _resolve_team_uuid(user)
    project_uuid = uuid_lib.uuid4().hex

    root_folder = SmartFolder(
        title=title,
        parent_id="0",
        user_id=user.user_id if not team_uuid else None,
        team_id=team_uuid,
        created_by=user.user_id,
        uuid=uuid_lib.uuid4().hex,
    )
    await root_folder.insert()

    # The implicit KB — a hidden KnowledgeBase that auto-ingests project files.
    # Reusing the KB machinery means chat/retrieval work with zero new plumbing.
    kb = await knowledge_service.create_knowledge_base(
        title=title,
        user_id=user.user_id,
        team_id=team_uuid,
        description=f"Implicit knowledge base for project “{title}”.",
        implicit=True,
    )

    project = Project(
        uuid=project_uuid,
        title=title,
        description=description,
        owner_user_id=user.user_id,
        team_id=team_uuid,
        state="active",
        root_folder_uuid=root_folder.uuid,
        kb_uuid=kb.uuid,
    )
    await project.insert()
    return project


async def list_projects(user: User) -> list[Project]:
    """Projects the user owns, can reach via team, or is a member of."""
    access = await access_control.get_team_access_context(user)
    or_clauses: list[dict] = [{"owner_user_id": user.user_id}]
    if access.team_uuids:
        or_clauses.append({"team_id": {"$in": list(access.team_uuids)}})
    projects = await Project.find({"$or": or_clauses}).to_list()

    memberships = await ProjectMembership.find(
        ProjectMembership.user_id == user.user_id
    ).to_list()
    member_uuids = [m.project_uuid for m in memberships]
    seen = {p.uuid for p in projects}
    extra_uuids = [u for u in member_uuids if u not in seen]
    if extra_uuids:
        projects.extend(
            await Project.find({"uuid": {"$in": extra_uuids}}).to_list()
        )

    projects.sort(key=lambda p: p.updated_at, reverse=True)
    return projects


async def update_project(
    project: Project,
    *,
    title: str | None = None,
    description: str | None = None,
    state: str | None = None,
) -> Project:
    if title is not None:
        project.title = title
    if description is not None:
        project.description = description
    if state is not None:
        project.state = state
    project.updated_at = datetime.datetime.now()
    await project.save()
    return project


async def delete_project(project: Project) -> None:
    """Remove the project record, its memberships, and its pins.

    The root folder and its documents are intentionally left intact — deleting
    a project should not destroy the user's files. (Archiving via state is the
    expected path; hard file deletion can be added deliberately later.)
    """
    await ProjectMembership.find(
        ProjectMembership.project_uuid == project.uuid
    ).delete()
    await ProjectPin.find(ProjectPin.project_uuid == project.uuid).delete()
    await project.delete()


async def get_project_role(project: Project, user: User) -> str:
    """The requesting user's role in the project: owner|editor|viewer|none."""
    if project.owner_user_id == user.user_id:
        return "owner"
    if project.team_id:
        access = await access_control.get_team_access_context(user)
        if project.team_id in access.team_uuids or project.team_id in access.team_object_ids:
            return "editor"
    membership = await ProjectMembership.find_one(
        ProjectMembership.project_uuid == project.uuid,
        ProjectMembership.user_id == user.user_id,
    )
    if membership:
        return membership.role
    if user.is_admin:
        return "owner"
    return "none"


async def can_manage_project(project: Project, user: User) -> bool:
    return await get_project_role(project, user) in ("owner", "editor")


def _invite_status(link: ProjectJoinLink) -> str | None:
    if link.revoked:
        return "revoked"
    if link.expires_at and datetime.datetime.now() >= link.expires_at:
        return "expired"
    if link.max_uses is not None and link.use_count >= link.max_uses:
        return "exhausted"
    return None


def serialize_invite_link(link: ProjectJoinLink) -> dict:
    return {
        "token": link.token,
        "role": link.role,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "revoked": link.revoked,
        "use_count": link.use_count,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


async def create_project_invite_link(
    project: Project,
    actor: User,
    role: str = "viewer",
    expires_in_hours: int = PROJECT_INVITE_DEFAULT_EXPIRY_HOURS,
    max_uses: int | None = None,
) -> ProjectJoinLink:
    if role not in ("viewer", "editor"):
        raise ValueError("Role must be 'viewer' or 'editor'")
    if not await can_manage_project(project, actor):
        raise ValueError("Only the project owner or team can create invites")
    expires_in_hours = min(expires_in_hours, PROJECT_INVITE_MAX_EXPIRY_HOURS)
    link = ProjectJoinLink(
        project_uuid=project.uuid,
        token=secrets.token_urlsafe(32),
        created_by=actor.user_id,
        role=role,
        expires_at=datetime.datetime.now() + datetime.timedelta(hours=expires_in_hours),
        max_uses=max_uses,
    )
    await link.insert()
    return link


async def list_project_invite_links(project: Project) -> list[dict]:
    links = await ProjectJoinLink.find(
        ProjectJoinLink.project_uuid == project.uuid,
        ProjectJoinLink.revoked == False,  # noqa: E712
    ).to_list()
    return [serialize_invite_link(link) for link in links]


async def revoke_project_invite(token: str, actor: User) -> None:
    link = await ProjectJoinLink.find_one(ProjectJoinLink.token == token)
    if not link:
        raise ValueError("Invite link not found")
    project = await Project.find_one(Project.uuid == link.project_uuid)
    if not project or not await can_manage_project(project, actor):
        raise ValueError("Not allowed")
    link.revoked = True
    await link.save()


async def get_project_invite_info(token: str) -> dict | None:
    """Public preview of an invite link (shown before the user logs in)."""
    link = await ProjectJoinLink.find_one(ProjectJoinLink.token == token)
    if not link:
        return None
    project = await Project.find_one(Project.uuid == link.project_uuid)
    creator = await User.find_one(User.user_id == link.created_by)
    return {
        "role": link.role,
        "project_title": project.title if project else "a project",
        "project_uuid": project.uuid if project else None,
        "inviter_name": (creator.name or creator.user_id) if creator else None,
        "status": _invite_status(link),
    }


async def accept_project_invite(token: str, user: User) -> Project:
    link = await ProjectJoinLink.find_one(ProjectJoinLink.token == token)
    if not link:
        raise ValueError("Invalid invite link")
    status = _invite_status(link)
    if status == "revoked":
        raise ValueError("This invite link has been revoked")
    if status == "expired":
        raise ValueError("This invite link has expired")
    if status == "exhausted":
        raise ValueError("This invite link has reached its use limit")

    project = await Project.find_one(Project.uuid == link.project_uuid)
    if not project:
        raise ValueError("Project not found")

    # Owner / team members already have access — no membership needed.
    if await can_view_project(project, user):
        return project

    await ProjectMembership(
        project_uuid=project.uuid, user_id=user.user_id, role=link.role
    ).insert()
    link.use_count += 1
    await link.save()
    return project


async def list_project_members(project: Project) -> list[dict]:
    memberships = await ProjectMembership.find(
        ProjectMembership.project_uuid == project.uuid
    ).to_list()
    user_ids = [project.owner_user_id] + [m.user_id for m in memberships]
    users = await User.find({"user_id": {"$in": user_ids}}).to_list()
    umap = {u.user_id: u for u in users}

    owner = umap.get(project.owner_user_id)
    result = [{
        "user_id": project.owner_user_id,
        "role": "owner",
        "name": owner.name if owner else None,
        "email": owner.email if owner else None,
    }]
    for m in memberships:
        u = umap.get(m.user_id)
        result.append({
            "user_id": m.user_id,
            "role": m.role,
            "name": u.name if u else None,
            "email": u.email if u else None,
        })
    return result


async def remove_project_member(
    project: Project, member_user_id: str, actor: User
) -> None:
    if not await can_manage_project(project, actor):
        raise ValueError("Not allowed")
    if member_user_id == project.owner_user_id:
        raise ValueError("Cannot remove the project owner")
    await ProjectMembership.find(
        ProjectMembership.project_uuid == project.uuid,
        ProjectMembership.user_id == member_user_id,
    ).delete()


async def share_project_with_team(project: Project, user: User) -> Project:
    """Convert a personal project to the user's current team.

    Converts the project's whole folder subtree (and its documents) to team
    ownership too — otherwise teammates couldn't see the files — and marks the
    implicit KB team-scoped. Owner-only.
    """
    if project.owner_user_id != user.user_id and not user.is_admin:
        raise ValueError("Only the project owner can share it with the team")
    if project.team_id:
        raise ValueError("Project is already shared with a team")
    if not user.current_team:
        raise ValueError("You are not on a team")
    team = await Team.get(user.current_team)
    if not team:
        raise ValueError("Team not found")

    # Reuse the existing folder→team conversion (folder + descendants + docs).
    from app.services import folder_service

    await folder_service.convert_to_team_folder(project.root_folder_uuid, user)

    project.team_id = team.uuid
    project.updated_at = datetime.datetime.now()
    await project.save()

    if project.kb_uuid:
        from app.models.knowledge import KnowledgeBase

        kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == project.kb_uuid)
        if kb:
            kb.team_id = team.uuid
            kb.shared_with_team = True
            await kb.save()

    return project


async def add_pin(project: Project, pin_type: str, target_id: str, user: User) -> None:
    """Pin an existing artifact (workflow/extraction/automation/KB) to a project.

    A pin is a reference for quick access — it never moves or copies the artifact.
    """
    from app.models.project import PIN_TYPES

    if not await can_manage_project(project, user):
        raise ValueError("Not allowed")
    if pin_type not in PIN_TYPES:
        raise ValueError("Invalid pin type")
    existing = await ProjectPin.find_one(
        ProjectPin.project_uuid == project.uuid,
        ProjectPin.pin_type == pin_type,
        ProjectPin.target_id == target_id,
    )
    if existing:
        return
    await ProjectPin(
        project_uuid=project.uuid,
        pin_type=pin_type,
        target_id=target_id,
        created_by=user.user_id,
    ).insert()


async def remove_pin(project: Project, pin_type: str, target_id: str, user: User) -> None:
    if not await can_manage_project(project, user):
        raise ValueError("Not allowed")
    await ProjectPin.find(
        ProjectPin.project_uuid == project.uuid,
        ProjectPin.pin_type == pin_type,
        ProjectPin.target_id == target_id,
    ).delete()


async def _resolve_pin_name(pin: ProjectPin) -> str | None:
    """The display name of a pin's target, or None if it no longer exists."""
    from beanie import PydanticObjectId

    if pin.pin_type == "workflow":
        from app.models.workflow import Workflow
        try:
            wf = await Workflow.get(PydanticObjectId(pin.target_id))
        except Exception:
            wf = None
        return wf.name if wf else None
    if pin.pin_type == "extraction":
        from app.models.search_set import SearchSet
        ss = await SearchSet.find_one(SearchSet.uuid == pin.target_id)
        return ss.title if ss else None
    if pin.pin_type == "automation":
        from app.models.automation import Automation
        try:
            auto = await Automation.get(PydanticObjectId(pin.target_id))
        except Exception:
            auto = None
        return auto.name if auto else None
    if pin.pin_type == "knowledge_base":
        from app.models.knowledge import KnowledgeBase
        kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == pin.target_id)
        return kb.title if kb else None
    return None


async def list_pins(project: Project) -> list[dict]:
    pins = await ProjectPin.find(
        ProjectPin.project_uuid == project.uuid
    ).to_list()
    result = []
    for pin in pins:
        name = await _resolve_pin_name(pin)
        if name is None:
            continue  # target was deleted — skip stale pin
        result.append({
            "pin_type": pin.pin_type,
            "target_id": pin.target_id,
            "name": name,
        })
    return result


async def get_project_document_uuids(project: Project) -> list[str]:
    """All (non-deleted) document uuids in the project's folder subtree.

    The default input set for running an extraction/workflow "on the project".
    """
    folder_uuids = await _project_folder_uuids(project.root_folder_uuid)
    docs = await SmartDocument.find(
        {"folder": {"$in": folder_uuids}, "soft_deleted": {"$ne": True}}
    ).to_list()
    return [d.uuid for d in docs]


async def get_project_overview(project: Project, user: User) -> dict:
    """A self-contained snapshot: every capability and what's in it.

    Powers the project home so it's clear at a glance what the project holds.
    """
    folder_uuids = await _project_folder_uuids(project.root_folder_uuid)
    file_count = await SmartDocument.find(
        {"folder": {"$in": folder_uuids}, "soft_deleted": {"$ne": True}}
    ).count()

    # Implicit-KB indexing progress (how many files are searchable in chat).
    indexed = 0
    if project.kb_uuid:
        from app.models.knowledge import KnowledgeBase

        kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == project.kb_uuid)
        indexed = kb.sources_ready if kb else 0

    pins = await ProjectPin.find(ProjectPin.project_uuid == project.uuid).to_list()
    pin_counts = {kind: 0 for kind in ("workflow", "extraction", "automation", "knowledge_base")}
    for pin in pins:
        if pin.pin_type in pin_counts:
            pin_counts[pin.pin_type] += 1

    member_count = await ProjectMembership.find(
        ProjectMembership.project_uuid == project.uuid
    ).count()

    return {
        **serialize_project(project),
        "role": await get_project_role(project, user),
        "capabilities": {
            "files": {"count": file_count, "folders": len(folder_uuids) - 1},
            "knowledge": {"ready": bool(project.kb_uuid), "documents": indexed},
            "workflows": {"count": pin_counts["workflow"]},
            "extractions": {"count": pin_counts["extraction"]},
            "automations": {"count": pin_counts["automation"]},
            "external_kbs": {"count": pin_counts["knowledge_base"]},
            # owner + invited collaborators
            "members": {"count": member_count + 1},
        },
    }


def serialize_project(project: Project) -> dict:
    return {
        "uuid": project.uuid,
        "title": project.title,
        "description": project.description,
        "owner_user_id": project.owner_user_id,
        "team_id": project.team_id,
        "state": project.state,
        "root_folder_uuid": project.root_folder_uuid,
        "kb_uuid": project.kb_uuid,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }
