"""Integration tests for automation API routes."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _make_api_user(user_id="testuser", current_team=None):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    from app.utils.security import hash_api_token

    user.api_token_hash = hash_api_token("test-api-key")
    user.api_token_expires_at = None
    user.is_admin = False
    user.is_examiner = False
    user.current_team = current_team
    user.is_demo_user = False
    user.demo_status = None
    return user


def _make_automation(action_type="extraction", action_id="search-set-1"):
    auto = MagicMock()
    auto.id = "automation-id"
    auto.name = "My Automation"
    auto.enabled = True
    auto.action_type = action_type
    auto.action_id = action_id
    auto.output_config = {}
    return auto


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


class TestAutomationTriggerAuth:
    @pytest.mark.asyncio
    async def test_trigger_rejects_foreign_existing_document_uuid(self, client):
        user = _make_api_user()
        auto = _make_automation()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get_automation, \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock) as mock_get_doc, \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock) as mock_get_search_set:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_automation.return_value = auto
            mock_team_access.return_value = MagicMock()
            mock_get_doc.return_value = None

            resp = await client.post(
                "/api/automations/automation-id/trigger",
                data={"document_uuids": "foreign-doc"},
                headers={"x-api-key": "test-api-key"},
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Document not found: foreign-doc"
        mock_get_search_set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_trigger_authorizes_existing_documents_before_extraction(self, client):
        user = _make_api_user()
        auto = _make_automation()
        doc = MagicMock()
        doc.uuid = "doc-1"
        activity = MagicMock()
        activity.id = "activity-1"
        activity.started_at = datetime.datetime.now(datetime.timezone.utc)

        mock_ext_event = MagicMock()
        mock_ext_event.id = "ext-event-1"

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get_automation, \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock) as mock_get_doc, \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock) as mock_get_search_set, \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock) as mock_activity_start, \
             patch("app.routers.automations.ExtractionTriggerEvent", return_value=mock_ext_event) as MockExtEvent, \
             patch("app.tasks.passive_tasks.process_extraction_outputs.delay") as mock_delay:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_automation.return_value = auto
            mock_team_access.return_value = MagicMock()
            mock_get_doc.return_value = doc
            mock_get_search_set.return_value = MagicMock()
            mock_activity_start.return_value = activity
            mock_ext_event.insert = AsyncMock()

            resp = await client.post(
                "/api/automations/automation-id/trigger",
                data={"document_uuids": "doc-1"},
                headers={"x-api-key": "test-api-key"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
        assert resp.json()["documents"] == ["doc-1"]
        assert "trigger_event_id" in resp.json()
        mock_delay.assert_called_once_with(
            automation_id="automation-id",
            search_set_uuid="search-set-1",
            document_uuids=["doc-1"],
            user_id="testuser",
            extraction_event_id="ext-event-1",
        )
