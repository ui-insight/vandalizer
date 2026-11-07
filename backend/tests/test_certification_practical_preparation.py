"""Read real configuration shapes without creating global settings."""
import datetime
import json
from unittest.mock import AsyncMock

from beanie import PydanticObjectId
import pytest

from app.models.system_config import SystemConfig
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.lab_execution import runtime_digest
from app.services.certification_versions.practical_preparation import configured_runtime


@pytest.mark.asyncio
async def test_preparation_runtime_serializes_settings_and_excludes_nonexecution_metadata(monkeypatch):
    config = SystemConfig.model_construct(id=PydanticObjectId(), updated_at=datetime.datetime.now(datetime.timezone.utc),
        updated_by='configuration-owner', available_models=[{'name': 'configured-model', 'api_key': 'first-key'}],
        extraction_config={'mode': 'one_pass', 'model': 'configured-model', 'temperature': 0.1})
    monkeypatch.setattr(SystemConfig, 'find_one', AsyncMock(return_value=config))
    create = AsyncMock(side_effect=AssertionError('Preparation must not create global settings'))
    monkeypatch.setattr(SystemConfig, 'get_config', create)
    first = await configured_runtime()
    json.dumps(first, allow_nan=False)
    assert not {'id', 'updated_at', 'updated_by'} & first.keys()
    assert first['extraction_config']['model'] == 'configured-model'
    original = runtime_digest(first)
    config.updated_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    config.updated_by = 'another-configuration-owner'
    config.available_models = [{'name': 'configured-model', 'api_key': 'rotated-key'}]
    assert runtime_digest(await configured_runtime()) == original
    config.extraction_config = {**config.extraction_config, 'temperature': 0.9}
    assert runtime_digest(await configured_runtime()) != original
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_preparation_runtime_does_not_initialize_missing_configuration(monkeypatch):
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(SystemConfig, 'find_one', lookup)
    create = AsyncMock(side_effect=AssertionError('No configuration initialization'))
    monkeypatch.setattr(SystemConfig, 'get_config', create)
    with pytest.raises(CourseCatalogError, match='settings are unavailable'):
        await configured_runtime()
    lookup.assert_awaited_once()
    create.assert_not_awaited()
