"""Tier 2: previewing URLs before they enter a knowledge base, on real MongoDB.

The preview must run the same fetch, gates and crawl as an add while writing
nothing to the KB, and committing must index exactly the pages the user kept,
from the text they were shown.
"""

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.web_fetcher import WebFetchResult

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("INTEGRATION_MONGODB"),
        reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests",
    ),
    pytest.mark.integration_tier2,
    pytest.mark.asyncio(loop_scope="session"),
]

CONTENT = "Allowable costs under the award are described in this section. " * 60  # ~3,800 chars
NAV = "Home Topics Agencies Contact"


def _page(url: str, text: str, links: list[str] | None = None, title: str = "t") -> WebFetchResult:
    html = "".join(f'<a href="{link}">x</a>' for link in (links or []))
    return WebFetchResult(
        url=url, title=title, text=text, raw_html=f"<html>{html}</html>",
        used_browser=False, status_code=200, final_url=url,
    )


SITE = {
    "https://example.gov/policy": _page(
        "https://example.gov/policy", CONTENT,
        ["https://example.gov/rule-a", "https://example.gov/nav", "https://example.gov/rule-b"],
        title="Policy",
    ),
    "https://example.gov/rule-a": _page("https://example.gov/rule-a", CONTENT, title="Rule A"),
    "https://example.gov/nav": _page("https://example.gov/nav", NAV, ["https://example.gov/rule-c"]),
    "https://example.gov/rule-b": _page("https://example.gov/rule-b", CONTENT, title="Rule B"),
    "https://example.gov/rule-c": _page("https://example.gov/rule-c", CONTENT, title="Rule C"),
    "https://example.gov/blank": _page("https://example.gov/blank", "   "),
    "https://example.gov/short": _page("https://example.gov/short", "A short note about the policy."),
}


async def _fake_fetch(url, **_kwargs):
    if url == "https://example.gov/down":
        raise ValueError("Could not connect")
    return SITE[url]


async def _kb():
    from app.models.knowledge import KnowledgeBase

    kb = KnowledgeBase(uuid=uuid.uuid4().hex, title="Preview KB", user_id="alice")
    await kb.insert()
    return kb


def _fake_dm():
    dm = MagicMock()
    dm.add_to_kb = MagicMock(side_effect=lambda kb, sid, name, text, **kw: max(1, len(text) // 800))
    return dm


async def _preview(kb, urls, **crawl):
    from app.services import kb_url_preview

    preview = await kb_url_preview.start_preview(
        kb, "alice", urls,
        crawl_enabled=crawl.get("crawl_enabled", False),
        max_crawl_pages=crawl.get("max_crawl_pages", 5),
        allowed_domains="",
    )
    with patch("app.services.web_fetcher.fetch_url", AsyncMock(side_effect=_fake_fetch)):
        await kb_url_preview.run_preview(preview.uuid)
    preview = await kb_url_preview.get_preview(kb.uuid, preview.uuid, "alice")
    pages = await kb_url_preview.list_pages(preview)
    return preview, {p.url: p for p in pages}


class TestPreviewWritesNothingAndJudgesEachPage:
    async def test_each_seed_gets_a_verdict_and_the_kb_is_untouched(self, mongo_client):
        from app.models.knowledge import KnowledgeBaseSource
        from app.services.document_manager import count_chunks

        kb = await _kb()
        await KnowledgeBaseSource(
            knowledge_base_uuid=kb.uuid, source_type="url", url="https://example.gov/rule-b",
        ).insert()

        preview, pages = await _preview(kb, [
            "https://example.gov/policy",
            "example.gov/blank",            # normalized like an add
            "https://example.gov/short",
            "https://example.gov/down",
            "https://example.gov/rule-b",   # already in the KB
        ])

        assert preview.status == "ready"
        assert pages["https://example.gov/policy"].verdict == "good"
        assert pages["https://example.gov/policy"].chunk_count == count_chunks(CONTENT)
        assert pages["https://example.gov/blank"].verdict == "empty"
        assert pages["https://example.gov/short"].verdict == "low"
        assert "characters of content" in pages["https://example.gov/short"].reason
        assert pages["https://example.gov/down"].verdict == "error"
        assert pages["https://example.gov/rule-b"].verdict == "duplicate"
        # Nothing but the pre-existing row.
        assert await KnowledgeBaseSource.find(
            KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
        ).count() == 1

    async def test_crawl_matches_an_adds_crawl(self, mongo_client):
        kb = await _kb()
        _, pages = await _preview(
            kb, ["https://example.gov/policy"], crawl_enabled=True, max_crawl_pages=5,
        )
        # The navigation page is fetched for its links and shown as not addable;
        # the page behind it is reached through it.
        assert pages["https://example.gov/nav"].verdict == "navigation"
        for child in ("rule-a", "rule-b", "rule-c"):
            page = pages[f"https://example.gov/{child}"]
            assert page.verdict == "good"
            assert page.parent_url == "https://example.gov/policy"
        assert list(pages) == [
            "https://example.gov/policy",
            "https://example.gov/rule-a",
            "https://example.gov/nav",
            "https://example.gov/rule-b",
            "https://example.gov/rule-c",
        ]


class TestCommitIndexesWhatWasKept:
    async def test_only_kept_addable_pages_are_indexed_from_the_shown_text(self, mongo_client):
        from app.models.knowledge import KnowledgeBaseSource
        from app.services import kb_url_preview

        kb = await _kb()
        preview, pages = await _preview(
            kb, ["https://example.gov/policy", "https://example.gov/blank"],
            crawl_enabled=True, max_crawl_pages=5,
        )
        keep = [
            pages["https://example.gov/policy"].page_id,
            pages["https://example.gov/rule-a"].page_id,
            pages["https://example.gov/rule-c"].page_id,
            pages["https://example.gov/blank"].page_id,   # not addable: ignored
            pages["https://example.gov/nav"].page_id,     # not addable: ignored
        ]
        assert await kb_url_preview.claim_for_commit(preview)
        dm = _fake_dm()
        with patch("app.services.knowledge_service._get_dm", return_value=dm), \
             patch("app.services.web_fetcher.fetch_url", AsyncMock(side_effect=AssertionError("no refetch"))):
            added = await kb_url_preview.commit_preview(preview.uuid, keep)

        assert added == 3
        rows = {
            s.url: s for s in await KnowledgeBaseSource.find(
                KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
            ).to_list()
        }
        assert set(rows) == {
            "https://example.gov/policy", "https://example.gov/rule-a", "https://example.gov/rule-c",
        }
        seed = rows["https://example.gov/policy"]
        assert seed.status == "ready" and seed.crawl_enabled is True
        assert seed.crawled_urls == ["https://example.gov/rule-a", "https://example.gov/rule-c"]
        assert seed.skipped_urls == ["https://example.gov/nav"]
        assert rows["https://example.gov/rule-a"].parent_source_uuid == seed.uuid
        assert rows["https://example.gov/rule-a"].url_title == "Rule A"
        assert rows["https://example.gov/rule-a"].content == CONTENT
        indexed = {call.args[1]: call.args[3] for call in dm.add_to_kb.call_args_list}
        assert set(indexed.values()) == {CONTENT}
        assert (await kb_url_preview.get_preview(kb.uuid, preview.uuid, "alice")).status == "committed"

    async def test_a_preview_commits_once(self, mongo_client):
        from app.services import kb_url_preview

        kb = await _kb()
        preview, _ = await _preview(kb, ["https://example.gov/policy"])
        assert await kb_url_preview.claim_for_commit(preview) is True
        assert await kb_url_preview.claim_for_commit(preview) is False

    async def test_a_running_preview_cannot_be_claimed(self, mongo_client):
        from app.services import kb_url_preview

        kb = await _kb()
        preview = await kb_url_preview.start_preview(
            kb, "alice", ["https://example.gov/policy"],
            crawl_enabled=False, max_crawl_pages=5, allowed_domains="",
        )
        assert await kb_url_preview.claim_for_commit(preview) is False

    async def test_someone_elses_preview_is_not_found(self, mongo_client):
        from app.services import kb_url_preview

        kb = await _kb()
        preview, _ = await _preview(kb, ["https://example.gov/policy"])
        assert await kb_url_preview.get_preview(kb.uuid, preview.uuid, "mallory") is None
