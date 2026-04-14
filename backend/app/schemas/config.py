"""Request/response models for config endpoints."""

from typing import Optional

from pydantic import BaseModel


class ModelInfo(BaseModel):
    name: str
    tag: str = ""
    external: bool = False
    thinking: bool = False
    speed: str = ""
    tier: str = ""
    privacy: str = ""
    supports_structured: bool = True
    multimodal: bool = False
    supports_pdf: bool = False
    context_window: int = 128000


class UserConfigResponse(BaseModel):
    model: str
    temperature: float = 0.7
    top_p: float = 0.9
    available_models: list[ModelInfo] = []


class UpdateUserConfigRequest(BaseModel):
    model: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None


class ThemeConfigResponse(BaseModel):
    highlight_color: str = "#eab308"
    highlight_text_color: str = "#000000"
    highlight_complement: str = "#154cf7"
    ui_radius: str = "12px"


class UpdateThemeConfigRequest(BaseModel):
    highlight_color: Optional[str] = None
    ui_radius: Optional[str] = None


class OnboardingStatusResponse(BaseModel):
    has_documents: bool = False
    has_workflows: bool = False
    has_run_workflow: bool = False
    has_extraction_sets: bool = False
    has_library_items: bool = False
    has_pinned_item: bool = False
    has_favorited_item: bool = False
    has_team_members: bool = False
    has_automations: bool = False
    has_enabled_automation: bool = False
    has_knowledge_base: bool = False
    has_ready_knowledge_base: bool = False
    has_chatted_with_docs: bool = False
    has_conversations: bool = False
    first_session_completed: bool = False
    is_certified: bool = False
