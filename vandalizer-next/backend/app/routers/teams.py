from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.teams import (
    ChangeRoleRequest,
    CreateTeamRequest,
    InviteRequest,
    RemoveMemberRequest,
    UpdateTeamNameRequest,
)
from app.services import team_service

router = APIRouter()


@router.get("/")
async def list_teams(user: User = Depends(get_current_user)):
    """List all teams the user belongs to."""
    return await team_service.get_user_teams(user.user_id)


@router.get("/{team_uuid}/members")
async def list_members(team_uuid: str, user: User = Depends(get_current_user)):
    """List members of a team."""
    from app.models.team import Team

    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return await team_service.get_team_members(team.id)


@router.get("/{team_uuid}/invites")
async def list_invites(team_uuid: str, user: User = Depends(get_current_user)):
    """List pending invites for a team."""
    from app.models.team import Team

    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return await team_service.get_team_invites(team.id)


@router.post("/create")
async def create_team(
    body: CreateTeamRequest,
    user: User = Depends(get_current_user),
):
    team = await team_service.create_team(body.name, user.user_id)
    return {"id": str(team.id), "uuid": team.uuid, "name": team.name}


@router.patch("/update_name")
async def update_name(
    body: UpdateTeamNameRequest,
    user: User = Depends(get_current_user),
):
    try:
        team = await team_service.update_team_name(
            body.team_id, body.name, user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "name": team.name}


@router.post("/invite")
async def invite(
    body: InviteRequest,
    user: User = Depends(get_current_user),
):
    try:
        inv = await team_service.invite_member(
            body.team_id, body.email, body.role, user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"token": inv.token, "email": inv.email}


@router.post("/invite/accept/{token}")
async def accept_invite(
    token: str,
    user: User = Depends(get_current_user),
):
    try:
        team = await team_service.accept_invite(token, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"uuid": team.uuid, "name": team.name}


@router.post("/switch/{team_uuid}")
async def switch_team(
    team_uuid: str,
    user: User = Depends(get_current_user),
):
    try:
        team = await team_service.switch_team(team_uuid, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"uuid": team.uuid, "name": team.name}


@router.post("/member/role")
async def change_role(
    body: ChangeRoleRequest,
    user: User = Depends(get_current_user),
):
    try:
        await team_service.change_role(
            body.team_id, body.user_id, body.role, user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/member/remove")
async def remove_member(
    body: RemoveMemberRequest,
    user: User = Depends(get_current_user),
):
    try:
        await team_service.remove_member(
            body.team_id, body.user_id, user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}
