"""Heuristics for telling substantive crawled pages from site navigation.

A crawl seeded from a single link reaches two very different kinds of page:
the documents the user actually wanted (a policy, a regulation part, a
guidance page) and the scaffolding that links them together (Home, Topics,
Agencies, A–Z index). Both fetch cleanly and neither errors, so a crawler that
only checks "did this page load?" files them side by side — a couple of
near-contentless chunks each, buried among the real sources.

Nav pages are still valuable as *link hubs*: the way to the good content is
usually through them. Callers should therefore keep following their links and
simply not retain them as sources.
"""

from __future__ import annotations

# A page with less extracted text than this is menu labels, a breadcrumb and a
# footer — roughly one or two chunks at the 1000-char chunk size, which is
# exactly the junk-source signature users report. Real documents clear it by
# two orders of magnitude.
DEFAULT_MIN_CONTENT_CHARS = 1200

# Text-per-link floor. An index page's "content" is almost entirely the anchor
# text of the links it lists, so it stays lean per link no matter how many
# entries it carries; a real document surrounds its links with prose.
_MIN_CHARS_PER_LINK = 100

# Only judge link density once a page has enough links for the ratio to mean
# something — a short page with three links is not an index.
_MIN_LINKS_FOR_DENSITY = 25


def describe_low_value_page(
    text: str,
    link_count: int,
    *,
    min_chars: int = DEFAULT_MIN_CONTENT_CHARS,
) -> str | None:
    """Return why a crawled page isn't worth keeping, or None if it is.

    ``text`` is the extracted main content (not raw HTML) and ``link_count``
    the number of distinct outbound links on the page. The return value is a
    human-readable reason, suitable for logging or showing to the user.
    """
    content = (text or "").strip()
    if len(content) < min_chars:
        return (
            f"Navigation or near-empty page — {len(content)} characters of "
            f"content, below the {min_chars} minimum"
        )
    if link_count >= _MIN_LINKS_FOR_DENSITY and len(content) / link_count < _MIN_CHARS_PER_LINK:
        return (
            f"Link index page — {link_count} links against only "
            f"{len(content)} characters of content"
        )
    return None
