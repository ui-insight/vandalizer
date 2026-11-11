"""The Assistant page: what chat can use, and the switches for it."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import get_current_user
from app.models.system_config import SystemConfig
from app.models.user import User
from app.schemas.skills import SkillSnapshot
from app.services import assistant_capabilities, skill_service

router = APIRouter()


class CoreSkillRef(BaseModel):
    uuid: str = Field(min_length=1, max_length=200)


class AcceptedVersion(BaseModel):
    # The version the page showed, so a second edit made while the person was
    # reading is never accepted unseen.
    version: str = Field(min_length=1, max_length=128)


class Switch(BaseModel):
    on: bool


def _known(capability_id: str) -> str:
    if assistant_capabilities.clean_ids([capability_id]) != [capability_id]:
        raise HTTPException(status_code=422, detail="Unknown capability.")
    return capability_id


def _toggle(capability_id: str, on: bool) -> dict:
    # One capability per request, applied in the database: two tabs, or two
    # administrators, changing different switches never overwrite each other.
    return {"$pull" if on else "$addToSet": {"assistant_capabilities_off": capability_id}}


async def _page(user: User, config: SystemConfig) -> dict:
    page = assistant_capabilities.describe(user, config.model_dump())
    page["can_set_limits"] = bool(user.is_admin)
    return page


@router.get("/capabilities", response_model=None)
async def get_capabilities(user: User = Depends(get_current_user)) -> dict:
    return await _page(user, await SystemConfig.get_config())


@router.put("/capabilities/{capability_id}", response_model=None)
async def set_capability(capability_id: str, body: Switch, user: User = Depends(get_current_user)) -> dict:
    """A person's own switch. It applies from their next message."""
    await user.update(_toggle(_known(capability_id), body.on))
    return await _page(user, await SystemConfig.get_config())


@router.put("/capabilities/{capability_id}/limit", response_model=None)
async def set_capability_limit(capability_id: str, body: Switch, user: User = Depends(get_current_user)) -> dict:
    """An admin's limit for everyone on this deployment."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Only an administrator can change what chat may use for everyone.")
    capability_id = _known(capability_id)
    config = await SystemConfig.get_config()
    before = assistant_capabilities.clean_ids(config.assistant_capabilities_off)
    if (capability_id not in before) != body.on:
        import datetime

        from app.models.audit_log import AdminAuditLog

        await config.update({
            **_toggle(capability_id, body.on),
            "$set": {"updated_by": user.user_id, "updated_at": datetime.datetime.now(tz=datetime.timezone.utc)},
        })
        after = assistant_capabilities.clean_ids(config.assistant_capabilities_off)
        label = next(c.label for c in assistant_capabilities.CAPABILITIES if c.id == capability_id)
        await AdminAuditLog(
            user_id=user.user_id, action="update_assistant_capability_limits",
            detail=f"{label} turned {'on' if body.on else 'off'} in chat for everyone",
            payload={"capability": capability_id, "on": body.on, "before": before, "after": after},
        ).insert()
    return await _page(user, config)


# ── Core Skills ─────────────────────────────────────────────────────────────

async def _core_skill_page(user: User) -> dict:
    """The person's list, including entries chat is not using and why."""
    rows = []
    for state in await skill_service.core_skill_states(user):
        skill = state.skill
        rows.append({
            "uuid": state.uuid, "title": state.title, "status": state.status,
            "version": skill.version if skill else None,
            "usable": state.status == "ok", "problem": state.problem,
            "when_to_use": skill.when_to_use if skill else "",
            # Sent only for an edited Skill, so the person can read the new
            # text before accepting it.
            "instructions": skill.instructions if skill and state.status == "changed" else None,
        })
    return {"skills": rows, "max": skill_service.MAX_CORE_SKILLS}


async def _addable(skill_uuid: str, user: User) -> SkillSnapshot:
    skill = await skill_service.snapshot_skill(skill_uuid, user)
    if not skill.when_to_use:
        raise HTTPException(
            status_code=422,
            detail=f'Add a When to use line to "{skill.title}" in the Library first, so chat knows when to use it.',
        )
    return skill


@router.get("/core-skills", response_model=None)
async def get_core_skills(user: User = Depends(get_current_user)) -> dict:
    return await _core_skill_page(user)


@router.get("/core-skills/choices", response_model=None)
async def core_skill_choices(search: str = "", user: User = Depends(get_current_user)) -> dict:
    """Skills the person could add: the same Library search chat's list_skills uses."""
    from app.services.library_service import search_libraries

    team_id = str(user.current_team) if user.current_team else None
    listed = {entry["uuid"] for entry in skill_service.core_skill_entries(user)}
    choices: list[dict] = []
    seen: set[str] = set()
    for item in await search_libraries(user, search.strip()[:200], team_id=team_id, kind="search_set"):
        skill_uuid = item.get("item_uuid")
        if item.get("set_type") != "prompt" or not skill_uuid or skill_uuid in seen or skill_uuid in listed:
            continue
        seen.add(skill_uuid)
        choices.append({"uuid": skill_uuid, "title": item.get("name") or "Untitled Skill",
                        "when_to_use": item.get("when_to_use") or ""})
    choices.sort(key=lambda choice: str(choice["title"]).lower())
    return {"choices": choices[:50], "more": len(choices) > 50}


@router.post("/core-skills", response_model=None)
async def add_core_skill(body: CoreSkillRef, user: User = Depends(get_current_user)) -> dict:
    """Add a Skill and pin the text the person is accepting."""
    skill = await _addable(body.uuid, user)
    outcome = await skill_service.add_core_skill(user, skill)
    if outcome == "full":
        raise HTTPException(status_code=422, detail=f"You can keep up to {skill_service.MAX_CORE_SKILLS} core Skills. Remove one to add another.")
    await skill_service.reload_core_skills(user)
    return await _core_skill_page(user)


@router.post("/core-skills/{skill_uuid}/accept", response_model=None)
async def accept_core_skill(skill_uuid: str, body: AcceptedVersion, user: User = Depends(get_current_user)) -> dict:
    """Accept an edited Skill's current text, after the page showed it."""
    skill = await _addable(skill_uuid, user)
    if skill.version != body.version:
        raise HTTPException(status_code=409, detail="This Skill was edited again. Review the latest text before accepting it.")
    if not await skill_service.accept_core_skill(user, skill):
        raise HTTPException(status_code=404, detail="That Skill is not one of your core Skills.")
    await skill_service.reload_core_skills(user)
    return await _core_skill_page(user)


@router.delete("/core-skills/{skill_uuid}", response_model=None)
async def remove_core_skill(skill_uuid: str, user: User = Depends(get_current_user)) -> dict:
    await skill_service.remove_core_skill(user, skill_uuid)
    await skill_service.reload_core_skills(user)
    return await _core_skill_page(user)
