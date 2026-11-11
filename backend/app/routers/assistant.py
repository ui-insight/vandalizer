"""The Assistant page: what chat can use, and the switches for it."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import get_current_user
from app.models.system_config import SystemConfig
from app.models.user import User
from app.services import assistant_capabilities, skill_service

router = APIRouter()


class CoreSkills(BaseModel):
    uuids: list[str] = Field(max_length=20)


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
