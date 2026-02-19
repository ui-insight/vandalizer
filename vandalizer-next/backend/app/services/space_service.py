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
