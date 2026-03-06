"""Configuration service  - async helpers for SystemConfig and UserModelConfig."""

from copy import deepcopy

from app.models.system_config import (
    DEFAULT_EXTRACTION_CONFIG,
    SystemConfig,
    _apply_legacy_strategy,
    _deep_merge,
)
from app.models.user_config import UserModelConfig


# ---------------------------------------------------------------------------
# LLM model helpers
# ---------------------------------------------------------------------------

async def get_llm_models() -> list[dict]:
    """Return the current list of LLM models from SystemConfig."""
    config = await SystemConfig.get_config()
    if config and config.available_models:
        return config.available_models
    return []


async def get_default_model_name() -> str:
    """Return the first configured model name (never empty when models exist)."""
    models = await get_llm_models()
    for m in models:
        if isinstance(m, dict):
            name = m.get("name", "")
            if name:
                return name
    return ""


async def get_llm_model_names() -> set[str]:
    """Return set of configured model names."""
    models = await get_llm_models()
    return {
        m.get("name")
        for m in models
        if isinstance(m, dict) and m.get("name")
    }


async def get_llm_model_by_name(model_name: str | None) -> dict | None:
    """Return a model config dict by name or tag."""
    if not model_name:
        return None
    models = await get_llm_models()
    # Try exact name match first
    for m in models:
        if isinstance(m, dict) and m.get("name") == model_name:
            return m
    # Fall back to tag match
    for m in models:
        if isinstance(m, dict) and m.get("tag") == model_name:
            return m
    return None


async def resolve_model_name(model_name: str | None) -> str:
    """Resolve a model name or tag to the actual model name for LLM calls."""
    if model_name:
        model = await get_llm_model_by_name(model_name)
        if model:
            return model.get("name", model_name)
    return await get_default_model_name()


# ---------------------------------------------------------------------------
# LLM endpoint
# ---------------------------------------------------------------------------

async def get_llm_endpoint() -> str:
    """Get LLM endpoint from SystemConfig."""
    config = await SystemConfig.get_config()
    if config and config.llm_endpoint:
        return config.llm_endpoint
    return "https://mindrouter-api.nkn.uidaho.edu/v1"


# ---------------------------------------------------------------------------
# Extraction config
# ---------------------------------------------------------------------------

async def get_extraction_config() -> dict:
    """Get the full extraction configuration dict (DB > defaults)."""
    config = await SystemConfig.get_config()
    if config:
        return config.get_extraction_config()
    # Fallback to defaults
    return deepcopy(DEFAULT_EXTRACTION_CONFIG)


# ---------------------------------------------------------------------------
# User model config
# ---------------------------------------------------------------------------

async def get_user_model_name(user_id: str | None) -> str:
    """Return a valid current model name for the user (resolves tag→name for LLM calls)."""
    if not user_id:
        return await get_default_model_name()

    user_config = await UserModelConfig.find_one(UserModelConfig.user_id == user_id)
    if not user_config:
        return await get_default_model_name()

    # Resolve stored value (could be tag or name) to actual model name
    resolved = await resolve_model_name(user_config.name)

    # Sync available_models list if stale
    models = await get_llm_models()
    needs_save = False
    if user_config.available_models != models:
        user_config.available_models = models
        needs_save = True

    # If stored value doesn't match any model, reset to default
    if not await get_llm_model_by_name(user_config.name):
        user_config.name = resolved
        needs_save = True

    if needs_save:
        await user_config.save()

    # Final guard: if resolved is still empty, try default one more time
    if not resolved:
        resolved = await get_default_model_name()

    return resolved


async def reconcile_user_model_config(
    user_id: str,
    create_if_missing: bool = False,
):
    """Reconcile a user's model config with system models.

    Returns (user_config_or_none, configured_models, resolved_model_name).
    """
    models = await get_llm_models()
    resolved_default = await resolve_model_name(None)

    user_config = await UserModelConfig.find_one(UserModelConfig.user_id == user_id)
    if user_config is None:
        if create_if_missing:
            user_config = UserModelConfig(
                user_id=user_id,
                name=resolved_default,
                available_models=models,
            )
            await user_config.insert()
        return user_config, models, resolved_default

    resolved = await resolve_model_name(user_config.name)

    needs_save = False
    # Only reset stored value if it doesn't match any model at all
    if not await get_llm_model_by_name(user_config.name):
        user_config.name = resolved
        needs_save = True
    if user_config.available_models != models:
        user_config.available_models = models
        needs_save = True
    if needs_save:
        await user_config.save()

    return user_config, models, resolved
