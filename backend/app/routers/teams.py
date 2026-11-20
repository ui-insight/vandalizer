from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.schemas.teams import (
    ChangeRoleRequest,
    CreateJoinLinkRequest,
    CreateTeamRequest,
    InviteRequest,
    RemoveMemberRequest,
    TransferOwnershipRequest,
    UpdateTeamNameRequest,
)
from app.services import team_service

router = APIRouter()


@router.get("/", response_model=None)
async def list_teams(user: User = Depends(get_current_user)) -> list[dict]:
    """List all teams the user belongs to."""
    return await team_service.get_user_teams(user.user_id)


@router.get("/{team_uuid}/members", response_model=None)
async def list_members(team_uuid: str, user: User = Depends(get_current_user)) -> list[dict]:
    """List members of a team."""
    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    membership = await TeamMembership.find_one(
        TeamMembership.team == team.id,
        TeamMembership.user_id == user.user_id,
    )
    if not membership and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not a member of this team")
    return await team_service.get_team_members(team_service.persisted_team_id(team))


@router.get("/{team_uuid}/invites", response_model=None)
async def list_invites(team_uuid: str, user: User = Depends(get_current_user)) -> list[dict]:
    """List pending invites for a team."""
    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    membership = await TeamMembership.find_one(
        TeamMembership.team == team.id,
        TeamMembership.user_id == user.user_id,
    )
    if not membership and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not a member of this team")
    if membership and membership.role not in ("owner", "admin") and not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin or owner role required")
    return await team_service.get_team_invites(team_service.persisted_team_id(team))


@router.post("/create", response_model=None)
async def create_team(
    body: CreateTeamRequest,
    user: User = Depends(get_current_user),
) -> dict:
    team = await team_service.create_team(body.name, user.user_id)
    return {"id": str(team.id), "uuid": team.uuid, "name": team.name}


@router.patch("/update_name", response_model=None)
async def update_name(
    body: UpdateTeamNameRequest,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        team = await team_service.update_team_name(
            body.team_id, body.name, user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "name": team.name}


@router.post("/invite", response_model=None)
async def invite(
    body: InviteRequest,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        inv = await team_service.invite_member(
            body.team_id, body.email, body.role, user.user_id,
            settings=settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"token": inv.token, "email": inv.email}


@router.get("/invite/info/{token}", response_model=None)
async def invite_info(token: str) -> dict:
    """Public — return team + inviter metadata for a pending invite token."""
    info = await team_service.get_invite_info(token)
    if not info:
        raise HTTPException(status_code=404, detail="Invalid or already-used invite")
    return info


@router.post("/invite/accept/{token}", response_model=None)
async def accept_invite(
    token: str,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        team = await team_service.accept_invite(token, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"uuid": team.uuid, "name": team.name}


@router.post("/{team_uuid}/join-link", response_model=None)
async def create_join_link(
    team_uuid: str,
    body: CreateJoinLinkRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """Create a new public join link for the team. Admin/owner only."""
    try:
        link = await team_service.create_join_link(
            team_uuid,
            user.user_id,
            role=body.role,
            expires_in_hours=body.expires_in_hours,
            max_uses=body.max_uses,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return team_service._serialize_join_link(link)


@router.get("/{team_uuid}/join-links", response_model=None)
async def list_join_links(
    team_uuid: str,
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List active (non-revoked) join links for a team. Admin/owner only."""
    try:
        return await team_service.get_team_join_links(team_uuid, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/join-link/{token}", response_model=None)
async def revoke_join_link(
    token: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Revoke a join link. Admin/owner of the team only."""
    try:
        await team_service.revoke_join_link(token, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.get("/join-link/info/{token}", response_model=None)
async def join_link_info(token: str) -> dict:
    """Public — return team metadata for a join-link token."""
    info = await team_service.get_join_link_info(token)
    if not info:
        raise HTTPException(status_code=404, detail="Invalid join link")
    return info


@router.post("/join-link/accept/{token}", response_model=None)
async def accept_join_link(
    token: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Accept a join link — adds the current user to the team."""
    try:
        team = await team_service.accept_join_link(token, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"uuid": team.uuid, "name": team.name}


@router.post("/switch/{team_uuid}", response_model=None)
async def switch_team(
    team_uuid: str,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        team = await team_service.switch_team(team_uuid, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"uuid": team.uuid, "name": team.name}


@router.post("/member/role", response_model=None)
async def change_role(
    body: ChangeRoleRequest,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        await team_service.change_role(
            body.team_id, body.user_id, body.role, user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/member/remove", response_model=None)
async def remove_member(
    body: RemoveMemberRequest,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        await team_service.remove_member(
            body.team_id, body.user_id, user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/transfer-ownership", response_model=None)
async def transfer_ownership(
    body: TransferOwnershipRequest,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        team = await team_service.transfer_ownership(
            body.team_uuid, user.user_id, body.new_owner_user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"uuid": team.uuid, "name": team.name, "owner_user_id": team.owner_user_id}


@router.delete("/{team_uuid}", response_model=None)
async def delete_team(
    team_uuid: str,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        await team_service.delete_team(team_uuid, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}
