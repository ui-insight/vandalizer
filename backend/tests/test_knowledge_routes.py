"""Authorization tests for knowledge-base routes."""

import datetime
import secrets
from types import SimpleNamespace
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
    user.token_version = 0
    user.demo_status = None
    user.api_token_hash = None
    user.api_token_created_at = None
    user.api_token_expires_at = None
    return user


def _auth(user_id="user1"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture(autouse=True)
def stub_team_access():
    """KB responses carry a per-user ``can_manage`` flag, computed from the
    caller's team memberships. Beanie isn't initialized under the ASGI test
    client, so the real ``TeamMembership`` query can't run — stub it to "no
    teams". Ownership/verified/admin branches of the gate still run for real.
    """
    from app.services.access_control import TeamAccessContext

    with patch(
        "app.routers.knowledge.access_control.get_team_access_context",
        new_callable=AsyncMock,
        return_value=TeamAccessContext(),
    ):
        yield


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
    s.source_reference = overrides.get("source_reference", None)
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
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.routers.knowledge.KBOptimizationRun") as MockOpt,
            patch("app.routers.knowledge.optimization_status_by_kb", AsyncMock(return_value={})),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.list_knowledge_bases = AsyncMock(return_value=([kb], 1))
            mock_svc.list_references = AsyncMock(return_value=[])
            mock_svc.get_kb_usage_map = AsyncMock(return_value={})
            MockRun.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockOpt.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

            resp = await client.get(
                "/api/knowledge/list/v2?scope=mine",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["uuid"] == "kb-uuid-1"
        assert data["items"][0]["last_used_at"] is None

    @pytest.mark.asyncio
    async def test_list_v2_includes_per_user_last_used_at(self, client):
        """A usage record for the requesting user surfaces as last_used_at."""
        user = _make_user()
        cookies, headers = _auth()
        used_kb = _mock_kb(uuid="kb-used")
        unused_kb = _mock_kb(uuid="kb-unused")
        used_at = datetime.datetime(2026, 7, 20, 12, 0, tzinfo=datetime.timezone.utc)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.routers.knowledge.KBOptimizationRun") as MockOpt,
            patch("app.routers.knowledge.optimization_status_by_kb", AsyncMock(return_value={})),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.list_knowledge_bases = AsyncMock(return_value=([used_kb, unused_kb], 2))
            mock_svc.list_references = AsyncMock(return_value=[])
            mock_svc.get_kb_usage_map = AsyncMock(return_value={"kb-used": used_at})
            MockRun.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockOpt.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

            resp = await client.get(
                "/api/knowledge/list/v2?scope=mine",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        by_uuid = {item["uuid"]: item for item in resp.json()["items"]}
        assert by_uuid["kb-used"]["last_used_at"] == used_at.isoformat()
        assert by_uuid["kb-unused"]["last_used_at"] is None
        # The usage lookup is scoped to the requesting user.
        mock_svc.get_kb_usage_map.assert_awaited_once_with("user1", ["kb-used", "kb-unused"])

    @pytest.mark.asyncio
    async def test_list_v2_reference_uses_catalog_display_name(self, client):
        """Adopted references show the catalog's display-name override.

        The Explore tab renders VerifiedItemMetadata.display_name over the
        KB's own title, so My KBs must do the same for adopted references or
        the KB appears under two different names.
        """
        user = _make_user()
        cookies, headers = _auth()
        source_kb = _mock_kb(uuid="kb-src", title="Raw KB Title", user_id="owner", verified=True)
        source_kb.id = "oid-123"
        ref = MagicMock()
        ref.uuid = "ref-1"
        ref.source_kb_uuid = "kb-src"
        meta = MagicMock()
        meta.item_id = "oid-123"
        meta.display_name = "Curated Catalog Name"

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.routers.knowledge.KBOptimizationRun") as MockOpt,
            patch("app.routers.knowledge.optimization_status_by_kb", AsyncMock(return_value={})),
            patch("app.routers.knowledge.VerifiedItemMetadata") as MockMeta,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.list_knowledge_bases = AsyncMock(return_value=([], 0))
            mock_svc.list_references = AsyncMock(return_value=[ref])
            mock_svc.resolve_reference = AsyncMock(return_value=source_kb)
            mock_svc.get_kb_usage_map = AsyncMock(return_value={})
            MockRun.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockOpt.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockMeta.find.return_value.to_list = AsyncMock(return_value=[meta])

            resp = await client.get(
                "/api/knowledge/list/v2?scope=mine",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["is_reference"] is True
        assert items[0]["title"] == "Curated Catalog Name"
        # Adopting a verified catalog KB doesn't confer manage rights on it.
        assert items[0]["can_manage"] is False
        # The catalog lookup is scoped to KB items for the adopted source KBs.
        MockMeta.find.assert_called_once_with({
            "item_kind": "knowledge_base",
            "item_id": {"$in": ["oid-123"]},
        })

    @pytest.mark.asyncio
    async def test_list_v2_reference_without_override_keeps_kb_title(self, client):
        """A reference to a catalog KB with no display_name keeps the KB title."""
        user = _make_user()
        cookies, headers = _auth()
        source_kb = _mock_kb(uuid="kb-src", title="Raw KB Title")
        source_kb.id = "oid-123"
        ref = MagicMock()
        ref.uuid = "ref-1"
        ref.source_kb_uuid = "kb-src"
        meta = MagicMock()
        meta.item_id = "oid-123"
        meta.display_name = None

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.routers.knowledge.KBOptimizationRun") as MockOpt,
            patch("app.routers.knowledge.optimization_status_by_kb", AsyncMock(return_value={})),
            patch("app.routers.knowledge.VerifiedItemMetadata") as MockMeta,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.list_knowledge_bases = AsyncMock(return_value=([], 0))
            mock_svc.list_references = AsyncMock(return_value=[ref])
            mock_svc.resolve_reference = AsyncMock(return_value=source_kb)
            mock_svc.get_kb_usage_map = AsyncMock(return_value={})
            MockRun.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockOpt.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockMeta.find.return_value.to_list = AsyncMock(return_value=[meta])

            resp = await client.get(
                "/api/knowledge/list/v2?scope=mine",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["title"] == "Raw KB Title"

    @pytest.mark.asyncio
    async def test_list_v2_broken_reference_surfaces_as_unavailable_stub(self, client):
        """A bookmark whose source KB no longer resolves (deleted, un-verified,
        retired from the catalog, or org-scoped away) renders as an
        'unavailable' stub with the reference uuid intact — not silently
        dropped — so the user sees what happened and can remove it."""
        user = _make_user()
        cookies, headers = _auth()
        ref = MagicMock()
        ref.uuid = "ref-broken"
        ref.source_kb_uuid = "kb-gone"
        ref.created_at = datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.routers.knowledge.KBOptimizationRun") as MockOpt,
            patch("app.routers.knowledge.optimization_status_by_kb", AsyncMock(return_value={})),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.list_knowledge_bases = AsyncMock(return_value=([], 0))
            mock_svc.list_references = AsyncMock(return_value=[ref])
            mock_svc.resolve_reference = AsyncMock(return_value=None)
            mock_svc.get_kb_usage_map = AsyncMock(return_value={})
            MockRun.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockOpt.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

            resp = await client.get(
                "/api/knowledge/list/v2?scope=mine",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        stub = items[0]
        assert stub["status"] == "unavailable"
        assert stub["is_reference"] is True
        assert stub["reference_uuid"] == "ref-broken"
        assert stub["source_kb_uuid"] == "kb-gone"
        assert stub["can_manage"] is False
        assert stub["title"] == "Knowledge base no longer available"
        # The stub counts toward the total like any other reference row.
        assert resp.json()["total"] == 1


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
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.routers.knowledge.KBOptimizationRun") as MockOpt,
            patch("app.routers.knowledge.optimization_status_by_kb", AsyncMock(return_value={})),
            # SmartDocument.find requires Beanie initialization which the
            # ASGI test client skips; stub the title lookup helper directly.
            patch(
                "app.routers.knowledge._resolve_document_titles",
                new_callable=AsyncMock,
                return_value={"doc-1": "Some Document.pdf"},
            ),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.get_kb_sources = AsyncMock(return_value=[src])
            mock_svc.resolve_document_titles = AsyncMock(return_value={})
            MockRun.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockOpt.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

            resp = await client.get("/api/knowledge/kb-uuid-1", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["uuid"] == "kb-uuid-1"
        assert len(data["sources"]) == 1
        assert data["sources"][0]["document_title"] == "Some Document.pdf"
        # The owner manages their own KB.
        assert data["can_manage"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "is_examiner,is_admin,expected",
        [
            (False, False, False),  # regular user: view only
            (True, False, True),    # examiners curate verified KBs
            (False, True, True),    # admins manage everything
        ],
    )
    async def test_get_detail_can_manage_on_foreign_verified_kb(
        self, client, is_examiner, is_admin, expected,
    ):
        """A verified catalog KB the user doesn't own is viewable by everyone but
        manageable only by an examiner or admin. The detail response must say so,
        so the UI can disable Add Documents / Add URLs instead of letting the user
        finish the flow and collect a 403.
        """
        user = _make_user("viewer")
        user.is_examiner = is_examiner
        user.is_admin = is_admin
        cookies, headers = _auth("viewer")
        kb = _mock_kb(user_id="someone-else", verified=True)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.routers.knowledge.KBOptimizationRun") as MockOpt,
            patch("app.routers.knowledge.optimization_status_by_kb", AsyncMock(return_value={})),
            patch(
                "app.routers.knowledge._resolve_document_titles",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.get_kb_sources = AsyncMock(return_value=[])
            mock_svc.resolve_document_titles = AsyncMock(return_value={})
            MockRun.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockOpt.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

            resp = await client.get("/api/knowledge/kb-uuid-1", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["can_manage"] is expected

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
            # The route gates manage access (via _require_manageable_kb) before
            # calling the service, so the manageable-KB lookup must resolve.
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
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
            # Neither manage nor view lookup resolves → genuinely missing → 404.
            mock_svc.get_knowledge_base = AsyncMock(return_value=None)
            mock_svc.update_knowledge_base = AsyncMock(return_value=None)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/update",
                json={"title": "Updated"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_forbidden_when_view_only(self, client):
        # A KB the user can view but not manage (e.g. a bookmarked verified
        # catalog KB) returns an actionable 403, not a misleading 404.
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb(user_id="someone-else", verified=True)

        async def fake_get_kb(uuid, user_arg, *, manage=False, **kw):
            return None if manage else kb

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(side_effect=fake_get_kb)
            mock_svc.update_knowledge_base = AsyncMock(return_value=None)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/update",
                json={"title": "Updated"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        # The service mutation must never run once the manage gate denies.
        mock_svc.update_knowledge_base.assert_not_called()

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
            patch("app.routers.knowledge._dispatch_kb_ingest") as mock_dispatch,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.register_documents = AsyncMock(return_value=["src-1", "src-2"])

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_documents",
                json={"document_uuids": ["doc-1", "doc-2"]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["added"] == 2
        # Embedding must not run inline — it is queued per source so the request
        # returns immediately and the UI can poll per-source status.
        mock_svc.add_documents.assert_not_called()
        mock_dispatch.assert_called_once_with(["src-1", "src-2"])

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
    async def test_add_urls_dispatches_background_task(self, client):
        """URL ingestion must be dispatched to a worker (not awaited inline) so
        slow fetches/crawls can't blow past the proxy timeout and 502."""
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.tasks.kb_validation_tasks.add_urls_task.delay") as mock_delay,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.partition_new_urls = AsyncMock(
                return_value=(["https://example.com", "https://example.org"], []),
            )

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_urls",
                json={"urls": ["https://example.com", "https://example.org"],
                      "crawl_enabled": True, "max_crawl_pages": 5},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        # Returns immediately with the count of URLs queued.
        assert resp.json() == {"ok": True, "added": 2, "skipped": 0, "skipped_urls": []}
        # Work was handed off to the worker, not run inline.
        mock_svc.add_urls.assert_not_called()
        mock_delay.assert_called_once()
        args, kwargs = mock_delay.call_args
        assert args[0] == kb.uuid
        assert args[1] == ["https://example.com", "https://example.org"]
        assert kwargs["crawl_enabled"] is True
        assert kwargs["max_crawl_pages"] == 5

    @pytest.mark.asyncio
    async def test_add_urls_reports_already_present_urls_and_skips_dispatch(self, client):
        """Re-submitting URLs the KB already holds is not a refresh. The worker
        would dedupe them silently; the response must say nothing was fetched
        (support ticket: "Added 2 URLs" on a no-op re-add)."""
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()
        kb.status = "ready"

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.tasks.kb_validation_tasks.add_urls_task.delay") as mock_delay,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.partition_new_urls = AsyncMock(
                return_value=([], ["https://www.uidaho.edu/policies/apm/45/13",
                                   "https://www.uidaho.edu/policies/apm/45/14"]),
            )

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_urls",
                json={"urls": ["https://www.uidaho.edu/policies/apm/45/13",
                               "https://www.uidaho.edu/policies/apm/45/14"]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "ok": True, "added": 0, "skipped": 2,
            "skipped_urls": ["https://www.uidaho.edu/policies/apm/45/13",
                             "https://www.uidaho.edu/policies/apm/45/14"],
        }
        mock_delay.assert_not_called()
        assert kb.status == "ready"  # nothing queued, so the KB is not left "building"

    @pytest.mark.asyncio
    async def test_add_urls_dispatches_only_the_new_urls(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.tasks.kb_validation_tasks.add_urls_task.delay") as mock_delay,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.partition_new_urls = AsyncMock(
                return_value=(["https://example.org/new"], ["https://example.org/old"]),
            )

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_urls",
                json={"urls": ["https://example.org/old", "https://example.org/new"]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["added"] == 1
        assert resp.json()["skipped_urls"] == ["https://example.org/old"]
        assert mock_delay.call_args.args[1] == ["https://example.org/new"]

    @pytest.mark.asyncio
    async def test_refresh_source_dispatches_worker_and_marks_pending(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()
        src = SimpleNamespace(
            uuid="src-1", source_type="url", url="https://www.uidaho.edu/policies/apm/45/14",
            status="ready", save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.models.knowledge.KnowledgeBaseSource.find_one", AsyncMock(return_value=src)),
            patch("app.tasks.kb_validation_tasks.refresh_url_source_task.delay") as mock_delay,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/source/src-1/refresh",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "status": "queued", "source_uuid": "src-1"}
        mock_delay.assert_called_once_with(kb.uuid, "src-1")
        assert src.status == "pending"
        assert kb.status == "building"
        # The refresh must not run inline — the service isn't touched here.
        mock_svc.refresh_url_source.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_source_rejects_document_sources(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()
        src = SimpleNamespace(
            uuid="src-1", source_type="document", url=None, document_uuid="doc-1",
            status="ready", save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.models.knowledge.KnowledgeBaseSource.find_one", AsyncMock(return_value=src)),
            patch("app.tasks.kb_validation_tasks.refresh_url_source_task.delay") as mock_delay,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/source/src-1/refresh",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        mock_delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_urls_empty_list_rejected(self, client):
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
                "/api/knowledge/kb-uuid-1/add_urls",
                json={"urls": []},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "No URLs provided"

    @pytest.mark.asyncio
    async def test_get_source_detail_document_returns_extracted_text(self, client):
        """Document sources don't cache content, so the inspector endpoint must
        fall back to the SmartDocument's full extracted raw_text (the text that
        was chunked into the KB) — not return empty / a single chunk."""
        from datetime import datetime, timezone
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        source = MagicMock()
        source.uuid = "src-1"
        source.source_type = "document"
        source.document_uuid = "doc-1"
        source.url = None
        source.url_title = None
        source.custom_name = None
        source.source_reference = None
        source.status = "ready"
        source.error_message = None
        source.chunk_count = 5
        source.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        source.content = None  # document sources never cache content on the source
        source.crawl_enabled = False
        source.max_crawl_pages = 5
        source.parent_source_uuid = None
        source.crawled_urls = None
        source.processed_at = None

        doc = MagicMock()
        doc.uuid = "doc-1"
        doc.title = "My Doc"
        doc.raw_text = "FULL EXTRACTED TEXT " * 50  # spans many chunks

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.models.knowledge.KnowledgeBaseSource") as MockKBSource,
            patch("app.models.document.SmartDocument") as MockDoc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            MockKBSource.find_one = AsyncMock(return_value=source)
            MockKBSource.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
            MockDoc.find_one = AsyncMock(return_value=doc)

            resp = await client.get(
                "/api/knowledge/kb-uuid-1/source/src-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == doc.raw_text
        assert body["document_title"] == "My Doc"

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
            patch("app.routers.knowledge._resolve_document_titles", new_callable=AsyncMock) as mock_titles,
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
            mock_svc.resolve_document_titles = AsyncMock(return_value={})

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
            patch("app.services.name_conflicts.kb_title_taken", new_callable=AsyncMock, return_value=False),
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
            patch("app.services.name_conflicts.kb_title_taken", new_callable=AsyncMock, return_value=False),
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

    # Every query is wrapped in an outer ``$and`` that also excludes implicit
    # (project-owned) KBs, which never surface in the normal lists. The helpers
    # below peel that wrapper off so each test can assert its scope clause.
    IMPLICIT_EXCLUSION = {"implicit": {"$ne": True}}

    def _unwrap_implicit(self, q: dict) -> dict:
        """Return the scope clause from inside the outer implicit-exclusion $and."""
        assert self.IMPLICIT_EXCLUSION in q["$and"]
        return next(c for c in q["$and"] if c != self.IMPLICIT_EXCLUSION)

    def test_mine_scope_excludes_team_owned(self):
        from app.services.knowledge_service import build_kb_list_query

        q = build_kb_list_query("user1", "team-1", "mine", None)
        assert self._unwrap_implicit(q) == {"user_id": "user1", "team_owned": {"$ne": True}}

    def test_team_scope_filters_by_shared_and_team_id(self):
        from app.services.knowledge_service import build_kb_list_query

        q = build_kb_list_query("user1", "team-1", "team", None)
        assert self._unwrap_implicit(q) == {"shared_with_team": True, "team_id": "team-1"}

    def test_team_scope_without_team_id_returns_none(self):
        from app.services.knowledge_service import build_kb_list_query

        assert build_kb_list_query("user1", None, "team", None) is None

    def test_default_scope_excludes_team_owned_from_mine_branch(self):
        from app.services.knowledge_service import build_kb_list_query

        q = build_kb_list_query("user1", "team-1", None, None)
        or_clauses = self._unwrap_implicit(q)["$or"]
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
        inner = self._unwrap_implicit(q)
        assert "$and" in inner
        base, search = inner["$and"]
        assert base == {"user_id": "user1", "team_owned": {"$ne": True}}
        assert search["$or"][0]["title"]["$regex"] == "needle"


class TestBaselineProbe:
    """Cover the cheap no-KB probe used by the tuning wizard."""

    @pytest.mark.asyncio
    async def test_returns_404_when_kb_missing(self, client):
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
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org_ancestry.return_value = []
            mock_get_kb.return_value = None
            resp = await client.post(
                "/api/knowledge/kb-1/baseline-probe", json={}, cookies=cookies, headers=headers,
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_invalid_sample_size(self, client):
        user = _make_user("manager")
        cookies, headers = _auth("manager")
        kb = MagicMock(uuid="kb-1")
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "manager", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
            ) as mock_org_ancestry,
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org_ancestry.return_value = []
            mock_get_kb.return_value = kb
            resp = await client.post(
                "/api/knowledge/kb-1/baseline-probe",
                json={"sample_size": 999},
                cookies=cookies,
                headers=headers,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_score_for_judgeable_queries(self, client):
        user = _make_user("manager")
        cookies, headers = _auth("manager")
        kb = MagicMock(uuid="kb-1")

        # Two test queries: one judgeable, one without expected_answer.
        judgeable = MagicMock(uuid="q1", query="What is X?", expected_answer="X is foo.")
        unjudgeable = MagicMock(uuid="q2", query="What about Y?", expected_answer=None)

        # Beanie's chained `find().to_list()` — mock the find result to return
        # an awaitable list when ``to_list`` is called.
        find_result = MagicMock()
        find_result.to_list = AsyncMock(return_value=[judgeable, unjudgeable])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "manager", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
            ) as mock_org_ancestry,
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
            patch("app.models.kb_test_query.KBTestQuery.find", return_value=find_result),
            patch(
                "app.services.workflow_validator._resolve_model_name",
                return_value="gpt-4o-mini",
            ),
            patch(
                "app.services.kb_validation_service.judge_baselines_only",
                new_callable=AsyncMock,
            ) as mock_judge,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org_ancestry.return_value = []
            mock_get_kb.return_value = kb
            mock_judge.return_value = {
                "avg_baseline_score": 0.72,
                "num_baselines_judged": 1,
                "tokens_used": 1500,
                "details": [],
            }

            resp = await client.post(
                "/api/knowledge/kb-1/baseline-probe",
                json={"sample_size": 5},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["no_kb_score"] == 0.72
        assert body["num_queries_judged"] == 1
        assert body["sample_query_ids"] == ["q1"]
        assert body["tokens_used"] == 1500
        assert "duration_ms" in body

    @pytest.mark.asyncio
    async def test_returns_null_score_when_no_judgeable_queries(self, client):
        user = _make_user("manager")
        cookies, headers = _auth("manager")
        kb = MagicMock(uuid="kb-1")
        find_result = MagicMock()
        find_result.to_list = AsyncMock(return_value=[])  # no queries at all

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "manager", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
            ) as mock_org_ancestry,
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
            patch("app.models.kb_test_query.KBTestQuery.find", return_value=find_result),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org_ancestry.return_value = []
            mock_get_kb.return_value = kb
            resp = await client.post(
                "/api/knowledge/kb-1/baseline-probe", json={}, cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["no_kb_score"] is None
        assert body["num_queries_judged"] == 0
        assert body["sample_query_ids"] == []


def _make_source(uuid="s1", source_type="document"):
    s = MagicMock()
    s.uuid = uuid
    s.source_type = source_type
    s.document_uuid = "doc1" if source_type == "document" else None
    s.url = None if source_type == "document" else "https://www.uidaho.edu/apm/45"
    s.url_title = None
    s.custom_name = "My label"
    s.source_reference = "APM Ch.45"
    s.status = "ready"
    s.error_message = None
    s.chunk_count = 3
    s.created_at = datetime.datetime(2026, 6, 9, tzinfo=datetime.timezone.utc)
    return s


class TestUpdateSourceFields:
    @pytest.mark.asyncio
    async def test_source_reference_only_does_not_clear_custom_name(self, client):
        """A PATCH carrying only source_reference must route to
        set_source_reference and NOT call update_source_name (which would
        otherwise clear the custom_name)."""
        user = _make_user("manager")
        cookies, headers = _auth("manager")
        kb = MagicMock()
        kb.uuid = "kb-1"
        updated = _make_source()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "manager", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock,
            ) as mock_org_ancestry,
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
            patch("app.routers.knowledge.svc.set_source_reference", new_callable=AsyncMock) as mock_set_ref,
            patch("app.routers.knowledge.svc.update_source_name", new_callable=AsyncMock) as mock_rename,
            patch("app.routers.knowledge._resolve_document_titles", new_callable=AsyncMock) as mock_titles,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org_ancestry.return_value = []
            mock_get_kb.return_value = kb
            mock_set_ref.return_value = updated
            mock_titles.return_value = {}

            resp = await client.patch(
                "/api/knowledge/kb-1/source/s1",
                json={"source_reference": "APM Ch.45"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        mock_set_ref.assert_awaited_once()
        mock_rename.assert_not_awaited()  # custom_name left untouched
        assert resp.json()["source_reference"] == "APM Ch.45"


class TestAdminKBInventory:
    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, client):
        user = _make_user("plebe")
        user.is_admin = False
        user.is_staff = False  # MagicMock attrs are truthy by default — pin it
        cookies, headers = _auth("plebe")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "plebe", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.services.knowledge_service.admin_list_all_knowledge_bases",
                new_callable=AsyncMock,
            ) as mock_list,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/admin/knowledge-bases", cookies=cookies, headers=headers)

        assert resp.status_code == 403
        mock_list.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_admin_lists_kbs(self, client):
        user = _make_user("boss")
        user.is_admin = True
        cookies, headers = _auth("boss")
        kb = MagicMock()
        kb.uuid = "kb-1"
        kb.title = "APM Chapter 45"
        kb.status = "ready"
        kb.verified = True
        kb.tags = ["v2026-06"]
        kb.total_sources = 2
        kb.total_chunks = 40
        kb.user_id = "boss"
        kb.team_id = None
        kb.created_at = datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc)
        kb.updated_at = datetime.datetime(2026, 6, 9, tzinfo=datetime.timezone.utc)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "boss", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.services.knowledge_service.admin_list_all_knowledge_bases",
                new_callable=AsyncMock,
            ) as mock_list,
            patch("app.routers.admin.User.find") as mock_user_find,
            patch("app.routers.admin.Team.find") as mock_team_find,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_list.return_value = [kb]
            mock_user_find.return_value.to_list = AsyncMock(return_value=[])
            mock_team_find.return_value.to_list = AsyncMock(return_value=[])

            resp = await client.get("/api/admin/knowledge-bases", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["knowledge_bases"][0]["title"] == "APM Chapter 45"
        assert body["knowledge_bases"][0]["tags"] == ["v2026-06"]


class TestKnowledgeReingest:
    @pytest.mark.asyncio
    async def test_reingest_dispatches_task_and_sets_building(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.tasks.knowledge_base_tasks.kb_reingest") as mock_task,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_task.delay = MagicMock(return_value=MagicMock(id="task-123"))

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/reingest",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"task_id": "task-123", "status": "queued"}
        assert kb.status == "building"
        kb.save.assert_awaited()
        mock_task.delay.assert_called_once_with("kb-uuid-1")

    @pytest.mark.asyncio
    async def test_reingest_view_only_user_gets_403(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb(user_id="someone-else", verified=True)

        async def gated_lookup(uuid, u, manage=False, **kw):
            return None if manage else kb

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(side_effect=gated_lookup)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/reingest",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403


class TestTestQueryImport:
    """Bulk CSV/XLSX import of validation test queries."""

    @staticmethod
    def _payload(csv_text, filename="set.csv"):
        import base64

        return {
            "filename": filename,
            "content_base64": base64.b64encode(csv_text.encode("utf-8")).decode(),
        }

    @staticmethod
    def _existing_query(**overrides):
        # Beanie Documents can't be constructed without an initialized
        # collection, so stand-ins carry the exact attrs the endpoint touches
        # (explicit values — a bare MagicMock's auto-attrs are truthy and
        # would satisfy the external_id lookup by accident).
        from types import SimpleNamespace

        defaults = {
            "knowledge_base_uuid": "kb-uuid-1",
            "query": "Old question?",
            "expected_answer": None,
            "expected_answer_contains": None,
            "expected_source_labels": [],
            "category": None,
            "notes": None,
            "external_id": None,
            "updated_at": None,
            "user_id": "user1",
        }
        defaults.update(overrides)
        q = SimpleNamespace(**defaults)
        q.save = AsyncMock()
        return q

    @staticmethod
    def _fake_query_cls(existing):
        """Stand-in for the KBTestQuery class: find() returns ``existing``,
        constructing an instance records it and gives it an AsyncMock insert."""
        from types import SimpleNamespace

        created = []

        def construct(**kwargs):
            inst = SimpleNamespace(uuid="new-uuid", **kwargs)
            inst.insert = AsyncMock()
            created.append(inst)
            return inst

        cls = MagicMock(side_effect=construct)
        find_result = MagicMock()
        find_result.to_list = AsyncMock(return_value=existing)
        cls.find.return_value = find_result
        return cls, created

    @pytest.mark.asyncio
    async def test_import_creates_updates_and_skips(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()
        # One row matched by stable ID (updated in place), one existing
        # ID-less question repeated verbatim in the file (skipped).
        existing_by_id = self._existing_query(external_id="EXIST-1")
        existing_dup = self._existing_query(query="Duplicate question?")

        csv_text = (
            "Question,Expected Answer,Category,Source,Notes,ID\n"
            "New question?,New answer,factual,Doc A,fresh,NEW-1\n"
            "Updated question?,Better answer,summary,Doc B,,EXIST-1\n"
            "Duplicate question?,,,,,\n"
        )

        fake_cls, created = self._fake_query_cls([existing_by_id, existing_dup])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.models.kb_test_query.KBTestQuery", fake_cls),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.get_kb_sources = AsyncMock(return_value=[])
            mock_svc.resolve_document_titles = AsyncMock(return_value={})

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/test-queries/import",
                json=self._payload(csv_text),
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] == 1
        assert body["updated"] == 1
        assert body["skipped"] == 1
        assert body["total_rows"] == 3
        assert body["errors"] == []
        assert len(created) == 1
        assert created[0].query == "New question?"
        assert created[0].external_id == "NEW-1"
        created[0].insert.assert_awaited_once()
        existing_by_id.save.assert_awaited_once()
        existing_dup.save.assert_not_awaited()
        # The ID-matched row was rewritten from the spreadsheet.
        assert existing_by_id.query == "Updated question?"
        assert existing_by_id.expected_answer == "Better answer"
        assert existing_by_id.category == "summary"
        assert existing_by_id.expected_source_labels == ["Doc B"]
        assert existing_by_id.updated_at is not None

    @pytest.mark.asyncio
    async def test_import_reports_row_errors_without_failing(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        csv_text = "Question,Answer\nQ1,A1\n,orphan answer\n"
        fake_cls, created = self._fake_query_cls([])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.models.kb_test_query.KBTestQuery", fake_cls),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.get_kb_sources = AsyncMock(return_value=[])
            mock_svc.resolve_document_titles = AsyncMock(return_value={})

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/test-queries/import",
                json=self._payload(csv_text),
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] == 1
        assert body["errors"] == [{"row": 3, "error": "Missing question"}]

    @pytest.mark.asyncio
    async def test_import_bad_file_type_is_400(self, client):
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
            mock_svc.get_kb_sources = AsyncMock(return_value=[])
            mock_svc.resolve_document_titles = AsyncMock(return_value={})

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/test-queries/import",
                json=self._payload("Question\nQ1\n", filename="set.txt"),
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_import_invalid_base64_is_400(self, client):
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
            mock_svc.get_kb_sources = AsyncMock(return_value=[])
            mock_svc.resolve_document_titles = AsyncMock(return_value={})

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/test-queries/import",
                json={"filename": "set.csv", "content_base64": "%%% not base64 %%%"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_import_view_only_user_gets_403(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb(user_id="someone-else", verified=True)

        async def gated_lookup(uuid, u, manage=False, **kw):
            return None if manage else kb

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(side_effect=gated_lookup)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/test-queries/import",
                json=self._payload("Question\nQ1\n"),
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403


    @pytest.mark.asyncio
    async def test_document_backed_sources_are_matched_by_their_title(self, client):
        """Resolving a name as ``custom_name or url_title or url`` leaves a
        document-backed source with an empty name — those two fields are only
        set for URL sources — so it was dropped and every correct label in a
        document KB was reported as matching nothing, inviting the user to
        clear labels that were right. Ingestion writes the document's *title*,
        and that title is what the validation run scores against.
        """
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()
        fake_cls, _created = self._fake_query_cls([])

        from types import SimpleNamespace
        doc_source = SimpleNamespace(
            custom_name=None,
            source_type="document",
            document_uuid="doc-1",
            url_title=None,
            url=None,
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.models.kb_test_query.KBTestQuery", fake_cls),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.get_kb_sources = AsyncMock(return_value=[doc_source])
            mock_svc.resolve_document_titles = AsyncMock(
                return_value={"doc-1": "NSF PAPPG 24-1.pdf"},
            )

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/test-queries/import",
                json=self._payload("Question,Source\nQ1,NSF PAPPG 24-1.pdf\n"),
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["unmatched_source_labels"] == [], (
            "a label naming an uploaded document by its title was reported as "
            "matching no source"
        )

    @pytest.mark.asyncio
    async def test_import_warns_on_source_labels_matching_no_source(self, client):
        """A label that matches no source scores 0 retrieval precision forever.

        This is how the 2 CFR 200 set silently lost its precision metric: an
        imported taxonomy ("Subpart E-i — Cost Principles | §§200.400-200.419")
        named nothing in the KB, so every question carrying it was scored as a
        retrieval miss no matter how good the retrieval was.
        """
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        csv_text = (
            "Question,Source\n"
            "Q1,Subpart E-i — Cost Principles | §§200.400-200.419\n"
            "Q2,Subpart E-i — Cost Principles | §§200.400-200.419\n"
            "Q3,Subpart E—Cost Principles\n"
        )
        fake_cls, _created = self._fake_query_cls([])

        from types import SimpleNamespace
        real_source = SimpleNamespace(
            custom_name=None,
            source_type="url",
            document_uuid=None,
            url_title="Subpart E—Cost Principles",
            url="https://example.gov/subpart-e",
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.models.kb_test_query.KBTestQuery", fake_cls),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.get_kb_sources = AsyncMock(return_value=[real_source])
            mock_svc.resolve_document_titles = AsyncMock(return_value={})

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/test-queries/import",
                json=self._payload(csv_text),
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] == 3          # every row still imports
        unmatched = body["unmatched_source_labels"]
        assert len(unmatched) == 1
        assert unmatched[0]["label"] == "Subpart E-i — Cost Principles | §§200.400-200.419"
        assert unmatched[0]["questions"] == 2  # the label that does match is not reported

    @pytest.mark.asyncio
    async def test_import_succeeds_when_label_check_fails(self, client):
        """The questions are already written when the check runs, so a failure
        there must not report the import as failed."""
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()
        fake_cls, _created = self._fake_query_cls([])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.models.kb_test_query.KBTestQuery", fake_cls),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.get_kb_sources = AsyncMock(side_effect=RuntimeError("mongo down"))
            mock_svc.resolve_document_titles = AsyncMock(return_value={})

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/test-queries/import",
                json=self._payload("Question,Source\nQ1,Doc A\n"),
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["created"] == 1
        assert resp.json()["unmatched_source_labels"] == []


class TestTestQueryBulkDelete:
    """POST /{uuid}/test-queries/bulk-delete — prune a large test set."""

    @staticmethod
    def _recording_find(deleted_count=0):
        """Stand-in for KBTestQuery.find that records the Mongo filter it was
        handed and reports ``deleted_count`` from .delete()."""
        calls = []

        def fake_find(*args, **kwargs):
            calls.append(args[0] if args else kwargs)
            result = MagicMock()
            result.delete = AsyncMock(return_value=SimpleNamespace(deleted_count=deleted_count))
            return result

        return fake_find, calls

    @pytest.mark.asyncio
    async def test_bulk_delete_scopes_to_kb_and_dedupes(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()
        fake_find, calls = self._recording_find(deleted_count=2)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.models.kb_test_query.KBTestQuery.find", side_effect=fake_find),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/test-queries/bulk-delete",
                json={"query_uuids": ["q-1", "q-2", "q-1", "", 7]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"deleted": 2}
        # Blanks and non-strings dropped, duplicates collapsed, KB scope applied.
        assert calls == [{"knowledge_base_uuid": "kb-uuid-1", "uuid": {"$in": ["q-1", "q-2"]}}]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body", [None, "not json", "[]", '"x"'])
    async def test_bulk_delete_malformed_body_is_a_client_error(self, client, body):
        """A body that is empty, not JSON, or JSON that is not an object used
        to raise inside the handler and surface as a 500 — reading it with
        ``request.json()`` throws, and ``.get`` throws again on a JSON array.
        """
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
                "/api/knowledge/kb-uuid-1/test-queries/bulk-delete",
                content=body,
                headers={**headers, "Content-Type": "application/json"},
                cookies=cookies,
            )

        assert resp.status_code < 500, (
            f"malformed body {body!r} produced {resp.status_code}"
        )
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_bulk_delete_rejects_empty_selection(self, client):
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
                "/api/knowledge/kb-uuid-1/test-queries/bulk-delete",
                json={"query_uuids": []},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_delete_caps_batch_size(self, client):
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
                "/api/knowledge/kb-uuid-1/test-queries/bulk-delete",
                json={"query_uuids": [f"q-{i}" for i in range(2001)]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert "2000" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_bulk_delete_view_only_user_gets_403(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb(user_id="someone-else", verified=True)

        async def gated_lookup(uuid, u, manage=False, **kw):
            return None if manage else kb

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(side_effect=gated_lookup)

            resp = await client.post(
                "/api/knowledge/kb-uuid-1/test-queries/bulk-delete",
                json={"query_uuids": ["q-1"]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403


class TestValidationRunExport:
    """GET /{uuid}/validation-runs/{run_uuid}/export — per-query results."""

    def _kb(self):
        kb = MagicMock()
        kb.uuid = "kb-1"
        kb.title = "NSF PAPPG"
        kb.tags = []
        kb.total_sources = 1
        kb.total_chunks = 10
        kb.resource_config = {"seed_id": "kb-nsf"}
        kb.rag_config_override = None
        return kb

    def _vr(self, snapshot):
        vr = MagicMock()
        vr.uuid = "run-abcdef123456"
        vr.score = 80.0
        vr.score_breakdown = {}
        vr.created_at = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)
        vr.result_snapshot = snapshot
        return vr

    def _full_snapshot(self):
        return {
            "mode": "judge",
            "judge_model": "claude-x",
            "retrieval_precision": {
                "details": [
                    {
                        "query": "Q1?",
                        "query_uuid": "q-1",
                        "precision": 1.0,
                        "actual_answer": "A1.",
                        "judge": {"score": 0.9, "verdict": "PASS", "reasoning": "ok"},
                    },
                ],
            },
        }

    @pytest.mark.asyncio
    async def test_export_csv_happy_path(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")
        kb = self._kb()
        vr = self._vr(self._full_snapshot())
        cfg = MagicMock()
        cfg.catalog_version = "1.3.1"
        tq_query = MagicMock()
        tq_query.to_list = AsyncMock(return_value=[])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock, return_value=[],
            ),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.models.kb_test_query.KBTestQuery.find", return_value=tq_query),
            patch("app.models.system_config.SystemConfig.get_config", new_callable=AsyncMock, return_value=cfg),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=vr)

            resp = await client.get(
                "/api/knowledge/kb-1/validation-runs/run-abcdef123456/export",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert 'filename="NSF_PAPPG-validation-20260801-000000-run-abcd.csv"' in (
            resp.headers["content-disposition"]
        )
        lines = resp.text.splitlines()
        assert lines[0].startswith("run_uuid,run_created_at,kb_uuid,kb_title")
        assert "Q1?" in lines[1]
        assert "PASS" in lines[1]

    @pytest.mark.asyncio
    async def test_export_json_carries_format_tag(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")
        kb = self._kb()
        vr = self._vr(self._full_snapshot())
        cfg = MagicMock()
        cfg.catalog_version = None
        tq_query = MagicMock()
        tq_query.to_list = AsyncMock(return_value=[])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock, return_value=[],
            ),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.models.kb_test_query.KBTestQuery.find", return_value=tq_query),
            patch("app.models.system_config.SystemConfig.get_config", new_callable=AsyncMock, return_value=cfg),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=vr)

            resp = await client.get(
                "/api/knowledge/kb-1/validation-runs/run-abcdef123456/export?format=json",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["format"] == "vandalizer.kb-validation-results.v1"
        assert body["validation_run"]["judge_model"] == "claude-x"
        assert len(body["results"]) == 1

    @pytest.mark.asyncio
    async def test_export_optimizer_apply_row_is_400(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")
        kb = self._kb()
        # Apply rows persist a lightweight snapshot with no per-query details.
        vr = self._vr({"source": "optimizer_apply", "score": 90.0})

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock, return_value=[],
            ),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=kb),
            patch("app.routers.knowledge.ValidationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock(return_value=vr)

            resp = await client.get(
                "/api/knowledge/kb-1/validation-runs/run-abcdef123456/export",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert "optimizer apply" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_foreign_kb_is_404(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.knowledge.organization_service.get_user_org_ancestry",
                new_callable=AsyncMock, return_value=[],
            ),
            patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock, return_value=None),
            patch("app.routers.knowledge.ValidationRun") as MockRun,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockRun.find_one = AsyncMock()

            resp = await client.get(
                "/api/knowledge/kb-1/validation-runs/run-abcdef123456/export",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        MockRun.find_one.assert_not_awaited()


class TestKnowledgeOptimizationStatus:
    """The Optimized chip's full story rides on the v2 list and the detail."""

    @pytest.mark.asyncio
    async def test_list_v2_carries_optimization_status(self, client):
        from app.services.kb_optimization_status import OptimizationStatus

        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()
        status = OptimizationStatus(
            state="stale",
            applied_at=datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc),
            applied_run_uuid="run-1",
            last_run_at=datetime.datetime(2026, 8, 1, 13, 0, tzinfo=datetime.timezone.utc),
            last_run_uuid="run-1",
            tuned_keys=["k"],
            stale=True,
            stale_reasons=["Sources changed since the settings were tuned: 5 added (had 50 sources)."],
            sources_at_run=50, sources_added=5,
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.routers.knowledge.KBOptimizationRun") as MockOpt,
            patch(
                "app.routers.knowledge.optimization_status_by_kb",
                AsyncMock(return_value={"kb-uuid-1": status}),
            ) as loader,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.list_knowledge_bases = AsyncMock(return_value=([kb], 1))
            mock_svc.list_references = AsyncMock(return_value=[])
            mock_svc.get_kb_usage_map = AsyncMock(return_value={})
            MockRun.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockOpt.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

            resp = await client.get(
                "/api/knowledge/list/v2?scope=mine", cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        loader.assert_awaited_once_with([kb])
        item = resp.json()["items"][0]
        assert item["optimization"] == {
            "state": "stale",
            "applied_at": "2026-08-01T12:00:00+00:00",
            "applied_run_uuid": "run-1",
            "last_run_at": "2026-08-01T13:00:00+00:00",
            "last_run_uuid": "run-1",
            "tuned_keys": ["k"],
            "stale": True,
            "stale_reasons": ["Sources changed since the settings were tuned: 5 added (had 50 sources)."],
            "sources_at_run": 50, "sources_added": 5, "sources_removed": 0,
            "queries_at_run": 0, "queries_added": 0, "queries_removed": 0, "queries_edited": 0,
        }

    @pytest.mark.asyncio
    async def test_list_v2_omits_optimization_when_there_is_nothing_to_say(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kb = _mock_kb()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.routers.knowledge.KBOptimizationRun") as MockOpt,
            patch("app.routers.knowledge.optimization_status_by_kb", AsyncMock(return_value={})),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.list_knowledge_bases = AsyncMock(return_value=([kb], 1))
            mock_svc.list_references = AsyncMock(return_value=[])
            mock_svc.get_kb_usage_map = AsyncMock(return_value={})
            MockRun.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockOpt.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

            resp = await client.get(
                "/api/knowledge/list/v2?scope=mine", cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["items"][0]["optimization"] is None
