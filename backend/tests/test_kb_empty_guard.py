"""Tests for the empty-knowledge-base guard on export and clone.

A KB with no sources kept both actions live: Export downloaded a file whose
``sources`` list was empty — nothing anyone could import or share — and Clone
produced a second empty KB. Chat and the validation family already refused.
These tests pin the refusal at the service and at the route. Mocked models —
no DB.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.services.knowledge_service import (
    clone_knowledge_base,
    export_knowledge_base,
    kb_has_sources,
    require_kb_sources,
)
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


def _make_kb(uuid="kb-1", title="Export Control Regulations"):
    kb = MagicMock()
    kb.uuid = uuid
    kb.title = title
    kb.description = ""
    kb.tags = []
    kb.status = "empty"
    kb.shared_with_team = False
    kb.verified = False
    kb.organization_ids = []
    kb.total_sources = 0
    kb.sources_ready = 0
    kb.sources_failed = 0
    kb.total_chunks = 0
    kb.created_at = None
    kb.updated_at = None
    kb.user_id = "user1"
    return kb


def _url_source(uuid="src-1"):
    """A URL source with cached content — the export path that needs no
    SmartDocument lookup."""
    src = MagicMock()
    src.uuid = uuid
    src.source_type = "url"
    src.document_uuid = None
    src.url = "https://example.edu/policy"
    src.url_title = "Policy"
    src.custom_name = None
    src.content = "Export control policy text."
    src.crawl_enabled = False
    src.max_crawl_pages = 1
    src.parent_source_uuid = None
    src.crawled_urls = None
    return src


def _stub_sources(rows):
    """Patch the KnowledgeBaseSource queries the guard and export both make."""
    cls = MagicMock()
    query = cls.find.return_value
    query.count = AsyncMock(return_value=len(rows))
    query.sort.return_value.to_list = AsyncMock(return_value=list(rows))
    return patch("app.services.knowledge_service.KnowledgeBaseSource", cls)


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kb_has_sources_counts_rows_rather_than_trusting_the_counter():
    """``total_sources`` is denormalized; a stale one must not open the gate."""
    kb = _make_kb()
    kb.total_sources = 7  # stale counter, no rows behind it

    with _stub_sources([]):
        assert await kb_has_sources(kb) is False

    with _stub_sources([_url_source()]):
        assert await kb_has_sources(kb) is True


@pytest.mark.asyncio
async def test_require_kb_sources_names_the_action():
    kb = _make_kb()
    with _stub_sources([_url_source()]):
        await require_kb_sources(kb, "exporting")  # does not raise

    with _stub_sources([]):
        with pytest.raises(
            ValueError,
            match="no sources yet — add at least one source before exporting it",
        ):
            await require_kb_sources(kb, "exporting")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_rejects_kb_with_no_sources():
    kb = _make_kb()
    doc_cls = MagicMock()
    doc_cls.find_one = AsyncMock()

    with _stub_sources([]), patch("app.services.knowledge_service.SmartDocument", doc_cls):
        with pytest.raises(ValueError, match="no sources yet"):
            await export_knowledge_base(kb)

    doc_cls.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_export_still_serializes_a_kb_with_a_source():
    kb = _make_kb()

    with _stub_sources([_url_source()]):
        payload = await export_knowledge_base(kb)

    assert payload["title"] == "Export Control Regulations"
    assert len(payload["sources"]) == 1
    assert payload["sources"][0]["url"] == "https://example.edu/policy"


@pytest.mark.asyncio
async def test_export_route_returns_400_for_an_empty_kb(client):
    user = _make_user()
    cookies, headers = _auth()
    kb = _make_kb()

    with (
        patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
        patch("app.dependencies.User") as MockUser,
        patch(
            "app.routers.knowledge.organization_service.get_user_org_ancestry",
            new_callable=AsyncMock,
        ) as mock_org_ancestry,
        patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
        _stub_sources([]),
    ):
        MockUser.find_one = AsyncMock(return_value=user)
        mock_org_ancestry.return_value = []
        mock_get_kb.return_value = kb

        resp = await client.get(
            "/api/knowledge/kb-1/export",
            cookies=cookies,
            headers=headers,
        )

    assert resp.status_code == 400
    assert "no sources yet" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_export_route_still_downloads_a_kb_with_a_source(client):
    user = _make_user()
    cookies, headers = _auth()
    kb = _make_kb()

    with (
        patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
        patch("app.dependencies.User") as MockUser,
        patch(
            "app.routers.knowledge.organization_service.get_user_org_ancestry",
            new_callable=AsyncMock,
        ) as mock_org_ancestry,
        patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
        _stub_sources([_url_source()]),
    ):
        MockUser.find_one = AsyncMock(return_value=user)
        mock_org_ancestry.return_value = []
        mock_get_kb.return_value = kb

        resp = await client.get(
            "/api/knowledge/kb-1/export",
            cookies=cookies,
            headers=headers,
        )

    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    assert len(resp.json()["sources"]) == 1


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clone_rejects_kb_with_no_sources_before_creating_anything():
    kb = _make_kb()
    user = _make_user()
    name_conflicts = MagicMock()
    name_conflicts.next_available_name = AsyncMock()
    kb_cls = MagicMock()

    with (
        _stub_sources([]),
        patch("app.services.knowledge_service.name_conflicts", name_conflicts),
        patch("app.services.knowledge_service.KnowledgeBase", kb_cls),
    ):
        with pytest.raises(ValueError, match="no sources yet — add at least one source before cloning it"):
            await clone_knowledge_base(kb, user)

    # No half-made clone left behind: the guard runs before the title check.
    name_conflicts.next_available_name.assert_not_awaited()
    kb_cls.assert_not_called()


@pytest.mark.asyncio
async def test_clone_route_returns_400_for_an_empty_kb(client):
    user = _make_user()
    cookies, headers = _auth()
    kb = _make_kb()
    name_conflicts = MagicMock()
    name_conflicts.next_available_name = AsyncMock()

    with (
        patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
        patch("app.dependencies.User") as MockUser,
        patch(
            "app.routers.knowledge.organization_service.get_user_org_ancestry",
            new_callable=AsyncMock,
        ) as mock_org_ancestry,
        patch("app.routers.knowledge.svc.get_knowledge_base", new_callable=AsyncMock) as mock_get_kb,
        patch("app.services.knowledge_service.name_conflicts", name_conflicts),
        _stub_sources([]),
    ):
        MockUser.find_one = AsyncMock(return_value=user)
        mock_org_ancestry.return_value = []
        mock_get_kb.return_value = kb

        resp = await client.post(
            "/api/knowledge/kb-1/clone",
            json={},
            cookies=cookies,
            headers=headers,
        )

    assert resp.status_code == 400
    assert "no sources yet" in resp.json()["detail"]
    name_conflicts.next_available_name.assert_not_awaited()
