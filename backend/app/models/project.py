import datetime
from typing import Optional

from beanie import Document
from pydantic import Field

# Project lifecycle states. A project is goal-scoped and temporal (unlike a
# Team, which is persistent), so it carries a lifecycle that lets it archive
# cleanly when the underlying work (e.g. a grant) closes out.
PROJECT_STATES = ("draft", "active", "submitted", "awarded", "closeout", "archived")

# Capability kinds a project can pin. Pins are *references* to existing
# user/team-owned artifacts — pinning never moves or copies the artifact, so a
# workflow can be pinned into many projects and stay in the owner's library.
PIN_TYPES = ("workflow", "extraction", "automation", "knowledge_base")

# Project-local collaborator roles. Deliberately lighter than Team roles: a
# Project ACL is for sharing one unit of work (read-mostly), not running an org.
PROJECT_ROLES = ("viewer", "editor")


class Project(Document):
    """A persistent, goal-scoped container for a unit of work (e.g. a grant).

    A Project owns one root SmartFolder (reusing the existing folder/upload/
    Chroma pipeline) and a dedicated Chroma collection (the implicit KB). It is
    scoped to the owner and, optionally, a team; capabilities (workflows,
    extractions, automations, external KBs) attach as ``ProjectPin`` references.
    """

    uuid: str
    title: str
    description: Optional[str] = None
    owner_user_id: str
    # Team UUID (matches SmartFolder/SmartDocument.team_id). None = personal
    # project. Both Team and Project scopes are optional by design.
    team_id: Optional[str] = None
    state: str = "active"  # one of PROJECT_STATES
    # The project's root folder — all of its files live in this subtree.
    root_folder_uuid: str
    # The project's implicit KB: a real (hidden) KnowledgeBase whose Chroma
    # collection auto-ingests every file dropped into the project, so
    # "chat with this project" works with no KB-building. Set at creation.
    kb_uuid: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "project"
        indexes = ["uuid", "owner_user_id", "team_id"]


class ProjectMembership(Document):
    """A lightweight, project-local collaborator grant (viewer/editor).

    Distinct from TeamMembership: no org hierarchy, just read-mostly sharing of
    a single project (the "share my grant with a PI to ask questions" case).
    """

    project_uuid: str
    user_id: str
    role: str = "viewer"  # one of PROJECT_ROLES
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "project_membership"
        indexes = [
            [("project_uuid", 1), ("user_id", 1)],
            "user_id",
        ]


class ProjectJoinLink(Document):
    """A public, revocable invite link that grants viewer (or editor) access to
    a single project — the "share my grant with a PI to ask questions" path.

    Mirrors TeamJoinLink but scoped to one project and defaulting to viewer.
    """

    project_uuid: str
    token: str
    created_by: str
    role: str = "viewer"  # viewer or editor
    expires_at: datetime.datetime
    revoked: bool = False
    max_uses: Optional[int] = None
    use_count: int = 0
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "project_join_link"
        indexes = ["token", "project_uuid"]


class ProjectPin(Document):
    """A reference attaching an existing artifact to a project for easy access.

    The pinned artifact (workflow/extraction/automation/KB) stays user/team
    owned — the pin is a pointer, never a copy, so cross-project reuse holds.
    """

    project_uuid: str
    pin_type: str  # one of PIN_TYPES
    target_id: str  # uuid or ObjectId string of the referenced artifact
    created_by: str
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "project_pin"
        indexes = [
            [("project_uuid", 1), ("pin_type", 1)],
        ]
