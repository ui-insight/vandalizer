"""Route tests for config endpoints."""

import datetime
import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id: str = "testuser"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.token_version = 0
    user.demo_status = None
    return user


def _auth(user_id: str = "testuser"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


class TestAutomationStatsRoute:
    @pytest.mark.asyncio
    async def test_automation_stats_are_scoped_to_visible_workflows(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")
        now = datetime.datetime.now(datetime.timezone.utc)
        visible_workflows = [
            SimpleNamespace(
                id="wf-1",
                input_config={"folder_watch": {"enabled": True, "folders": ["folder-a"]}},
            ),
            SimpleNamespace(id="wf-2", input_config={}),
        ]
        recent_results = [
            SimpleNamespace(
                id="run-1",
                workflow="wf-1",
                status="completed",
                trigger_type="manual",
                is_passive=False,
                start_time=now,
                num_steps_completed=2,
                num_steps_total=2,
            ),
            SimpleNamespace(
                id="run-2",
                workflow="wf-2",
                status="failed",
                trigger_type="manual",
                is_passive=False,
                start_time=now - datetime.timedelta(days=2),
                num_steps_completed=1,
                num_steps_total=2,
            ),
        ]
        mock_find = MagicMock()
        mock_find.limit.return_value.to_list = AsyncMock(return_value=recent_results)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.config.workflow_service.list_workflows",
                new_callable=AsyncMock,
            ) as mock_list_workflows,
            patch("app.routers.config.WorkflowResult") as MockWorkflowResult,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_list_workflows.return_value = visible_workflows
            MockWorkflowResult.find.return_value = mock_find

            resp = await client.get("/api/config/automation-stats", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_workflows"] == 2
        assert data["passive_workflows"] == 1
        assert data["watched_folders"] == 1
        assert data["runs_today"] == 1
        assert data["runs_today_success"] == 1
        assert data["runs_today_failed"] == 0
        assert data["runs_this_week"] == 2
        query = MockWorkflowResult.find.call_args.args[0]
        assert query["workflow"]["$in"] == ["wf-1", "wf-2"]
        assert "start_time" in query

    @pytest.mark.asyncio
    async def test_automation_stats_handles_naive_start_times(self, client):
        """MongoDB returns datetimes tz-naive, so start_time comes back without
        tzinfo. Comparing that to an aware ``now`` must not 500 (regression:
        'can't compare offset-naive and offset-aware datetimes')."""
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")
        # Naive UTC, exactly as Beanie reads them back from Mongo.
        now_naive = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        visible_workflows = [SimpleNamespace(id="wf-1", input_config={})]
        recent_results = [
            SimpleNamespace(
                id="run-1", workflow="wf-1", status="completed", trigger_type="manual",
                is_passive=True, start_time=now_naive,
                num_steps_completed=1, num_steps_total=1,
            ),
            SimpleNamespace(
                id="run-2", workflow="wf-1", status="error", trigger_type="folder_watch",
                is_passive=True, start_time=now_naive - datetime.timedelta(days=3),
                num_steps_completed=0, num_steps_total=1,
            ),
        ]
        mock_find = MagicMock()
        mock_find.limit.return_value.to_list = AsyncMock(return_value=recent_results)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.config.workflow_service.list_workflows",
                new_callable=AsyncMock,
            ) as mock_list_workflows,
            patch("app.routers.config.WorkflowResult") as MockWorkflowResult,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_list_workflows.return_value = visible_workflows
            MockWorkflowResult.find.return_value = mock_find

            resp = await client.get("/api/config/automation-stats", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["runs_today"] == 1
        assert data["runs_today_failed"] == 0
        assert data["runs_this_week"] == 2
        # Sort (also naive/aware-sensitive) puts the newer run first.
        assert data["recent_runs"][0]["id"] == "run-1"

    @pytest.mark.asyncio
    async def test_automation_stats_skip_recent_run_query_without_visible_workflows(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.config.workflow_service.list_workflows",
                new_callable=AsyncMock,
            ) as mock_list_workflows,
            patch("app.routers.config.WorkflowResult") as MockWorkflowResult,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_list_workflows.return_value = []

            resp = await client.get("/api/config/automation-stats", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_workflows"] == 0
        assert data["runs_this_week"] == 0
        assert data["recent_runs"] == []
        MockWorkflowResult.find.assert_not_called()


class TestThemeRoute:
    @pytest.mark.asyncio
    async def test_get_theme_includes_icon_hide_in_nav(self, client):
        cfg = SimpleNamespace(
            highlight_color="#eab308",
            ui_radius="12px",
            org_name="Acme",
            logo_data_url="",
            icon_data_url="data:image/png;base64,AAAA",
            icon_hide_in_nav=True,
        )
        with patch("app.routers.config.SystemConfig") as MockSC:
            MockSC.get_config = AsyncMock(return_value=cfg)
            resp = await client.get("/api/config/theme")

        assert resp.status_code == 200
        assert resp.json()["icon_hide_in_nav"] is True

    @pytest.mark.asyncio
    async def test_update_theme_persists_icon_hide_in_nav(self, client):
        admin = _make_user("admin")
        admin.is_admin = True
        cookies, headers = _auth("admin")
        cfg = SimpleNamespace(
            highlight_color="#eab308",
            ui_radius="12px",
            org_name="",
            logo_data_url="",
            icon_data_url="",
            icon_hide_in_nav=False,
            updated_at=None,
            updated_by=None,
        )
        cfg.save = AsyncMock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.config.SystemConfig") as MockSC,
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockSC.get_config = AsyncMock(return_value=cfg)

            resp = await client.put(
                "/api/config/theme",
                json={"icon_hide_in_nav": True},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["icon_hide_in_nav"] is True
        assert cfg.icon_hide_in_nav is True
        cfg.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_theme_requires_admin(self, client):
        user = _make_user("viewer")  # is_admin defaults to False
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.put(
                "/api/config/theme",
                json={"icon_hide_in_nav": True},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
