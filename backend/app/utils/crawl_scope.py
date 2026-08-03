"""Crawl-scope matching shared by the KB crawler and the workflow CrawlerNode.

An allowed-domains entry may be a bare hostname ("example.com"), a hostname
with a path prefix ("example.com/irb"), or a full URL
("https://example.com/irb/"). A path prefix restricts the crawl to that
section of the site. Matching is segment-aware: "example.com/irb" matches
/irb and /irb/apply but not /irb-archive.
"""

from urllib.parse import urlparse

# (hostname, path_prefix) — path_prefix is "" for whole-domain rules
ScopeRule = tuple[str, str]


def parse_crawl_scope(allowed_domains: str, start_url: str) -> list[ScopeRule]:
    """Parse a comma-separated allowed-domains setting into scope rules.

    Explicit entries define the entire scope — the start URL's domain is NOT
    implicitly included, so a single path-qualified entry can narrow the crawl
    below the domain level. When no usable entries are given, the scope
    defaults to the start URL's whole domain.
    """
    rules: list[ScopeRule] = []
    for entry in (allowed_domains or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "://" not in entry:
            # Bare "example.com/path" parses as all-path; force a netloc split.
            entry = "//" + entry
        parsed = urlparse(entry)
        if not parsed.netloc:
            continue
        rules.append((parsed.netloc.lower(), parsed.path.rstrip("/")))
    if not rules:
        rules.append((urlparse(start_url).netloc.lower(), ""))
    return rules


def url_in_crawl_scope(url: str, rules: list[ScopeRule]) -> bool:
    """True if url's hostname matches a rule and its path is under the rule's prefix."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    for rule_host, rule_path in rules:
        if host != rule_host:
            continue
        if not rule_path or path == rule_path or path.startswith(rule_path + "/"):
            return True
    return False
