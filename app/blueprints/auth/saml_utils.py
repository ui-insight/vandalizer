"""SAML2 utilities for building python3-saml settings from SystemConfig."""

import logging

from flask import request as flask_request
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser

logger = logging.getLogger(__name__)

# Common SAML attribute OIDs and friendly names for user mapping
ATTR_MAIL = [
    "urn:oid:0.9.2342.19200300.100.1.3",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    "mail",
    "email",
    "emailAddress",
]
ATTR_DISPLAY_NAME = [
    "urn:oid:2.16.840.1.113730.3.1.241",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
    "displayName",
]
ATTR_GIVEN_NAME = [
    "urn:oid:2.5.4.42",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
    "givenName",
    "firstName",
]
ATTR_SURNAME = [
    "urn:oid:2.5.4.4",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
    "sn",
    "lastName",
]


def _first_attr(attributes: dict, candidates: list[str]) -> str | None:
    """Return the first attribute value found from a list of candidate keys."""
    for key in candidates:
        vals = attributes.get(key)
        if vals:
            return vals[0] if isinstance(vals, list) else vals
    return None


def extract_user_attrs(auth: OneLogin_Saml2_Auth) -> dict:
    """Extract user_id, email, and name from SAML response attributes."""
    attrs = auth.get_attributes()
    name_id = auth.get_nameid()

    email = _first_attr(attrs, ATTR_MAIL) or name_id
    display_name = _first_attr(attrs, ATTR_DISPLAY_NAME)
    if not display_name:
        given = _first_attr(attrs, ATTR_GIVEN_NAME) or ""
        surname = _first_attr(attrs, ATTR_SURNAME) or ""
        display_name = f"{given} {surname}".strip() or None

    return {
        "user_id": email,
        "email": email,
        "name": display_name,
    }


def _prepare_flask_request() -> dict:
    """Convert the current Flask request into the dict python3-saml expects."""
    return {
        "https": "on" if flask_request.scheme == "https" else "off",
        "http_host": flask_request.host,
        "server_port": flask_request.environ.get("SERVER_PORT", "443"),
        "script_name": flask_request.path,
        "get_data": flask_request.args.copy(),
        "post_data": flask_request.form.copy(),
    }


def _build_settings(provider: dict) -> dict:
    """Build python3-saml settings dict from a SystemConfig SAML provider entry."""
    from flask import url_for

    sp_entity_id = url_for("auth.saml_metadata", _external=True)
    sp_acs_url = url_for("auth.saml_acs", _external=True)
    sp_sls_url = url_for("auth.saml_sls", _external=True)

    name_id_format = provider.get(
        "name_id_format",
        "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
    )

    settings: dict = {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": provider.get("entity_id") or sp_entity_id,
            "assertionConsumerService": {
                "url": sp_acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": sp_sls_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": name_id_format,
        },
        "security": {
            "nameIdEncrypted": False,
            "authnRequestsSigned": bool(provider.get("x509cert") and provider.get("private_key")),
            "logoutRequestSigned": False,
            "logoutResponseSigned": False,
            "signMetadata": False,
            "wantMessagesSigned": False,
            "wantAssertionsSigned": True,
            "wantNameIdEncrypted": False,
            "wantAssertionsEncrypted": False,
        },
    }

    # Add SP certificate/key if provided
    if provider.get("x509cert"):
        settings["sp"]["x509cert"] = provider["x509cert"]
    if provider.get("private_key"):
        settings["sp"]["privateKey"] = provider["private_key"]

    # Build IdP section — prefer metadata_url for automatic config
    metadata_url = provider.get("metadata_url", "").strip()
    if metadata_url:
        try:
            idp_data = OneLogin_Saml2_IdPMetadataParser.parse_remote(
                metadata_url,
                timeout=10,
                headers={"User-Agent": "Vandalizer-SP/1.0"},
            )
            if "idp" in idp_data:
                settings["idp"] = idp_data["idp"]
            else:
                msg = (
                    f"SAML metadata from {metadata_url} did not contain an IdP section. "
                    "Verify this is a metadata URL (not an SSO login URL)."
                )
                logger.error(msg)
                raise ValueError(msg)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to fetch SAML IdP metadata from %s", metadata_url)
            raise ValueError(
                f"Could not fetch IdP metadata from {metadata_url}. "
                "Check the URL is correct and reachable. "
                "It should be the IdP metadata endpoint (e.g. "
                "https://mocksaml.com/api/saml/metadata), "
                "not the SSO login URL."
            )
    else:
        # Manual IdP configuration fallback
        settings["idp"] = {
            "entityId": provider.get("idp_entity_id", ""),
            "singleSignOnService": {
                "url": provider.get("idp_sso_url", ""),
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": provider.get("idp_x509cert", ""),
        }

    return settings


def prepare_saml_auth(provider: dict) -> OneLogin_Saml2_Auth:
    """Return a configured OneLogin_Saml2_Auth instance for the given provider."""
    req = _prepare_flask_request()
    settings = _build_settings(provider)
    return OneLogin_Saml2_Auth(req, settings)
