"""Request/response models for config endpoints."""

from typing import Optional

from pydantic import BaseModel


class ModelInfo(BaseModel):
    name: str
    tag: str = ""
    external: bool = False
    thinking: bool = False


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
