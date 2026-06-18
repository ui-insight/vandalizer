"""Tests for extraction router endpoints."""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(
    user_id: str = "testuser",
    *,
    is_admin: bool = False,
    current_team=None,
):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = is_admin
    user.is_examiner = False
    user.current_team = current_team
    user.is_demo_user = False
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


def _mock_search_set(**overrides):
    ss = MagicMock()
    ss.id = "ss-obj-id"
    ss.uuid = overrides.get("uuid", "ss-uuid-1")
    ss.title = overrides.get("title", "Test SearchSet")
    ss.status = overrides.get("status", "active")
    ss.set_type = overrides.get("set_type", "extraction")
    ss.user_id = overrides.get("user_id", "testuser")
    ss.team_id = overrides.get("team_id", None)
    ss.is_global = overrides.get("is_global", False)
    ss.verified = overrides.get("verified", False)
    ss.extraction_config = overrides.get("extraction_config", {})
    ss.fillable_pdf_url = overrides.get("fillable_pdf_url", None)
    ss.item_count = AsyncMock(return_value=overrides.get("item_count", 3))
    ss.cross_field_rules = overrides.get("cross_field_rules", [])
    # Mirror the real SearchSet helper: by default the normalized view returns
    # the raw rules unchanged. Tests that want migration behavior can override.
    ss.normalized_cross_field_rules = MagicMock(return_value=ss.cross_field_rules)
    ss.tuning_result = overrides.get("tuning_result", None)
    ss.extraction_config_override = overrides.get("extraction_config_override", None)
    ss.extraction_config_override_set_at = overrides.get("extraction_config_override_set_at", None)
    ss.save = AsyncMock()
    return ss


def _mock_item(**overrides):
    item = MagicMock()
    item.id = overrides.get("id", "item-obj-id")
    item.searchphrase = overrides.get("searchphrase", "What is the PI name?")
    item.searchset = overrides.get("searchset", "ss-uuid-1")
    item.searchtype = overrides.get("searchtype", "extraction")
    item.title = overrides.get("title", None)
    item.is_optional = overrides.get("is_optional", False)
    item.enum_values = overrides.get("enum_values", [])
    item.pdf_binding = overrides.get("pdf_binding", None)
    return item


class TestExtractionsRoutes:
    """Test extraction router endpoints."""

    # ------------------------------------------------------------------
    # Auth required
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_search_sets_requires_auth(self, client):
        resp = await client.get("/api/extractions/search-sets")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_search_set_requires_auth(self, client):
        csrf = secrets.token_urlsafe(32)
        resp = await client.post(
            "/api/extractions/search-sets",
            json={"title": "Test"},
            cookies={"csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 401

    # ------------------------------------------------------------------
    # SearchSet CRUD - happy paths
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_search_set_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.svc") as mock_svc,
            patch("app.routers.extractions._attach_quality", new_callable=AsyncMock, return_value={
                "quality_score": None, "quality_tier": None,
                "last_validated_at": None, "validation_run_count": 0,
            }),
            patch("app.routers.extractions.val_svc.portability_summary", new_callable=AsyncMock, return_value=None),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.create_search_set = AsyncMock(return_value=ss)

            resp = await client.post(
                "/api/extractions/search-sets",
                json={"title": "My Extraction"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test SearchSet"
        assert data["uuid"] == "ss-uuid-1"

    @pytest.mark.asyncio
    async def test_list_search_sets_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.svc") as mock_svc,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.routers.extractions._attach_quality", new_callable=AsyncMock, return_value={
                "quality_score": None, "quality_tier": None,
                "last_validated_at": None, "validation_run_count": 0,
            }),
            patch("app.routers.extractions.val_svc.portability_summary", new_callable=AsyncMock, return_value=None),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.list_search_sets = AsyncMock(return_value=[ss])
            mock_ac.get_team_access_context = AsyncMock(return_value=MagicMock())
            mock_ac.can_manage_search_set = MagicMock(return_value=True)

            resp = await client.get(
                "/api/extractions/search-sets",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["uuid"] == "ss-uuid-1"

    @pytest.mark.asyncio
    async def test_get_search_set_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.routers.extractions._attach_quality", new_callable=AsyncMock, return_value={
                "quality_score": None, "quality_tier": None,
                "last_validated_at": None, "validation_run_count": 0,
            }),
            patch("app.routers.extractions.val_svc.portability_summary", new_callable=AsyncMock, return_value=None),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            mock_ac.get_team_access_context = AsyncMock(return_value=MagicMock())
            mock_ac.can_manage_search_set = MagicMock(return_value=True)

            resp = await client.get(
                "/api/extractions/search-sets/ss-uuid-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["uuid"] == "ss-uuid-1"

    @pytest.mark.asyncio
    async def test_get_search_set_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/extractions/search-sets/nonexistent",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "SearchSet not found"

    @pytest.mark.asyncio
    async def test_delete_search_set_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.routers.extractions.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            mock_svc.delete_search_set = AsyncMock(return_value=True)

            resp = await client.delete(
                "/api/extractions/search-sets/ss-uuid-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_clone_search_set_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()
        cloned_ss = _mock_search_set(uuid="ss-uuid-cloned", title="Test SearchSet (Copy)")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.routers.extractions.svc") as mock_svc,
            patch("app.routers.extractions._attach_quality", new_callable=AsyncMock, return_value={
                "quality_score": None, "quality_tier": None,
                "last_validated_at": None, "validation_run_count": 0,
            }),
            patch("app.routers.extractions.val_svc.portability_summary", new_callable=AsyncMock, return_value=None),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            mock_svc.clone_search_set = AsyncMock(return_value=cloned_ss)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/clone",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["uuid"] == "ss-uuid-cloned"

    # ------------------------------------------------------------------
    # SearchSetItem CRUD
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_add_item_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()
        item = _mock_item()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.routers.extractions.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            mock_svc.add_item = AsyncMock(return_value=item)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/items",
                json={"searchphrase": "What is the PI name?"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["searchphrase"] == "What is the PI name?"

    @pytest.mark.asyncio
    async def test_list_items_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()
        item = _mock_item()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.routers.extractions.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            mock_svc.list_items = AsyncMock(return_value=[item])

            resp = await client.get(
                "/api/extractions/search-sets/ss-uuid-1/items",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["searchphrase"] == "What is the PI name?"

    @pytest.mark.asyncio
    async def test_delete_item_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()
        item = _mock_item()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.svc") as mock_svc,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_search_set_item = AsyncMock(return_value=item)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            mock_svc.delete_item = AsyncMock(return_value=True)

            resp = await client.delete(
                "/api/extractions/items/item-obj-id",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    # ------------------------------------------------------------------
    # Cross-field rules
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_cross_field_rules_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set(cross_field_rules=[
            {"id": "r1", "type": "range_check", "field": "Score", "min": 0, "max": 100},
        ])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

            resp = await client.get(
                "/api/extractions/search-sets/ss-uuid-1/cross-field-rules",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        rules = resp.json()["rules"]
        assert len(rules) == 1
        assert rules[0]["type"] == "range_check"
        assert rules[0]["field"] == "Score"

    @pytest.mark.asyncio
    async def test_update_cross_field_rules_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()
        ss.cross_field_rules = []

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

            resp = await client.put(
                "/api/extractions/search-sets/ss-uuid-1/cross-field-rules",
                json={"rules": [
                    {"type": "range_check", "field": "Score", "min": 0, "max": 100},
                ]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        ss.save.assert_called_once()

    # ------------------------------------------------------------------
    # Tuning result
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_tuning_result_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set(tuning_result={"best_model": "gpt-4o"})

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

            resp = await client.get(
                "/api/extractions/search-sets/ss-uuid-1/tuning-result",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["tuning_result"] == {"best_model": "gpt-4o"}

    @pytest.mark.asyncio
    async def test_clear_tuning_result_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set(tuning_result={"best_model": "gpt-4o"})

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

            resp = await client.delete(
                "/api/extractions/search-sets/ss-uuid-1/tuning-result",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert ss.tuning_result is None
        ss.save.assert_called_once()

    # ------------------------------------------------------------------
    # Optimizer apply / revert
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_apply_extraction_config_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set(extraction_config={"model": "claude-haiku"})

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/apply-config",
                json={"config": {"model": "claude-sonnet", "strategy": "two-pass"}},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["previous_override"] is None
        assert "applied_at" in body
        assert ss.extraction_config_override == {"model": "claude-sonnet", "strategy": "two-pass"}
        assert ss.extraction_config_override_set_at is not None
        ss.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_extraction_config_returns_previous(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set(extraction_config_override={"model": "claude-opus"})

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/apply-config",
                json={"config": {"model": "claude-sonnet"}},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        # Previous override is returned so the caller (optimization run) can
        # persist it for revert.
        assert resp.json()["previous_override"] == {"model": "claude-opus"}

    @pytest.mark.asyncio
    async def test_apply_extraction_config_rejects_empty(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/apply-config",
                json={"config": {}},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        ss.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_revert_extraction_config_clears_override(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set(
            extraction_config_override={"model": "claude-sonnet"},
            extraction_config_override_set_at="2026-05-23T10:00:00Z",
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/revert-config",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert ss.extraction_config_override is None
        assert ss.extraction_config_override_set_at is None
        ss.save.assert_called_once()

    # ------------------------------------------------------------------
    # Optimization start / poll / cancel / apply
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_start_extraction_optimization_queues_task(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        # Build a run doc that records its uuid after insert()
        run_doc = MagicMock()
        run_doc.uuid = "opt-uuid-1"
        run_doc.insert = AsyncMock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.models.extraction_optimization_run.ExtractionOptimizationRun") as MockRun,
            patch("app.services.extraction_optimizer.reap_stale_runs", new=AsyncMock()),
            patch("app.services.optimization_governance.enforce_and_record_start", new=AsyncMock()),
            patch("app.tasks.extraction_tasks.optimize_extraction_task") as mock_task,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            # No active run blocking (the stale-run watchdog is stubbed above).
            MockRun.find_one = AsyncMock(return_value=None)
            MockRun.return_value = run_doc
            mock_task.apply_async = MagicMock()

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/optimize",
                json={"token_budget": 0, "max_candidates": 4, "apply_on_finish": False},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["run_uuid"] == "opt-uuid-1"
        assert body["status"] == "queued"
        run_doc.insert.assert_awaited_once()
        mock_task.apply_async.assert_called_once()
        # Task id is generated up front and passed through to the dispatch so
        # the cancel endpoint / watchdog can revoke it.
        _, kwargs = mock_task.apply_async.call_args
        assert kwargs.get("task_id")

    @pytest.mark.asyncio
    async def test_start_extraction_optimization_rejects_when_already_running(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        active_run = MagicMock()
        active_run.uuid = "opt-existing"

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.models.extraction_optimization_run.ExtractionOptimizationRun") as MockRun,
            patch("app.services.extraction_optimizer.reap_stale_runs", new=AsyncMock()),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            MockRun.find_one = AsyncMock(return_value=active_run)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/optimize",
                json={"token_budget": 0},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 409
        assert "opt-existing" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_active_optimization_returns_null_when_idle(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.models.extraction_optimization_run.ExtractionOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            MockRun.find_one = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/extractions/search-sets/ss-uuid-1/optimize/active",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["run"] is None

    @pytest.mark.asyncio
    async def test_cancel_optimization_sets_flag(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        run = MagicMock()
        run.uuid = "opt-uuid-1"
        run.search_set_uuid = "ss-uuid-1"
        run.status = "running"
        run.cancel_requested = False
        run.save = AsyncMock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.models.extraction_optimization_run.ExtractionOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            MockRun.find_one = AsyncMock(return_value=run)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/optimize/opt-uuid-1/cancel",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "cancel_requested"
        assert run.cancel_requested is True
        run.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_optimization_history_returns_summaries_newest_first(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        # Two past runs, both completed. Backend's .sort("-started_at") puts
        # the more recent one first; we just verify the response carries
        # whatever the DB returns (we mock the DB to return in sort order).
        old_run = MagicMock(
            uuid="run-old", search_set_uuid="ss-uuid-1", status="completed",
            started_at=None, completed_at=None,
            token_budget=0, tokens_used=0,
            baseline_no_tool_score=0.3, baseline_default_score=0.6,
            optimized_score=0.7, judge_model=None,
            trials=[{"trial_id": "t1"}], best_config={"model": "m"}, options={},
            error_message=None,
        )
        new_run = MagicMock(
            uuid="run-new", search_set_uuid="ss-uuid-1", status="completed",
            started_at=None, completed_at=None,
            token_budget=0, tokens_used=0,
            baseline_no_tool_score=0.3, baseline_default_score=0.6,
            optimized_score=0.85, judge_model="claude-haiku",
            trials=[{"trial_id": "t1"}, {"trial_id": "t2"}],
            best_config={"model": "claude-sonnet"}, options={},
            error_message=None,
        )

        # Chain .find().sort().skip().limit().to_list()
        chain = MagicMock()
        chain.sort.return_value = chain
        chain.skip.return_value = chain
        chain.limit.return_value = chain
        chain.to_list = AsyncMock(return_value=[new_run, old_run])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.models.extraction_optimization_run.ExtractionOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            MockRun.find = MagicMock(return_value=chain)

            resp = await client.get(
                "/api/extractions/search-sets/ss-uuid-1/optimize",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert body["items"][0]["uuid"] == "run-new"
        assert body["items"][1]["uuid"] == "run-old"
        # Summary shape — trial list is replaced by a count, no per-trial detail
        assert body["items"][0]["num_trials"] == 2
        assert "trials" not in body["items"][0]
        # Sort/skip/limit chain was invoked
        chain.sort.assert_called_once_with("-started_at")

    @pytest.mark.asyncio
    async def test_list_optimization_history_honours_limit_and_skip(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        chain = MagicMock()
        chain.sort.return_value = chain
        chain.skip.return_value = chain
        chain.limit.return_value = chain
        chain.to_list = AsyncMock(return_value=[])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.models.extraction_optimization_run.ExtractionOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            MockRun.find = MagicMock(return_value=chain)

            resp = await client.get(
                "/api/extractions/search-sets/ss-uuid-1/optimize?limit=5&skip=10",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["limit"] == 5
        assert body["skip"] == 10
        chain.skip.assert_called_once_with(10)
        chain.limit.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_apply_optimization_writes_override_and_records_previous(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set(extraction_config_override={"model": "claude-haiku"})

        run = MagicMock()
        run.uuid = "opt-uuid-1"
        run.search_set_uuid = "ss-uuid-1"
        run.status = "completed"
        run.best_config = {"model": "claude-sonnet", "strategy": "two-pass"}
        run.previous_override = None
        run.save = AsyncMock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.models.extraction_optimization_run.ExtractionOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            MockRun.find_one = AsyncMock(return_value=run)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/optimize/opt-uuid-1/apply",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        # Override now has the optimizer's choice
        assert ss.extraction_config_override == {"model": "claude-sonnet", "strategy": "two-pass"}
        # Previous override preserved for revert
        assert run.previous_override == {"model": "claude-haiku"}

    # ------------------------------------------------------------------
    # Test-case generator (Phase 1B)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_generate_test_cases_returns_proposals(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        proposals_payload = {
            "proposals": [
                {
                    "proposal_id": "p1",
                    "label": "Award A",
                    "source_type": "document",
                    "document_uuid": "doc-1",
                    "source_text": "snapshot",
                    "expected_values": {"PI Name": "Smith"},
                    "auto_generated": True,
                },
            ],
            "errors": [],
        }

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.routers.extractions._authorize_documents", new=AsyncMock()),
            patch("app.services.extraction_test_case_generator.generate_proposals",
                  new=AsyncMock(return_value=proposals_payload)),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/generate-test-cases",
                json={"document_uuids": ["doc-1"], "coverage": "standard"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["proposals"]) == 1
        assert body["proposals"][0]["document_uuid"] == "doc-1"

    @pytest.mark.asyncio
    async def test_generate_test_cases_rejects_empty_document_list(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/generate-test-cases",
                json={"document_uuids": [], "coverage": "standard"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_approve_bulk_persists_test_cases(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        saved_tc = MagicMock()
        saved_tc.uuid = "tc-uuid-1"
        saved_tc.label = "Award A"
        saved_tc.source_type = "document"
        saved_tc.document_uuid = "doc-1"
        saved_tc.expected_values = {"PI Name": "Smith"}

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.services.extraction_test_case_generator.persist_approved_proposals",
                  new=AsyncMock(return_value=[saved_tc])),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/test-cases/approve-bulk",
                json={
                    "proposals": [
                        {
                            "label": "Award A",
                            "source_type": "document",
                            "document_uuid": "doc-1",
                            "source_text": "x",
                            "expected_values": {"PI Name": "Smith"},
                        },
                    ],
                },
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["test_cases"][0]["uuid"] == "tc-uuid-1"
        assert body["test_cases"][0]["expected_values"] == {"PI Name": "Smith"}

    @pytest.mark.asyncio
    async def test_apply_optimization_rejects_when_not_completed(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        run = MagicMock()
        run.uuid = "opt-uuid-1"
        run.search_set_uuid = "ss-uuid-1"
        run.status = "running"  # not completed
        run.best_config = {"model": "x"}

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.models.extraction_optimization_run.ExtractionOptimizationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            MockRun.find_one = AsyncMock(return_value=run)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/optimize/opt-uuid-1/apply",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert "running" in resp.json()["detail"]

    # ------------------------------------------------------------------
    # Reorder items
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_reorder_items_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.routers.extractions.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            mock_svc.reorder_items = AsyncMock(return_value=True)

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/reorder-items",
                json={"item_ids": ["id1", "id2", "id3"]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestExtractionBaselineProbe:
    """Cover the cheap no-settings probe used by the tuning wizard."""

    @pytest.mark.asyncio
    async def test_returns_404_when_search_set_missing(self, client):
        user = _make_user()
        cookies, headers = _auth()
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=None)
            resp = await client.post(
                "/api/extractions/search-sets/missing/baseline-probe",
                json={}, cookies=cookies, headers=headers,
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_invalid_sample_size(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/baseline-probe",
                json={"sample_size": 999},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_score_for_judgeable_cases(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()

        judgeable = MagicMock(uuid="tc1", expected_values={"PI Name": "Smith"})
        unjudgeable = MagicMock(uuid="tc2", expected_values={})

        find_result = MagicMock()
        find_result.to_list = AsyncMock(return_value=[judgeable, unjudgeable])

        sys_cfg = MagicMock()
        sys_cfg.model_dump = MagicMock(return_value={})

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.models.extraction_test_case.ExtractionTestCase.find", return_value=find_result),
            patch("app.services.config_service.get_user_model_name", new_callable=AsyncMock) as mock_model,
            patch("app.services.search_set_service.get_extraction_keys", new_callable=AsyncMock) as mock_keys,
            patch("app.services.search_set_service.get_extraction_field_metadata", new_callable=AsyncMock) as mock_meta,
            patch("app.models.system_config.SystemConfig.get_config", new_callable=AsyncMock) as mock_sys,
            patch("app.services.extraction_tuning_service._run_single_config", new_callable=AsyncMock) as mock_run,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            mock_model.return_value = "claude-haiku"
            mock_keys.return_value = ["PI Name"]
            mock_meta.return_value = []
            mock_sys.return_value = sys_cfg
            mock_run.return_value = {"score": 42.0, "judge_tokens": 1500}

            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/baseline-probe",
                json={"sample_size": 5},
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["no_settings_score"] == 0.42
        assert body["num_cases_judged"] == 1
        assert body["sample_case_ids"] == ["tc1"]
        assert body["tokens_used"] == 1500
        assert "duration_ms" in body

    @pytest.mark.asyncio
    async def test_returns_null_score_when_no_judgeable_cases(self, client):
        user = _make_user()
        cookies, headers = _auth()
        ss = _mock_search_set()
        find_result = MagicMock()
        find_result.to_list = AsyncMock(return_value=[])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.access_control") as mock_ac,
            patch("app.models.extraction_test_case.ExtractionTestCase.find", return_value=find_result),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)
            resp = await client.post(
                "/api/extractions/search-sets/ss-uuid-1/baseline-probe",
                json={}, cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["no_settings_score"] is None
        assert body["num_cases_judged"] == 0
        assert body["sample_case_ids"] == []
