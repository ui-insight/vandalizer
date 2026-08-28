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
    # Switch the credential to another type. The stored secrets belong to the
    # old type, so a type change requires a complete ``payload`` for the new
    # one; API Node steps using this credential are re-pointed to match.
    type: Optional[CredentialType] = None


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
    # Set on an update that changed the type: how many API Node steps were
    # re-pointed to the new type so their runs keep working.
    steps_updated: Optional[int] = None


class TestCredentialDraftRequest(BaseModel):
    """Test an unsaved credential: the secrets travel in the request."""

    type: CredentialType
    payload: dict
    test_url: Optional[str] = None


class TestSavedCredentialRequest(BaseModel):
    """Test a saved credential. ``payload`` carries unsaved form edits and is
    merged over the stored payload the same way an update is (a blank secret
    keeps the stored one)."""

    payload: Optional[dict] = None
    test_url: Optional[str] = None


class CredentialTestStep(BaseModel):
    step: str
    ok: bool
    detail: str


class CredentialTestResponse(BaseModel):
    ok: bool
    steps: list[CredentialTestStep]
    status_code: Optional[int] = None
    elapsed_ms: Optional[int] = None
