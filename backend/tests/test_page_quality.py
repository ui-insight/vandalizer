"""Unit tests for the crawl page-quality heuristic.

A crawl that keeps every page that loads fills the knowledge base with site
navigation (Home, Topics, Agencies) alongside the documents the user wanted.
``describe_low_value_page`` is the gate that separates them.
"""

from app.utils.page_quality import DEFAULT_MIN_CONTENT_CHARS, describe_low_value_page

_ARTICLE = "The policy applies to all funded research. " * 60  # ~2.5k chars


def test_substantive_page_is_kept():
    assert describe_low_value_page(_ARTICLE, link_count=8) is None


def test_thin_page_is_rejected():
    reason = describe_low_value_page("Home Topics Agencies World", link_count=40)
    assert reason is not None
    assert "Navigation or near-empty" in reason


def test_empty_and_none_text_are_rejected():
    assert describe_low_value_page("", link_count=0) is not None
    assert describe_low_value_page("   \n  ", link_count=0) is not None


def test_length_is_measured_after_stripping():
    """Whitespace padding must not carry a page over the minimum."""
    padded = "Contact us" + " " * DEFAULT_MIN_CONTENT_CHARS
    assert describe_low_value_page(padded, link_count=3) is not None


def test_link_index_rejected_even_when_long_enough():
    """An A-Z index clears the length floor purely on anchor text, but its
    content is still nothing but links."""
    text = "Agency listing " * 200  # ~3k chars
    reason = describe_low_value_page(text, link_count=120)
    assert reason is not None
    assert "Link index" in reason


def test_link_heavy_but_prose_rich_page_is_kept():
    """A real document that happens to cite many links is not an index."""
    text = "x" * 12_000
    assert describe_low_value_page(text, link_count=40) is None


def test_few_links_never_trips_the_density_rule():
    """A short-but-real page with a handful of links is judged on length only."""
    text = "y" * 1500
    assert describe_low_value_page(text, link_count=3) is None


def test_min_chars_is_configurable():
    text = "z" * 800
    assert describe_low_value_page(text, link_count=2) is not None
    assert describe_low_value_page(text, link_count=2, min_chars=500) is None
