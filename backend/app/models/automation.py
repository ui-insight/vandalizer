"""Automation model for trigger-based workflow execution."""

import datetime
from typing import Optional

from beanie import Document


class Automation(Document):
    """An automation that links a trigger to an action."""

    name: str
    description: Optional[str] = None
    enabled: bool = False
    trigger_type: str = "folder_watch"  # folder_watch | m365_intake | api | schedule
    trigger_config: dict = {}
    action_type: str = "workflow"  # workflow | extraction | task
    action_id: Optional[str] = None
    user_id: str
    team_id: Optional[str] = None
    shared_with_team: bool = False
    space: Optional[str] = None
    created_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)
    updated_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)

    class Settings:
        name = "automation"
