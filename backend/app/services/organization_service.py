"""Organization hierarchy CRUD and visibility resolution."""

import datetime
import uuid
from typing import Optional

from app.models.organization import Organization
from app.models.team import Team
from app.models.user import User


# Valid parent org_type for each child org_type
VALID_PARENT_TYPES: dict[str, set[str | None]] = {
    "university": {None},  # root only
    "college": {"university"},
    "central_office": {"university"},
    "department": {"college", "central_office"},
    "unit": {"department"},
}

VALID_TYPES = set(VALID_PARENT_TYPES.keys())


async def create_organization(
    name: str,
    org_type: str,
    parent_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Organization:
    """Create a new org node with hierarchy validation."""
    if org_type not in VALID_TYPES:
        raise ValueError(f"org_type must be one of {VALID_TYPES}")

    if parent_id:
        parent = await Organization.find_one(Organization.uuid == parent_id)
        if not parent:
            raise ValueError(f"Parent org {parent_id} not found")
        allowed_parents = VALID_PARENT_TYPES.get(org_type, set())
        if parent.org_type not in allowed_parents:
            raise ValueError(
                f"A {org_type} cannot be a child of a {parent.org_type}. "
                f"Valid parent types: {allowed_parents - {None}}"
            )
    else:
        # No parent — only university can be root
        if org_type != "university":
            raise ValueError(f"Only 'university' can be a root node (no parent). Got '{org_type}'.")

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    org = Organization(
        uuid=str(uuid.uuid4()),
        name=name,
        org_type=org_type,
        parent_id=parent_id,
        metadata=metadata or {},
        created_at=now,
        updated_at=now,
    )
    await org.insert()
    return org


async def update_organization(
    org_uuid: str,
    name: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Organization:
    org = await Organization.find_one(Organization.uuid == org_uuid)
    if not org:
        raise ValueError(f"Organization {org_uuid} not found")

    if name is not None:
        org.name = name
    if metadata is not None:
        org.metadata = metadata
    org.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await org.save()
    return org


async def delete_organization(org_uuid: str) -> None:
    """Delete an org node and re-parent children to this org's parent."""
    org = await Organization.find_one(Organization.uuid == org_uuid)
    if not org:
        raise ValueError(f"Organization {org_uuid} not found")

    # Re-parent children
    children = await Organization.find(Organization.parent_id == org_uuid).to_list()
    for child in children:
        child.parent_id = org.parent_id
        await child.save()

    await org.delete()


async def get_organization(org_uuid: str) -> Optional[Organization]:
    return await Organization.find_one(Organization.uuid == org_uuid)


async def get_org_tree(root_uuid: Optional[str] = None) -> list[dict]:
    """Build the full org tree with a single DB query + in-memory assembly."""
    all_orgs = await Organization.find_all().to_list()

    # Index by uuid and group children by parent_id
    by_uuid: dict[str, Organization] = {o.uuid: o for o in all_orgs}
    children_of: dict[str | None, list[Organization]] = {}
    for o in all_orgs:
        children_of.setdefault(o.parent_id, []).append(o)

    # Load user and team counts per org
    user_counts: dict[str, int] = {}
    team_counts: dict[str, int] = {}
    users_with_org = await User.find(
        User.organization_id != None  # noqa: E711
    ).to_list()
    for u in users_with_org:
        user_counts[u.organization_id] = user_counts.get(u.organization_id, 0) + 1

    teams_with_org = await Team.find(
        Team.organization_id != None  # noqa: E711
    ).to_list()
    for t in teams_with_org:
        team_counts[t.organization_id] = team_counts.get(t.organization_id, 0) + 1

    def _build(org: Organization) -> dict:
        return {
            "uuid": org.uuid,
            "name": org.name,
            "org_type": org.org_type,
            "parent_id": org.parent_id,
            "metadata": org.metadata,
            "user_count": user_counts.get(org.uuid, 0),
            "team_count": team_counts.get(org.uuid, 0),
            "children": [_build(c) for c in children_of.get(org.uuid, [])],
        }

    if root_uuid:
        root = by_uuid.get(root_uuid)
        if not root:
            return []
        return [_build(root)]
    else:
        roots = children_of.get(None, [])
        return [_build(r) for r in roots]


async def get_org_members(org_uuid: str) -> dict:
    """Get users and teams assigned to a specific org node."""
    users = await User.find(User.organization_id == org_uuid).to_list()
    teams = await Team.find(Team.organization_id == org_uuid).to_list()
    return {
        "users": [
            {
                "user_id": u.user_id,
                "name": u.name,
                "email": u.email,
            }
            for u in users
        ],
        "teams": [
            {
                "uuid": t.uuid,
                "name": t.name,
                "owner_user_id": t.owner_user_id,
            }
            for t in teams
        ],
    }


async def get_ancestor_ids(org_uuid: str) -> list[str]:
    """Walk up the tree and return list of ancestor org UUIDs (closest first).

    Uses a single query to load all orgs for efficient traversal.
    """
    all_orgs = await Organization.find_all().to_list()
    by_uuid = {o.uuid: o for o in all_orgs}

    ancestors = []
    current_uuid = org_uuid
    seen = set()
    while current_uuid and current_uuid not in seen:
        seen.add(current_uuid)
        org = by_uuid.get(current_uuid)
        if not org or not org.parent_id:
            break
        ancestors.append(org.parent_id)
        current_uuid = org.parent_id
    return ancestors


async def get_descendant_ids(org_uuid: str) -> list[str]:
    """Get all descendant org UUIDs using a single query + in-memory BFS."""
    all_orgs = await Organization.find_all().to_list()
    children_of: dict[str | None, list[str]] = {}
    for o in all_orgs:
        children_of.setdefault(o.parent_id, []).append(o.uuid)

    descendants = []
    queue = [org_uuid]
    while queue:
        current = queue.pop(0)
        for child_uuid in children_of.get(current, []):
            descendants.append(child_uuid)
            queue.append(child_uuid)
    return descendants


async def get_visible_org_ids(user: User) -> Optional[list[str]]:
    """Determine which org IDs a user can see.

    Returns None if user can see everything (admin).
    Returns list of org IDs otherwise.
    """
    if user.is_admin:
        return None  # sees everything

    if not user.organization_id:
        return []  # no org assigned, sees nothing beyond their team

    org = await Organization.find_one(Organization.uuid == user.organization_id)
    if not org:
        return []

    # Central offices see everything under the university
    if org.org_type == "central_office":
        all_orgs = await Organization.find_all().to_list()
        return [o.uuid for o in all_orgs]

    # Others see their org and descendants
    descendants = await get_descendant_ids(org.uuid)
    return [org.uuid] + descendants


async def move_organization(org_uuid: str, new_parent_id: str | None) -> Organization:
    """Move an org node to a new parent (drag-and-drop reparenting)."""
    org = await Organization.find_one(Organization.uuid == org_uuid)
    if not org:
        raise ValueError(f"Organization {org_uuid} not found")

    if new_parent_id:
        parent = await Organization.find_one(Organization.uuid == new_parent_id)
        if not parent:
            raise ValueError(f"New parent org {new_parent_id} not found")
        # Prevent moving a node under itself or its descendants
        descendants = await get_descendant_ids(org_uuid)
        if new_parent_id in descendants:
            raise ValueError("Cannot move an organization under its own descendant")
    else:
        # Moving to root — only university can be root
        if org.org_type != "university":
            raise ValueError("Only 'university' nodes can be root (no parent)")

    org.parent_id = new_parent_id
    org.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await org.save()
    return org


async def update_org_type(org_uuid: str, new_type: str) -> Organization:
    """Change the org_type of a node."""
    if new_type not in VALID_TYPES:
        raise ValueError(f"org_type must be one of {VALID_TYPES}")
    org = await Organization.find_one(Organization.uuid == org_uuid)
    if not org:
        raise ValueError(f"Organization {org_uuid} not found")
    org.org_type = new_type
    org.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await org.save()
    return org


async def bulk_import_organizations(
    nodes: list[dict],
) -> list[Organization]:
    """Bulk import org nodes. Each node has: name, parent_name (optional), org_type.

    Processes nodes in order - parents must come before their children.
    Uses name matching to resolve parent references.
    """
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    # Build a map of name -> uuid for resolving parent references
    # Include existing orgs so imports can attach to existing tree
    existing = await Organization.find_all().to_list()
    name_to_uuid: dict[str, str] = {o.name: o.uuid for o in existing}

    created = []
    for node in nodes:
        name = node.get("name", "").strip()
        if not name:
            continue
        parent_name = (node.get("parent_name") or "").strip()
        org_type = node.get("org_type", "department")

        parent_id = None
        if parent_name:
            parent_id = name_to_uuid.get(parent_name)
            if not parent_id:
                raise ValueError(f"Parent '{parent_name}' not found for '{name}'. Make sure parents are listed before their children.")

        org = Organization(
            uuid=str(uuid.uuid4()),
            name=name,
            org_type=org_type,
            parent_id=parent_id,
            metadata={},
            created_at=now,
            updated_at=now,
        )
        await org.insert()
        name_to_uuid[name] = org.uuid
        created.append(org)

    return created


async def get_user_org_ancestry(user: User) -> Optional[list[str]]:
    """Get the user's org UUID + all ancestor org UUIDs.

    Used for checking visibility of org-scoped items (verified items, KBs).
    When an item is tagged with org X, anyone in X or a descendant of X can see it.
    We check this by seeing if X is in the user's ancestry chain.

    Returns None for admins/examiners (bypass filtering).
    Returns None for users with no org when no orgs exist (bypass filtering).
    Returns [] for users with no org assigned (when orgs are configured).
    """
    if user.is_admin or user.is_examiner:
        return None  # bypass filtering
    if not user.organization_id:
        # If no organizations exist in the system, bypass filtering entirely
        # so all users can see all verified items in dev / fresh installs.
        from app.models.organization import Organization
        org_count = await Organization.count()
        if org_count == 0:
            return None
        return []
    ancestors = await get_ancestor_ids(user.organization_id)
    return [user.organization_id] + ancestors
