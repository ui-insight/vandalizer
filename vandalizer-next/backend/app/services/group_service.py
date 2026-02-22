"""Group service — CRUD, membership, and cascade operations."""

import re
from typing import Optional

from beanie import PydanticObjectId

from app.models.group import Group, GroupMembership
from app.models.user import User
from app.models.verification import VerifiedItemMetadata
from app.models.knowledge import KnowledgeBase


async def list_groups() -> list[dict]:
    """List all groups sorted by name, with member counts."""
    groups = await Group.find_all().sort(+Group.name).to_list()
    results = []
    for g in groups:
        count = await GroupMembership.find(
            GroupMembership.group_id == g.id,
        ).count()
        results.append({
            "id": str(g.id),
            "uuid": g.uuid,
            "name": g.name,
            "description": g.description,
            "created_by_user_id": g.created_by_user_id,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "member_count": count,
        })
    return results


async def create_group(
    name: str,
    user_id: str,
    description: Optional[str] = None,
) -> dict:
    """Create a new group."""
    g = Group(
        name=name.strip()[:200],
        description=(description or "").strip()[:2000] or None,
        created_by_user_id=user_id,
    )
    await g.insert()
    return {
        "id": str(g.id),
        "uuid": g.uuid,
        "name": g.name,
        "description": g.description,
        "created_by_user_id": g.created_by_user_id,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "member_count": 0,
    }


async def update_group(
    group_uuid: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> dict | None:
    """Update a group's name/description."""
    g = await Group.find_one(Group.uuid == group_uuid)
    if not g:
        return None
    if name is not None:
        g.name = name.strip()[:200]
    if description is not None:
        g.description = description.strip()[:2000] or None
    await g.save()
    count = await GroupMembership.find(GroupMembership.group_id == g.id).count()
    return {
        "id": str(g.id),
        "uuid": g.uuid,
        "name": g.name,
        "description": g.description,
        "created_by_user_id": g.created_by_user_id,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "member_count": count,
    }


async def delete_group(group_uuid: str) -> bool:
    """Delete a group and cascade: remove memberships, pull uuid from items/KBs."""
    g = await Group.find_one(Group.uuid == group_uuid)
    if not g:
        return False

    # Delete all memberships for this group
    await GroupMembership.find(GroupMembership.group_id == g.id).delete()

    # Pull this group uuid from VerifiedItemMetadata.group_ids
    await VerifiedItemMetadata.find(
        {"group_ids": group_uuid},
    ).update_many({"$pull": {"group_ids": group_uuid}})

    # Pull this group uuid from KnowledgeBase.group_ids
    await KnowledgeBase.find(
        {"group_ids": group_uuid},
    ).update_many({"$pull": {"group_ids": group_uuid}})

    await g.delete()
    return True


async def list_group_members(group_uuid: str) -> list[dict]:
    """List members of a group with user details."""
    g = await Group.find_one(Group.uuid == group_uuid)
    if not g:
        return []
    memberships = await GroupMembership.find(
        GroupMembership.group_id == g.id,
    ).to_list()
    results = []
    for m in memberships:
        user = await User.find_one(User.user_id == m.user_id)
        results.append({
            "user_id": m.user_id,
            "name": user.name if user else None,
            "email": user.email if user else None,
            "added_by_user_id": m.added_by_user_id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })
    return results


async def add_user_to_group(
    group_uuid: str,
    user_id: str,
    added_by: str,
) -> bool:
    """Add a user to a group. Idempotent."""
    g = await Group.find_one(Group.uuid == group_uuid)
    if not g:
        return False
    # Check if already a member
    existing = await GroupMembership.find_one(
        GroupMembership.group_id == g.id,
        GroupMembership.user_id == user_id,
    )
    if existing:
        return True  # idempotent
    m = GroupMembership(
        group_id=g.id,
        user_id=user_id,
        added_by_user_id=added_by,
    )
    await m.insert()
    return True


async def remove_user_from_group(group_uuid: str, user_id: str) -> bool:
    """Remove a user from a group."""
    g = await Group.find_one(Group.uuid == group_uuid)
    if not g:
        return False
    m = await GroupMembership.find_one(
        GroupMembership.group_id == g.id,
        GroupMembership.user_id == user_id,
    )
    if not m:
        return False
    await m.delete()
    return True


async def get_user_group_uuids(user_id: str) -> list[str]:
    """Get the list of group UUIDs a user belongs to."""
    memberships = await GroupMembership.find(
        GroupMembership.user_id == user_id,
    ).to_list()
    if not memberships:
        return []
    group_ids = [m.group_id for m in memberships]
    groups = await Group.find({"_id": {"$in": group_ids}}).to_list()
    return [g.uuid for g in groups]


async def search_users(query: str, limit: int = 20) -> list[dict]:
    """Search users by name or email."""
    regex = re.compile(re.escape(query), re.IGNORECASE)
    users = await User.find(
        {"$or": [{"name": {"$regex": regex}}, {"email": {"$regex": regex}}]}
    ).limit(limit).to_list()
    return [
        {
            "user_id": u.user_id,
            "name": u.name,
            "email": u.email,
        }
        for u in users
    ]
