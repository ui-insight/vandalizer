"""eCFR regulations come from the catalog's bundled text, never eCFR's shell.

Support ticket (FCOI, prod, 2026-10-13): the FCOI knowledge base's only source,
42 CFR 50 Subpart F, held one chunk: eCFR's 434-character search-box help,
which ecfr.gov serves an automated fetch in place of the regulation. Every
fetch check passed it, an in-app refresh fetched the live page even though the
catalog bundles the regulation, and the repair script rated the source
healthy. The KB then answered "the source lacks it" for the subpart's own
definitions.
"""

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import bundled_sources, knowledge_service
from app.services.web_fetcher import WebFetchResult
from app.utils.bot_challenge import looks_like_boilerplate_only, looks_like_search_shell

FCOI_URL = "https://www.ecfr.gov/current/title-42/chapter-I/subchapter-D/part-50/subpart-F"

# Byte for byte what ecfr.gov returned to the app's fetcher, and what prod's
# FCOI source held (content_hash 2a0047870648fc51…).
ECFR_SHELL = (
    "Navigate by entering citations or phrases (eg: 1 CFR 1.1 49 CFR 172.101 "
    "Organization and Purpose 1/1.1 Regulation Y FAR).\n"
    "Choosing an item from citations and headings will bring you directly to the "
    "content. Choosing an item from full text search results will bring you to "
    "those results. Pressing enter in the search box will also bring you to "
    "search results.\n"
    "Background and more details are available in the Search & Navigation guide."
)


def test_fixture_is_the_text_prod_held():
    assert hashlib.sha256(ECFR_SHELL.encode()).hexdigest().startswith("2a0047870648fc51")


class TestSearchShell:
    def test_ecfrs_search_help_is_a_shell(self):
        assert looks_like_search_shell(ECFR_SHELL)
        assert looks_like_boilerplate_only(ECFR_SHELL)

    def test_the_fetch_gate_refuses_it(self):
        result = WebFetchResult(
            url=FCOI_URL, title="42 CFR Part 50 Subpart F", text=ECFR_SHELL,
            raw_html="<html/>", used_browser=False, status_code=200,
        )
        assert knowledge_service._reject_fetched_page(result)

    def test_a_short_real_section_under_the_same_help_is_kept(self):
        # A full eCFR page renders the help above the regulation; one short
        # section of it must not be refused for that.
        section = (
            "§ 50.603 Definitions. Investigator means the project director or principal "
            "Investigator and any other person, regardless of title or position, who is "
            "responsible for the design, conduct, or reporting of research funded by the "
            "PHS, or proposed for such funding, which may include, for example, "
            "collaborators or consultants. "
        ) * 2
        assert not looks_like_search_shell(ECFR_SHELL + "\n" + section)
        assert not looks_like_boilerplate_only(ECFR_SHELL + "\n" + section)

    def test_one_help_sentence_alone_is_not_enough(self):
        assert not looks_like_search_shell("Navigate by entering citations or phrases.")


class TestBundledSource:
    def test_the_fcoi_url_has_the_regulation_bundled(self):
        text, title = bundled_sources.bundled_source(FCOI_URL)
        assert len(text) > 30_000 and "Investigator" in text
        assert title and "Promoting Objectivity in Research" in title

    def test_a_trailing_slash_still_matches(self):
        assert bundled_sources.bundled_source(FCOI_URL + "/") is not None

    def test_other_urls_have_none(self):
        assert bundled_sources.bundled_source("https://www.nsf.gov/pappg") is None
        assert bundled_sources.bundled_source(None) is None

    def test_falls_short_of_bundle(self):
        full, _ = bundled_sources.bundled_source(FCOI_URL)
        assert bundled_sources.falls_short_of_bundle(ECFR_SHELL, FCOI_URL)
        assert bundled_sources.falls_short_of_bundle(full[:5000], FCOI_URL)
        assert not bundled_sources.falls_short_of_bundle(full, FCOI_URL)
        assert not bundled_sources.falls_short_of_bundle("short", "https://www.nsf.gov/pappg")


class TestFetchSourcePage:
    @pytest.mark.asyncio
    async def test_a_bundled_url_never_reaches_the_live_site(self):
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(side_effect=AssertionError("fetched"))):
            result = await knowledge_service.fetch_source_page(FCOI_URL)
        full, title = bundled_sources.bundled_source(FCOI_URL)
        assert result.text == full and result.title == title
        assert knowledge_service._reject_fetched_page(result) is None

    @pytest.mark.asyncio
    async def test_any_other_url_is_fetched(self):
        live = WebFetchResult(
            url="https://x.test", title="t", text="body", raw_html="<html/>",
            used_browser=False, status_code=200,
        )
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=live)) as fetch:
            assert await knowledge_service.fetch_source_page("https://x.test") is live
        fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_refreshing_the_fcoi_source_restores_the_regulation():
    """The prod case: a source holding the shell, refreshed. The live page
    would hand back the same shell; the bundle is used instead."""
    src = SimpleNamespace(
        uuid="src-fcoi", knowledge_base_uuid="kb-fcoi", source_type="url", url=FCOI_URL,
        url_title="42 CFR Part 50 Subpart F -- Promoting Objectivity in Research",
        custom_name=None, content=ECFR_SHELL, status="pending", error_message=None,
        chunk_count=1, truncated=False, processed_at=None, last_collapsed_hash=None,
        parent_source_uuid=None, content_hash=hashlib.sha256(ECFR_SHELL.encode()).hexdigest(),
    )
    src.save = AsyncMock()
    dm = MagicMock()
    dm.replace_kb_source.return_value = 42
    shell = WebFetchResult(
        url=FCOI_URL, title="42 CFR Part 50 Subpart F", text=ECFR_SHELL,
        raw_html="<html/>", used_browser=False, status_code=200,
    )
    with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=shell)) as fetch, \
         patch.object(knowledge_service, "_get_dm", return_value=dm), \
         patch("app.services.kb_source_versions.ensure_baseline", AsyncMock()), \
         patch("app.services.kb_source_versions.record_current", AsyncMock()):
        reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-fcoi"))

    full, _ = bundled_sources.bundled_source(FCOI_URL)
    assert reason is None
    fetch.assert_not_awaited()
    assert dm.replace_kb_source.call_args.args[3] == full
    assert src.content == full and src.chunk_count == 42 and src.status == "ready"


def test_the_repair_script_now_flags_the_source():
    from scripts.repair_gov_kb_sources import _is_broken

    full, _ = bundled_sources.bundled_source(FCOI_URL)

    def source(content):
        return SimpleNamespace(status="ready", content=content, url=FCOI_URL, error_message=None)

    assert _is_broken(source(ECFR_SHELL))
    assert "far less text" in (_is_broken(source(full[:5000])) or "")
    assert _is_broken(source(full)) is None
