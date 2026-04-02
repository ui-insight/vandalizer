"""Request/response models for automation endpoints."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, model_validator

TRIGGER_TYPES = ("folder_watch", "m365_intake", "api", "schedule")
ACTION_TYPES = ("workflow", "extraction", "task")

TriggerType = Literal["folder_watch", "m365_intake", "api", "schedule"]
ActionType = Literal["workflow", "extraction", "task"]


class CreateAutomationRequest(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[dict] = None
    action_type: Optional[ActionType] = None
    action_id: Optional[str] = None
    shared_with_team: bool = False
    output_config: Optional[dict] = None

    @model_validator(mode="after")
    def validate_trigger_config(self) -> "CreateAutomationRequest":
        if self.trigger_type == "schedule":
            cfg = self.trigger_config or {}
            if not cfg.get("cron_expression"):
                raise ValueError("Schedule trigger requires 'cron_expression' in trigger_config")
        if self.trigger_type == "folder_watch":
            cfg = self.trigger_config or {}
            if not cfg.get("folder_id"):
                raise ValueError("Folder watch trigger requires 'folder_id' in trigger_config")
        return self


class UpdateAutomationRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[dict] = None
    action_type: Optional[ActionType] = None
    action_id: Optional[str] = None
    shared_with_team: Optional[bool] = None
    output_config: Optional[dict] = None

    @model_validator(mode="after")
    def validate_trigger_config(self) -> "UpdateAutomationRequest":
        if self.trigger_type == "schedule":
            cfg = self.trigger_config or {}
            if not cfg.get("cron_expression"):
                raise ValueError("Schedule trigger requires 'cron_expression' in trigger_config")
        if self.trigger_type == "folder_watch":
            cfg = self.trigger_config or {}
            if not cfg.get("folder_id"):
                raise ValueError("Folder watch trigger requires 'folder_id' in trigger_config")
        return self


class AutomationResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    enabled: bool
    trigger_type: str
    trigger_config: dict
    action_type: str
    action_id: Optional[str] = None
    action_name: Optional[str] = None
    user_id: str
    team_id: Optional[str] = None
    shared_with_team: bool = False
    output_config: dict = {}
    created_at: str
    updated_at: str


class TriggerEventStatusResponse(BaseModel):
    trigger_event_id: str
    status: str  # queued | running | completed | failed
    action_type: str  # workflow | extraction
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output: Optional[Any] = None
    error: Optional[str] = None
