"""Tests for app.services.audit_service.

Mocks AuditLog model's Beanie query methods.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLogEvent:
    @pytest.mark.asyncio
    async def test_creates_entry_with_correct_fields(self):
        mock_instance = MagicMock()
        mock_instance.insert = AsyncMock()

        with patch("app.services.audit_service.AuditLog") as MockAuditLog:
            MockAuditLog.return_value = mock_instance

            from app.services.audit_service import log_event

            await log_event(
                action="document.create",
                actor_user_id="user-1",
                resource_type="document",
                resource_id="doc-123",
                resource_name="test.pdf",
                team_id="team-1",
                organization_id="org-1",
                detail={"size": 1024},
                ip_address="127.0.0.1",
            )

            MockAuditLog.assert_called_once()
            call_kwargs = MockAuditLog.call_args.kwargs
            assert call_kwargs["action"] == "document.create"
            assert call_kwargs["actor_user_id"] == "user-1"
            assert call_kwargs["resource_type"] == "document"
            assert call_kwargs["resource_id"] == "doc-123"
            assert call_kwargs["resource_name"] == "test.pdf"
            assert call_kwargs["team_id"] == "team-1"
            assert call_kwargs["organization_id"] == "org-1"
            assert call_kwargs["detail"] == {"size": 1024}
            assert call_kwargs["ip_address"] == "127.0.0.1"
            mock_instance.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_suppresses_exceptions(self):
        """log_event should not raise even if insert fails."""
        mock_instance = MagicMock()
        mock_instance.insert = AsyncMock(side_effect=RuntimeError("DB down"))

        with patch("app.services.audit_service.AuditLog") as MockAuditLog:
            MockAuditLog.return_value = mock_instance

            from app.services.audit_service import log_event

            # Should not raise
            await log_event(
                action="document.create",
                actor_user_id="user-1",
                resource_type="document",
            )


class TestQueryAuditLog:
    @pytest.mark.asyncio
    async def test_applies_filters_and_returns(self):
        entry1 = MagicMock()
        entry1.uuid = "entry-1"
        entry1.action = "document.create"

        mock_query = MagicMock()
        mock_query.count = AsyncMock(return_value=1)
        mock_sort = MagicMock()
        mock_skip = MagicMock()
        mock_skip.limit = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[entry1])))
        mock_sort.skip = MagicMock(return_value=mock_skip)
        mock_query.sort = MagicMock(return_value=mock_sort)

        with patch("app.services.audit_service.AuditLog") as MockAuditLog:
            MockAuditLog.find = MagicMock(return_value=mock_query)
            MockAuditLog.timestamp = MagicMock()  # supports unary negation in sort()

            from app.services.audit_service import query_audit_log

            entries, total = await query_audit_log(
                action="document.create",
                skip=0,
                limit=10,
            )

        assert total == 1
        assert len(entries) == 1
        assert entries[0].uuid == "entry-1"
        # Verify find was called with the action filter
        find_args = MockAuditLog.find.call_args
        assert find_args[0][0].get("action") == "document.create"
