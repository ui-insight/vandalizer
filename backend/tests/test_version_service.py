"""Tests for pure helpers in app.services.version_service.

Redis- and HTTP-backed paths (`_fetch_latest_release`, `get_latest_release`)
are exercised by integration tests; here we cover the tag parsing, version
comparison, and VERSION-file fallback — pure logic only.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.version_service import (
    _is_newer,
    _parse_tag,
    get_current_version,
)


class TestParseTag:
    def test_semver_tag_parsed(self):
        assert _parse_tag("v5.1.0") == (5, 1, 0)

    def test_calver_tag_parsed(self):
        assert _parse_tag("v2026.04.2") == (2026, 4, 2)

    def test_tag_without_v_prefix_rejected(self):
        assert _parse_tag("5.1.0") is None

    def test_non_numeric_tag_rejected(self):
        assert _parse_tag("v5.1.beta") is None

    def test_two_component_tag_rejected(self):
        assert _parse_tag("v5.1") is None

    def test_empty_string_rejected(self):
        assert _parse_tag("") is None


class TestIsNewer:
    def test_strictly_greater_returns_true(self):
        assert _is_newer("v5.1.1", "v5.1.0") is True
        assert _is_newer("v5.2.0", "v5.1.99") is True
        assert _is_newer("v6.0.0", "v5.99.99") is True

    def test_equal_versions_return_false(self):
        assert _is_newer("v5.1.0", "v5.1.0") is False

    def test_lower_returns_false(self):
        assert _is_newer("v5.1.0", "v5.2.0") is False

    def test_unparseable_current_returns_false(self):
        # Running on a non-release build (e.g. sha-abc, dev, feature branch)
        # should never surface an "update available" claim.
        assert _is_newer("v5.1.0", "dev") is False
        assert _is_newer("v5.1.0", "sha-abc123") is False

    def test_unparseable_latest_returns_false(self):
        assert _is_newer("main", "v5.1.0") is False


class TestGetCurrentVersion:
    def test_falls_back_to_dev_when_version_file_missing(self, tmp_path):
        fake_version = tmp_path / "VERSION"  # doesn't exist
        with patch("app.services.version_service.Path", return_value=fake_version):
            assert get_current_version() == "dev"

    def test_reads_version_file_when_present(self, tmp_path):
        fake_version = tmp_path / "VERSION"
        fake_version.write_text("v5.2.3\n")
        with patch("app.services.version_service.Path", return_value=fake_version):
            assert get_current_version() == "v5.2.3"

    def test_empty_version_file_falls_back_to_dev(self, tmp_path):
        fake_version = tmp_path / "VERSION"
        fake_version.write_text("   \n")
        with patch("app.services.version_service.Path", return_value=fake_version):
            assert get_current_version() == "dev"
