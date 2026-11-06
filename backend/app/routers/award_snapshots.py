"""A project's award snapshot (app.services.award_snapshot)."""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import get_current_user
from app.models.project import Project
from app.models.user import User
from app.rate_limit import limiter
from app.services import award_snapshot, project_service

router = APIRouter()


async def _project(project_uuid: str, user: User, *, manage: bool = False) -> Project:
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if manage and not await project_service.can_manage_project(project, user):
        raise HTTPException(status_code=403, detail="Only the project's owner and editors can build or share its snapshot.")
    return project


@router.get("/{project_uuid}/award-snapshot", response_model=None)
async def get_award_snapshot(project_uuid: str, user: User = Depends(get_current_user)) -> dict:
    """Where the award stands: facts with sources, budget, live deadlines, status, activity."""
    return await award_snapshot.view(await _project(project_uuid, user), user)


@router.post("/{project_uuid}/award-snapshot/build", response_model=None)
@limiter.limit("6/minute")
async def build_award_snapshot(request: Request, project_uuid: str, user: User = Depends(get_current_user)) -> dict:
    """Read the facts from the project's documents again (Build snapshot / Refresh)."""
    project = await _project(project_uuid, user, manage=True)
    await award_snapshot.request_build(project, user)
    return await award_snapshot.view(project, user)


@router.post("/{project_uuid}/award-snapshot/page", response_model=None)
@limiter.limit("10/minute")
async def share_award_snapshot(request: Request, project_uuid: str, user: User = Depends(get_current_user)) -> dict:
    """Save the snapshot as a private project Page (or a new revision of the earlier one)."""
    project = await _project(project_uuid, user, manage=True)
    return await award_snapshot.share_as_page(project, user)
