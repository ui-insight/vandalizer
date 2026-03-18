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


class MoveOrgRequest(BaseModel):
    new_parent_id: Optional[str] = None


class UpdateOrgTypeRequest(BaseModel):
    org_type: str


class ImportOrgNode(BaseModel):
    name: str
    parent_name: Optional[str] = None
    org_type: str = "department"


class ImportOrgRequest(BaseModel):
    nodes: list[ImportOrgNode]


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


# ---------------------------------------------------------------------------
# User-facing: my org info
# ---------------------------------------------------------------------------


@router.get("/me")
async def get_my_org(user: User = Depends(get_current_user)):
    """Get the current user's organization info and ancestry."""
    if not user.organization_id:
        return {"organization": None, "ancestry": []}

    org = await organization_service.get_organization(user.organization_id)
    if not org:
        return {"organization": None, "ancestry": []}

    # Build ancestry chain (closest first)
    ancestor_ids = await organization_service.get_ancestor_ids(org.uuid)
    ancestry = []
    for aid in ancestor_ids:
        ancestor = await organization_service.get_organization(aid)
        if ancestor:
            ancestry.append(_org_to_dict(ancestor))

    return {
        "organization": _org_to_dict(org),
        "ancestry": ancestry,
    }


# ---------------------------------------------------------------------------
# Admin: tree and CRUD
# ---------------------------------------------------------------------------


@router.get("/tree")
async def get_org_tree(user: User = Depends(get_current_user)):
    """Get the full organization tree with user/team counts."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    tree = await organization_service.get_org_tree()
    return {"tree": tree}


@router.get("/flat")
async def list_organizations_flat(user: User = Depends(get_current_user)):
    """List all organizations as a flat list (for org pickers)."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    orgs = await Organization.find_all().sort(+Organization.name).to_list()
    return {"organizations": [_org_to_dict(o) for o in orgs]}


@router.get("/")
async def list_organizations(
    org_type: Optional[str] = None,
    parent_id: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """List organizations, optionally filtered by type or parent."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    filters = {}
    if org_type:
        filters["org_type"] = org_type
    if parent_id:
        filters["parent_id"] = parent_id

    orgs = await Organization.find(filters).to_list()
    return {"organizations": [_org_to_dict(o) for o in orgs]}


@router.post("/import")
async def import_organizations(body: ImportOrgRequest, user: User = Depends(get_current_user)):
    """Bulk import organization nodes from a list. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        created = await organization_service.bulk_import_organizations(
            [n.model_dump() for n in body.nodes]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await audit_service.log_event(
        action="org.import",
        actor_user_id=user.user_id,
        resource_type="organization",
        detail={"count": len(created)},
    )

    return {"created": [_org_to_dict(o) for o in created], "count": len(created)}


@router.get("/{org_uuid}")
async def get_organization(org_uuid: str, user: User = Depends(get_current_user)):
    org = await organization_service.get_organization(org_uuid)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not user.is_admin:
        # Allow if this is the user's own org or an ancestor
        if user.organization_id:
            ancestors = await organization_service.get_ancestor_ids(user.organization_id)
            if org_uuid != user.organization_id and org_uuid not in ancestors:
                raise HTTPException(status_code=403, detail="Access denied")
        else:
            raise HTTPException(status_code=403, detail="Access denied")
    return _org_to_dict(org)


@router.get("/{org_uuid}/members")
async def get_org_members(org_uuid: str, user: User = Depends(get_current_user)):
    """Get users and teams assigned to a specific org node."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    org = await organization_service.get_organization(org_uuid)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return await organization_service.get_org_members(org_uuid)


@router.patch("/{org_uuid}/move")
async def move_organization(
    org_uuid: str, body: MoveOrgRequest, user: User = Depends(get_current_user)
):
    """Move an org node to a new parent. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        org = await organization_service.move_organization(org_uuid, body.new_parent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await audit_service.log_event(
        action="org.move",
        actor_user_id=user.user_id,
        resource_type="organization",
        resource_id=org.uuid,
        resource_name=org.name,
        detail={"new_parent_id": body.new_parent_id},
    )
    return _org_to_dict(org)


@router.patch("/{org_uuid}/type")
async def update_org_type(
    org_uuid: str, body: UpdateOrgTypeRequest, user: User = Depends(get_current_user)
):
    """Change the type of an org node. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        org = await organization_service.update_org_type(org_uuid, body.org_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await audit_service.log_event(
        action="org.update_type",
        actor_user_id=user.user_id,
        resource_type="organization",
        resource_id=org.uuid,
        detail={"new_type": body.org_type},
    )
    return _org_to_dict(org)


@router.post("/{org_uuid}/unassign-user/{target_user_id}")
async def unassign_user_from_org(
    org_uuid: str, target_user_id: str, user: User = Depends(get_current_user)
):
    """Remove a user's organization assignment. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    target_user = await User.find_one(User.user_id == target_user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    target_user.organization_id = None
    await target_user.save()
    return {"detail": "User unassigned from organization"}


@router.post("/{org_uuid}/unassign-team/{team_uuid}")
async def unassign_team_from_org(
    org_uuid: str, team_uuid: str, user: User = Depends(get_current_user)
):
    """Remove a team's organization assignment. Admin only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    from app.models.team import Team
    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team.organization_id = None
    await team.save()
    return {"detail": "Team unassigned from organization"}


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
