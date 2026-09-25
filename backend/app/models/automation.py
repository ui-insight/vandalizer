"""Automation model for trigger-based workflow execution."""

import datetime
from typing import Optional

from beanie import Document
from pydantic import Field


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
    output_config: dict = {}
    # Schedule triggers: when the schedule last fired, and when it was last
    # enabled or changed — see automation_schedule.last_run_base.
    last_scheduled_run_at: Optional[datetime.datetime] = None
    schedule_armed_at: Optional[datetime.datetime] = None
    # "Only new documents": documents from here on are new; carryover names
    # ones still processing at the last run, which run next time instead.
    schedule_docs_watermark: Optional[datetime.datetime] = None
    schedule_carryover_uuids: list[str] = []
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = "automation"
