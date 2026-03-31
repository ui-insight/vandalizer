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
    ss.tuning_result = overrides.get("tuning_result", None)
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
            patch("app.routers.extractions._attach_quality", new_callable=AsyncMock, return_value={
                "quality_score": None, "quality_tier": None,
                "last_validated_at": None, "validation_run_count": 0,
            }),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.list_search_sets = AsyncMock(return_value=[ss])

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
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_authorized_search_set = AsyncMock(return_value=ss)

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
        ss = _mock_search_set(cross_field_rules=[{"rule": "a > b"}])

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
        assert resp.json()["rules"] == [{"rule": "a > b"}]

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
                json={"rules": [{"rule": "x == y"}]},
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
