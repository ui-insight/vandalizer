"""Tests for SSRF protection in url_validation utility."""

from unittest.mock import patch

import pytest

from app.utils.url_validation import (
    InvalidAllowedHost,
    allowed_private_hosts,
    env_allowed_hosts,
    normalize_allowed_host,
    validate_outbound_url,
)


class TestValidateOutboundUrl:
    def test_allows_public_https(self):
        assert validate_outbound_url("https://example.com/api") == "https://example.com/api"

    def test_allows_public_http(self):
        assert validate_outbound_url("http://example.com") == "http://example.com"

    def test_blocks_file_scheme(self):
        with pytest.raises(ValueError, match="Blocked URL scheme"):
            validate_outbound_url("file:///etc/passwd")

    def test_blocks_ftp_scheme(self):
        with pytest.raises(ValueError, match="Blocked URL scheme"):
            validate_outbound_url("ftp://internal.server/data")

    def test_blocks_no_scheme(self):
        with pytest.raises(ValueError, match="Blocked URL scheme"):
            validate_outbound_url("//example.com")

    def test_blocks_empty_hostname(self):
        with pytest.raises(ValueError):
            validate_outbound_url("http://")

    def test_blocks_localhost(self):
        with pytest.raises(ValueError, match="blocked IP"):
            validate_outbound_url("http://localhost/admin")

    def test_blocks_127_0_0_1(self):
        with pytest.raises(ValueError, match="blocked IP"):
            validate_outbound_url("http://127.0.0.1:6379/")

    def test_blocks_private_10_network(self):
        with pytest.raises(ValueError, match="blocked IP"):
            validate_outbound_url("http://10.0.0.1/internal")

    def test_blocks_private_172_network(self):
        with pytest.raises(ValueError, match="blocked IP"):
            validate_outbound_url("http://172.16.0.1/internal")

    def test_blocks_private_192_168(self):
        with pytest.raises(ValueError, match="blocked IP"):
            validate_outbound_url("http://192.168.1.1/router")

    def test_blocks_link_local(self):
        with pytest.raises(ValueError, match="blocked IP"):
            validate_outbound_url("http://169.254.169.254/latest/meta-data/")

    def test_blocks_metadata_hostname(self):
        with pytest.raises(ValueError, match="Blocked hostname"):
            validate_outbound_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_blocks_unresolvable_hostname(self):
        with pytest.raises(ValueError, match="Cannot resolve"):
            validate_outbound_url("http://this-host-definitely-does-not-exist-xyz123.invalid/")



# ---------------------------------------------------------------------------
# Operator allowlist (OUTBOUND_URL_ALLOWED_HOSTS)
# ---------------------------------------------------------------------------

_PRIVATE = [(2, 1, 6, "", ("172.27.192.252", 443))]


def _resolves_private(*_a, **_k):
    return _PRIVATE


class TestAllowedPrivateHosts:
    """An on-campus API that only has an RFC 1918 address must be reachable
    from a workflow's API Call step when an operator names it, without
    loosening the block for anything else (support ticket, 2026-09-09)."""

    @patch("app.utils.url_validation.socket.getaddrinfo", side_effect=_resolves_private)
    def test_a_listed_host_passes_the_range_check(self, _dns):
        url = "https://router.example.edu/v1/search"
        assert validate_outbound_url(url, allowed_hosts=frozenset({"router.example.edu"})) == url

    @patch("app.utils.url_validation.socket.getaddrinfo", side_effect=_resolves_private)
    def test_an_unlisted_host_on_the_same_address_is_still_blocked(self, _dns):
        with pytest.raises(ValueError, match="blocked IP"):
            validate_outbound_url(
                "https://other.example.edu/v1/search", allowed_hosts=frozenset({"router.example.edu"}),
            )

    @patch("app.utils.url_validation.socket.getaddrinfo", side_effect=_resolves_private)
    def test_the_block_message_says_how_to_allow_it(self, _dns):
        with pytest.raises(ValueError, match="Allowed private hosts.*OUTBOUND_URL_ALLOWED_HOSTS"):
            validate_outbound_url("https://router.example.edu/v1/search", allowed_hosts=frozenset())

    @patch("app.utils.url_validation.socket.getaddrinfo", side_effect=_resolves_private)
    def test_match_is_case_insensitive_and_ignores_a_trailing_dot(self, _dns):
        allowed = frozenset({"router.example.edu"})
        assert validate_outbound_url("https://Router.Example.EDU./v1", allowed_hosts=allowed)

    def test_a_listed_host_keeps_the_scheme_check(self):
        with pytest.raises(ValueError, match="Blocked URL scheme"):
            validate_outbound_url("ftp://router.example.edu/x", allowed_hosts=frozenset({"router.example.edu"}))

    def test_a_metadata_hostname_cannot_be_allowlisted(self):
        with pytest.raises(ValueError, match="Blocked hostname"):
            validate_outbound_url(
                "http://metadata.google.internal/computeMetadata/v1/",
                allowed_hosts=frozenset({"metadata.google.internal"}),
            )

    def test_a_listed_host_must_still_resolve(self):
        with pytest.raises(ValueError, match="Cannot resolve"):
            validate_outbound_url(
                "http://this-host-definitely-does-not-exist-xyz123.invalid/",
                allowed_hosts=frozenset({"this-host-definitely-does-not-exist-xyz123.invalid"}),
            )

    def test_the_setting_is_parsed_from_a_comma_separated_string(self):
        with patch("app.config.Settings") as MockSettings:
            MockSettings.return_value.outbound_url_allowed_hosts = (
                " Router.Example.edu, other.example.edu ,, metadata.google.internal , https://bad.example.edu/x"
            )
            assert env_allowed_hosts() == frozenset({"router.example.edu", "other.example.edu"})
            assert allowed_private_hosts() == frozenset({"router.example.edu", "other.example.edu"})

    def test_an_empty_setting_allows_nothing(self):
        with patch("app.config.Settings") as MockSettings:
            MockSettings.return_value.outbound_url_allowed_hosts = ""
            assert allowed_private_hosts() == frozenset()

    def test_the_admin_list_merges_with_the_env_list(self):
        """The System Config list is passed by the caller (a Beanie document
        or the raw pymongo dict); the validator never reads the database."""
        with patch("app.config.Settings") as MockSettings:
            MockSettings.return_value.outbound_url_allowed_hosts = "env.example.edu"
            as_dict = {"outbound_url_allowed_hosts": ["Admin.Example.EDU", "bad host", ""]}
            assert allowed_private_hosts(as_dict) == frozenset({"env.example.edu", "admin.example.edu"})

            class Cfg:
                outbound_url_allowed_hosts = ["admin.example.edu"]

            assert allowed_private_hosts(Cfg()) == frozenset({"env.example.edu", "admin.example.edu"})
            assert allowed_private_hosts({}) == frozenset({"env.example.edu"})


class TestNormalizeAllowedHost:
    """What the admin page may store: a bare hostname and nothing else."""

    @pytest.mark.parametrize("entry, expected", [
        ("mindrouter.example.edu", "mindrouter.example.edu"),
        ("  MindRouter.Example.EDU.  ", "mindrouter.example.edu"),
        ("localhost", "localhost"),
        ("a-b.c1", "a-b.c1"),
    ])
    def test_accepts_bare_hostnames(self, entry, expected):
        assert normalize_allowed_host(entry) == expected

    @pytest.mark.parametrize("entry", [
        "",
        "   ",
        "https://mindrouter.example.edu",
        "mindrouter.example.edu/v1/search",
        "mindrouter.example.edu:8443",
        "*.example.edu",
        "two words.example.edu",
        "-leading.example.edu",
        "[::1]",
    ])
    def test_rejects_anything_that_is_not_a_bare_hostname(self, entry):
        with pytest.raises(InvalidAllowedHost):
            normalize_allowed_host(entry)

    @pytest.mark.parametrize("entry", ["metadata.google.internal", "METADATA.internal", "instance-data"])
    def test_rejects_cloud_metadata_hostnames_outright(self, entry):
        with pytest.raises(InvalidAllowedHost, match="metadata"):
            normalize_allowed_host(entry)

    @patch("app.utils.url_validation.socket.getaddrinfo", side_effect=_resolves_private)
    def test_the_default_allowlist_comes_from_settings(self, _dns):
        with patch("app.config.Settings") as MockSettings:
            MockSettings.return_value.outbound_url_allowed_hosts = "router.example.edu"
            assert validate_outbound_url("https://router.example.edu/v1/search")


class TestAllowlistNeverExemptsLocalRanges:
    """An allowlisted name may reach RFC 1918 space, never loopback,
    link-local (cloud metadata) or reserved ranges: a listed name that
    resolves there is DNS rebinding or a misconfiguration."""

    @pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "240.0.0.1"])
    def test_listed_host_is_still_blocked(self, address):
        with patch(
            "app.utils.url_validation.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", (address, 443))],
        ):
            with pytest.raises(ValueError, match="blocked IP"):
                validate_outbound_url(
                    "https://router.example.edu/", allowed_hosts=frozenset({"router.example.edu"}),
                )

    def test_ssrf_allowed_hosts_is_read_alongside_the_outbound_setting(self):
        with patch("app.config.Settings") as MockSettings:
            MockSettings.return_value.outbound_url_allowed_hosts = "env.example.edu"
            MockSettings.return_value.ssrf_allowed_hosts = "MindRouter.Example.edu"
            assert env_allowed_hosts() == frozenset({"env.example.edu", "mindrouter.example.edu"})
