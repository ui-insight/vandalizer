import uuid

from app.models.space import Space
from app.models.user import User


def _space_owned_by_user(space: Space, user: User) -> bool:
    return space.user == user.user_id


async def list_spaces(user: User) -> list[dict]:
    """List spaces owned by the current user."""
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


async def create_space(title: str, user_id: str | None = None) -> Space:
    """Create a new space."""
    space = Space(
        uuid=uuid.uuid4().hex,
        title=title,
        user=user_id,
    )
    await space.insert()
    return space


async def update_space(space_uuid: str, user: User, title: str | None = None) -> Space | None:
    """Update a space owned by the current user."""
    space = await Space.find_one(Space.uuid == space_uuid)
    if not space or not _space_owned_by_user(space, user):
        return None
    if title is not None:
        space.title = title
    await space.save()
    return space


async def delete_space(space_uuid: str, user: User) -> bool:
    """Delete a space owned by the current user."""
    space = await Space.find_one(Space.uuid == space_uuid)
    if not space or not _space_owned_by_user(space, user):
        return False
    await space.delete()
    return True
