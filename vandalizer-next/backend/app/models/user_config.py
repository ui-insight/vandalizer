"""UserModelConfig model for per-user LLM settings."""

from typing import Optional

from beanie import Document


class UserModelConfig(Document):
    """User-specific model configuration."""

    user_id: str
    name: str  # selected model name
    temperature: float = 0.7
    top_p: float = 0.9
    available_models: list[dict] = []
    pinned_items: list[str] = []
    favorite_items: list[str] = []

    class Settings:
        name = "user_model_config"
