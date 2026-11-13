"""The RA inbox: deadlines, required material and sponsor limits per project (#999)."""
from app.models.project import Project

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.obligation import Obligation
from app.models.user import User
from app.services import obligation_service, project_service

router = APIRouter()


async def _project_for(project_uuid: str, user: User, *, manage: bool) -> Project:
    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if manage and not await project_service.can_manage_project(project, user):
        raise HTTPException(status_code=403, detail="Only the project's owner and editors can change its inbox.")
    return project


async def _obligation_for(obligation_uuid: str, user: User, *, manage: bool) -> tuple[Obligation, Project]:
    ob = await Obligation.find_one(Obligation.uuid == obligation_uuid)
    if not ob:
        raise HTTPException(status_code=404, detail="Item not found")
    project = await _project_for(ob.project_uuid, user, manage=manage)
    return ob, project


@router.get("", response_model=None)
async def list_obligations(
    project_uuid: Optional[str] = None,
    include_dismissed: bool = False,
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Home: open items across your projects. With ``project_uuid``: that project's.

    Support ticket: inside a project, "Due and needed" listed deadlines from
    other projects, because the panel always asked for the Home list. Both
    answers have the same shape, so the panel shows either.
    """
    if project_uuid:
        project = await _project_for(project_uuid, user, manage=False)
        return {
            "items": await obligation_service.inbox(
                user, include_dismissed=include_dismissed, projects={project.uuid: project},
            ),
            # Hiding is a Home preference; a project always shows its own list.
            "inbox_hidden": False,
            "project_count": 1,
        }
    projects = await obligation_service.inbox_projects(user)
    return {
        "items": await obligation_service.inbox(
            user, include_dismissed=include_dismissed, projects=projects,
        ),
        "inbox_hidden": bool(getattr(user, "home_inbox_hidden", False)),
        # How many projects the list covers, so an empty inbox can say what
        # it checked instead of vanishing (#1014 item 34).
        "project_count": len(projects),
    }


@router.get("/reminder-settings", response_model=None)
async def get_reminder_settings(user: User = Depends(get_current_user)) -> dict[str, object]:
    """Your deadline reminder settings, and whether the team-projects option applies to you."""
    from app.services.deadline_reminders import normalize_settings

    return {
        "settings": normalize_settings(user.deadline_reminders),
        "team_admin": await _is_team_admin(user),
    }


@router.put("/reminder-settings", response_model=None)
async def update_reminder_settings(body: dict, user: User = Depends(get_current_user)) -> dict[str, object]:
    """Turn bell and email reminders on or off and change their timing."""
    from app.services.deadline_reminders import apply_update

    try:
        user.deadline_reminders = apply_update(user.deadline_reminders, body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await user.save()
    return {"settings": user.deadline_reminders, "team_admin": await _is_team_admin(user)}


async def _is_team_admin(user: User) -> bool:
    from app.models.team import TeamMembership

    return await TeamMembership.find(
        {"user_id": user.user_id, "role": {"$in": ["owner", "admin"]}},
    ).count() > 0


def _calendar_response(items: list[tuple[Obligation, str]], user: User, filename: str, name: str) -> Response:
    from app.config import Settings
    from app.services.deadline_reminders import calendar_file, normalize_settings

    prefs = normalize_settings(user.deadline_reminders)
    body = calendar_file(
        items, frontend_url=Settings().frontend_url.rstrip("/"),
        alarm_days=prefs["days_before"], name=name,
    )
    return Response(
        content=body, media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60] or "deadlines"


@router.get("/calendar.ics", response_model=None)
async def download_calendar(
    project_uuid: Optional[str] = None, user: User = Depends(get_current_user),
) -> Response:
    """A calendar file of open deadlines: one project's, or all of yours."""
    if project_uuid:
        project = await _project_for(project_uuid, user, manage=False)
        projects = {project.uuid: project}
        filename, name = f"{_slug(project.title)}-deadlines.ics", f"{project.title} deadlines"
    else:
        projects = await obligation_service.inbox_projects(user)
        filename, name = "project-deadlines.ics", "Project deadlines"
    obligations = await Obligation.find(
        {"project_uuid": {"$in": list(projects)}, "kind": "deadline", "status": "open", "due_at": {"$ne": None}},
    ).to_list()
    if not project_uuid:
        obligations = [o for o in obligations if user.user_id not in (o.dismissed_by or [])]
    obligations.sort(key=lambda o: o.due_at or o.created_at)
    return _calendar_response(
        [(o, projects[o.project_uuid].title) for o in obligations], user, filename, name,
    )


@router.get("/{obligation_uuid}", response_model=None)
async def get_obligation(obligation_uuid: str, user: User = Depends(get_current_user)) -> dict:
    """One item, for a reminder's link to it."""
    ob, project = await _obligation_for(obligation_uuid, user, manage=False)
    return await obligation_service.serialize_checked(ob, user, project.title)


@router.get("/{obligation_uuid}/calendar.ics", response_model=None)
async def download_obligation_calendar(obligation_uuid: str, user: User = Depends(get_current_user)) -> Response:
    """One deadline as a calendar file."""
    ob, project = await _obligation_for(obligation_uuid, user, manage=False)
    if ob.kind != "deadline" or ob.due_at is None:
        raise HTTPException(status_code=400, detail="Only a deadline with a date can be added to a calendar.")
    return _calendar_response([(ob, project.title)], user, f"{_slug(ob.title)}.ics", ob.title)


class CreateObligationsRequest(BaseModel):
    project_uuid: str
    items: list[dict]


@router.post("", response_model=None)
async def create_obligations(body: CreateObligationsRequest, user: User = Depends(get_current_user)) -> dict[str, object]:
    """Add items by hand. Each is checked against the document it cites; rejected ones say why."""
    project = await _project_for(body.project_uuid, user, manage=True)
    checked = await obligation_service.propose(project, user, body.items)
    # This manual endpoint has no calculation-preview approval handshake.
    # Relative schedules go through the chat tool's server-enforced gate.
    manual = []
    for accepted in checked["accepted"]:
        if accepted["clean"].get("deadline_calculation"):
            checked["rejected"].append({"title": accepted["clean"]["title"],
                                        "reason": "Review and approve calculated deadlines in project chat before adding them."})
        else:
            manual.append(accepted)
    created = [await obligation_service.save_checked(project, user, a["clean"]) for a in manual]
    return {
        "created": [obligation_service.serialize(o, user, project.title) for o in created],
        "rejected": checked["rejected"],
    }


class AddByHandRequest(BaseModel):
    project_uuid: str
    title: str
    due_date: str
    source_note: Optional[str] = None


@router.post("/by-hand", response_model=None)
async def add_by_hand(body: AddByHandRequest, user: User = Depends(get_current_user)) -> dict:
    """Add a deadline typed into the project's inbox, saved as not checked against a document."""
    project = await _project_for(body.project_uuid, user, manage=True)
    ob, reason = await obligation_service.add_by_hand(
        project, user, title=body.title, due_date=body.due_date, source_note=body.source_note,
    )
    if ob is None:
        raise HTTPException(status_code=422, detail=reason)
    return obligation_service.serialize(ob, user, project.title)


class DoneRequest(BaseModel):
    done: bool


@router.post("/{obligation_uuid}/done", response_model=None)
async def mark_done(obligation_uuid: str, body: DoneRequest, user: User = Depends(get_current_user)) -> dict:
    """Done (or reopened) for everyone on the project."""
    ob, project = await _obligation_for(obligation_uuid, user, manage=True)
    if ob.status == "superseded":
        raise HTTPException(status_code=409, detail="An amendment replaced this item; update the newer one instead.")
    ob = await obligation_service.set_done(ob, user, body.done)
    return await obligation_service.serialize_checked(ob, user, project.title)


class KeepRequest(BaseModel):
    keep: bool


@router.post("/{obligation_uuid}/keep", response_model=None)
async def keep_without_source(obligation_uuid: str, body: KeepRequest, user: User = Depends(get_current_user)) -> dict:
    """Keep an item whose source file was deleted, for everyone on the project."""
    ob, project = await _obligation_for(obligation_uuid, user, manage=True)
    ob = await obligation_service.set_kept_without_source(ob, body.keep)
    return await obligation_service.serialize_checked(ob, user, project.title)


class DismissRequest(BaseModel):
    dismissed: bool


@router.post("/{obligation_uuid}/dismiss", response_model=None)
async def dismiss(obligation_uuid: str, body: DismissRequest, user: User = Depends(get_current_user)) -> dict:
    """Hide (or restore) an item on your own Home. Teammates still see it."""
    ob, project = await _obligation_for(obligation_uuid, user, manage=False)
    ob = await obligation_service.set_dismissed(ob, user, body.dismissed)
    return await obligation_service.serialize_checked(ob, user, project.title)


class InboxSettingsRequest(BaseModel):
    inbox_hidden: bool


@router.put("/home-settings", response_model=None)
async def update_home_settings(body: InboxSettingsRequest, user: User = Depends(get_current_user)) -> dict[str, object]:
    """Turn the whole RA inbox on Home off or back on, for this account."""
    user.home_inbox_hidden = body.inbox_hidden
    await user.save()
    return {"inbox_hidden": user.home_inbox_hidden}
