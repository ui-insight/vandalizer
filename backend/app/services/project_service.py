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

    Projects are **personal by default** — owned only by the creator, even when
    they're on a team. Sharing is an explicit choice: ``share_project_with_team``
    converts the project (and its folder subtree + KB) to the team, and invite
    links grant per-person access. This keeps "my projects are mine until I
    share them" true, rather than silently exposing every project to teammates.
    """
    from app.services import knowledge_service

    project_uuid = uuid_lib.uuid4().hex

    root_folder = SmartFolder(
        title=title,
        parent_id="0",
        user_id=user.user_id,
        team_id=None,
        created_by=user.user_id,
        uuid=uuid_lib.uuid4().hex,
    )
    await root_folder.insert()

    # The implicit KB — a hidden KnowledgeBase that auto-ingests project files.
    # Reusing the KB machinery means chat/retrieval work with zero new plumbing.
    kb = await knowledge_service.create_knowledge_base(
        title=title,
        user_id=user.user_id,
        team_id=None,
        description=f"Implicit knowledge base for project “{title}”.",
        implicit=True,
    )

    project = Project(
        uuid=project_uuid,
        title=title,
        description=description,
        owner_user_id=user.user_id,
        team_id=None,
        state="active",
        root_folder_uuid=root_folder.uuid,
        kb_uuid=kb.uuid,
    )
    await project.insert()
    return project


async def duplicate_project(source: Project, user: User) -> Project:
    """Create a copy of ``source`` owned by ``user``, returning immediately.

    Only the lightweight "shell" is built synchronously — a fresh root folder,
    a fresh implicit KB, the Project record, and copies of the pin *references*
    — so the new project appears in the list right away. The heavy content
    (folder subtree, files, and KB ingestion) is deep-copied in the background
    by ``copy_project_contents`` (enqueued by the router). The copy is always
    **personal** to the caller (``team_id=None``), matching ``create_project``.
    """
    from app.services import knowledge_service

    new_uuid = uuid_lib.uuid4().hex
    title = f"{source.title} (Copy)"

    root_folder = SmartFolder(
        title=title,
        parent_id="0",
        user_id=user.user_id,
        team_id=None,
        created_by=user.user_id,
        uuid=uuid_lib.uuid4().hex,
    )
    await root_folder.insert()

    kb = await knowledge_service.create_knowledge_base(
        title=title,
        user_id=user.user_id,
        team_id=None,
        description=f"Implicit knowledge base for project “{title}”.",
        implicit=True,
    )

    project = Project(
        uuid=new_uuid,
        title=title,
        description=source.description,
        owner_user_id=user.user_id,
        team_id=None,
        state="active",
        root_folder_uuid=root_folder.uuid,
        kb_uuid=kb.uuid,
    )
    await project.insert()

    # Pins are references, never copies of the artifact — cheap to duplicate and
    # safe to do synchronously so the new project's tools show up immediately.
    src_pins = await ProjectPin.find(ProjectPin.project_uuid == source.uuid).to_list()
    for pin in src_pins:
        await ProjectPin(
            project_uuid=new_uuid,
            pin_type=pin.pin_type,
            target_id=pin.target_id,
            created_by=user.user_id,
        ).insert()

    return project


async def copy_project_contents(
    source_project_uuid: str,
    new_project_uuid: str,
    user_id: str,
) -> dict:
    """Deep-copy the source project's folder subtree + documents into the new
    project, re-ingesting each file into the new project's implicit KB.

    Runs in the background (see ``tasks.project.duplicate``). Idempotency isn't
    guaranteed — it's meant to run once, right after ``duplicate_project`` built
    the shell. Memberships and invite links are intentionally NOT copied: access
    is per-project and shouldn't carry over to a personal copy.
    """
    import logging

    from app.config import Settings
    from app.services.storage import get_storage
    from app.tasks.document_tasks import perform_semantic_ingestion

    logger = logging.getLogger(__name__)

    source = await Project.find_one(Project.uuid == source_project_uuid)
    new = await Project.find_one(Project.uuid == new_project_uuid)
    if not source or not new:
        return {"folders": 0, "documents": 0}

    storage = get_storage(Settings())

    # 1. Recreate the folder subtree, mapping each old folder uuid to its new
    #    one. Walk breadth-first from the root so a parent is always mapped
    #    before its children (child.parent_id resolves via the map).
    id_map: dict[str, str] = {source.root_folder_uuid: new.root_folder_uuid}
    frontier = [source.root_folder_uuid]
    while frontier:
        children = await SmartFolder.find({"parent_id": {"$in": frontier}}).to_list()
        next_frontier: list[str] = []
        for child in children:
            new_parent = id_map.get(child.parent_id)
            if new_parent is None:
                continue  # orphan (parent not copied) — shouldn't happen
            new_child_uuid = uuid_lib.uuid4().hex
            await SmartFolder(
                title=child.title,
                parent_id=new_parent,
                user_id=user_id,
                team_id=None,
                created_by=user_id,
                uuid=new_child_uuid,
            ).insert()
            id_map[child.uuid] = new_child_uuid
            next_frontier.append(child.uuid)
        frontier = next_frontier

    # 2. Copy every (non-deleted) document in the subtree into the mapped folder,
    #    duplicating the stored file so the copy is independent, then re-ingest.
    docs = await SmartDocument.find(
        {"folder": {"$in": list(id_map.keys())}, "soft_deleted": {"$ne": True}}
    ).to_list()

    copied = 0
    for doc in docs:
        new_doc_uuid = uuid_lib.uuid4().hex.upper()
        ext = doc.extension or "pdf"
        new_rel_path = f"{user_id}/{new_doc_uuid}.{ext}"
        # Copy the underlying file to a new path. A duplicate must own its own
        # file — sharing the path would let deleting one copy remove the other's
        # bytes (delete_document physically removes the stored file).
        src_path = doc.downloadpath or doc.path
        try:
            data = await storage.read(src_path)
            await storage.write(new_rel_path, data)
        except Exception:
            logger.warning(
                "duplicate_project: could not copy stored file for doc %s (%s); "
                "sharing the source path", doc.uuid, src_path,
            )
            new_rel_path = src_path

        new_doc = SmartDocument(
            title=doc.title,
            raw_text=doc.raw_text,
            text_markers=list(doc.text_markers or []),
            extension=ext,
            path=new_rel_path,
            downloadpath=new_rel_path,
            uuid=new_doc_uuid,
            user_id=user_id,
            team_id=None,
            folder=id_map.get(doc.folder),
            token_count=doc.token_count,
            num_pages=doc.num_pages,
            classification=doc.classification,
            classification_confidence=doc.classification_confidence,
            classified_at=doc.classified_at,
            classified_by=doc.classified_by,
            valid=doc.valid,
            processing=False,
            chromadb_ready=False,
            chunk_count=0,
        )
        await new_doc.insert()

        # Ingest into ChromaDB (doc-level) and mirror into the new project's
        # implicit KB. perform_semantic_ingestion resolves the owning project by
        # folder ancestry, which now points at the new project.
        if (new_doc.raw_text or "").strip():
            perform_semantic_ingestion.delay(new_doc.raw_text, new_doc_uuid, user_id)
        copied += 1

    new.updated_at = datetime.datetime.now()
    await new.save()
    return {"folders": len(id_map), "documents": copied}


async def list_projects(user: User) -> list[Project]:
    """Projects the user owns, can reach via team, or is a member of."""
    access = await access_control.get_team_access_context(user)
    or_clauses: list[dict] = [{"owner_user_id": user.user_id}]
    # Match can_view_project: a team project keys on the team UUID, but accept
    # ObjectId-string team_ids too so list/view never disagree (the team
    # _id-vs-uuid trap that has silently hidden content before).
    team_ids = list(access.team_uuids) + list(access.team_object_ids)
    if team_ids:
        or_clauses.append({"team_id": {"$in": team_ids}})
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


async def _is_project_member(project: Project, user: User) -> bool:
    """True if the user has a personal (invite-granted) membership in the project."""
    membership = await ProjectMembership.find_one(
        ProjectMembership.project_uuid == project.uuid,
        ProjectMembership.user_id == user.user_id,
    )
    return membership is not None


async def leave_project(project: Project, user: User) -> None:
    """Remove the requesting user's own invite-granted membership.

    Owners can't leave (they delete the project instead), and access that comes
    from team membership can't be dropped here — only a personal invite grant.
    """
    if project.owner_user_id == user.user_id:
        raise ValueError("The owner can't leave a project — delete it instead")
    membership = await ProjectMembership.find_one(
        ProjectMembership.project_uuid == project.uuid,
        ProjectMembership.user_id == user.user_id,
    )
    if not membership:
        raise ValueError(
            "Your access comes from your team, not a personal invite, so there's "
            "nothing to leave here"
        )
    await membership.delete()


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


async def make_project_personal(project: Project, user: User) -> Project:
    """Revert a team-shared project back to personal ownership (owner-only).

    Inverse of ``share_project_with_team``: returns the folder subtree and its
    documents to the owner and un-shares the implicit KB. Per-person invite
    memberships are kept — only the team-wide exposure is removed.
    """
    if project.owner_user_id != user.user_id and not user.is_admin:
        raise ValueError("Only the project owner can make it personal")
    if not project.team_id:
        raise ValueError("Project is already personal")

    from app.services import folder_service

    await folder_service.convert_to_personal_folder(
        project.root_folder_uuid, user, owner_user_id=project.owner_user_id
    )

    project.team_id = None
    project.updated_at = datetime.datetime.now()
    await project.save()

    if project.kb_uuid:
        from app.models.knowledge import KnowledgeBase

        kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == project.kb_uuid)
        if kb:
            kb.team_id = None
            kb.shared_with_team = False
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


async def get_project_capabilities(project: Project) -> dict:
    """Count what's inside a project: files, indexed docs, pins, members.

    Shared by the project home (overview) and the project list, so an explorer
    card can show the same at-a-glance "what's in here" summary as the home.
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
        "files": {"count": file_count, "folders": len(folder_uuids) - 1},
        "knowledge": {"ready": bool(project.kb_uuid), "documents": indexed},
        "workflows": {"count": pin_counts["workflow"]},
        "extractions": {"count": pin_counts["extraction"]},
        "automations": {"count": pin_counts["automation"]},
        "external_kbs": {"count": pin_counts["knowledge_base"]},
        # owner + invited collaborators
        "members": {"count": member_count + 1},
    }


async def get_project_overview(project: Project, user: User) -> dict:
    """A self-contained snapshot: every capability and what's in it.

    Powers the project home so it's clear at a glance what the project holds.
    """
    return {
        **serialize_project(project),
        "role": await get_project_role(project, user),
        "can_leave": (
            project.owner_user_id != user.user_id
            and await _is_project_member(project, user)
        ),
        "capabilities": await get_project_capabilities(project),
    }


async def summarize_project(project: Project, user: User) -> dict:
    """List-card view: the base project, the viewer's role, and capability counts.

    Lets the project explorer show what's inside each project — and which manage
    actions to offer — without a separate per-project overview fetch.
    """
    return {
        **serialize_project(project),
        "role": await get_project_role(project, user),
        "can_leave": (
            project.owner_user_id != user.user_id
            and await _is_project_member(project, user)
        ),
        "capabilities": await get_project_capabilities(project),
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
