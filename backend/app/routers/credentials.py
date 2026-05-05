"""Credentials API routes — team-scoped CRUD with secret payloads encrypted at rest."""

import datetime
import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.credential import Credential
from app.models.team import TeamMembership
from app.models.user import User
from app.schemas.credentials import (
    CreateCredentialRequest,
    CredentialResponse,
    UpdateCredentialRequest,
)
from app.services import credentials_service

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
    if req.payload is not None:
        try:
            credentials_service.validate_payload(cred.type, req.payload)
        except credentials_service.CredentialError as e:
            raise HTTPException(status_code=400, detail=str(e))
        cred.payload = credentials_service.encrypt_payload(cred.type, req.payload)
        # Drop any cached bearer keyed by this credential.
        credentials_service.invalidate_cached_token(str(cred.id))
    cred.updated_at = _now()
    await cred.save()
    return _to_response(cred)


@router.delete("/{credential_id}")
async def delete_credential(credential_id: str, user: User = Depends(get_current_user)) -> dict:
    cred = await _load_for_manage(credential_id, user)
    cred_id = str(cred.id)
    await cred.delete()
    credentials_service.invalidate_cached_token(cred_id)
    return {"status": "deleted", "id": cred_id}


@router.post("/{credential_id}/invalidate-cache")
async def invalidate_cache(credential_id: str, user: User = Depends(get_current_user)) -> dict:
    """Drop any cached bearer token for this credential. Useful after upstream rotations."""
    cred = await _load_for_manage(credential_id, user)
    credentials_service.invalidate_cached_token(str(cred.id))
    return {"status": "invalidated", "id": str(cred.id)}
