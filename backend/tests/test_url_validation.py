"""Tests for SSRF protection in url_validation utility."""

import pytest

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
