"""Reading a site's sitemap so the user can pick which pages to add.

Feature request: bulk URL import, including a site's own page map as a clean,
complete alternative to blind crawling. Every hop is checked against the
outbound URL rules, the XML is parsed safely, and sizes are bounded.
"""

import gzip
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import sitemap_reader as sr

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def urlset(*urls, lastmod=None):
    entries = "".join(
        f"<url><loc>{u}</loc>{f'<lastmod>{lastmod}</lastmod>' if lastmod else ''}</url>" for u in urls
    )
    return f'<?xml version="1.0"?><urlset {NS}>{entries}</urlset>'.encode()


def index(*sitemaps):
    entries = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in sitemaps)
    return f'<?xml version="1.0"?><sitemapindex {NS}>{entries}</sitemapindex>'.encode()


class TestParse:
    def test_urlset_pages_with_lastmod(self):
        kind, pages, children = sr.parse_sitemap(urlset("https://a.gov/x", "https://a.gov/y", lastmod="2026-09-01"))
        assert kind == "urlset" and children == []
        assert [(p.url, p.lastmod) for p in pages] == [("https://a.gov/x", "2026-09-01"), ("https://a.gov/y", "2026-09-01")]

    def test_index_lists_child_sitemaps(self):
        kind, pages, children = sr.parse_sitemap(index("https://a.gov/s1.xml", "https://a.gov/s2.xml"))
        assert kind == "sitemapindex" and pages == [] and children == ["https://a.gov/s1.xml", "https://a.gov/s2.xml"]

    def test_gzipped(self):
        _, pages, _ = sr.parse_sitemap(gzip.compress(urlset("https://a.gov/x")))
        assert pages[0].url == "https://a.gov/x"

    def test_non_web_locs_are_dropped(self):
        _, pages, _ = sr.parse_sitemap(urlset("javascript:alert(1)", "ftp://a.gov/f", "https://a.gov/ok"))
        assert [p.url for p in pages] == ["https://a.gov/ok"]

    def test_entity_expansion_is_refused(self):
        bomb = (
            b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
            b'<urlset ' + NS.encode() + b'><url><loc>https://a.gov/&b;</loc></url></urlset>'
        )
        with pytest.raises(sr.SitemapError):
            sr.parse_sitemap(bomb)

    def test_gzip_bomb_is_refused(self):
        with patch.object(sr, "MAX_FILE_BYTES", 1000):
            with pytest.raises(sr.SitemapError, match="once unzipped"):
                sr.parse_sitemap(gzip.compress(b" " * 5000))

    @pytest.mark.parametrize("body", [b"<html><body>Not found</body></html>", b"not xml at all"])
    def test_a_page_that_isnt_a_sitemap(self, body):
        with pytest.raises(sr.SitemapError, match="isn't a sitemap"):
            sr.parse_sitemap(body)


def _site(routes: dict[str, httpx.Response]):
    """Patch the reader's HTTP client onto a fixed route table."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        return routes.get(url, httpx.Response(404))

    real = httpx.AsyncClient

    def client(**kw):
        kw.pop("follow_redirects", None)
        return real(transport=httpx.MockTransport(handler), follow_redirects=False, **kw)

    def validate(url, allowed_hosts=None):
        if "internal" in url:
            raise ValueError("private address")
        return url

    return seen, [
        patch.object(sr.httpx, "AsyncClient", client),
        patch("app.utils.url_validation.validate_outbound_url", validate),
        patch("app.utils.url_validation.load_allowed_hosts", AsyncMock(return_value=frozenset())),
    ]


async def _read(url, routes):
    seen, patches = _site(routes)
    for p in patches:
        p.start()
    try:
        return await sr.read_sitemap(url), seen
    finally:
        for p in patches:
            p.stop()


class TestRead:
    @pytest.mark.asyncio
    async def test_follows_an_index_into_its_children(self):
        result, _ = await _read("https://a.gov/sitemap.xml", {
            "https://a.gov/sitemap.xml": httpx.Response(200, content=index("https://a.gov/s1.xml", "https://a.gov/s2.xml.gz")),
            "https://a.gov/s1.xml": httpx.Response(200, content=urlset("https://a.gov/x", "https://a.gov/y")),
            "https://a.gov/s2.xml.gz": httpx.Response(200, content=gzip.compress(urlset("https://a.gov/y", "https://a.gov/z"))),
        })
        assert [p.url for p in result.pages] == ["https://a.gov/x", "https://a.gov/y", "https://a.gov/z"]
        assert result.sitemaps_read == 3 and not result.truncated and result.errors == []

    @pytest.mark.asyncio
    async def test_a_site_address_finds_the_sitemap_in_robots_txt(self):
        result, _ = await _read("a.gov/research", {
            "https://a.gov/robots.txt": httpx.Response(200, text="User-agent: *\nSitemap: https://a.gov/maps/main.xml\n"),
            "https://a.gov/maps/main.xml": httpx.Response(200, content=urlset("https://a.gov/x")),
        })
        assert result.sitemap_url == "https://a.gov/maps/main.xml"
        assert [p.url for p in result.pages] == ["https://a.gov/x"]

    @pytest.mark.asyncio
    async def test_falls_back_to_sitemap_xml(self):
        result, _ = await _read("https://a.gov/", {
            "https://a.gov/sitemap.xml": httpx.Response(200, content=urlset("https://a.gov/x")),
        })
        assert result.sitemap_url == "https://a.gov/sitemap.xml"

    @pytest.mark.asyncio
    async def test_no_sitemap_names_what_was_checked(self):
        with pytest.raises(sr.SitemapError, match="checked robots.txt, /sitemap.xml and /sitemap_index.xml"):
            await _read("https://a.gov/", {})

    @pytest.mark.asyncio
    async def test_a_redirect_to_a_private_address_is_refused(self):
        with pytest.raises(sr.SitemapError, match="can't be fetched: private address"):
            await _read("https://a.gov/sitemap.xml", {
                "https://a.gov/sitemap.xml": httpx.Response(302, headers={"location": "http://internal.local/sitemap.xml"}),
            })

    @pytest.mark.asyncio
    async def test_a_child_sitemap_on_a_private_address_is_skipped_not_fetched(self):
        result, seen = await _read("https://a.gov/sitemap.xml", {
            "https://a.gov/sitemap.xml": httpx.Response(200, content=index("http://internal.local/s.xml", "https://a.gov/s1.xml")),
            "https://a.gov/s1.xml": httpx.Response(200, content=urlset("https://a.gov/x")),
        })
        assert [p.url for p in result.pages] == ["https://a.gov/x"]
        assert not any("internal" in u for u in seen)
        assert result.errors and "private address" in result.errors[0]

    @pytest.mark.asyncio
    async def test_page_cap_marks_truncated(self):
        with patch.object(sr, "MAX_PAGES", 2):
            result, _ = await _read("https://a.gov/sitemap.xml", {
                "https://a.gov/sitemap.xml": httpx.Response(200, content=urlset("https://a.gov/1", "https://a.gov/2", "https://a.gov/3")),
            })
        assert len(result.pages) == 2 and result.truncated

    @pytest.mark.asyncio
    async def test_an_index_that_points_at_itself_is_read_once(self):
        result, _ = await _read("https://a.gov/sitemap.xml", {
            "https://a.gov/sitemap.xml": httpx.Response(200, content=index("https://a.gov/sitemap.xml")),
        })
        assert result.sitemaps_read == 1 and result.pages == []

    @pytest.mark.asyncio
    async def test_oversized_file_is_refused(self):
        with patch.object(sr, "MAX_FILE_BYTES", 100):
            with pytest.raises(sr.SitemapError, match="larger than"):
                await _read("https://a.gov/sitemap.xml", {
                    "https://a.gov/sitemap.xml": httpx.Response(200, content=urlset(*[f"https://a.gov/{i}" for i in range(20)])),
                })
