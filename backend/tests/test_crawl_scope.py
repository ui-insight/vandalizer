"""Unit tests for crawl-scope parsing and matching (app.utils.crawl_scope).

The allowed-domains setting accepts bare hostnames, hostnames with path
prefixes, and full URLs. Explicit entries define the entire scope; blank
falls back to the start URL's domain.
"""

from app.utils.crawl_scope import parse_crawl_scope, url_in_crawl_scope


START = "https://www.suu.edu/irb/"


def test_blank_defaults_to_start_domain():
    scope = parse_crawl_scope("", START)
    assert scope == [("www.suu.edu", "")]
    assert url_in_crawl_scope("https://www.suu.edu/academics", scope)
    assert not url_in_crawl_scope("https://other.edu/irb", scope)


def test_bare_hostname_entry_allows_whole_domain():
    scope = parse_crawl_scope("docs.example.com", START)
    assert url_in_crawl_scope("https://docs.example.com/any/page", scope)
    assert not url_in_crawl_scope("https://example.com/any/page", scope)


def test_explicit_entries_replace_start_domain():
    # A restrictive entry must actually restrict — the start URL's domain is
    # not implicitly kept in scope (the silent no-op from the ticket).
    scope = parse_crawl_scope("www.grants.gov", "https://www.usda.gov/x")
    assert url_in_crawl_scope("https://www.grants.gov/learn", scope)
    assert not url_in_crawl_scope("https://www.usda.gov/policies", scope)


def test_path_entry_scopes_to_subdirectory():
    scope = parse_crawl_scope("www.suu.edu/irb", START)
    assert url_in_crawl_scope("https://www.suu.edu/irb", scope)
    assert url_in_crawl_scope("https://www.suu.edu/irb/", scope)
    assert url_in_crawl_scope("https://www.suu.edu/irb/apply", scope)
    assert not url_in_crawl_scope("https://www.suu.edu/", scope)
    assert not url_in_crawl_scope("https://www.suu.edu/admissions", scope)


def test_path_match_is_segment_aware():
    scope = parse_crawl_scope("www.suu.edu/irb", START)
    assert not url_in_crawl_scope("https://www.suu.edu/irb-archive", scope)
    assert not url_in_crawl_scope("https://www.suu.edu/irbs/old", scope)


def test_full_url_entry_with_scheme_and_trailing_slash():
    # Exactly what the ticket reporter typed into the field.
    scope = parse_crawl_scope("https://www.suu.edu/irb/", START)
    assert scope == [("www.suu.edu", "/irb")]
    assert url_in_crawl_scope("https://www.suu.edu/irb/forms", scope)
    assert not url_in_crawl_scope("https://www.suu.edu/admissions", scope)


def test_multiple_entries_and_whitespace():
    scope = parse_crawl_scope(" www.suu.edu/irb , docs.example.com ,, ", START)
    assert url_in_crawl_scope("https://www.suu.edu/irb/faq", scope)
    assert url_in_crawl_scope("https://docs.example.com/guide", scope)
    assert not url_in_crawl_scope("https://www.suu.edu/athletics", scope)


def test_hostname_match_is_case_insensitive_path_is_not():
    scope = parse_crawl_scope("WWW.SUU.EDU/Forms", START)
    assert url_in_crawl_scope("https://www.suu.edu/Forms/consent", scope)
    assert not url_in_crawl_scope("https://www.suu.edu/forms/consent", scope)


def test_unparseable_entry_falls_back_to_start_domain():
    # An entry with no recoverable hostname is dropped; with nothing left,
    # the scope defaults to the start domain rather than allowing everything.
    scope = parse_crawl_scope("/just-a-path", START)
    assert scope == [("www.suu.edu", "")]
