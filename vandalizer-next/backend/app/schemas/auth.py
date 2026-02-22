from typing import Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    user_id: str
    password: str


class RegisterRequest(BaseModel):
    user_id: Optional[str] = None
    email: str
    password: str
    name: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    is_admin: bool = False
    is_examiner: bool = False
    current_team: Optional[str] = None
    current_team_uuid: Optional[str] = None
