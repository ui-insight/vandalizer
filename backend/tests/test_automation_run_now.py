""""Run now" for automations: document selection mirrors the trigger, the
route dispatches through the passive pipeline as a ``manual`` trigger, and the
editor can poll the run with cookie auth."""

import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.services.automation_run_now import (
    RUN_NOW_FOLDER_LIMIT,
    filter_documents_for_trigger,
    select_run_now_documents,
)
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _auth(user_id="testuser"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


def _user(user_id="testuser"):
    u = MagicMock()
    u.id = "fake-id"
    u.user_id = user_id
    u.email = f"{user_id}@x"
    u.name = "T"
    u.is_admin = False
    u.is_examiner = False
    u.current_team = None
    u.is_demo_user = False
    u.token_version = 0
    u.demo_status = None
    return u


def _auto(trigger_type="folder_watch", action_type="workflow", action_id="wf-1", **cfg):
    return SimpleNamespace(
        id="auto-1", name="Nightly", user_id="testuser", enabled=False,
        trigger_type=trigger_type, trigger_config=cfg, action_type=action_type, action_id=action_id,
    )


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

class TestFilterDocumentsForTrigger:
    DOCS = [
        {"uuid": "a", "title": "award.pdf", "extension": "pdf"},
        {"uuid": "b", "title": "notes.docx", "extension": "docx"},
        {"uuid": "c", "title": "draft-award.pdf", "extension": "pdf"},
    ]

    def test_no_filters_keeps_everything(self):
        assert filter_documents_for_trigger(self.DOCS, {}) == self.DOCS
        assert filter_documents_for_trigger(self.DOCS, None) == self.DOCS

    def test_file_types_and_exclude_patterns_like_the_upload_path(self):
        out = filter_documents_for_trigger(self.DOCS, {"file_types": ["pdf"], "exclude_patterns": "draft-*, *.tmp"})
        assert [d["uuid"] for d in out] == ["a"]

    def test_exclude_patterns_as_a_list(self):
        out = filter_documents_for_trigger(self.DOCS, {"exclude_patterns": ["*.docx"]})
        assert [d["uuid"] for d in out] == ["a", "c"]


class TestSelectRunNowDocuments:
    @pytest.mark.asyncio
    async def test_chosen_documents_win_for_any_trigger(self):
        with patch("app.services.automation_run_now._documents_by_uuid",
                   new=AsyncMock(return_value=[{"uuid": "x", "title": "X", "extension": "pdf"}])):
            sel = await select_run_now_documents(_auto("api"), chosen_uuids=["x"])
        assert sel["source"] == "chosen" and [d["uuid"] for d in sel["documents"]] == ["x"]

    @pytest.mark.asyncio
    async def test_folder_watch_uses_the_watched_folder_with_filters_and_cap(self):
        folder_docs = [{"uuid": f"d{i}", "title": f"f{i}.pdf", "extension": "pdf"} for i in range(RUN_NOW_FOLDER_LIMIT + 5)]
        folder_docs.append({"uuid": "skip", "title": "skip.docx", "extension": "docx"})
        with patch("app.services.automation_run_now._folder_documents", new=AsyncMock(return_value=folder_docs)) as fd:
            sel = await select_run_now_documents(_auto(folder_id="F1", file_types=["pdf"]))
        fd.assert_awaited_once_with("F1")
        assert sel["source"] == "folder"
        assert sel["matched"] == RUN_NOW_FOLDER_LIMIT + 5
        assert len(sel["documents"]) == RUN_NOW_FOLDER_LIMIT
        assert all(d["extension"] == "pdf" for d in sel["documents"])

    @pytest.mark.asyncio
    async def test_folder_watch_without_folder_or_matches_explains(self):
        sel = await select_run_now_documents(_auto())
        assert sel["documents"] == [] and "no watched folder" in sel["reason"]
        with patch("app.services.automation_run_now._folder_documents", new=AsyncMock(return_value=[])):
            sel = await select_run_now_documents(_auto(folder_id="F1"))
        assert "no documents that pass" in sel["reason"]

    @pytest.mark.asyncio
    async def test_schedule_uses_configured_documents_then_folder(self):
        with patch("app.services.automation_run_now._documents_by_uuid",
                   new=AsyncMock(return_value=[{"uuid": "s1", "title": "S", "extension": "pdf"}])):
            sel = await select_run_now_documents(_auto("schedule", document_uuids=["s1"]))
        assert sel["source"] == "configured" and sel["matched"] == 1
        with patch("app.services.automation_run_now._folder_documents",
                   new=AsyncMock(return_value=[{"uuid": "f", "title": "F", "extension": "pdf"}])):
            sel = await select_run_now_documents(_auto("schedule", folder_id="F2"))
        assert sel["source"] == "folder" and [d["uuid"] for d in sel["documents"]] == ["f"]

    @pytest.mark.asyncio
    async def test_api_and_m365_need_chosen_documents(self):
        for t in ("api", "m365_intake"):
            sel = await select_run_now_documents(_auto(t))
            assert sel["documents"] == [] and "Choose documents" in sel["reason"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


def _authed(user, auto):
    return (
        patch("app.dependencies.decode_token", return_value={"sub": user.user_id, "type": "access"}),
        patch("app.dependencies.User"),
        patch("app.routers.automations._load_authorized_automation", new=AsyncMock(return_value=(auto, MagicMock()))),
    )


class TestRunNowRoute:
    @pytest.mark.asyncio
    async def test_requires_login(self, client):
        resp = await client.post("/api/automations/auto-1/run-now", json={})
        # CSRF middleware answers 403 before auth would say 401; either way, no run.
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_dispatches_as_a_manual_trigger_with_the_folder_selection(self, client):
        user, auto = _user(), _auto(folder_id="F1")
        cookies, headers = _auth()
        p_tok, p_user, p_load = _authed(user, auto)
        selection = {"documents": [{"uuid": "d1", "title": "award.pdf", "extension": "pdf"}],
                     "source": "folder", "matched": 3, "reason": None}
        with p_tok, p_user as MockUser, p_load, \
             patch("app.routers.automations.automation_run_now.select_run_now_documents",
                   new=AsyncMock(return_value=selection)) as mock_select, \
             patch("app.routers.automations._dispatch_action",
                   new=AsyncMock(return_value={"status": "queued", "trigger_event_id": "evt-1"})) as mock_dispatch, \
             patch("app.routers.automations.audit_service.log_event", new=AsyncMock()) as mock_audit:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post("/api/automations/auto-1/run-now", json={}, cookies=cookies, headers=headers)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["trigger_event_id"] == "evt-1"
        assert body["documents"] == [{"uuid": "d1", "title": "award.pdf"}]
        assert body["document_source"] == "folder" and body["documents_matched"] == 3
        # Manage rights, and the selection was asked for without chosen docs.
        assert mock_select.await_args.kwargs["chosen_uuids"] == []
        kwargs = mock_dispatch.await_args.kwargs
        assert kwargs["trigger_type"] == "manual"
        assert kwargs["extra_context"] == {"manual_run": True, "run_by_user_id": "testuser"}
        assert mock_dispatch.await_args.args[2] == ["d1"]
        assert mock_audit.await_args.kwargs["action"] == "automation.run_now"

    @pytest.mark.asyncio
    async def test_chosen_documents_are_authorized_first(self, client):
        user, auto = _user(), _auto("api")
        cookies, headers = _auth()
        p_tok, p_user, p_load = _authed(user, auto)
        with p_tok, p_user as MockUser, p_load, \
             patch("app.routers.automations._authorize_existing_documents",
                   new=AsyncMock(return_value=["ok1"])) as mock_authz, \
             patch("app.routers.automations.automation_run_now.select_run_now_documents",
                   new=AsyncMock(return_value={"documents": [{"uuid": "ok1", "title": "T", "extension": "pdf"}],
                                               "source": "chosen", "matched": 1, "reason": None})) as mock_select, \
             patch("app.routers.automations._dispatch_action",
                   new=AsyncMock(return_value={"status": "queued", "trigger_event_id": "evt-2"})), \
             patch("app.routers.automations.audit_service.log_event", new=AsyncMock()):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post("/api/automations/auto-1/run-now",
                                     json={"document_uuids": [" ok1 ", ""]}, cookies=cookies, headers=headers)
        assert resp.status_code == 200
        mock_authz.assert_awaited_once()
        assert mock_authz.await_args.args[0] == ["ok1"]
        assert mock_select.await_args.kwargs["chosen_uuids"] == ["ok1"]

    @pytest.mark.asyncio
    async def test_nothing_to_run_is_a_400_with_the_reason(self, client):
        user, auto = _user(), _auto("api")
        cookies, headers = _auth()
        p_tok, p_user, p_load = _authed(user, auto)
        with p_tok, p_user as MockUser, p_load, \
             patch("app.routers.automations.automation_run_now.select_run_now_documents",
                   new=AsyncMock(return_value={"documents": [], "source": "chosen", "matched": 0,
                                               "reason": "Choose documents to run with."})), \
             patch("app.routers.automations._dispatch_action", new=AsyncMock()) as mock_dispatch:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post("/api/automations/auto-1/run-now", json={}, cookies=cookies, headers=headers)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Choose documents to run with."
        mock_dispatch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_action_is_a_400(self, client):
        user, auto = _user(), _auto(action_id=None)
        cookies, headers = _auth()
        p_tok, p_user, p_load = _authed(user, auto)
        with p_tok, p_user as MockUser, p_load:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post("/api/automations/auto-1/run-now", json={}, cookies=cookies, headers=headers)
        assert resp.status_code == 400
        assert "no action target" in resp.json()["detail"]


class TestRunStatusRoute:
    @pytest.mark.asyncio
    async def test_cookie_status_is_scoped_to_the_automation(self, client):
        user, auto = _user(), _auto()
        cookies, headers = _auth()
        p_tok, p_user, p_load = _authed(user, auto)
        event = SimpleNamespace(
            trigger_context={"automation_id": "auto-1"}, status="completed", workflow_result=None,
            created_at=None, started_at=None, completed_at=None, error=None,
        )
        with p_tok, p_user as MockUser, p_load, \
             patch("app.routers.automations.WorkflowTriggerEvent.find_one", new=AsyncMock(return_value=event)):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/automations/auto-1/runs/507f1f77bcf86cd799439011", cookies=cookies, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        other = SimpleNamespace(**{**event.__dict__, "trigger_context": {"automation_id": "someone-elses"}})
        with p_tok, p_user as MockUser, p_load, \
             patch("app.routers.automations.WorkflowTriggerEvent.find_one", new=AsyncMock(return_value=other)):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/automations/auto-1/runs/507f1f77bcf86cd799439011", cookies=cookies, headers=headers)
        assert resp.status_code == 404
