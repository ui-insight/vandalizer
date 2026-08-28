"""Credentials API routes — team-scoped CRUD with secret payloads encrypted at rest."""

import asyncio
import datetime
import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.credential import Credential
from app.models.team import TeamMembership
from app.models.user import User
from app.schemas.credentials import (
    CredentialTestResponse,
    TestCredentialDraftRequest,
    TestSavedCredentialRequest,
    CreateCredentialRequest,
    CredentialResponse,
    UpdateCredentialRequest,
)
from app.services import audit_service, credentials_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _to_response(cred: Credential, *, can_manage: bool = True) -> CredentialResponse:
    safe = credentials_service.metadata_view({
        "_id": cred.id,
        "name": cred.name,
        "type": cred.type,
        "description": cred.description,
        "team_id": cred.team_id,
        "user_id": cred.user_id,
        "payload": cred.payload,
        "created_at": cred.created_at,
        "updated_at": cred.updated_at,
    })
    return CredentialResponse(
        id=str(cred.id),
        name=safe["name"],
        type=safe["type"],
        description=safe["description"],
        team_id=safe["team_id"],
        user_id=safe["user_id"],
        payload=safe["payload"],
        created_at=cred.created_at.isoformat() if cred.created_at else None,
        updated_at=cred.updated_at.isoformat() if cred.updated_at else None,
        can_manage=can_manage,
    )


async def _can_manage_team(user: User, team_id: str | None) -> bool:
    """User can manage credentials they own; team-scoped credentials require admin/owner role."""
    if not team_id:
        return True
    if user.is_admin:
        return True
    try:
        team_oid = PydanticObjectId(team_id)
    except Exception:
        return False
    membership = await TeamMembership.find_one(
        TeamMembership.team == team_oid,
        TeamMembership.user_id == user.user_id,
    )
    return bool(membership and membership.role in ("owner", "admin"))


async def _can_view_team(user: User, team_id: str | None) -> bool:
    if not team_id:
        return True
    if user.is_admin:
        return True
    try:
        team_oid = PydanticObjectId(team_id)
    except Exception:
        return False
    membership = await TeamMembership.find_one(
        TeamMembership.team == team_oid,
        TeamMembership.user_id == user.user_id,
    )
    return membership is not None


async def _load_for_manage(credential_id: str, user: User) -> Credential:
    try:
        cred = await Credential.get(PydanticObjectId(credential_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Credential not found")
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    if cred.user_id != user.user_id:
        if not await _can_manage_team(user, cred.team_id):
            raise HTTPException(status_code=403, detail="You don't have permission to manage this credential")
    return cred


async def _load_for_view(credential_id: str, user: User) -> Credential:
    try:
        cred = await Credential.get(PydanticObjectId(credential_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Credential not found")
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    if cred.user_id != user.user_id and not await _can_view_team(user, cred.team_id):
        raise HTTPException(status_code=404, detail="Credential not found")
    return cred


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

@router.post("/test", response_model=CredentialTestResponse)
async def test_credential_draft(
    body: TestCredentialDraftRequest, user: User = Depends(get_current_user),
) -> CredentialTestResponse:
    """Test a credential before it is saved — the form's values, as typed.

    A real attempt: OAuth performs the token exchange; a test URL, if given,
    receives one GET with the auth applied. The report names each step and
    why it failed; secret values never appear in it.
    """
    result = await asyncio.to_thread(
        credentials_service.run_connection_test, body.type, body.payload, test_url=body.test_url,
    )
    return CredentialTestResponse(**result)


@router.post("/{credential_id}/test", response_model=CredentialTestResponse)
async def test_saved_credential(
    credential_id: str,
    body: TestSavedCredentialRequest | None = None,
    user: User = Depends(get_current_user),
) -> CredentialTestResponse:
    """Test a saved credential with its stored secrets — anyone who can use
    the credential may test it. Unsaved form edits in ``payload`` are merged
    over the stored payload (blank secret = keep the stored one)."""
    cred = await _load_for_view(credential_id, user)
    encrypted = cred.payload or {}
    if body and body.payload:
        # Merged edits can redirect the stored secrets (a new token_endpoint
        # receives the stored client_secret and a freshly signed assertion),
        # so testing with edits needs the same permission as saving them.
        if cred.user_id != user.user_id and not await _can_manage_team(user, cred.team_id):
            raise HTTPException(status_code=403, detail="You don't have permission to manage this credential")
        try:
            encrypted = credentials_service.merge_update_payload(cred.type, encrypted, body.payload)
        except credentials_service.CredentialError as e:
            raise HTTPException(status_code=400, detail=str(e))
    payload = credentials_service.decrypt_payload(cred.type, encrypted)
    result = await asyncio.to_thread(
        credentials_service.run_connection_test, cred.type, payload,
        test_url=(body.test_url if body else None) or payload.get("test_url") or None,
    )
    return CredentialTestResponse(**result)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=CredentialResponse)
async def create_credential(
    req: CreateCredentialRequest,
    user: User = Depends(get_current_user),
) -> CredentialResponse:
    try:
        credentials_service.validate_payload(req.type, req.payload)
    except credentials_service.CredentialError as e:
        raise HTTPException(status_code=400, detail=str(e))

    team_id = req.team_id or (str(user.current_team) if user.current_team else None)
    if team_id and not await _can_manage_team(user, team_id):
        raise HTTPException(status_code=403, detail="Not allowed to create credentials for this team")

    encrypted = credentials_service.encrypt_payload(req.type, req.payload)
    cred = Credential(
        name=req.name,
        type=req.type,
        description=req.description,
        team_id=team_id,
        user_id=user.user_id,
        payload=encrypted,
    )
    await cred.insert()
    return _to_response(cred)


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(user: User = Depends(get_current_user)) -> list[CredentialResponse]:
    """List credentials owned by the user or shared with their current team."""
    team_id = str(user.current_team) if user.current_team else None
    query: dict
    if team_id:
        query = {"$or": [{"user_id": user.user_id}, {"team_id": team_id}]}
    else:
        query = {"user_id": user.user_id}
    creds = await Credential.find(query).to_list()
    results: list[CredentialResponse] = []
    for cred in creds:
        can_manage = (
            cred.user_id == user.user_id
            or await _can_manage_team(user, cred.team_id)
        )
        results.append(_to_response(cred, can_manage=can_manage))
    return results


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(credential_id: str, user: User = Depends(get_current_user)) -> CredentialResponse:
    try:
        cred = await Credential.get(PydanticObjectId(credential_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Credential not found")
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    if cred.user_id != user.user_id and not await _can_view_team(user, cred.team_id):
        raise HTTPException(status_code=403, detail="You don't have permission to view this credential")
    can_manage = (
        cred.user_id == user.user_id
        or await _can_manage_team(user, cred.team_id)
    )
    return _to_response(cred, can_manage=can_manage)


@router.patch("/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: str,
    req: UpdateCredentialRequest,
    user: User = Depends(get_current_user),
) -> CredentialResponse:
    cred = await _load_for_manage(credential_id, user)
    if req.name is not None:
        cred.name = req.name
    if req.description is not None:
        cred.description = req.description
    steps_updated: int | None = None
    if req.type is not None and req.type != cred.type:
        # The stored secrets belong to the old type, so a type change is a
        # fresh credential under the same id: the new type's payload must be
        # complete, nothing is merged, and the old secrets are gone.
        if req.payload is None:
            raise HTTPException(
                status_code=400,
                detail="Changing the credential type requires the complete payload for the new type.",
            )
        try:
            credentials_service.validate_payload(req.type, req.payload)
        except credentials_service.CredentialError as e:
            raise HTTPException(status_code=400, detail=str(e))
        cred.type = req.type
        cred.payload = credentials_service.encrypt_payload(req.type, req.payload)
        credentials_service.invalidate_cached_token(str(cred.id))
        # An API Node step stores auth_strategy alongside credential_id and
        # the run refuses a mismatch — re-point every step that uses this
        # credential so the workflows keep running.
        steps_updated = await _repoint_api_steps(str(cred.id), req.type)
    elif req.payload is not None:
        # Merge over the stored payload so a caller can rotate just the private
        # key (or change one field) without resending the others — secrets are
        # never returned, so the client can't echo them back.
        merged = credentials_service.merge_update_payload(
            cred.type, cred.payload, req.payload
        )
        try:
            credentials_service.validate_payload(cred.type, merged)
        except credentials_service.CredentialError as e:
            raise HTTPException(status_code=400, detail=str(e))
        cred.payload = credentials_service.encrypt_payload(cred.type, merged)
        # Drop any cached bearer keyed by this credential.
        credentials_service.invalidate_cached_token(str(cred.id))
    cred.updated_at = _now()
    await cred.save()
    resp = _to_response(cred)
    if steps_updated is not None:
        resp.steps_updated = steps_updated
    return resp


async def _repoint_api_steps(credential_id: str, new_type: str) -> int:
    """Set ``auth_strategy`` to *new_type* on every API Node step task that
    uses this credential. Returns how many were changed."""
    from app.models.workflow import WorkflowStepTask

    tasks = await WorkflowStepTask.find({"data.credential_id": credential_id}).to_list()
    changed = 0
    for task in tasks:
        data = dict(task.data or {})
        if data.get("auth_strategy") == new_type:
            continue
        data["auth_strategy"] = new_type
        task.data = data
        await task.save()
        changed += 1
    return changed


@router.delete("/{credential_id}")
async def delete_credential(credential_id: str, user: User = Depends(get_current_user)) -> dict:
    cred = await _load_for_manage(credential_id, user)
    cred_id = str(cred.id)
    await cred.delete()
    credentials_service.invalidate_cached_token(cred_id)
    await audit_service.log_event(
        action="credential.delete",
        actor_user_id=user.user_id,
        resource_type="credential",
        resource_id=cred_id,
        resource_name=cred.name,
        team_id=cred.team_id,
        detail={"credential_type": cred.type},
    )
    return {"status": "deleted", "id": cred_id}


@router.post("/{credential_id}/invalidate-cache")
async def invalidate_cache(credential_id: str, user: User = Depends(get_current_user)) -> dict:
    """Drop any cached bearer token for this credential. Useful after upstream rotations."""
    cred = await _load_for_manage(credential_id, user)
    credentials_service.invalidate_cached_token(str(cred.id))
    return {"status": "invalidated", "id": str(cred.id)}
