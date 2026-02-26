from typing import Optional
from pydantic import BaseModel


class CreateTeamRequest(BaseModel):
    name: str


class UpdateTeamNameRequest(BaseModel):
    team_id: str
    name: str


class InviteRequest(BaseModel):
    team_id: str
    email: str
    role: str = "member"


class ChangeRoleRequest(BaseModel):
    team_id: str
    user_id: str
    role: str


class RemoveMemberRequest(BaseModel):
    team_id: str
    user_id: str


class TeamResponse(BaseModel):
    id: str
    uuid: str
    name: str
    owner_user_id: str
    role: Optional[str] = None  # caller's role in this team


class MemberResponse(BaseModel):
    user_id: str
    role: str
    name: Optional[str] = None
    email: Optional[str] = None


class InviteResponse(BaseModel):
    id: str
    email: str
    role: str
    accepted: bool
    token: str
