"""Tests for SSRF protection in url_validation utility."""

import pytest

from app.utils import url_validation
from app.utils.url_validation import validate_outbound_url


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


class TestAllowedPrivateHosts:
    """Hosts in ssrf_allowed_hosts may resolve to private (campus) ranges."""

    @pytest.fixture
    def allow_trusted_host(self, monkeypatch):
        def _allow(*hosts, resolve_to="172.27.192.252"):
            monkeypatch.setattr(
                url_validation, "_allowed_private_hosts",
                lambda: frozenset(h.lower() for h in hosts),
            )
            monkeypatch.setattr(
                url_validation.socket, "getaddrinfo",
                lambda host, port, proto=None: [(2, 1, 6, "", (resolve_to, port))],
            )
        return _allow

    def test_allowed_host_may_resolve_private(self, allow_trusted_host):
        allow_trusted_host("mindrouter.uidaho.edu")
        url = "https://mindrouter.uidaho.edu/v1/search"
        assert validate_outbound_url(url) == url

    def test_allowed_host_match_is_case_insensitive(self, allow_trusted_host):
        allow_trusted_host("mindrouter.uidaho.edu")
        url = "https://MindRouter.uidaho.edu/v1/search"
        assert validate_outbound_url(url) == url

    def test_other_private_hosts_still_blocked(self, allow_trusted_host):
        allow_trusted_host("mindrouter.uidaho.edu")
        with pytest.raises(ValueError, match="blocked IP"):
            validate_outbound_url("https://other.uidaho.edu/")

    def test_allowed_host_still_blocked_on_loopback(self, allow_trusted_host):
        allow_trusted_host("mindrouter.uidaho.edu", resolve_to="127.0.0.1")
        with pytest.raises(ValueError, match="blocked IP"):
            validate_outbound_url("https://mindrouter.uidaho.edu/")

    def test_allowed_host_still_blocked_on_link_local(self, allow_trusted_host):
        allow_trusted_host("mindrouter.uidaho.edu", resolve_to="169.254.169.254")
        with pytest.raises(ValueError, match="blocked IP"):
            validate_outbound_url("https://mindrouter.uidaho.edu/")

    def test_allowlist_parses_settings_csv(self, monkeypatch):
        class _FakeSettings:
            ssrf_allowed_hosts = " MindRouter.uidaho.edu , other.host ,"

        import app.config

        url_validation._allowed_private_hosts.cache_clear()
        monkeypatch.setattr(app.config, "Settings", lambda: _FakeSettings())
        try:
            assert url_validation._allowed_private_hosts() == frozenset(
                {"mindrouter.uidaho.edu", "other.host"}
            )
        finally:
            url_validation._allowed_private_hosts.cache_clear()
