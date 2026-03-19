"""Automation CRUD service."""

import datetime
from typing import Optional

from beanie import PydanticObjectId

from app.models.automation import Automation
from app.models.user import User
from app.services.access_control import get_authorized_automation


async def create_automation(
    name: str,
    user_id: str,
    space: str | None = None,
    description: str | None = None,
    trigger_type: str | None = None,
    trigger_config: dict | None = None,
    action_type: str | None = None,
    action_id: str | None = None,
    team_id: str | None = None,
    shared_with_team: bool = False,
    output_config: dict | None = None,
) -> Automation:
    auto = Automation(
        name=name,
        user_id=user_id,
        space=space,
        description=description,
        trigger_type=trigger_type or "folder_watch",
        trigger_config=trigger_config or {},
        action_type=action_type or "workflow",
        action_id=action_id,
        team_id=team_id,
        shared_with_team=shared_with_team,
        output_config=output_config or {},
    )
    await auto.insert()
    return auto


async def list_automations(
    user_id: str,
    team_id: str | None = None,
    space: str | None = None,
) -> list[Automation]:
    # Return user's own automations OR team-shared ones
    user_query: dict = {"user_id": user_id}
    if space:
        user_query["space"] = space

    if team_id:
        team_query: dict = {"shared_with_team": True, "team_id": team_id}
        if space:
            team_query["space"] = space
        return await Automation.find({"$or": [user_query, team_query]}).to_list()

    return await Automation.find(user_query).to_list()


async def get_automation(
    automation_id: str,
    user: User | None = None,
    *,
    manage: bool = False,
) -> Automation | None:
    if user is not None:
        return await get_authorized_automation(automation_id, user, manage=manage)
    return await Automation.get(PydanticObjectId(automation_id))


async def update_automation(
    automation_id: str,
    user: User,
    name: str | None = None,
    description: str | None = None,
    enabled: bool | None = None,
    trigger_type: str | None = None,
    trigger_config: dict | None = None,
    action_type: str | None = None,
    action_id: str | None = None,
    shared_with_team: bool | None = None,
    output_config: dict | None = None,
) -> Automation | None:
    auto = await get_authorized_automation(automation_id, user, manage=True)
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
    if shared_with_team is not None:
        auto.shared_with_team = shared_with_team
    if output_config is not None:
        auto.output_config = output_config
    auto.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await auto.save()
    return auto


async def delete_automation(automation_id: str, user: User) -> bool:
    auto = await get_authorized_automation(automation_id, user, manage=True)
    if not auto:
        return False
    await auto.delete()
    return True
