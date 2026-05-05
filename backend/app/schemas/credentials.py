"""Request/response models for credentials endpoints."""

from typing import Literal, Optional

from pydantic import BaseModel


CredentialType = Literal["static_header", "oauth_client_credentials"]


class CreateCredentialRequest(BaseModel):
    name: str
    type: CredentialType
    description: Optional[str] = None
    payload: dict
    team_id: Optional[str] = None


class UpdateCredentialRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    # If provided, replaces the encrypted payload wholesale. Omit to keep
    # existing secrets in place when only renaming.
    payload: Optional[dict] = None


class CredentialResponse(BaseModel):
    id: str
    name: str
    type: str
    description: Optional[str] = None
    team_id: Optional[str] = None
    user_id: str
    payload: dict  # secret fields appear as "<set>" or ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    can_manage: bool = True
