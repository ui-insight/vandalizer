from typing import Optional

from app.models.space import Space
from app.models.user import User


async def list_spaces(user: User) -> list[dict]:
    """Return all spaces belonging to the given user."""
    spaces = await Space.find(Space.user == user.user_id).to_list()
    return [
        {
            "id": str(s.id),
            "uuid": s.uuid,
            "title": s.title,
            "user": s.user,
        }
        for s in spaces
    ]


async def update_space(space_uuid: str, title: str, user: User) -> Optional[dict]:
    """Update a space's title. Returns None if space not found or not owned by user."""
    space = await Space.find_one(Space.uuid == space_uuid)
    if not space or space.user != user.user_id:
        return None
    space.title = title
    await space.save()
    return {
        "id": str(space.id),
        "uuid": space.uuid,
        "title": space.title,
        "user": space.user,
    }


async def delete_space(space_uuid: str, user: User) -> bool:
    """Delete a space. Returns False if space not found or not owned by user."""
    space = await Space.find_one(Space.uuid == space_uuid)
    if not space or space.user != user.user_id:
        return False
    await space.delete()
    return True
