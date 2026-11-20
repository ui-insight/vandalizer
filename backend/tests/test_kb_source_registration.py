from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import knowledge_service as service


@pytest.mark.asyncio
async def test_missing_document_in_batch_writes_no_pending_sources():
    model = MagicMock()
    with patch.object(service, 'KnowledgeBaseSource', model), patch.object(service.access_control, 'get_team_access_context', AsyncMock()), patch.object(service.access_control, 'get_authorized_document', AsyncMock(side_effect=[SimpleNamespace(uuid='allowed'), None])), patch.object(service, 'recalculate_stats', AsyncMock()) as stats:
        with pytest.raises(ValueError, match='Document not found: missing'):
            await service.register_documents(SimpleNamespace(uuid='kb'), ['allowed', 'missing'], SimpleNamespace(user_id='user'))
    model.assert_not_called()
    model.find_one.assert_not_called()
    stats.assert_not_called()


@pytest.mark.asyncio
async def test_repeated_ids_register_once_and_existing_sources_are_skipped():
    model = MagicMock()
    model.find_one = AsyncMock(side_effect=[None, SimpleNamespace(uuid='existing-source')])
    model.return_value.insert = AsyncMock()
    model.return_value.uuid = 'new-source'
    with patch.object(service, 'KnowledgeBaseSource', model), patch.object(service.access_control, 'get_team_access_context', AsyncMock()), patch.object(service.access_control, 'get_authorized_document', AsyncMock(side_effect=[SimpleNamespace(uuid='new'), SimpleNamespace(uuid='existing')])) as authorized, patch.object(service, 'recalculate_stats', AsyncMock()) as stats:
        result = await service.register_documents(SimpleNamespace(uuid='kb'), ['new', 'new', 'existing'], SimpleNamespace(user_id='user'))
    assert result == ['new-source']
    assert authorized.await_count == 2
    model.return_value.insert.assert_awaited_once()
    stats.assert_awaited_once()
