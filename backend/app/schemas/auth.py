import re
from typing import Optional

from pydantic import BaseModel, field_validator


class LoginRequest(BaseModel):
    user_id: str
    password: str


class RegisterRequest(BaseModel):
    user_id: Optional[str] = None
    email: str
    password: str
    name: Optional[str] = None
    invite_token: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        errors: list[str] = []
        if len(v) < 8:
            errors.append("at least 8 characters")
        if not re.search(r"[A-Z]", v):
            errors.append("at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("at least one lowercase letter")
        if not re.search(r"\d", v):
            errors.append("at least one digit")
        if errors:
            raise ValueError(
                "Password does not meet complexity requirements. "
                "Must contain: " + "; ".join(errors) + "."
            )
        return v


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        errors: list[str] = []
        if len(v) < 8:
            errors.append("at least 8 characters")
        if not re.search(r"[A-Z]", v):
            errors.append("at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("at least one lowercase letter")
        if not re.search(r"\d", v):
            errors.append("at least one digit")
        if errors:
            raise ValueError(
                "Password does not meet complexity requirements. "
                "Must contain: " + "; ".join(errors) + "."
            )
        return v


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


class DeleteAccountRequest(BaseModel):
    password: Optional[str] = None
    confirmation: str


class UserResponse(BaseModel):
    id: str
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    is_admin: bool = False
    is_staff: bool = False
    is_examiner: bool = False
    is_support_agent: bool = False
    is_demo_user: bool = False
    current_team: Optional[str] = None
    current_team_uuid: Optional[str] = None
