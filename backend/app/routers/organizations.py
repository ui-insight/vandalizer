"""Organization hierarchy management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.dependencies import get_current_user
from app.models.user import User
from app.models.organization import Organization
from app.services import organization_service, audit_service

router = APIRouter()


class CreateOrgRequest(BaseModel):
    name: str
    org_type: str
    parent_id: Optional[str] = None
    metadata: Optional[dict] = None


class UpdateOrgRequest(BaseModel):
    name: Optional[str] = None
    metadata: Optional[dict] = None


def _org_to_dict(org: Organization) -> dict:
    return {
        "uuid": org.uuid,
        "name": org.name,
        "org_type": org.org_type,
        "parent_id": org.parent_id,
        "metadata": org.metadata,
        "created_at": org.created_at.isoformat() if org.created_at else None,
        "updated_at": org.updated_at.isoformat() if org.updated_at else None,
    }


@router.get("/tree")
async def get_org_tree(user: User = Depends(get_current_user)):
    """Get the full organization tree."""
    tree = await organization_service.get_org_tree()
    return {"tree": tree}


@router.get("/")
async def list_organizations(
    org_type: Optional[str] = None,
    parent_id: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """List organizations, optionally filtered by type or parent."""
    filters = {}
    if org_type:
        filters["org_type"] = org_type
    if parent_id:
        filters["parent_id"] = parent_id

    orgs = await Organization.find(filters).to_list()
    return {"organizations": [_org_to_dict(o) for o in orgs]}


@router.get("/{org_uuid}")
async def get_organization(org_uuid: str, user: User = Depends(get_current_user)):
    org = await organization_service.get_organization(org_uuid)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return _org_to_dict(org)


@router.post("/")
async def create_organization(body: CreateOrgRequest, user: User = Depends(get_current_user)):
    """Create a new organization node. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        org = await organization_service.create_organization(
            name=body.name,
            org_type=body.org_type,
            parent_id=body.parent_id,
            metadata=body.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await audit_service.log_event(
        action="org.create",
        actor_user_id=user.user_id,
        resource_type="organization",
        resource_id=org.uuid,
        resource_name=org.name,
        detail={"org_type": org.org_type, "parent_id": org.parent_id},
    )

    return _org_to_dict(org)


@router.put("/{org_uuid}")
async def update_organization(
    org_uuid: str, body: UpdateOrgRequest, user: User = Depends(get_current_user)
):
    """Update an organization node. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        org = await organization_service.update_organization(
            org_uuid=org_uuid, name=body.name, metadata=body.metadata
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await audit_service.log_event(
        action="org.update",
        actor_user_id=user.user_id,
        resource_type="organization",
        resource_id=org.uuid,
        resource_name=org.name,
    )

    return _org_to_dict(org)


@router.delete("/{org_uuid}")
async def delete_organization(org_uuid: str, user: User = Depends(get_current_user)):
    """Delete an organization node. Admin only. Children are re-parented."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    org = await organization_service.get_organization(org_uuid)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    await organization_service.delete_organization(org_uuid)

    await audit_service.log_event(
        action="org.delete",
        actor_user_id=user.user_id,
        resource_type="organization",
        resource_id=org_uuid,
        resource_name=org.name,
    )

    return {"detail": "Organization deleted"}


@router.post("/{org_uuid}/assign-user/{target_user_id}")
async def assign_user_to_org(
    org_uuid: str, target_user_id: str, user: User = Depends(get_current_user)
):
    """Assign a user to an organization. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    org = await organization_service.get_organization(org_uuid)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    target_user = await User.find_one(User.user_id == target_user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.organization_id = org_uuid
    await target_user.save()

    return {"detail": f"User assigned to {org.name}"}


@router.post("/{org_uuid}/assign-team/{team_uuid}")
async def assign_team_to_org(
    org_uuid: str, team_uuid: str, user: User = Depends(get_current_user)
):
    """Assign a team to an organization. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.models.team import Team

    org = await organization_service.get_organization(org_uuid)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    team.organization_id = org_uuid
    await team.save()

    return {"detail": f"Team assigned to {org.name}"}
