"""Batch resolution of user_ids to AuthorRef records for list endpoints."""

from typing import Iterable, Optional

from app.models.user import User
from app.schemas.user import AuthorRef


SYSTEM_AUTHOR_NAME = "Verified Catalog"


async def resolve_authors(user_ids: Iterable[str]) -> dict[str, AuthorRef]:
    """Resolve a batch of user_ids to AuthorRef. Unknown ids get an AuthorRef with id only.

    The reserved "system" user_id (used by the seeded verified catalog) is rendered
    with a friendly display name so it doesn't surface as a literal "system" chip.
    """
    ids = sorted({uid for uid in user_ids if uid})
    if not ids:
        return {}
    real_ids = [uid for uid in ids if uid != "system"]
    users = await User.find({"user_id": {"$in": real_ids}}).to_list() if real_ids else []
    by_id = {u.user_id: u for u in users}
    result: dict[str, AuthorRef] = {}
    for uid in ids:
        if uid == "system":
            result[uid] = AuthorRef(user_id=uid, name=SYSTEM_AUTHOR_NAME, email=None)
        else:
            result[uid] = AuthorRef(
                user_id=uid,
                name=by_id[uid].name if uid in by_id else None,
                email=by_id[uid].email if uid in by_id else None,
            )
    return result


async def resolve_author(user_id: Optional[str]) -> Optional[AuthorRef]:
    """Resolve a single user_id to an AuthorRef, or None if user_id is empty."""
    if not user_id:
        return None
    refs = await resolve_authors([user_id])
    return refs.get(user_id)
