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
    user.api_token = None
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
