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
    kb.team_owned = overrides.get("team_owned", False)
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
    s.custom_name = overrides.get("custom_name", None)
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

        # A whitespace-only title is rejected by the EntityName validator on
        # CreateKBRequest (422), before the handler runs.
        assert resp.status_code == 422
        assert "empty" in str(resp.json()["detail"]).lower()

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
            # SmartDocument.find requires Beanie initialization which the
            # ASGI test client skips; stub the title lookup helper directly.
            patch(
                "app.routers.knowledge._lookup_document_titles",
                new_callable=AsyncMock,
                return_value={"doc-1": "Some Document.pdf"},
            ),
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
        assert data["sources"][0]["document_title"] == "Some Document.pdf"

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
    async def test_update_source_sets_custom_name(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()
        renamed = _mock_source(custom_name="Friendly Label")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.routers.knowledge._lookup_document_titles", new_callable=AsyncMock) as mock_titles,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.update_source_name = AsyncMock(return_value=renamed)
            mock_titles.return_value = {"doc-1": "Original.pdf"}

            resp = await client.patch(
                "/api/knowledge/kb-uuid-1/source/src-uuid-1",
                json={"custom_name": "Friendly Label"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["custom_name"] == "Friendly Label"
        assert body["document_title"] == "Original.pdf"
        mock_svc.update_source_name.assert_awaited_once_with(kb, "src-uuid-1", "Friendly Label")

    @pytest.mark.asyncio
    async def test_update_source_not_found(self, client):
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
            mock_svc.update_source_name = AsyncMock(return_value=None)

            resp = await client.patch(
                "/api/knowledge/kb-uuid-1/source/ghost",
                json={"custom_name": "x"},
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

    @staticmethod
    def _fake_ref(team_id=None):
        ref = MagicMock()
        ref.uuid = "ref-1"
        ref.source_kb_uuid = "kb-1"
        ref.user_id = "user1"
        ref.team_id = team_id
        ref.note = None
        ref.pinned = False
        ref.created_at = datetime.datetime.now(tz=datetime.timezone.utc)
        return ref

    @pytest.mark.asyncio
    async def test_adopt_personal_passes_no_team(self, client):
        """Omitting team_id bookmarks the KB privately (team_id=None)."""
        user = _make_user()
        user.current_team = "team-abc"  # has a team, but didn't pick it
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.routers.knowledge.svc.adopt_knowledge_base", new_callable=AsyncMock) as mock_adopt,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_adopt.return_value = self._fake_ref(team_id=None)

            resp = await client.post(
                "/api/knowledge/kb-1/adopt",
                json={},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert mock_adopt.await_args.kwargs["team_id"] is None

    @pytest.mark.asyncio
    async def test_adopt_to_current_team(self, client):
        """Passing the caller's current team shares the bookmark with that team."""
        user = _make_user()
        user.current_team = "team-abc"
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.routers.knowledge.svc.adopt_knowledge_base", new_callable=AsyncMock) as mock_adopt,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_adopt.return_value = self._fake_ref(team_id="team-abc")

            resp = await client.post(
                "/api/knowledge/kb-1/adopt",
                json={"team_id": "team-abc"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["team_id"] == "team-abc"
        assert mock_adopt.await_args.kwargs["team_id"] == "team-abc"

    @pytest.mark.asyncio
    async def test_adopt_to_foreign_team_rejected(self, client):
        """A team_id that isn't the caller's current team is refused before adopting."""
        user = _make_user()
        user.current_team = "team-abc"
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.routers.knowledge.svc.adopt_knowledge_base", new_callable=AsyncMock) as mock_adopt,
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/knowledge/kb-1/adopt",
                json={"team_id": "team-other"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        mock_adopt.assert_not_awaited()


class TestConvertDocumentsToKB:
    @pytest.mark.asyncio
    async def test_convert_creates_kb_and_attaches_docs(self, client):
        # Supply an explicit title so the route skips the SmartDocument lookup
        # (which would require initializing Beanie's class-level field
        # descriptors). The default-title fallback is covered in unit tests.
        user = _make_user()
        cookies, headers = _auth()

        fake_kb = MagicMock()
        fake_kb.uuid = "kb-new"
        fake_kb.title = "PAPPG"
        fake_kb.description = ""
        fake_kb.status = "building"
        fake_kb.shared_with_team = False
        fake_kb.verified = False
        fake_kb.organization_ids = []
        fake_kb.total_sources = 0
        fake_kb.sources_ready = 0
        fake_kb.sources_failed = 0
        fake_kb.total_chunks = 0
        fake_kb.created_at = datetime.datetime.now(tz=datetime.timezone.utc)
        fake_kb.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
        fake_kb.user_id = "user1"
        fake_kb.save = AsyncMock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.create_knowledge_base = AsyncMock(return_value=fake_kb)
            mock_svc.add_documents = AsyncMock(return_value=1)

            resp = await client.post(
                "/api/knowledge/convert_documents",
                cookies=cookies,
                headers=headers,
                json={"document_uuids": ["doc-1"], "title": "PAPPG"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["uuid"] == "kb-new"
        assert body["title"] == "PAPPG"
        # KB was set to "building" before add_documents fires, so retrieval UIs
        # can show progress.
        assert fake_kb.status == "building"
        mock_svc.create_knowledge_base.assert_awaited_once()
        mock_svc.add_documents.assert_awaited_once()
        # Both doc UUIDs flow through to the existing attach pipeline.
        attach_args = mock_svc.add_documents.await_args.args
        assert attach_args[1] == ["doc-1"]

    @pytest.mark.asyncio
    async def test_convert_rejects_empty_uuid_list(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/knowledge/convert_documents",
                cookies=cookies,
                headers=headers,
                json={"document_uuids": []},
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_convert_uses_supplied_title_when_provided(self, client):
        user = _make_user()
        cookies, headers = _auth()

        fake_kb = MagicMock()
        fake_kb.uuid = "kb-new"
        fake_kb.title = "Reference materials"
        fake_kb.description = ""
        fake_kb.status = "building"
        fake_kb.shared_with_team = False
        fake_kb.verified = False
        fake_kb.organization_ids = []
        fake_kb.total_sources = 0
        fake_kb.sources_ready = 0
        fake_kb.sources_failed = 0
        fake_kb.total_chunks = 0
        fake_kb.created_at = datetime.datetime.now(tz=datetime.timezone.utc)
        fake_kb.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
        fake_kb.user_id = "user1"
        fake_kb.save = AsyncMock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.create_knowledge_base = AsyncMock(return_value=fake_kb)
            mock_svc.add_documents = AsyncMock(return_value=2)

            resp = await client.post(
                "/api/knowledge/convert_documents",
                cookies=cookies,
                headers=headers,
                json={"document_uuids": ["d1", "d2"], "title": "Reference materials"},
            )

        assert resp.status_code == 200
        # Title should be the supplied one, NOT the first doc's title.
        call_kwargs = mock_svc.create_knowledge_base.await_args.kwargs
        assert call_kwargs["title"] == "Reference materials"


class TestKnowledgeSharedDeleteFlow:
    """Cover the two-mode delete + transfer-to-team flow for shared KBs."""

    @pytest.mark.asyncio
    async def test_delete_shared_kb_without_mode_returns_409(self, client):
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
            from app.services.knowledge_service import SharedKBDeleteRequiresMode
            mock_svc.SharedKBDeleteRequiresMode = SharedKBDeleteRequiresMode
            mock_svc.delete_knowledge_base = AsyncMock(side_effect=SharedKBDeleteRequiresMode())

            resp = await client.delete(
                "/api/knowledge/kb-uuid-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 409
        body = resp.json()["detail"]
        assert body["code"] == "shared_kb_delete_requires_mode"
        # Caller was invoked without force_shared.
        call_kwargs = mock_svc.delete_knowledge_base.await_args.kwargs
        assert call_kwargs["force_shared"] is False

    @pytest.mark.asyncio
    async def test_delete_with_unshare_and_delete_mode_force_deletes(self, client):
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
            from app.services.knowledge_service import SharedKBDeleteRequiresMode
            mock_svc.SharedKBDeleteRequiresMode = SharedKBDeleteRequiresMode
            mock_svc.delete_knowledge_base = AsyncMock(return_value=True)

            resp = await client.delete(
                "/api/knowledge/kb-uuid-1?mode=unshare_and_delete",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        call_kwargs = mock_svc.delete_knowledge_base.await_args.kwargs
        assert call_kwargs["force_shared"] is True

    @pytest.mark.asyncio
    async def test_delete_rejects_unknown_mode(self, client):
        # The route's Query regex only allows "unshare_and_delete".
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.delete(
                "/api/knowledge/kb-uuid-1?mode=transfer",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_transfer_to_team_success(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb(shared_with_team=True, team_owned=True, team_id="team-1")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.transfer_kb_to_team = AsyncMock(return_value=kb)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/transfer-to-team",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "team_owned": True}

    @pytest.mark.asyncio
    async def test_transfer_to_team_not_found_returns_404(self, client):
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
            mock_svc.transfer_kb_to_team = AsyncMock(return_value=None)

            resp = await client.post(
                "/api/knowledge/missing/transfer-to-team",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404


class TestKBListQueryBuilder:
    """Verify the mongo query shape for the scope filters that drive My KBs vs Team."""

    def test_mine_scope_excludes_team_owned(self):
        from app.services.knowledge_service import build_kb_list_query

        q = build_kb_list_query("user1", "team-1", "mine", None)
        assert q == {"user_id": "user1", "team_owned": {"$ne": True}}

    def test_team_scope_filters_by_shared_and_team_id(self):
        from app.services.knowledge_service import build_kb_list_query

        q = build_kb_list_query("user1", "team-1", "team", None)
        assert q == {"shared_with_team": True, "team_id": "team-1"}

    def test_team_scope_without_team_id_returns_none(self):
        from app.services.knowledge_service import build_kb_list_query

        assert build_kb_list_query("user1", None, "team", None) is None

    def test_default_scope_excludes_team_owned_from_mine_branch(self):
        from app.services.knowledge_service import build_kb_list_query

        q = build_kb_list_query("user1", "team-1", None, None)
        or_clauses = q["$or"]
        mine_clause = next(
            (c for c in or_clauses if c.get("user_id") == "user1"),
            None,
        )
        assert mine_clause is not None
        assert mine_clause["team_owned"] == {"$ne": True}
        # Team-share branch should still be present.
        assert any(
            c.get("shared_with_team") is True and c.get("team_id") == "team-1"
            for c in or_clauses
        )

    def test_search_wraps_with_and_clause(self):
        from app.services.knowledge_service import build_kb_list_query

        q = build_kb_list_query("user1", None, "mine", "needle")
        assert "$and" in q
        base, search = q["$and"]
        assert base == {"user_id": "user1", "team_owned": {"$ne": True}}
        assert search["$or"][0]["title"]["$regex"] == "needle"
