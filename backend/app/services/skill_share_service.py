"""Share links for Skills.

A link lets a signed-in person outside the owner's team read a Skill's
instructions and use it in their own chats. It gives nothing else: access
checks ignore it unless the caller asks for it by name
(the ``allow_shared`` switch of ``get_authorized_search_set``), and only the paths
that read a Skill for chat do.
"""

import datetime
import secrets
from typing import Any

from pymongo import ReturnDocument

from app.models.search_set_share import SearchSetShare

MAX_TOKEN_LENGTH = 200


def _shares() -> Any:
    return SearchSetShare.get_motor_collection()


async def create_link(search_set_uuid: str, user_id: str) -> str:
    """The Skill's link token, made on first use. One write, so two people
    copying the link at once get the same token."""
    doc = await _shares().find_one_and_update(
        {"search_set_uuid": search_set_uuid},
        {"$setOnInsert": {
            "search_set_uuid": search_set_uuid,
            "token": secrets.token_urlsafe(32),
            "recipients": [],
            "created_by": user_id,
            "created_at": datetime.datetime.now(tz=datetime.timezone.utc),
        }},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["token"]


async def turn_off(search_set_uuid: str) -> int:
    """Stop the link and drop everyone it let in. Returns how many that was."""
    doc = await _shares().find_one_and_delete({"search_set_uuid": search_set_uuid})
    return len(doc.get("recipients") or []) if doc else 0


async def open_link(search_set_uuid: str, token: str, user_id: str) -> bool:
    """Record *user_id* as someone the Skill is shared with, if *token* is the
    Skill's current one. The check and the write are one operation, so a link
    turned off at the same moment lets nobody in."""
    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH or not user_id:
        return False
    result = await _shares().update_one(
        {"search_set_uuid": search_set_uuid, "token": token},
        {"$addToSet": {"recipients": user_id}},
    )
    return result.matched_count == 1


async def is_recipient(search_set_uuid: str, user_id: str | None) -> bool:
    if not user_id:
        return False
    return await _shares().count_documents(
        {"search_set_uuid": search_set_uuid, "recipients": user_id}, limit=1,
    ) > 0
