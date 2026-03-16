"""Organization hierarchy CRUD and visibility resolution."""

import datetime
import uuid
from typing import Optional

from app.models.organization import Organization
from app.models.team import Team
from app.models.user import User


async def create_organization(
    name: str,
    org_type: str,
    parent_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Organization:
    """Create a new org node."""
    valid_types = {"university", "college", "central_office", "department", "unit"}
    if org_type not in valid_types:
        raise ValueError(f"org_type must be one of {valid_types}")

    if parent_id:
        parent = await Organization.find_one(Organization.uuid == parent_id)
        if not parent:
            raise ValueError(f"Parent org {parent_id} not found")

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
    """Delete an org node and unlink children (move them to parent)."""
    org = await Organization.find_one(Organization.uuid == org_uuid)
    if not org:
        raise ValueError(f"Organization {org_uuid} not found")

    # Re-parent children to this org's parent
    children = await Organization.find(Organization.parent_id == org_uuid).to_list()
    for child in children:
        child.parent_id = org.parent_id
        await child.save()

    await org.delete()


async def get_organization(org_uuid: str) -> Optional[Organization]:
    return await Organization.find_one(Organization.uuid == org_uuid)


async def get_org_tree(root_uuid: Optional[str] = None) -> list[dict]:
    """Get the full org tree as nested dicts. If root_uuid is None, return all roots."""
    if root_uuid:
        root = await Organization.find_one(Organization.uuid == root_uuid)
        if not root:
            return []
        return [await _build_subtree(root)]
    else:
        roots = await Organization.find(Organization.parent_id == None).to_list()  # noqa: E711
        return [await _build_subtree(r) for r in roots]


async def _build_subtree(org: Organization) -> dict:
    children = await Organization.find(Organization.parent_id == org.uuid).to_list()
    return {
        "uuid": org.uuid,
        "name": org.name,
        "org_type": org.org_type,
        "parent_id": org.parent_id,
        "metadata": org.metadata,
        "children": [await _build_subtree(c) for c in children],
    }


async def get_ancestor_ids(org_uuid: str) -> list[str]:
    """Walk up the tree and return list of ancestor org UUIDs (closest first)."""
    ancestors = []
    current_uuid = org_uuid
    seen = set()
    while current_uuid and current_uuid not in seen:
        seen.add(current_uuid)
        org = await Organization.find_one(Organization.uuid == current_uuid)
        if not org or not org.parent_id:
            break
        ancestors.append(org.parent_id)
        current_uuid = org.parent_id
    return ancestors


async def get_descendant_ids(org_uuid: str) -> list[str]:
    """Get all descendant org UUIDs (BFS)."""
    descendants = []
    queue = [org_uuid]
    while queue:
        current = queue.pop(0)
        children = await Organization.find(Organization.parent_id == current).to_list()
        for child in children:
            descendants.append(child.uuid)
            queue.append(child.uuid)
    return descendants


async def get_visible_org_ids(user: User) -> Optional[list[str]]:
    """Determine which org IDs a user can see.

    Returns None if user can see everything (admin or central_office).
    Returns list of org IDs otherwise.
    """
    if user.is_admin:
        return None  # sees everything

    if not user.organization_id:
        return []  # no org assigned, sees nothing beyond their team

    org = await Organization.find_one(Organization.uuid == user.organization_id)
    if not org:
        return []

    # Central offices see everything at the same university
    if org.org_type == "central_office":
        # Find root university
        ancestors = await get_ancestor_ids(org.uuid)
        root_id = ancestors[-1] if ancestors else org.uuid
        all_descendants = await get_descendant_ids(root_id)
        return [root_id] + all_descendants

    # Others see their org and descendants
    descendants = await get_descendant_ids(org.uuid)
    return [org.uuid] + descendants
