"""Integration tests for the automation API trigger endpoint.

Covers the full /api/automations/{id}/trigger surface: authentication,
input modes (files, document_uuids, text), action routing (workflow vs
extraction), validation, error handling, and document lifecycle.
"""

import datetime
import io
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token, hash_api_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

API_KEY = "test-api-key-12345"
_API_KEY_HASH = hash_api_token(API_KEY)


def _make_user(user_id="testuser", current_team=None, **overrides):
    defaults = {
        "id": "fake-id",
        "user_id": user_id,
        "email": f"{user_id}@example.com",
        "name": "Test User",
        "api_token_hash": _API_KEY_HASH,
        "api_token_expires_at": None,
        "is_admin": False,
        "is_examiner": False,
        "current_team": current_team,
        "is_demo_user": False,
        "demo_status": None,
    }
    defaults.update(overrides)
    user = MagicMock()
    for k, v in defaults.items():
        setattr(user, k, v)
    return user


def _make_automation(
    automation_id="auto-1",
    action_type="workflow",
    action_id=None,
    enabled=True,
    trigger_type="api",
    user_id="testuser",
    team_id=None,
    output_config=None,
):
    action_id = action_id or str(ObjectId())
    auto = MagicMock()
    auto.id = automation_id
    auto.name = "Test Automation"
    auto.description = "Integration test automation"
    auto.enabled = enabled
    auto.trigger_type = trigger_type
    auto.trigger_config = {}
    auto.action_type = action_type
    auto.action_id = action_id
    auto.user_id = user_id
    auto.team_id = team_id
    auto.shared_with_team = bool(team_id)
    auto.output_config = output_config or {}
    auto.created_at = datetime.datetime.now(datetime.timezone.utc)
    auto.updated_at = datetime.datetime.now(datetime.timezone.utc)
    return auto


def _make_doc(uuid="doc-1"):
    doc = MagicMock()
    doc.id = ObjectId()
    doc.uuid = uuid
    doc.title = f"Document {uuid}"
    doc.user_id = "testuser"
    return doc


def _make_activity(activity_id="activity-1"):
    activity = MagicMock()
    activity.id = activity_id
    activity.started_at = datetime.datetime.now(datetime.timezone.utc)
    return activity


def _api_headers():
    return {"x-api-key": API_KEY}


def _mock_extraction_event(event_id="ext-event-1"):
    """Return a mock ExtractionTriggerEvent with async insert."""
    evt = MagicMock()
    evt.id = event_id
    evt.insert = AsyncMock()
    return evt


def _auth_cookies(user_id="testuser"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


def _pdf_bytes():
    return b"%PDF-1.4 fake pdf content for testing"


def _docx_bytes():
    """Minimal bytes that start with the PK ZIP magic number."""
    return b"PK\x03\x04" + b"\x00" * 100


def _mock_smart_document_class():
    """Return a mock SmartDocument class that tracks constructor calls.

    Beanie Document classes require motor collection initialization,
    so we mock the entire class for tests that create documents.
    """
    created = []

    def constructor(**kwargs):
        doc = MagicMock()
        doc.id = ObjectId()
        doc.uuid = kwargs.get("uuid", "mock-uuid")
        doc.extension = kwargs.get("extension", "")
        doc.title = kwargs.get("title", "")
        doc.raw_text = kwargs.get("raw_text", "")
        doc.processing = kwargs.get("processing", False)
        doc.user_id = kwargs.get("user_id", "")
        doc.task_id = None
        doc.insert = AsyncMock()
        doc.save = AsyncMock()
        created.append(doc)
        return doc

    mock_cls = MagicMock(side_effect=constructor)
    # Support SmartDocument.find(query).to_list()
    mock_find_result = MagicMock()
    mock_find_result.to_list = AsyncMock(side_effect=lambda: list(created))
    mock_cls.find = MagicMock(return_value=mock_find_result)
    return mock_cls, created


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app
        from app.rate_limit import limiter

        limiter.enabled = False
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
        limiter.enabled = True


# ---------------------------------------------------------------------------
# Authentication & authorization
# ---------------------------------------------------------------------------


class TestTriggerAuth:
    """x-api-key authentication and automation-level authorization."""

    @pytest.mark.asyncio
    async def test_no_api_key_rejected(self, client):
        resp = await client.post(
            "/api/automations/auto-1/trigger",
            data={"text": "hello"},
        )
        # CSRF middleware returns 403 before the endpoint checks x-api-key
        assert resp.status_code in (401, 403, 422)

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_401(self, client):
        with patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=None)
            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"text": "hello"},
                headers={"x-api-key": "bad-key"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_api_key_returns_401(self, client):
        user = _make_user(
            api_token_expires_at=datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc),
        )
        with patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"text": "hello"},
                headers=_api_headers(),
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_automation_not_found_returns_404(self, client):
        user = _make_user()
        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = None

            resp = await client.post(
                "/api/automations/nonexistent/trigger",
                data={"text": "hello"},
                headers=_api_headers(),
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_disabled_automation_returns_400(self, client):
        user = _make_user()
        auto = _make_automation(enabled=False)
        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"text": "hello"},
                headers=_api_headers(),
            )
        assert resp.status_code == 400
        assert "disabled" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_no_action_configured_returns_400(self, client):
        user = _make_user()
        auto = _make_automation(action_id=None)
        auto.action_id = None
        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"text": "hello"},
                headers=_api_headers(),
            )
        assert resp.status_code == 400
        assert "no action" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cookie_auth_rejected_on_trigger(self, client):
        """The trigger endpoint requires x-api-key, not cookie auth."""
        user = _make_user()
        cookies, headers = _auth_cookies()
        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"text": "hello"},
                cookies=cookies,
                headers=headers,
            )
        # Without x-api-key header, get_api_key_user should fail
        assert resp.status_code in (401, 422, 403)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestTriggerInputValidation:
    """Validate the three input modes: files, document_uuids, text."""

    @pytest.mark.asyncio
    async def test_no_input_returns_400(self, client):
        """Trigger with empty body (no files, no doc UUIDs, no text)."""
        user = _make_user()
        auto = _make_automation()
        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                headers=_api_headers(),
            )
        assert resp.status_code == 400
        assert "no input" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_empty_text_treated_as_no_input(self, client):
        user = _make_user()
        auto = _make_automation()
        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"text": "   "},
                headers=_api_headers(),
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_foreign_document_uuid_returns_404(self, client):
        user = _make_user()
        auto = _make_automation()
        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock) as mock_ctx, \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock) as mock_doc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto
            mock_ctx.return_value = MagicMock()
            mock_doc.return_value = None  # Not authorized

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"document_uuids": "unauthorized-doc"},
                headers=_api_headers(),
            )
        assert resp.status_code == 404
        assert "unauthorized-doc" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_multiple_document_uuids_comma_separated(self, client):
        """All UUIDs in the comma-separated list are authorized individually."""
        user = _make_user()
        auto = _make_automation(action_type="extraction", action_id="ss-1")
        doc1 = _make_doc("doc-1")
        doc2 = _make_doc("doc-2")

        call_count = 0

        async def authorize_doc(uuid, user, **kw):
            nonlocal call_count
            call_count += 1
            return {"doc-1": doc1, "doc-2": doc2}.get(uuid)

        activity = _make_activity()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock) as mock_ctx, \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock, side_effect=authorize_doc), \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.routers.automations.ExtractionTriggerEvent", return_value=_mock_extraction_event()), \
             patch("app.tasks.passive_tasks.process_extraction_outputs.delay"):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto
            mock_ctx.return_value = MagicMock()

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"document_uuids": "doc-1, doc-2"},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        assert set(resp.json()["documents"]) == {"doc-1", "doc-2"}
        assert call_count == 2  # Both docs authorized individually

    @pytest.mark.asyncio
    async def test_partial_unauthorized_doc_stops_early(self, client):
        """If second of two document UUIDs is unauthorized, entire request fails."""
        user = _make_user()
        auto = _make_automation()
        doc1 = _make_doc("doc-1")

        async def authorize_doc(uuid, user, **kw):
            if uuid == "doc-1":
                return doc1
            return None  # doc-2 unauthorized

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock) as mock_ctx, \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock, side_effect=authorize_doc):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto
            mock_ctx.return_value = MagicMock()

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"document_uuids": "doc-1,doc-2"},
                headers=_api_headers(),
            )
        assert resp.status_code == 404
        assert "doc-2" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Text input
# ---------------------------------------------------------------------------


class TestTriggerTextInput:
    """Triggering with plain text creates a temp document."""

    @pytest.mark.asyncio
    async def test_text_creates_temp_document_and_queues_extraction(self, client):
        user = _make_user()
        auto = _make_automation(action_type="extraction", action_id="ss-1")
        activity = _make_activity()
        MockSmartDoc, created = _mock_smart_document_class()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.SmartDocument", MockSmartDoc), \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.routers.automations.ExtractionTriggerEvent", return_value=_mock_extraction_event()), \
             patch("app.tasks.passive_tasks.process_extraction_outputs.delay") as mock_delay:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"text": "Extract this content"},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
        assert resp.json()["action_type"] == "extraction"
        assert len(resp.json()["documents"]) == 1

        # Verify temp document was created correctly
        assert len(created) == 1
        doc = created[0]
        assert doc.raw_text == "Extract this content"
        assert doc.extension == "txt"
        assert doc.processing is False
        assert doc.user_id == "testuser"

        mock_delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_text_input_for_workflow_action(self, client):
        user = _make_user()
        action_id = str(ObjectId())
        auto = _make_automation(action_type="workflow", action_id=action_id)
        activity = _make_activity()
        trigger_event = {"_id": ObjectId()}
        MockSmartDoc, created = _mock_smart_document_class()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.SmartDocument", MockSmartDoc), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.services.passive_triggers.create_api_trigger", return_value=trigger_event), \
             patch("app.tasks.passive_tasks.execute_workflow_passive.delay") as mock_exec:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"text": "Process this text"},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        assert resp.json()["action_type"] == "workflow"
        assert resp.json()["status"] == "queued"
        mock_exec.assert_called_once_with(str(trigger_event["_id"]))


# ---------------------------------------------------------------------------
# File uploads
# ---------------------------------------------------------------------------


class TestTriggerFileUpload:
    """Triggering with file uploads."""

    @pytest.mark.asyncio
    async def test_file_upload_creates_document_and_dispatches(self, client):
        user = _make_user()
        auto = _make_automation(action_type="extraction", action_id="ss-1")
        activity = _make_activity()
        MockSmartDoc, created = _mock_smart_document_class()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.SmartDocument", MockSmartDoc), \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.routers.automations.ExtractionTriggerEvent", return_value=_mock_extraction_event()), \
             patch("app.tasks.upload_tasks.dispatch_upload_tasks", return_value="task-123") as mock_dispatch, \
             patch("app.tasks.passive_tasks.process_extraction_outputs.delay") as mock_extract, \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_bytes"):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                files={"files": ("test.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
        assert len(resp.json()["documents"]) == 1

        # Document created with correct metadata
        assert len(created) == 1
        doc = created[0]
        assert doc.title == "test.pdf"
        assert doc.extension == "pdf"
        assert doc.processing is True
        assert doc.user_id == "testuser"

        # Upload tasks dispatched
        mock_dispatch.assert_called_once()

        # Extraction queued
        mock_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_file_upload(self, client):
        user = _make_user()
        auto = _make_automation(action_type="extraction", action_id="ss-1")
        activity = _make_activity()
        MockSmartDoc, created = _mock_smart_document_class()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.SmartDocument", MockSmartDoc), \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.routers.automations.ExtractionTriggerEvent", return_value=_mock_extraction_event()), \
             patch("app.tasks.upload_tasks.dispatch_upload_tasks", return_value="task-x"), \
             patch("app.tasks.passive_tasks.process_extraction_outputs.delay"), \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_bytes"):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                files=[
                    ("files", ("a.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")),
                    ("files", ("b.docx", io.BytesIO(_docx_bytes()), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
                ],
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        assert len(resp.json()["documents"]) == 2
        assert len(created) == 2
        extensions = {d.extension for d in created}
        assert extensions == {"pdf", "docx"}

    @pytest.mark.asyncio
    async def test_file_without_extension_defaults_to_pdf(self, client):
        user = _make_user()
        auto = _make_automation(action_type="extraction", action_id="ss-1")
        activity = _make_activity()
        MockSmartDoc, created = _mock_smart_document_class()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.SmartDocument", MockSmartDoc), \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.routers.automations.ExtractionTriggerEvent", return_value=_mock_extraction_event()), \
             patch("app.tasks.upload_tasks.dispatch_upload_tasks", return_value="task-x"), \
             patch("app.tasks.passive_tasks.process_extraction_outputs.delay"), \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_bytes"):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                files={"files": ("noext", io.BytesIO(b"data"), "application/octet-stream")},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        assert created[0].extension == "pdf"  # default fallback


# ---------------------------------------------------------------------------
# Workflow action routing
# ---------------------------------------------------------------------------


class TestTriggerWorkflowAction:
    """Workflow/task action type creates trigger event and dispatches execution."""

    @pytest.mark.asyncio
    async def test_workflow_trigger_creates_event_and_dispatches(self, client):
        user = _make_user()
        action_id = str(ObjectId())
        auto = _make_automation(action_type="workflow", action_id=action_id)
        doc = _make_doc("doc-1")
        activity = _make_activity()
        trigger_event = {"_id": ObjectId()}

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock, return_value=doc), \
             patch("app.routers.automations.SmartDocument.find") as mock_find, \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.services.passive_triggers.create_api_trigger", return_value=trigger_event) as mock_create_trigger, \
             patch("app.tasks.passive_tasks.execute_workflow_passive.delay") as mock_exec:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto
            mock_find.return_value.to_list = AsyncMock(return_value=[doc])

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"document_uuids": "doc-1"},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["action_type"] == "workflow"
        assert body["documents"] == ["doc-1"]
        assert "trigger_event_id" in body

        # Trigger event created with correct workflow ID
        mock_create_trigger.assert_called_once()
        call_kwargs = mock_create_trigger.call_args[1]
        assert call_kwargs["workflow_id"] == action_id

        # Execution dispatched
        mock_exec.assert_called_once_with(str(trigger_event["_id"]))

    @pytest.mark.asyncio
    async def test_task_action_routes_like_workflow(self, client):
        """action_type='task' uses the same workflow pipeline."""
        user = _make_user()
        action_id = str(ObjectId())
        auto = _make_automation(action_type="task", action_id=action_id)
        doc = _make_doc("doc-1")
        activity = _make_activity()
        trigger_event = {"_id": ObjectId()}

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock, return_value=doc), \
             patch("app.routers.automations.SmartDocument.find") as mock_find, \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.services.passive_triggers.create_api_trigger", return_value=trigger_event), \
             patch("app.tasks.passive_tasks.execute_workflow_passive.delay") as mock_exec:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto
            mock_find.return_value.to_list = AsyncMock(return_value=[doc])

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"document_uuids": "doc-1"},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        assert resp.json()["action_type"] == "task"
        mock_exec.assert_called_once()


# ---------------------------------------------------------------------------
# Extraction action routing
# ---------------------------------------------------------------------------


class TestTriggerExtractionAction:
    """Extraction action type validates search set and dispatches extraction."""

    @pytest.mark.asyncio
    async def test_extraction_validates_search_set(self, client):
        user = _make_user()
        auto = _make_automation(action_type="extraction", action_id="ss-1")
        doc = _make_doc("doc-1")

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock, return_value=doc), \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock, return_value=None):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"document_uuids": "doc-1"},
                headers=_api_headers(),
            )

        assert resp.status_code == 404
        assert "extraction" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_extraction_dispatches_celery_task(self, client):
        user = _make_user()
        auto = _make_automation(action_type="extraction", action_id="ss-1")
        doc = _make_doc("doc-1")
        activity = _make_activity()
        mock_ext_event = MagicMock()
        mock_ext_event.id = "ext-event-1"
        mock_ext_event.insert = AsyncMock()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock, return_value=doc), \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.routers.automations.ExtractionTriggerEvent", return_value=mock_ext_event), \
             patch("app.tasks.passive_tasks.process_extraction_outputs.delay") as mock_delay:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"document_uuids": "doc-1"},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["action_type"] == "extraction"
        assert body["status"] == "queued"
        assert "trigger_event_id" in body

        mock_delay.assert_called_once_with(
            automation_id="auto-1",
            search_set_uuid="ss-1",
            document_uuids=["doc-1"],
            user_id="testuser",
            extraction_event_id="ext-event-1",
        )

    @pytest.mark.asyncio
    async def test_unsupported_action_type_returns_400(self, client):
        user = _make_user()
        auto = _make_automation(action_type="unknown_type")
        MockSmartDoc, _ = _mock_smart_document_class()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.SmartDocument", MockSmartDoc):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"text": "test"},
                headers=_api_headers(),
            )

        assert resp.status_code == 400
        assert "unsupported" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Mixed inputs
# ---------------------------------------------------------------------------


class TestTriggerMixedInputs:
    """Combining files + document_uuids + text in a single request."""

    @pytest.mark.asyncio
    async def test_text_and_document_uuids_combined(self, client):
        user = _make_user()
        auto = _make_automation(action_type="extraction", action_id="ss-1")
        doc = _make_doc("existing-doc")
        activity = _make_activity()
        MockSmartDoc, created = _mock_smart_document_class()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock, return_value=doc), \
             patch("app.routers.automations.SmartDocument", MockSmartDoc), \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.routers.automations.ExtractionTriggerEvent", return_value=_mock_extraction_event()), \
             patch("app.tasks.passive_tasks.process_extraction_outputs.delay"):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"document_uuids": "existing-doc", "text": "Additional content"},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        docs = resp.json()["documents"]
        # Should have existing doc + temp text doc
        assert len(docs) == 2
        assert "existing-doc" in docs

    @pytest.mark.asyncio
    async def test_file_and_text_combined(self, client):
        user = _make_user()
        auto = _make_automation(action_type="extraction", action_id="ss-1")
        activity = _make_activity()
        MockSmartDoc, created = _mock_smart_document_class()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock) as mock_get, \
             patch("app.routers.automations.SmartDocument", MockSmartDoc), \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.routers.automations.ExtractionTriggerEvent", return_value=_mock_extraction_event()), \
             patch("app.tasks.upload_tasks.dispatch_upload_tasks", return_value="task-x"), \
             patch("app.tasks.passive_tasks.process_extraction_outputs.delay"), \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_bytes"):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get.return_value = auto

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"text": "Plus this text"},
                files={"files": ("test.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        # Text doc + uploaded file doc
        assert len(resp.json()["documents"]) == 2
        # One should be txt (text input), one should be pdf (file upload)
        extensions = {d.extension for d in created}
        assert "txt" in extensions
        assert "pdf" in extensions


# ---------------------------------------------------------------------------
# CRUD endpoints (cookie auth)
# ---------------------------------------------------------------------------


class TestAutomationCRUD:
    """Tests for create, list, get, update, delete using cookie auth."""

    @pytest.mark.asyncio
    async def test_create_automation(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()
        now = datetime.datetime.now(datetime.timezone.utc)
        auto = _make_automation()
        auto.created_at = now
        auto.updated_at = now

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations._validate_action_target", new_callable=AsyncMock), \
             patch("app.routers.automations.svc.create_automation", new_callable=AsyncMock, return_value=auto):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/automations",
                json={"name": "My Automation", "trigger_type": "api"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Test Automation"
        assert body["id"] == "auto-1"

    @pytest.mark.asyncio
    async def test_create_folder_watch_requires_folder_id(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/automations",
                json={
                    "name": "Watch",
                    "trigger_type": "folder_watch",
                    "trigger_config": {},
                },
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 422  # Pydantic validation error

    @pytest.mark.asyncio
    async def test_create_schedule_requires_cron(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/automations",
                json={
                    "name": "Scheduled",
                    "trigger_type": "schedule",
                    "trigger_config": {},
                },
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_automations(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()
        now = datetime.datetime.now(datetime.timezone.utc)
        auto = _make_automation()
        auto.created_at = now
        auto.updated_at = now

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.list_automations", new_callable=AsyncMock, return_value=[auto]):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                "/api/automations",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["name"] == "Test Automation"

    @pytest.mark.asyncio
    async def test_get_automation_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock, return_value=None):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                "/api/automations/nonexistent",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_automation(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()
        now = datetime.datetime.now(datetime.timezone.utc)
        auto = _make_automation()
        auto.created_at = now
        auto.updated_at = now

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock, return_value=auto), \
             patch("app.routers.automations._validate_action_target", new_callable=AsyncMock), \
             patch("app.routers.automations.svc.update_automation", new_callable=AsyncMock, return_value=auto):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.patch(
                "/api/automations/auto-1",
                json={"name": "Updated Name", "enabled": True},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock, return_value=None):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.patch(
                "/api/automations/nonexistent",
                json={"name": "X"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_automation(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.delete_automation", new_callable=AsyncMock, return_value=True):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.delete(
                "/api/automations/auto-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.delete_automation", new_callable=AsyncMock, return_value=False):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.delete(
                "/api/automations/nonexistent",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_crud_returns_401(self, client):
        resp = await client.get("/api/automations")
        assert resp.status_code == 401

        # POST without CSRF hits 403 from middleware before auth check
        resp = await client.post("/api/automations", json={"name": "x"})
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestAutomationSchemaValidation:
    """Pydantic schema validation for create/update requests."""

    @pytest.mark.asyncio
    async def test_create_with_valid_folder_watch(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()
        now = datetime.datetime.now(datetime.timezone.utc)
        auto = _make_automation(trigger_type="folder_watch")
        auto.trigger_config = {"folder_id": "folder-1"}
        auto.created_at = now
        auto.updated_at = now

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations._validate_action_target", new_callable=AsyncMock), \
             patch("app.routers.automations.svc.create_automation", new_callable=AsyncMock, return_value=auto):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/automations",
                json={
                    "name": "Folder Watcher",
                    "trigger_type": "folder_watch",
                    "trigger_config": {"folder_id": "folder-1"},
                },
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_with_valid_schedule(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()
        now = datetime.datetime.now(datetime.timezone.utc)
        auto = _make_automation(trigger_type="schedule")
        auto.trigger_config = {"cron_expression": "0 9 * * *"}
        auto.created_at = now
        auto.updated_at = now

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations._validate_action_target", new_callable=AsyncMock), \
             patch("app.routers.automations.svc.create_automation", new_callable=AsyncMock, return_value=auto):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/automations",
                json={
                    "name": "Nightly Run",
                    "trigger_type": "schedule",
                    "trigger_config": {"cron_expression": "0 9 * * *"},
                },
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_missing_name_returns_422(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/automations",
                json={"trigger_type": "api"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Polling endpoint (GET /runs/{trigger_event_id})
# ---------------------------------------------------------------------------


class TestPollingEndpoint:
    """Tests for GET /api/automations/runs/{trigger_event_id}."""

    @pytest.mark.asyncio
    async def test_poll_invalid_id_returns_400(self, client):
        user = _make_user()
        with patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get(
                "/api/automations/runs/not-a-valid-oid",
                headers=_api_headers(),
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_poll_not_found_returns_404(self, client):
        user = _make_user()
        oid = str(ObjectId())
        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.WorkflowTriggerEvent.find_one", new_callable=AsyncMock, return_value=None), \
             patch("app.routers.automations.ExtractionTriggerEvent.find_one", new_callable=AsyncMock, return_value=None):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                f"/api/automations/runs/{oid}",
                headers=_api_headers(),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_poll_running_workflow_returns_retry_after(self, client):
        user = _make_user()
        oid = ObjectId()
        auto_oid = str(ObjectId())
        auto = _make_automation(automation_id=auto_oid)

        wf_event = MagicMock()
        wf_event.status = "running"
        wf_event.trigger_context = {"automation_id": auto_oid}
        wf_event.created_at = datetime.datetime.now(datetime.timezone.utc)
        wf_event.started_at = datetime.datetime.now(datetime.timezone.utc)
        wf_event.completed_at = None
        wf_event.workflow_result = None
        wf_event.error = None

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.WorkflowTriggerEvent.find_one", new_callable=AsyncMock, return_value=wf_event), \
             patch("app.routers.automations.Automation.get", new_callable=AsyncMock, return_value=auto):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                f"/api/automations/runs/{oid}",
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        assert resp.headers.get("retry-after") == "5"
        body = resp.json()
        assert body["status"] == "running"
        assert body["output"] is None

    @pytest.mark.asyncio
    async def test_poll_completed_workflow_returns_output(self, client):
        user = _make_user()
        oid = ObjectId()
        auto_oid = str(ObjectId())
        auto = _make_automation(automation_id=auto_oid)
        result_oid = ObjectId()

        wf_event = MagicMock()
        wf_event.status = "completed"
        wf_event.trigger_context = {"automation_id": auto_oid}
        wf_event.created_at = datetime.datetime.now(datetime.timezone.utc)
        wf_event.started_at = datetime.datetime.now(datetime.timezone.utc)
        wf_event.completed_at = datetime.datetime.now(datetime.timezone.utc)
        wf_event.workflow_result = result_oid
        wf_event.error = None

        wf_result = MagicMock()
        wf_result.final_output = {"output": {"name": "John", "age": 30}}

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.WorkflowTriggerEvent.find_one", new_callable=AsyncMock, return_value=wf_event), \
             patch("app.routers.automations.Automation.get", new_callable=AsyncMock, return_value=auto), \
             patch("app.routers.automations.WorkflowResult.get", new_callable=AsyncMock, return_value=wf_result):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                f"/api/automations/runs/{oid}",
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["output"] == {"name": "John", "age": 30}
        assert "retry-after" not in resp.headers

    @pytest.mark.asyncio
    async def test_poll_completed_extraction_returns_result(self, client):
        user = _make_user()
        oid = ObjectId()

        ext_event = MagicMock()
        ext_event.status = "completed"
        ext_event.user_id = "testuser"
        ext_event.created_at = datetime.datetime.now(datetime.timezone.utc)
        ext_event.started_at = datetime.datetime.now(datetime.timezone.utc)
        ext_event.completed_at = datetime.datetime.now(datetime.timezone.utc)
        ext_event.result = [{"document_id": "doc-1", "name": "Acme Corp"}]
        ext_event.error = None

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.WorkflowTriggerEvent.find_one", new_callable=AsyncMock, return_value=None), \
             patch("app.routers.automations.ExtractionTriggerEvent.find_one", new_callable=AsyncMock, return_value=ext_event):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                f"/api/automations/runs/{oid}",
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["action_type"] == "extraction"
        assert body["output"] == [{"document_id": "doc-1", "name": "Acme Corp"}]

    @pytest.mark.asyncio
    async def test_poll_wrong_user_returns_404(self, client):
        """Polling an event owned by another user should return 404."""
        user = _make_user(user_id="other-user")
        oid = ObjectId()
        auto_oid = str(ObjectId())
        auto = _make_automation(automation_id=auto_oid, user_id="original-owner")

        wf_event = MagicMock()
        wf_event.status = "completed"
        wf_event.trigger_context = {"automation_id": auto_oid}

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.WorkflowTriggerEvent.find_one", new_callable=AsyncMock, return_value=wf_event), \
             patch("app.routers.automations.Automation.get", new_callable=AsyncMock, return_value=auto):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                f"/api/automations/runs/{oid}",
                headers=_api_headers(),
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Extraction trigger_event_id in response
# ---------------------------------------------------------------------------


class TestExtractionTriggerEventId:
    """Extraction triggers now return trigger_event_id for polling."""

    @pytest.mark.asyncio
    async def test_extraction_response_includes_trigger_event_id(self, client):
        user = _make_user()
        auto = _make_automation(action_type="extraction", action_id="ss-1")
        doc = _make_doc("doc-1")
        activity = _make_activity()
        mock_ext_event = _mock_extraction_event("ext-123")

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock, return_value=auto), \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock, return_value=doc), \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.routers.automations.ExtractionTriggerEvent", return_value=mock_ext_event), \
             patch("app.tasks.passive_tasks.process_extraction_outputs.delay"):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"document_uuids": "doc-1"},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["trigger_event_id"] == "ext-123"
        assert body["action_type"] == "extraction"


# ---------------------------------------------------------------------------
# Callback URL validation
# ---------------------------------------------------------------------------


class TestCallbackUrl:
    """Tests for the callback_url parameter on trigger endpoint."""

    @pytest.mark.asyncio
    async def test_callback_url_accepted_on_extraction(self, client):
        """A valid callback_url is stored in ExtractionTriggerEvent trigger_context."""
        user = _make_user()
        auto = _make_automation(action_type="extraction", action_id="ss-1")
        doc = _make_doc("doc-1")
        activity = _make_activity()
        mock_ext_event = _mock_extraction_event()

        with patch("app.dependencies.User") as MockUser, \
             patch("app.routers.automations.svc.get_automation", new_callable=AsyncMock, return_value=auto), \
             patch("app.routers.automations.access_control.get_team_access_context", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.routers.automations.access_control.get_authorized_document", new_callable=AsyncMock, return_value=doc), \
             patch("app.routers.automations.get_authorized_search_set", new_callable=AsyncMock, return_value=MagicMock()), \
             patch("app.services.activity_service.activity_start", new_callable=AsyncMock, return_value=activity), \
             patch("app.routers.automations.ExtractionTriggerEvent", return_value=mock_ext_event) as MockExtCls, \
             patch("app.tasks.passive_tasks.process_extraction_outputs.delay"), \
             patch("app.utils.url_validation.validate_outbound_url", return_value="https://example.com/webhook"):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/automations/auto-1/trigger",
                data={"document_uuids": "doc-1", "callback_url": "https://example.com/webhook"},
                headers=_api_headers(),
            )

        assert resp.status_code == 200
        # Verify ExtractionTriggerEvent was created with callback_url in trigger_context
        call_kwargs = MockExtCls.call_args[1]
        assert call_kwargs["trigger_context"]["callback_url"] == "https://example.com/webhook"
