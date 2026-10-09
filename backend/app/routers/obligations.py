"""The RA inbox: deadlines, required material and sponsor limits per project (#999)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.obligation import Obligation
from app.models.user import User
from app.services import obligation_service, project_service

router = APIRouter()


async def _project_for(project_uuid: str, user: User, *, manage: bool):
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if manage and not await project_service.can_manage_project(project, user):
        raise HTTPException(status_code=403, detail="Only the project's owner and editors can change its inbox.")
    return project


async def _obligation_for(obligation_uuid: str, user: User, *, manage: bool):
    ob = await Obligation.find_one(Obligation.uuid == obligation_uuid)
    if not ob:
        raise HTTPException(status_code=404, detail="Item not found")
    project = await _project_for(ob.project_uuid, user, manage=manage)
    return ob, project


@router.get("")
async def list_obligations(
    project_uuid: Optional[str] = None,
    include_dismissed: bool = False,
    user: User = Depends(get_current_user),
):
    """Home: open items across your projects. With ``project_uuid``: that project's items."""
    if project_uuid:
        project = await _project_for(project_uuid, user, manage=False)
        return {"items": await obligation_service.project_obligations(project, user)}
    return {
        "items": await obligation_service.inbox(user, include_dismissed=include_dismissed),
        "inbox_hidden": bool(getattr(user, "home_inbox_hidden", False)),
    }


class CreateObligationsRequest(BaseModel):
    project_uuid: str
    items: list[dict]


@router.post("")
async def create_obligations(body: CreateObligationsRequest, user: User = Depends(get_current_user)):
    """Add items by hand. Each is checked against the document it cites; rejected ones say why."""
    project = await _project_for(body.project_uuid, user, manage=True)
    checked = await obligation_service.propose(project, user, body.items)
    created = [await obligation_service.save_checked(project, user, a["clean"]) for a in checked["accepted"]]
    return {
        "created": [obligation_service.serialize(o, user, project.title) for o in created],
        "rejected": checked["rejected"],
    }


class DoneRequest(BaseModel):
    done: bool


@router.post("/{obligation_uuid}/done")
async def mark_done(obligation_uuid: str, body: DoneRequest, user: User = Depends(get_current_user)):
    """Done (or reopened) for everyone on the project."""
    ob, project = await _obligation_for(obligation_uuid, user, manage=True)
    if ob.status == "superseded":
        raise HTTPException(status_code=409, detail="An amendment replaced this item; update the newer one instead.")
    ob = await obligation_service.set_done(ob, user, body.done)
    return obligation_service.serialize(ob, user, project.title)


class DismissRequest(BaseModel):
    dismissed: bool


@router.post("/{obligation_uuid}/dismiss")
async def dismiss(obligation_uuid: str, body: DismissRequest, user: User = Depends(get_current_user)):
    """Hide (or restore) an item on your own Home. Teammates still see it."""
    ob, project = await _obligation_for(obligation_uuid, user, manage=False)
    ob = await obligation_service.set_dismissed(ob, user, body.dismissed)
    return obligation_service.serialize(ob, user, project.title)


class InboxSettingsRequest(BaseModel):
    inbox_hidden: bool


@router.put("/home-settings")
async def update_home_settings(body: InboxSettingsRequest, user: User = Depends(get_current_user)):
    """Turn the whole RA inbox on Home off or back on, for this account."""
    user.home_inbox_hidden = body.inbox_hidden
    await user.save()
    return {"inbox_hidden": user.home_inbox_hidden}
