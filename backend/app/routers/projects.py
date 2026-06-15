from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.project import PROJECT_STATES
from app.models.user import User
from app.services import project_service

router = APIRouter()


class CreateProjectRequest(BaseModel):
    title: str
    description: str | None = None


class UpdateProjectRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    state: str | None = None


@router.post("")
async def create_project(
    body: CreateProjectRequest,
    user: User = Depends(get_current_user),
):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Project title is required")
    project = await project_service.create_project(title, body.description, user)
    return project_service.serialize_project(project)


@router.get("")
async def list_projects(user: User = Depends(get_current_user)):
    projects = await project_service.list_projects(user)
    return [await project_service.summarize_project(p, user) for p in projects]


@router.get("/{project_uuid}")
async def get_project(
    project_uuid: str,
    user: User = Depends(get_current_user),
):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return await project_service.get_project_overview(project, user)


class PinRequest(BaseModel):
    pin_type: str
    target_id: str


@router.get("/{project_uuid}/pins")
async def list_pins(project_uuid: str, user: User = Depends(get_current_user)):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return await project_service.list_pins(project)


@router.post("/{project_uuid}/pins")
async def add_pin(
    project_uuid: str,
    body: PinRequest,
    user: User = Depends(get_current_user),
):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        await project_service.add_pin(project, body.pin_type, body.target_id, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.delete("/{project_uuid}/pins")
async def remove_pin(
    project_uuid: str,
    pin_type: str,
    target_id: str,
    user: User = Depends(get_current_user),
):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        await project_service.remove_pin(project, pin_type, target_id, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.get("/{project_uuid}/documents")
async def get_project_documents(
    project_uuid: str,
    user: User = Depends(get_current_user),
):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"document_uuids": await project_service.get_project_document_uuids(project)}


@router.patch("/{project_uuid}")
async def update_project(
    project_uuid: str,
    body: UpdateProjectRequest,
    user: User = Depends(get_current_user),
):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await project_service.can_manage_project(project, user):
        raise HTTPException(
            status_code=403, detail="Only the project owner or an editor can edit it"
        )
    if body.state is not None and body.state not in PROJECT_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid state. Must be one of: {', '.join(PROJECT_STATES)}",
        )
    project = await project_service.update_project(
        project,
        title=body.title.strip() if body.title is not None else None,
        description=body.description,
        state=body.state,
    )
    return project_service.serialize_project(project)


@router.post("/{project_uuid}/share-with-team")
async def share_with_team(
    project_uuid: str,
    user: User = Depends(get_current_user),
):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        project = await project_service.share_project_with_team(project, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return project_service.serialize_project(project)


@router.delete("/{project_uuid}")
async def delete_project(
    project_uuid: str,
    user: User = Depends(get_current_user),
):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_user_id != user.user_id and not user.is_admin:
        raise HTTPException(
            status_code=403, detail="Only the project owner can delete it"
        )
    await project_service.delete_project(project)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Sharing — invite links + members
# ---------------------------------------------------------------------------


class CreateInviteRequest(BaseModel):
    role: str = "viewer"
    expires_in_hours: int | None = None
    max_uses: int | None = None


@router.post("/{project_uuid}/invite-link")
async def create_invite_link(
    project_uuid: str,
    body: CreateInviteRequest,
    user: User = Depends(get_current_user),
):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        link = await project_service.create_project_invite_link(
            project,
            user,
            role=body.role,
            expires_in_hours=body.expires_in_hours
            or project_service.PROJECT_INVITE_DEFAULT_EXPIRY_HOURS,
            max_uses=body.max_uses,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return project_service.serialize_invite_link(link)


@router.get("/{project_uuid}/invite-links")
async def list_invite_links(
    project_uuid: str,
    user: User = Depends(get_current_user),
):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project or not await project_service.can_manage_project(project, user):
        raise HTTPException(status_code=404, detail="Project not found")
    return await project_service.list_project_invite_links(project)


@router.delete("/invite-link/{token}")
async def revoke_invite_link(token: str, user: User = Depends(get_current_user)):
    try:
        await project_service.revoke_project_invite(token, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.get("/join/info/{token}")
async def join_link_info(token: str):
    """Public — preview a project invite before logging in."""
    info = await project_service.get_project_invite_info(token)
    if not info:
        raise HTTPException(status_code=404, detail="Invalid invite link")
    return info


@router.post("/join/accept/{token}")
async def accept_invite_link(token: str, user: User = Depends(get_current_user)):
    try:
        project = await project_service.accept_project_invite(token, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return project_service.serialize_project(project)


@router.get("/{project_uuid}/members")
async def list_members(
    project_uuid: str,
    user: User = Depends(get_current_user),
):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return await project_service.list_project_members(project)


@router.delete("/{project_uuid}/members/{member_user_id}")
async def remove_member(
    project_uuid: str,
    member_user_id: str,
    user: User = Depends(get_current_user),
):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        await project_service.remove_project_member(project, member_user_id, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}
