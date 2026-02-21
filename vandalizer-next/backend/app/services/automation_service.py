"""Automation CRUD service."""

import datetime
from typing import Optional

from beanie import PydanticObjectId

from app.models.automation import Automation


async def create_automation(
    name: str,
    user_id: str,
    space: str | None = None,
    description: str | None = None,
    trigger_type: str | None = None,
    action_type: str | None = None,
    action_id: str | None = None,
) -> Automation:
    auto = Automation(
        name=name,
        user_id=user_id,
        space=space,
        description=description,
        trigger_type=trigger_type or "folder_watch",
        action_type=action_type or "workflow",
        action_id=action_id,
    )
    await auto.insert()
    return auto


async def list_automations(space: str | None = None) -> list[Automation]:
    query = {}
    if space:
        query["space"] = space
    return await Automation.find(query).to_list()


async def get_automation(automation_id: str) -> Automation | None:
    return await Automation.get(PydanticObjectId(automation_id))


async def update_automation(
    automation_id: str,
    name: str | None = None,
    description: str | None = None,
    enabled: bool | None = None,
    trigger_type: str | None = None,
    trigger_config: dict | None = None,
    action_type: str | None = None,
    action_id: str | None = None,
) -> Automation | None:
    auto = await Automation.get(PydanticObjectId(automation_id))
    if not auto:
        return None
    if name is not None:
        auto.name = name
    if description is not None:
        auto.description = description
    if enabled is not None:
        auto.enabled = enabled
    if trigger_type is not None:
        auto.trigger_type = trigger_type
    if trigger_config is not None:
        auto.trigger_config = trigger_config
    if action_type is not None:
        auto.action_type = action_type
    if action_id is not None:
        auto.action_id = action_id
    auto.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await auto.save()
    return auto


async def delete_automation(automation_id: str) -> bool:
    auto = await Automation.get(PydanticObjectId(automation_id))
    if not auto:
        return False
    await auto.delete()
    return True
