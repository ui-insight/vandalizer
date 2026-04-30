"""Tests for app.services.config_service.

The service stitches SystemConfig + UserModelConfig lookups. We mock both
Beanie documents and verify the resolution rules (name→tag fallback,
default-name fallback, user-config sync on stale data).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.config_service import (
    get_default_model_name,
    get_extraction_config,
    get_llm_endpoint,
    get_llm_model_by_name,
    get_llm_model_names,
    get_llm_models,
    get_user_model_name,
    resolve_model_name,
)


def _system_config(
    *,
    available_models: list | None = None,
    default_model: str = "",
    llm_endpoint: str = "",
) -> SimpleNamespace:
    cfg = SimpleNamespace(
        available_models=available_models if available_models is not None else [],
        default_model=default_model,
        llm_endpoint=llm_endpoint,
    )
    cfg.get_extraction_config = lambda: {"mode": "two_pass"}
    return cfg


def _patch_system_config(config):
    """Patch SystemConfig.get_config to return *config*."""
    MockCls = SimpleNamespace(get_config=AsyncMock(return_value=config))
    return patch("app.services.config_service.SystemConfig", MockCls)


class TestGetLlmModels:
    @pytest.mark.asyncio
    async def test_returns_list_from_system_config(self):
        models = [{"name": "gpt-4o"}, {"name": "claude-opus"}]
        with _patch_system_config(_system_config(available_models=models)):
            assert await get_llm_models() == models

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_config(self):
        with _patch_system_config(None):
            assert await get_llm_models() == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_models(self):
        with _patch_system_config(_system_config(available_models=[])):
            assert await get_llm_models() == []


class TestGetDefaultModelName:
    @pytest.mark.asyncio
    async def test_returns_configured_default_when_valid(self):
        cfg = _system_config(
            available_models=[{"name": "gpt-4o"}, {"name": "claude"}],
            default_model="claude",
        )
        with _patch_system_config(cfg):
            assert await get_default_model_name() == "claude"

    @pytest.mark.asyncio
    async def test_falls_back_to_first_available_when_default_invalid(self):
        cfg = _system_config(
            available_models=[{"name": "gpt-4o"}, {"name": "claude"}],
            default_model="gemini",  # not in list
        )
        with _patch_system_config(cfg):
            assert await get_default_model_name() == "gpt-4o"

    @pytest.mark.asyncio
    async def test_whitespace_only_default_treated_as_unset(self):
        cfg = _system_config(
            available_models=[{"name": "gpt-4o"}],
            default_model="   ",
        )
        with _patch_system_config(cfg):
            assert await get_default_model_name() == "gpt-4o"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_models(self):
        with _patch_system_config(_system_config(available_models=[])):
            assert await get_default_model_name() == ""

    @pytest.mark.asyncio
    async def test_skips_non_dict_entries(self):
        cfg = _system_config(
            available_models=["not a dict", {"name": "gpt-4o"}],
        )
        with _patch_system_config(cfg):
            assert await get_default_model_name() == "gpt-4o"


class TestGetLlmModelNames:
    @pytest.mark.asyncio
    async def test_returns_set_of_names(self):
        cfg = _system_config(
            available_models=[{"name": "a"}, {"name": "b"}, {"name": ""}, {}],
        )
        with _patch_system_config(cfg):
            names = await get_llm_model_names()
        assert names == {"a", "b"}


class TestGetLlmModelByName:
    @pytest.mark.asyncio
    async def test_none_or_empty_returns_none(self):
        assert await get_llm_model_by_name(None) is None
        assert await get_llm_model_by_name("") is None

    @pytest.mark.asyncio
    async def test_matches_by_name_first(self):
        cfg = _system_config(available_models=[
            {"name": "gpt-4o", "tag": "turbo"},
            {"name": "claude-opus", "tag": "gpt-4o"},  # tag collides with the first model's name
        ])
        with _patch_system_config(cfg):
            found = await get_llm_model_by_name("gpt-4o")
        # Name match wins over tag match
        assert found["name"] == "gpt-4o"
        assert found["tag"] == "turbo"

    @pytest.mark.asyncio
    async def test_falls_back_to_tag_match(self):
        cfg = _system_config(available_models=[
            {"name": "gpt-4o", "tag": "turbo"},
            {"name": "claude-opus", "tag": "deep"},
        ])
        with _patch_system_config(cfg):
            found = await get_llm_model_by_name("deep")
        assert found["name"] == "claude-opus"

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        cfg = _system_config(available_models=[{"name": "gpt-4o"}])
        with _patch_system_config(cfg):
            assert await get_llm_model_by_name("unknown") is None


class TestResolveModelName:
    @pytest.mark.asyncio
    async def test_known_model_returns_its_name(self):
        cfg = _system_config(available_models=[{"name": "gpt-4o", "tag": "turbo"}])
        with _patch_system_config(cfg):
            assert await resolve_model_name("turbo") == "gpt-4o"

    @pytest.mark.asyncio
    async def test_unknown_model_falls_back_to_default(self):
        cfg = _system_config(
            available_models=[{"name": "gpt-4o"}],
            default_model="gpt-4o",
        )
        with _patch_system_config(cfg):
            assert await resolve_model_name("gemini") == "gpt-4o"

    @pytest.mark.asyncio
    async def test_empty_input_returns_default(self):
        cfg = _system_config(
            available_models=[{"name": "gpt-4o"}],
            default_model="gpt-4o",
        )
        with _patch_system_config(cfg):
            assert await resolve_model_name(None) == "gpt-4o"


class TestGetLlmEndpoint:
    @pytest.mark.asyncio
    async def test_returns_configured_endpoint(self):
        cfg = _system_config(llm_endpoint="https://api.example/v1")
        with _patch_system_config(cfg):
            assert await get_llm_endpoint() == "https://api.example/v1"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_config(self):
        with _patch_system_config(None):
            assert await get_llm_endpoint() == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_endpoint_unset(self):
        with _patch_system_config(_system_config(llm_endpoint="")):
            assert await get_llm_endpoint() == ""


class TestGetExtractionConfig:
    @pytest.mark.asyncio
    async def test_delegates_to_system_config_method(self):
        cfg = _system_config()
        cfg.get_extraction_config = lambda: {"mode": "one_pass"}
        with _patch_system_config(cfg):
            assert await get_extraction_config() == {"mode": "one_pass"}

    @pytest.mark.asyncio
    async def test_falls_back_to_defaults_when_no_config(self):
        with _patch_system_config(None):
            result = await get_extraction_config()
        assert isinstance(result, dict)
        # DEFAULT_EXTRACTION_CONFIG should include at least a "mode" key
        assert "mode" in result


class TestGetUserModelName:
    @pytest.mark.asyncio
    async def test_no_user_returns_default(self):
        cfg = _system_config(
            available_models=[{"name": "gpt-4o"}],
            default_model="gpt-4o",
        )
        with _patch_system_config(cfg):
            assert await get_user_model_name(None) == "gpt-4o"

    @pytest.mark.asyncio
    async def test_user_without_config_returns_default(self):
        cfg = _system_config(
            available_models=[{"name": "gpt-4o"}],
            default_model="gpt-4o",
        )
        with _patch_system_config(cfg), patch(
            "app.services.config_service.UserModelConfig"
        ) as MockUserConfig:
            MockUserConfig.find_one = AsyncMock(return_value=None)
            assert await get_user_model_name("alice") == "gpt-4o"
