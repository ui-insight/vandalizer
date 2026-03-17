"""Request/response models for automation endpoints."""

from typing import Optional
from pydantic import BaseModel


class CreateAutomationRequest(BaseModel):
    name: str
    space: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[dict] = None
    action_type: Optional[str] = None
    action_id: Optional[str] = None
    shared_with_team: bool = False
    output_config: Optional[dict] = None


class UpdateAutomationRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[dict] = None
    action_type: Optional[str] = None
    action_id: Optional[str] = None
    shared_with_team: Optional[bool] = None
    output_config: Optional[dict] = None


class AutomationResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    enabled: bool
    trigger_type: str
    trigger_config: dict
    action_type: str
    action_id: Optional[str] = None
    user_id: str
    team_id: Optional[str] = None
    shared_with_team: bool = False
    space: Optional[str] = None
    output_config: dict = {}
    created_at: str
    updated_at: str
