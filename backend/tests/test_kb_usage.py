"""Unit tests for per-user KB usage tracking (powers the "Recently Used" sort)."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import knowledge_service


class TestRecordKBUsage:
    @pytest.mark.asyncio
    async def test_upserts_last_used_and_increments_count(self):
        coll = MagicMock()
        coll.update_one = AsyncMock()
        with patch(
            "app.services.knowledge_service.KnowledgeBaseUsage"
        ) as MockUsage:
            MockUsage.get_motor_collection.return_value = coll
            await knowledge_service.record_kb_usage("user1", "kb-1")

        coll.update_one.assert_awaited_once()
        (filter_doc, update_doc), kwargs = coll.update_one.await_args
        assert filter_doc == {"user_id": "user1", "kb_uuid": "kb-1"}
        assert update_doc["$inc"] == {"use_count": 1}
        assert isinstance(update_doc["$set"]["last_used_at"], datetime.datetime)
        assert update_doc["$set"]["last_used_at"].tzinfo is not None
        assert kwargs == {"upsert": True}


class TestGetKBUsageMap:
    @pytest.mark.asyncio
    async def test_empty_uuid_list_short_circuits(self):
        with patch(
            "app.services.knowledge_service.KnowledgeBaseUsage"
        ) as MockUsage:
            result = await knowledge_service.get_kb_usage_map("user1", [])
        assert result == {}
        MockUsage.find.assert_not_called()

    @pytest.mark.asyncio
    async def test_maps_kb_uuid_to_last_used_at(self):
        rec = MagicMock()
        rec.kb_uuid = "kb-1"
        rec.last_used_at = datetime.datetime(
            2026, 7, 20, 12, 0, tzinfo=datetime.timezone.utc
        )
        with patch(
            "app.services.knowledge_service.KnowledgeBaseUsage"
        ) as MockUsage:
            MockUsage.find.return_value.to_list = AsyncMock(return_value=[rec])
            result = await knowledge_service.get_kb_usage_map("user1", ["kb-1", "kb-2"])

        assert result == {"kb-1": rec.last_used_at}
