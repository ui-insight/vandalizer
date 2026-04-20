"""Authorization tests for knowledge-base routes."""

import datetime
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="user1"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.demo_status = None
    user.api_token_hash = None
    user.api_token_created_at = None
    user.api_token_expires_at = None
    return user


def _auth(user_id="user1"):
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


class TestKnowledgeSuggestionAuth:
    @pytest.mark.asyncio
    async def test_create_suggestion_rejects_foreign_kb(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
            ) as mock_org_ancestry,
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
            patch("app.routers.knowledge.svc.create_suggestion", new_callable=AsyncMock) as mock_create,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org_ancestry.return_value = []
            mock_get_kb.return_value = None

            resp = await client.post(
                "/api/knowledge/kb-1/suggestions",
                json={"suggestion_type": "general", "note": "Please improve this"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Knowledge base not found"
        mock_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_review_suggestion_rejects_foreign_nested_uuid(self, client):
        user = _make_user("manager")
        cookies, headers = _auth("manager")
        kb = MagicMock()
        kb.uuid = "kb-1"

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "manager", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
            ) as mock_org_ancestry,
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
            patch("app.models.kb_suggestion.KBSuggestion.find_one", new_callable=AsyncMock) as mock_find_suggestion,
            patch("app.routers.knowledge.svc.review_suggestion", new_callable=AsyncMock) as mock_review,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org_ancestry.return_value = []
            mock_get_kb.return_value = kb
            mock_find_suggestion.return_value = None

            resp = await client.patch(
                "/api/knowledge/kb-1/suggestions/foreign-suggestion",
                json={"accept": True},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Suggestion not found"
        mock_review.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_review_suggestion_passes_bound_kb_and_suggestion(self, client):
        user = _make_user("manager")
        cookies, headers = _auth("manager")
        kb = MagicMock()
        kb.uuid = "kb-1"
        suggestion = MagicMock()
        suggestion.uuid = "suggestion-1"
        reviewed = MagicMock()
        reviewed.uuid = "suggestion-1"
        reviewed.status = "accepted"
        reviewed.reviewed_at = datetime.datetime.now(datetime.timezone.utc)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "manager", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
            ) as mock_org_ancestry,
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
            patch("app.models.kb_suggestion.KBSuggestion.find_one", new_callable=AsyncMock) as mock_find_suggestion,
            patch("app.routers.knowledge.svc.review_suggestion", new_callable=AsyncMock) as mock_review,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org_ancestry.return_value = []
            mock_get_kb.return_value = kb
            mock_find_suggestion.return_value = suggestion
            mock_review.return_value = reviewed

            resp = await client.patch(
                "/api/knowledge/kb-1/suggestions/suggestion-1",
                json={"accept": True},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        mock_review.assert_awaited_once_with(kb, suggestion, user, True)


class TestKnowledgeCloneAuth:
    @pytest.mark.asyncio
    async def test_clone_rejects_foreign_kb(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
            ) as mock_org_ancestry,
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
            patch("app.routers.knowledge.svc.clone_knowledge_base", new_callable=AsyncMock) as mock_clone,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org_ancestry.return_value = []
            mock_get_kb.return_value = None

            resp = await client.post(
                "/api/knowledge/kb-1/clone",
                json={"title": "Copy"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Knowledge base not found"
        mock_clone.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clone_uses_authorized_kb(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")
        source_kb = MagicMock()
        source_kb.uuid = "kb-1"
        cloned_kb = MagicMock()
        cloned_kb.uuid = "kb-clone"
        cloned_kb.title = "Copy"
        cloned_kb.description = ""
        cloned_kb.status = "ready"
        cloned_kb.shared_with_team = False
        cloned_kb.verified = False
        cloned_kb.organization_ids = []
        cloned_kb.total_sources = 0
        cloned_kb.sources_ready = 0
        cloned_kb.sources_failed = 0
        cloned_kb.total_chunks = 0
        cloned_kb.created_at = None
        cloned_kb.updated_at = None
        cloned_kb.user_id = "viewer"

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
            ) as mock_org_ancestry,
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
            patch("app.routers.knowledge.svc.clone_knowledge_base", new_callable=AsyncMock) as mock_clone,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org_ancestry.return_value = []
            mock_get_kb.return_value = source_kb
            mock_clone.return_value = cloned_kb

            resp = await client.post(
                "/api/knowledge/kb-1/clone",
                json={"title": "Copy"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["uuid"] == "kb-clone"
        mock_clone.assert_awaited_once_with(source_kb, user, new_title="Copy")


# ---------------------------------------------------------------------------
# Coverage expansion - CRUD, list, status, share, add docs, remove source
# ---------------------------------------------------------------------------


def _mock_kb(**overrides):
    from datetime import datetime, timezone

    kb = MagicMock()
    kb.uuid = overrides.get("uuid", "kb-uuid-1")
    kb.title = overrides.get("title", "Test KB")
    kb.description = overrides.get("description", "A test knowledge base")
    kb.status = overrides.get("status", "ready")
    kb.shared_with_team = overrides.get("shared_with_team", False)
    kb.verified = overrides.get("verified", False)
    kb.organization_ids = overrides.get("organization_ids", [])
    kb.total_sources = overrides.get("total_sources", 2)
    kb.sources_ready = overrides.get("sources_ready", 2)
    kb.sources_failed = overrides.get("sources_failed", 0)
    kb.total_chunks = overrides.get("total_chunks", 100)
    kb.created_at = overrides.get("created_at", datetime(2025, 1, 1, tzinfo=timezone.utc))
    kb.updated_at = overrides.get("updated_at", datetime(2025, 1, 2, tzinfo=timezone.utc))
    kb.user_id = overrides.get("user_id", "user1")
    kb.team_id = overrides.get("team_id", None)
    kb.save = AsyncMock()
    return kb


def _mock_source(**overrides):
    from datetime import datetime, timezone

    s = MagicMock()
    s.uuid = overrides.get("uuid", "src-uuid-1")
    s.source_type = overrides.get("source_type", "document")
    s.document_uuid = overrides.get("document_uuid", "doc-1")
    s.url = overrides.get("url", None)
    s.url_title = overrides.get("url_title", None)
    s.status = overrides.get("status", "ready")
    s.error_message = overrides.get("error_message", None)
    s.chunk_count = overrides.get("chunk_count", 50)
    s.created_at = overrides.get("created_at", datetime(2025, 1, 1, tzinfo=timezone.utc))
    return s


class TestKnowledgeListEndpoints:
    """Cover GET /list and GET /list/v2."""

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client):
        resp = await client.get("/api/knowledge/list")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_legacy_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.list_knowledge_bases_flat = AsyncMock(return_value=[kb])

            resp = await client.get("/api/knowledge/list", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["uuid"] == "kb-uuid-1"
        assert data[0]["title"] == "Test KB"

    @pytest.mark.asyncio
    async def test_list_v2_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.list_knowledge_bases = AsyncMock(return_value=([kb], 1))
            mock_svc.list_references = AsyncMock(return_value=[])

            resp = await client.get(
                "/api/knowledge/list/v2?scope=mine",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["uuid"] == "kb-uuid-1"


class TestKnowledgeCRUD:
    """Cover create, get-detail, update, delete, share endpoints."""

    @pytest.mark.asyncio
    async def test_create_requires_auth(self, client):
        csrf = secrets.token_urlsafe(32)
        resp = await client.post(
            "/api/knowledge/create",
            json={"title": "KB"},
            cookies={"csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.create_knowledge_base = AsyncMock(return_value=kb)

            resp = await client.post(
                "/api/knowledge/create",
                json={"title": "My KB"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["uuid"] == "kb-uuid-1"

    @pytest.mark.asyncio
    async def test_create_empty_title_rejected(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/knowledge/create",
                json={"title": "   "},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Title is required"

    @pytest.mark.asyncio
    async def test_get_detail_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()
        src = _mock_source()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.get_kb_sources = AsyncMock(return_value=[src])

            resp = await client.get("/api/knowledge/kb-uuid-1", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["uuid"] == "kb-uuid-1"
        assert len(data["sources"]) == 1

    @pytest.mark.asyncio
    async def test_get_detail_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=None)

            resp = await client.get("/api/knowledge/nonexistent", cookies=cookies, headers=headers)

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Knowledge base not found"

    @pytest.mark.asyncio
    async def test_update_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.update_knowledge_base = AsyncMock(return_value=kb)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/update",
                json={"title": "Updated"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_update_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.update_knowledge_base = AsyncMock(return_value=None)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/update",
                json={"title": "Updated"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_success(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.delete_knowledge_base = AsyncMock(return_value=True)

            resp = await client.delete("/api/knowledge/kb-uuid-1", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.delete_knowledge_base = AsyncMock(return_value=False)

            resp = await client.delete("/api/knowledge/kb-uuid-1", cookies=cookies, headers=headers)

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_share_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb(shared_with_team=True)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.share_with_team = AsyncMock(return_value=kb)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/share",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["shared_with_team"] is True

    @pytest.mark.asyncio
    async def test_share_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.share_with_team = AsyncMock(return_value=None)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/share",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404


class TestKnowledgeDocSources:
    """Cover add_documents, add_urls, remove_source, status endpoints."""

    @pytest.mark.asyncio
    async def test_add_documents_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.add_documents = AsyncMock(return_value=2)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_documents",
                json={"document_uuids": ["doc-1", "doc-2"]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["added"] == 2

    @pytest.mark.asyncio
    async def test_add_documents_empty_list_rejected(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_documents",
                json={"document_uuids": []},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "No documents provided"

    @pytest.mark.asyncio
    async def test_add_documents_kb_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=None)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_documents",
                json={"document_uuids": ["doc-1"]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_source_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.remove_source = AsyncMock(return_value=True)

            resp = await client.delete(
                "/api/knowledge/kb-uuid-1/source/src-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_remove_source_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.remove_source = AsyncMock(return_value=False)

            resp = await client.delete(
                "/api/knowledge/kb-uuid-1/source/src-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_status_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()
        src = _mock_source()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.get_kb_sources = AsyncMock(return_value=[src])

            resp = await client.get(
                "/api/knowledge/kb-uuid-1/status",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["uuid"] == "kb-uuid-1"
        assert data["status"] == "ready"
        assert len(data["sources"]) == 1

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/knowledge/kb-uuid-1/status",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404


class TestKnowledgeReference:
    """Cover remove_reference endpoint."""

    @pytest.mark.asyncio
    async def test_remove_reference_success(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.remove_reference = AsyncMock(return_value=True)

            resp = await client.delete(
                "/api/knowledge/reference/ref-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_remove_reference_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.remove_reference = AsyncMock(return_value=False)

            resp = await client.delete(
                "/api/knowledge/reference/ref-nonexistent",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
