"""Tests for app.services.saml_service.

Verifies SAML settings construction, request preparation, and response processing.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.saml_service import _get_saml_settings, _prepare_request, process_saml_response


def _make_request(
    scheme="https",
    host="app.example.com",
    path="/api/auth/saml/acs",
    query_params=None,
):
    """Build a mock FastAPI Request object."""
    request = MagicMock()
    request.url.scheme = scheme
    request.url.netloc = host
    request.url.path = path
    request.query_params = query_params or {}
    request.headers = {}
    return request


def _make_request_with_forwarded(
    forwarded_proto="https",
    forwarded_host="public.example.com",
    original_scheme="http",
    original_host="internal:8001",
    path="/api/auth/saml/acs",
    query_params=None,
):
    """Build a mock request with X-Forwarded-* headers."""
    request = MagicMock()
    request.url.scheme = original_scheme
    request.url.netloc = original_host
    request.url.path = path
    request.query_params = query_params or {}
    request.headers = {
        "x-forwarded-proto": forwarded_proto,
        "x-forwarded-host": forwarded_host,
    }
    return request


PROVIDER_CONFIG = {
    "idp_entity_id": "https://idp.example.com/metadata",
    "idp_sso_url": "https://idp.example.com/sso",
    "idp_x509_cert": "MIIC...",
    "sp_entity_id": "https://app.example.com/api/auth/saml/metadata",
    "acs_url": "https://app.example.com/api/auth/saml/acs",
}


class TestGetSamlSettings:
    def test_constructs_correct_structure(self):
        """Settings dict has the expected sp and idp structure."""
        request = _make_request()
        settings = _get_saml_settings(PROVIDER_CONFIG, request)

        assert settings["strict"] is True
        assert settings["sp"]["entityId"] == "https://app.example.com/api/auth/saml/metadata"
        assert settings["sp"]["assertionConsumerService"]["url"] == "https://app.example.com/api/auth/saml/acs"
        assert settings["sp"]["assertionConsumerService"]["binding"] == "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        assert settings["idp"]["entityId"] == "https://idp.example.com/metadata"
        assert settings["idp"]["singleSignOnService"]["url"] == "https://idp.example.com/sso"
        assert settings["idp"]["x509cert"] == "MIIC..."

    def test_uses_defaults_when_sp_fields_missing(self):
        """When sp_entity_id and acs_url are not in provider config, defaults are built from request."""
        request = _make_request(scheme="https", host="my.app.com")
        config = {"idp_entity_id": "https://idp.example.com", "idp_sso_url": "https://idp.example.com/sso", "idp_x509_cert": ""}
        settings = _get_saml_settings(config, request)

        assert settings["sp"]["entityId"] == "https://my.app.com/api/auth/saml/metadata"
        assert settings["sp"]["assertionConsumerService"]["url"] == "https://my.app.com/api/auth/saml/acs"

    def test_uses_forwarded_headers(self):
        """X-Forwarded-Proto and X-Forwarded-Host are respected."""
        request = _make_request_with_forwarded(
            forwarded_proto="https",
            forwarded_host="public.example.com",
        )
        config = {"idp_entity_id": "https://idp.example.com", "idp_sso_url": "", "idp_x509_cert": ""}
        settings = _get_saml_settings(config, request)

        assert settings["sp"]["entityId"] == "https://public.example.com/api/auth/saml/metadata"


class TestPrepareRequest:
    def test_https_scheme(self):
        """HTTPS scheme maps to 'on'."""
        request = _make_request(scheme="https", host="app.example.com", path="/saml/acs")
        result = _prepare_request(request)

        assert result["https"] == "on"
        assert result["http_host"] == "app.example.com"
        assert result["script_name"] == "/saml/acs"
        assert result["get_data"] == {}
        assert result["post_data"] == {}

    def test_http_scheme(self):
        """HTTP scheme maps to 'off'."""
        request = _make_request(scheme="http", host="localhost:8001", path="/test")
        result = _prepare_request(request)

        assert result["https"] == "off"
        assert result["http_host"] == "localhost:8001"

    def test_with_post_data(self):
        """Post data is passed through."""
        request = _make_request()
        post_data = {"SAMLResponse": "base64encoded..."}
        result = _prepare_request(request, post_data=post_data)

        assert result["post_data"] == post_data

    def test_forwarded_headers_override(self):
        """X-Forwarded-* headers take precedence over request URL."""
        request = _make_request_with_forwarded(
            forwarded_proto="https",
            forwarded_host="public.example.com",
            original_scheme="http",
            original_host="internal:8001",
        )
        result = _prepare_request(request)

        assert result["https"] == "on"
        assert result["http_host"] == "public.example.com"

    def test_query_params_included(self):
        """Query params are included in get_data."""
        request = _make_request(query_params={"RelayState": "/dashboard"})
        result = _prepare_request(request)

        assert result["get_data"] == {"RelayState": "/dashboard"}


class TestProcessSamlResponse:
    @patch("onelogin.saml2.auth.OneLogin_Saml2_Auth")
    def test_extracts_attributes_correctly(self, MockAuth):
        """Successful SAML response extracts uid, email, display_name, department."""
        mock_auth = MagicMock()
        MockAuth.return_value = mock_auth

        mock_auth.get_errors.return_value = []
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_nameid.return_value = "user@example.com"
        mock_auth.get_attributes.return_value = {
            "uid": ["jdoe"],
            "email": ["jdoe@example.com"],
            "displayName": ["Jane Doe"],
            "department": ["Computer Science"],
        }

        request = _make_request()
        post_data = {"SAMLResponse": "base64data"}

        result = process_saml_response(PROVIDER_CONFIG, request, post_data)

        assert result["uid"] == "jdoe"
        assert result["email"] == "jdoe@example.com"
        assert result["display_name"] == "Jane Doe"
        assert result["department"] == "Computer Science"
        assert result["name_id"] == "user@example.com"

    @patch("onelogin.saml2.auth.OneLogin_Saml2_Auth")
    def test_falls_back_to_name_id(self, MockAuth):
        """When uid/email attributes are missing, falls back to name_id."""
        mock_auth = MagicMock()
        MockAuth.return_value = mock_auth

        mock_auth.get_errors.return_value = []
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_nameid.return_value = "user@example.com"
        mock_auth.get_attributes.return_value = {}

        request = _make_request()
        result = process_saml_response(PROVIDER_CONFIG, request, {})

        assert result["uid"] == "user@example.com"
        assert result["email"] == "user@example.com"

    @patch("onelogin.saml2.auth.OneLogin_Saml2_Auth")
    def test_raises_on_errors(self, MockAuth):
        """Validation errors raise ValueError."""
        mock_auth = MagicMock()
        MockAuth.return_value = mock_auth

        mock_auth.get_errors.return_value = ["invalid_response"]
        mock_auth.get_last_error_reason.return_value = "Signature validation failed"

        request = _make_request()

        with pytest.raises(ValueError, match="SAML validation failed"):
            process_saml_response(PROVIDER_CONFIG, request, {})

    @patch("onelogin.saml2.auth.OneLogin_Saml2_Auth")
    def test_raises_when_not_authenticated(self, MockAuth):
        """When auth.is_authenticated() is False, raises ValueError."""
        mock_auth = MagicMock()
        MockAuth.return_value = mock_auth

        mock_auth.get_errors.return_value = []
        mock_auth.is_authenticated.return_value = False

        request = _make_request()

        with pytest.raises(ValueError, match="SAML authentication failed"):
            process_saml_response(PROVIDER_CONFIG, request, {})
