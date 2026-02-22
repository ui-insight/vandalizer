"""Group-based visibility control for verified items and knowledge bases."""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document, PydanticObjectId
from pydantic import Field


class Group(Document):
    """A named group for restricting visibility of verified items and KBs."""

    uuid: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    description: Optional[str] = None
    created_by_user_id: str
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "group"


class GroupMembership(Document):
    """Join document linking a user to a group."""

    group_id: PydanticObjectId
    user_id: str
    added_by_user_id: str
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "group_membership"
