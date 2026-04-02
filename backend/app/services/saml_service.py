"""SAML2 Service Provider wrapper using python3-saml."""

import logging
from typing import Optional

from fastapi import Request

logger = logging.getLogger(__name__)


def _get_saml_settings(provider_config: dict, request: Request) -> dict:
    """Build python3-saml settings dict from our provider config and request info."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    base_url = f"{scheme}://{host}"

    sp_entity_id = provider_config.get("sp_entity_id", f"{base_url}/api/auth/saml/metadata")
    acs_url = provider_config.get("acs_url", f"{base_url}/api/auth/saml/acs")

    return {
        "strict": True,
        "debug": provider_config.get("debug", False),
        "sp": {
            "entityId": sp_entity_id,
            "assertionConsumerService": {
                "url": acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
        "idp": {
            "entityId": provider_config.get("idp_entity_id", ""),
            "singleSignOnService": {
                "url": provider_config.get("idp_sso_url", ""),
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": provider_config.get("idp_x509_cert", ""),
        },
    }


def _prepare_request(request: Request, post_data: Optional[dict] = None) -> dict:
    """Convert FastAPI request to format expected by python3-saml."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)

    return {
        "https": "on" if scheme == "https" else "off",
        "http_host": host,
        "script_name": str(request.url.path),
        "get_data": dict(request.query_params),
        "post_data": post_data or {},
    }


def build_authn_request(provider_config: dict, request: Request) -> str:
    """Build SAML AuthnRequest and return redirect URL to IdP."""
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    saml_settings = _get_saml_settings(provider_config, request)
    req = _prepare_request(request)
    auth = OneLogin_Saml2_Auth(req, saml_settings)
    return str(auth.login())


def process_saml_response(
    provider_config: dict, request: Request, post_data: dict
) -> dict:
    """Process SAML response from IdP.

    Returns dict with user attributes: uid, email, display_name, department.
    Raises ValueError on validation failure.
    """
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    saml_settings = _get_saml_settings(provider_config, request)
    req = _prepare_request(request, post_data)
    auth = OneLogin_Saml2_Auth(req, saml_settings)
    auth.process_response()

    errors = auth.get_errors()
    if errors:
        error_reason = auth.get_last_error_reason()
        raise ValueError(f"SAML validation failed: {errors} - {error_reason}")

    if not auth.is_authenticated():
        raise ValueError("SAML authentication failed")

    attributes = auth.get_attributes()
    name_id = auth.get_nameid()

    # Extract standard attributes (attribute names vary by IdP)
    uid = (
        _first(attributes.get("uid"))
        or _first(attributes.get("urn:oid:0.9.2342.19200300.100.1.1"))
        or name_id
    )
    email = (
        _first(attributes.get("email"))
        or _first(attributes.get("urn:oid:0.9.2342.19200300.100.1.3"))
        or _first(attributes.get("mail"))
        or name_id
    )
    display_name = (
        _first(attributes.get("displayName"))
        or _first(attributes.get("urn:oid:2.16.840.1.113730.3.1.241"))
        or _first(attributes.get("cn"))
    )
    department = (
        _first(attributes.get("department"))
        or _first(attributes.get("urn:oid:2.5.4.11"))
        or _first(attributes.get("ou"))
    )

    return {
        "uid": uid,
        "email": email,
        "display_name": display_name,
        "department": department,
        "attributes": {k: v for k, v in attributes.items()},
        "name_id": name_id,
    }


def get_sp_metadata(provider_config: dict, request: Request) -> str:
    """Generate SP metadata XML."""
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    saml_settings = _get_saml_settings(provider_config, request)
    req = _prepare_request(request)
    auth = OneLogin_Saml2_Auth(req, saml_settings)
    settings = auth.get_settings()
    metadata = settings.get_sp_metadata()
    errors = settings.validate_metadata(metadata)
    if errors:
        raise ValueError(f"SP metadata validation failed: {errors}")
    return str(metadata)


def _first(val: object) -> Optional[str]:
    """Get first element from a list or return the value if it's a string."""
    if isinstance(val, list) and val:
        return str(val[0])
    if isinstance(val, str):
        return val
    return None
