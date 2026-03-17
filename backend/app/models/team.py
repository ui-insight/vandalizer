import datetime
from typing import Optional

from pydantic import Field
from beanie import Document
from beanie import PydanticObjectId


class Team(Document):
    uuid: str
    name: str
    owner_user_id: str
    organization_id: Optional[str] = None  # org uuid for university hierarchy
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "team"
        indexes = ["uuid", "owner_user_id", "organization_id"]


class TeamMembership(Document):
    team: PydanticObjectId
    user_id: str
    role: str = "member"  # owner, admin, member
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "team_membership"
        indexes = [
            [("team", 1), ("user_id", 1)],
            "user_id",
        ]


class TeamInvite(Document):
    team: PydanticObjectId
    email: str
    invited_by_user_id: str
    role: str = "member"  # owner, admin, member
    token: str
    accepted: bool = False
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    sent_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    resend_count: int = 0

    class Settings:
        name = "team_invite"
        indexes = ["token", "email"]
