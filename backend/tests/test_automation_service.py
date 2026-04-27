"""Tests for app.services.automation_service.

Thin CRUD layer on top of the Automation Beanie document. Beanie itself is
covered by integration tests; here we pin the argument-plumbing and the
authorization fast-path so refactors in the handler signatures surface
quickly.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.automation_service import (
    create_automation,
    delete_automation,
    get_automation,
    list_automations,
    update_automation,
)


def _auto(**overrides) -> SimpleNamespace:
    base = {
        "id": "oid-1",
        "name": "Test",
        "user_id": "alice",
        "description": None,
        "enabled": True,
        "trigger_type": "folder_watch",
        "trigger_config": {},
        "action_type": "workflow",
        "action_id": None,
        "team_id": None,
        "shared_with_team": False,
        "output_config": {},
        "updated_at": None,
    }
    base.update(overrides)
    n = SimpleNamespace(**base)
    n.save = AsyncMock()
    n.delete = AsyncMock()
    n.insert = AsyncMock()
    return n


class TestCreateAutomation:
    @pytest.mark.asyncio
    async def test_defaults_applied(self):
        auto = _auto(trigger_type="folder_watch", action_type="workflow",
                     trigger_config={}, output_config={})
        with patch("app.services.automation_service.Automation") as MockAuto:
            MockAuto.return_value = auto
            result = await create_automation("My Auto", "alice")

        auto.insert.assert_awaited_once()
        MockAuto.assert_called_once()
        call_kwargs = MockAuto.call_args.kwargs
        # Ensure defaults were plumbed correctly into the constructor
        assert call_kwargs["name"] == "My Auto"
        assert call_kwargs["user_id"] == "alice"
        assert call_kwargs["trigger_type"] == "folder_watch"
        assert call_kwargs["action_type"] == "workflow"
        assert call_kwargs["trigger_config"] == {}
        assert call_kwargs["output_config"] == {}
        assert result is auto

    @pytest.mark.asyncio
    async def test_explicit_values_override_defaults(self):
        auto = _auto()
        with patch("app.services.automation_service.Automation") as MockAuto:
            MockAuto.return_value = auto
            await create_automation(
                "A", "alice",
                description="auto description",
                trigger_type="m365",
                trigger_config={"intake": "shared-inbox"},
                action_type="chain",
                action_id="wf-1",
                team_id="team-1",
                shared_with_team=True,
                output_config={"target": "folder"},
            )
        kwargs = MockAuto.call_args.kwargs
        assert kwargs["description"] == "auto description"
        assert kwargs["trigger_type"] == "m365"
        assert kwargs["trigger_config"] == {"intake": "shared-inbox"}
        assert kwargs["action_type"] == "chain"
        assert kwargs["shared_with_team"] is True
        assert kwargs["team_id"] == "team-1"


class TestListAutomations:
    @pytest.mark.asyncio
    async def test_personal_only_when_no_team_provided(self):
        q = MagicMock()
        q.to_list = AsyncMock(return_value=[_auto()])
        with patch("app.services.automation_service.Automation") as MockA:
            MockA.find = MagicMock(return_value=q)
            result = await list_automations("alice")

        MockA.find.assert_called_once_with({"user_id": "alice"})
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_team_context_uses_or_query(self):
        q = MagicMock()
        q.to_list = AsyncMock(return_value=[])
        with patch("app.services.automation_service.Automation") as MockA:
            MockA.find = MagicMock(return_value=q)
            await list_automations("alice", team_id="team-xyz")

        MockA.find.assert_called_once()
        query = MockA.find.call_args.args[0]
        assert "$or" in query
        assert {"user_id": "alice"} in query["$or"]
        assert {"shared_with_team": True, "team_id": "team-xyz"} in query["$or"]


class TestGetAutomation:
    @pytest.mark.asyncio
    async def test_with_user_delegates_to_access_control(self):
        found = _auto()
        with patch(
            "app.services.automation_service.get_authorized_automation",
            AsyncMock(return_value=found),
        ) as mock_auth:
            user = SimpleNamespace(user_id="alice")
            result = await get_automation("auto-1", user=user, manage=True)
        mock_auth.assert_awaited_once_with("auto-1", user, manage=True)
        assert result is found

    @pytest.mark.asyncio
    async def test_without_user_uses_raw_get(self):
        found = _auto()
        with patch("app.services.automation_service.Automation") as MockA:
            MockA.get = AsyncMock(return_value=found)
            result = await get_automation("680000000000000000000001")
        assert result is found
        MockA.get.assert_awaited_once()


class TestUpdateAutomation:
    @pytest.mark.asyncio
    async def test_unauthorized_returns_none_without_side_effects(self):
        user = SimpleNamespace(user_id="alice")
        with patch(
            "app.services.automation_service.get_authorized_automation",
            AsyncMock(return_value=None),
        ):
            result = await update_automation("a-1", user, name="new")
        assert result is None

    @pytest.mark.asyncio
    async def test_selected_fields_updated_others_preserved(self):
        auto = _auto(name="Old", enabled=True, description="original")
        user = SimpleNamespace(user_id="alice")

        with patch(
            "app.services.automation_service.get_authorized_automation",
            AsyncMock(return_value=auto),
        ):
            result = await update_automation(
                "a-1", user,
                name="New name",
                enabled=False,
                trigger_config={"k": "v"},
            )

        assert result is auto
        assert auto.name == "New name"
        assert auto.enabled is False
        assert auto.description == "original"  # unchanged (None was not passed)
        assert auto.trigger_config == {"k": "v"}
        assert isinstance(auto.updated_at, datetime.datetime)
        auto.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_optional_fields_can_be_updated(self):
        auto = _auto()
        user = SimpleNamespace(user_id="alice")
        with patch(
            "app.services.automation_service.get_authorized_automation",
            AsyncMock(return_value=auto),
        ):
            await update_automation(
                "a-1", user,
                description="new description",
                trigger_type="m365",
                action_type="chain",
                action_id="wf-2",
                shared_with_team=True,
                output_config={"dest": "/out"},
            )
        assert auto.description == "new description"
        assert auto.trigger_type == "m365"
        assert auto.action_type == "chain"
        assert auto.action_id == "wf-2"
        assert auto.shared_with_team is True
        assert auto.output_config == {"dest": "/out"}


class TestDeleteAutomation:
    @pytest.mark.asyncio
    async def test_missing_returns_false(self):
        user = SimpleNamespace(user_id="alice")
        with patch(
            "app.services.automation_service.get_authorized_automation",
            AsyncMock(return_value=None),
        ):
            assert await delete_automation("a-1", user) is False

    @pytest.mark.asyncio
    async def test_deletes_and_returns_true(self):
        auto = _auto()
        user = SimpleNamespace(user_id="alice")
        with patch(
            "app.services.automation_service.get_authorized_automation",
            AsyncMock(return_value=auto),
        ):
            assert await delete_automation("a-1", user) is True
        auto.delete.assert_awaited_once()
