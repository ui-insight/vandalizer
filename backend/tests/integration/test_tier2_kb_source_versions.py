"""Tier 2: dated version history of KB URL sources, against a real MongoDB.

Support ticket: a scheduled refresh that found a revised page replaced the
source's text and discarded the old one, so nobody could show what the
source said when an earlier answer was produced. A refresh now keeps every
distinct text as a dated version. These run the real refresh path and the
real routes; only the network fetch and the vector index are stubbed.
"""

import datetime
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.web_fetcher import WebFetchResult
from tests.integration.test_tier2_services import _route_auth

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("INTEGRATION_MONGODB"),
        reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests",
    ),
    pytest.mark.integration_tier2,
    pytest.mark.asyncio(loop_scope="session"),
]

URL = "https://www.uidaho.edu/policies/apm/45/14"
TEXT_A = "APM 45.14. Prior approval is required for rebudgeting over $25,000. " * 4
TEXT_B = "APM 45.14. Prior approval is required for rebudgeting over $50,000. " * 4
TEXT_C = "APM 45.14. Prior approval is required for any rebudgeting at all. " * 4
UTC = datetime.timezone.utc


def _fetched(text: str) -> WebFetchResult:
    return WebFetchResult(
        url=URL, title="APM 45.14", text=text, raw_html="<html/>",
        used_browser=False, status_code=200,
    )


async def _seed_legacy_source(owner: str = "kbowner"):
    """A KB whose URL source was ingested before version history existed:
    text and currency dates, no version rows."""
    from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
    from app.models.user import User
    from app.utils import kb_source_currency as currency

    await User(user_id=owner, email=f"{owner}@example.com", name=owner).insert()
    kb = KnowledgeBase(title="OSP policies", user_id=owner)
    await kb.insert()
    ingested = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    source = KnowledgeBaseSource(
        knowledge_base_uuid=kb.uuid, source_type="url", url=URL, url_title="APM 45.14",
        content=TEXT_A, status="ready", chunk_count=3,
        **currency.ingestion_stamp(TEXT_A, now=ingested),
    )
    await source.insert()
    return kb, source


async def _refresh(kb, source, text: str):
    from app.models.knowledge import KnowledgeBaseSource
    from app.services import knowledge_service

    dm = MagicMock()
    dm.replace_kb_source.return_value = 4
    fresh = await KnowledgeBaseSource.find_one({"uuid": source.uuid})
    with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_fetched(text))), \
         patch.object(knowledge_service, "_get_dm", return_value=dm):
        reason = await knowledge_service.refresh_url_source(fresh, kb)
    assert reason is None
    return fresh


async def _versions(source_uuid: str):
    from app.services import kb_source_versions

    return await kb_source_versions.list_versions(source_uuid)


class TestRefreshKeepsHistory:
    async def test_a_changed_page_keeps_the_old_text_as_a_dated_version(self, mongo_client):
        kb, source = await _seed_legacy_source()

        await _refresh(kb, source, TEXT_B)

        newest, oldest = await _versions(source.uuid)
        # The text the source held before history existed is version 1,
        # dated from the source's own currency fields — not from today.
        assert (oldest.number, oldest.origin, oldest.content) == (1, "baseline", TEXT_A)
        assert oldest.captured_at.replace(tzinfo=UTC) == datetime.datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
        assert oldest.superseded_at is not None
        assert (newest.number, newest.origin, newest.content) == (2, "refresh", TEXT_B)
        assert newest.superseded_at is None
        # Contiguous: v1 ends exactly when v2 took effect.
        assert oldest.superseded_at == newest.in_effect_from

    async def test_an_unchanged_page_confirms_the_current_version_without_adding_one(self, mongo_client):
        kb, source = await _seed_legacy_source()
        await _refresh(kb, source, TEXT_B)

        await _refresh(kb, source, TEXT_B)

        versions = await _versions(source.uuid)
        assert [v.number for v in versions] == [2, 1]
        assert versions[0].last_confirmed_at is not None

    async def test_an_unchanged_refresh_of_a_legacy_source_starts_its_history(self, mongo_client):
        kb, source = await _seed_legacy_source()

        await _refresh(kb, source, TEXT_A)

        (only,) = await _versions(source.uuid)
        assert (only.number, only.origin, only.content) == (1, "baseline", TEXT_A)
        assert only.last_confirmed_at is not None

    async def test_a_failed_refresh_records_nothing_new(self, mongo_client):
        from app.models.knowledge import KnowledgeBaseSource
        from app.services import knowledge_service

        kb, source = await _seed_legacy_source()
        await _refresh(kb, source, TEXT_B)
        fresh = await KnowledgeBaseSource.find_one({"uuid": source.uuid})

        with patch("app.services.web_fetcher.fetch_url", AsyncMock(side_effect=RuntimeError("boom"))):
            assert await knowledge_service.refresh_url_source(fresh, kb)

        assert [v.number for v in await _versions(source.uuid)] == [2, 1]

    async def test_in_effect_at_finds_the_version_answers_came_from(self, mongo_client):
        from app.services import kb_source_versions

        kb, source = await _seed_legacy_source()
        await _refresh(kb, source, TEXT_B)
        await _refresh(kb, source, TEXT_C)
        versions = await _versions(source.uuid)
        v3, v2, v1 = versions

        july = datetime.datetime(2026, 7, 1, tzinfo=UTC)
        assert kb_source_versions.version_in_effect_at(versions, july).uuid == v1.uuid
        between = v2.in_effect_from.replace(tzinfo=UTC) + (
            v3.in_effect_from - v2.in_effect_from
        ) / 2
        assert kb_source_versions.version_in_effect_at(versions, between).uuid == v2.uuid
        assert kb_source_versions.version_in_effect_at(
            versions, datetime.datetime.now(tz=UTC),
        ).uuid == v3.uuid
        # Before the source's text was first indexed there was nothing to answer from.
        assert kb_source_versions.version_in_effect_at(
            versions, datetime.datetime(2026, 1, 1, tzinfo=UTC),
        ) is None

    async def test_removing_the_source_removes_its_history(self, mongo_client):
        from app.services import knowledge_service

        kb, source = await _seed_legacy_source()
        await _refresh(kb, source, TEXT_B)

        with patch.object(knowledge_service, "_get_dm", return_value=MagicMock()):
            assert await knowledge_service.remove_source(kb, source.uuid)

        assert await _versions(source.uuid) == []


@pytest.fixture
async def t2_client(mongo_client):
    """App client on the test DB. ``get_settings`` is replaced through
    ``dependency_overrides``: routes hold the function itself in their
    ``Depends``, so patching the module attribute would not reach them."""
    from httpx import ASGITransport, AsyncClient

    from app.config import Settings
    from app.dependencies import get_settings

    settings = Settings(jwt_secret_key="test-secret-key", environment="development")
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        app.dependency_overrides[get_settings] = lambda: settings
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.pop(get_settings, None)


class TestVersionRoutes:
    async def test_list_view_and_compare(self, t2_client):
        kb, source = await _seed_legacy_source()
        await _refresh(kb, source, TEXT_B)
        cookies, headers = _route_auth("kbowner")
        base = f"/api/knowledge/{kb.uuid}/source/{source.uuid}/versions"

        resp = await t2_client.get(base, params={"at": "2026-07-01T00:00:00Z"}, cookies=cookies, headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [v["number"] for v in body["versions"]] == [2, 1]
        assert body["versions"][0]["is_current"] is True
        v2, v1 = body["versions"]
        assert body["in_effect_version_uuid"] == v1["uuid"]
        # Dates go out with an offset, so a browser cannot read them as local time.
        assert v1["captured_at"].endswith("+00:00")

        resp = await t2_client.get(f"{base}/{v1['uuid']}", cookies=cookies, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["content"] == TEXT_A

        resp = await t2_client.get(
            f"{base}/compare", params={"base": v1["uuid"], "target": v2["uuid"]},
            cookies=cookies, headers=headers,
        )
        assert resp.status_code == 200, resp.text
        diff = resp.json()
        assert diff["identical"] is False
        assert diff["added"] == 1 and diff["removed"] == 1
        assert {"op": "+", "text": TEXT_B} in diff["lines"]

    async def test_another_users_kb_is_not_readable(self, t2_client):
        from app.models.user import User

        kb, source = await _seed_legacy_source()
        await User(user_id="stranger", email="stranger@example.com", name="stranger").insert()
        cookies, headers = _route_auth("stranger")

        resp = await t2_client.get(
            f"/api/knowledge/{kb.uuid}/source/{source.uuid}/versions", cookies=cookies, headers=headers,
        )
        assert resp.status_code == 404
