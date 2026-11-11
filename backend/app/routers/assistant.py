"""The Assistant page: what chat can use, and the switches for it."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import get_current_user
from app.models.system_config import SystemConfig
from app.models.user import User
from app.services import assistant_capabilities

router = APIRouter()


class CapabilitySwitches(BaseModel):
    # Ids to switch off; anything not listed is on.
    off: list[str] = Field(max_length=50)


def _checked(ids: list[str]) -> list[str]:
    cleaned = assistant_capabilities.clean_ids(ids)
    if len(cleaned) != len(set(ids)):
        raise HTTPException(status_code=422, detail="Unknown capability.")
    return cleaned


async def _page(user: User, config: SystemConfig) -> dict:
    page = assistant_capabilities.describe(user, config.model_dump())
    page["can_set_limits"] = bool(user.is_admin)
    return page


@router.get("/capabilities", response_model=None)
async def get_capabilities(user: User = Depends(get_current_user)) -> dict:
    return await _page(user, await SystemConfig.get_config())


@router.put("/capabilities", response_model=None)
async def set_capabilities(body: CapabilitySwitches, user: User = Depends(get_current_user)) -> dict:
    """A person's own switches. They apply from their next message."""
    user.assistant_capabilities_off = _checked(body.off)
    await user.set({"assistant_capabilities_off": user.assistant_capabilities_off})
    return await _page(user, await SystemConfig.get_config())


@router.put("/capabilities/limits", response_model=None)
async def set_capability_limits(body: CapabilitySwitches, user: User = Depends(get_current_user)) -> dict:
    """An admin's limit for everyone on this deployment."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Only an administrator can change what chat may use for everyone.")
    config = await SystemConfig.get_config()
    off = _checked(body.off)
    before = assistant_capabilities.clean_ids(config.assistant_capabilities_off)
    if off != before:
        await config.set({"assistant_capabilities_off": off, "updated_by": user.user_id})
        config.assistant_capabilities_off = off
        from app.models.audit_log import AdminAuditLog

        labels = [c.label for c in assistant_capabilities.CAPABILITIES if c.id in off]
        await AdminAuditLog(
            user_id=user.user_id, action="update_assistant_capability_limits",
            detail="Chat capabilities switched off for everyone: " + (", ".join(labels) or "(none)"),
            payload={"before": before, "after": off},
        ).insert()
    return await _page(user, config)
