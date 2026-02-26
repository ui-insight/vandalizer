import uuid

from app.models.space import Space


async def list_spaces() -> list[dict]:
    """List all spaces."""
    spaces = await Space.find_all().to_list()
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


async def update_space(space_uuid: str, title: str | None = None) -> Space | None:
    """Update a space."""
    space = await Space.find_one(Space.uuid == space_uuid)
    if not space:
        return None
    if title is not None:
        space.title = title
    await space.save()
    return space


async def delete_space(space_uuid: str) -> bool:
    """Delete a space."""
    space = await Space.find_one(Space.uuid == space_uuid)
    if not space:
        return False
    await space.delete()
    return True
