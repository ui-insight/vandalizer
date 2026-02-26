"""Utilities for SAML authentication."""

from urllib.parse import urlparse

from flask import Request, url_for
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser

from app.utilities.config import get_oauth_provider_by_type


def prepare_flask_request(request: Request) -> dict:
    """Attributes:
    request -- Flask Request object
    """
    # If server is behind proxys or balancers use the HTTP_X_FORWARDED fields
    url_data = urlparse(request.url)
    return {
        "https": "on" if request.scheme == "https" else "off",
        "http_host": request.host,
        "server_port": url_data.port,
        "script_name": request.path,
        "get_data": request.args.copy(),
        "post_data": request.form.copy(),
        # "lowercase_urlencoding": True,
        "query_string": request.query_string,
    }


def get_saml_config() -> dict | None:
    """
    Constructs the SAML settings dictionary for python3-saml.
    Fetches the 'saml' provider config from the DB.
    """
    provider_config = get_oauth_provider_by_type("saml")
    if not provider_config:
        return None

    # Common extraction
    metadata_url = provider_config.get("metadata_url")
    entity_id = provider_config.get("entity_id")
    # For a stricter setup, you might want to specify these explicitly in DB
    # or derive them from the current app context.
    
    # Base SP configuration (our app)
    # The ACS and EntityID must match what is registered in the IdP
    sp_base_url = url_for("home.index", _external=True).rstrip("/")
    # e.g., https://myapp.com
    
    # ACS URL is where IdP posts back to
    acs_url = url_for("auth.saml_authorized", _external=True)
    # Metadata URL for our SP
    sp_metadata_url = url_for("auth.saml_metadata", _external=True)

    settings = {
        "strict": True,
        "debug": True,
        "sp": {
            "entityId": sp_metadata_url,
            "assertionConsumerService": {
                "url": acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": url_for("auth.logout", _external=True),
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified",
        },
        "security": {
            "nameIdEncrypted": False,
            "authnRequestsSigned": False,
            "logoutRequestSigned": False,
            "logoutResponseSigned": False,
            "signMetadata": False,
            "wantMessagesSigned": False,
            "wantAssertionsSigned": False,
            "wantNameId": False,
            "wantNameIdEncrypted": False,
            "wantAssertionsEncrypted": False,
            "allowSingleSignOn": True,
            "wantAttributeStatement": False,
            "rejectDeprecatedAlgorithm": True,
            "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
            "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
        },
    }

    # If we have a metadata URL for the IdP, parse it
    if metadata_url:
        try:
            idp_data = OneLogin_Saml2_IdPMetadataParser.parse_remote(metadata_url)
            # Merge the parsed IdP data into our settings
            settings = OneLogin_Saml2_IdPMetadataParser.merge_settings(settings, idp_data)
        except Exception:
            # Fallback or re-raise if strict
            pass
    
    # If specific fields are set in DB config, override/augment:
    # provider_config.get("entity_id") -> settings["sp"]["entityId"] (if manual override needed)
    
    # If configurations are manual (no metadata URL), populate 'idp' dict manually here
    # from provider_config keys: sso_url, certificate, entity_id, etc.
    if "entry_point" in provider_config and "cert" in provider_config:
         settings["idp"] = {
            "entityId": provider_config.get("entity_id", ""),
            "singleSignOnService": {
                "url": provider_config["entry_point"],
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": provider_config["cert"],
        }

    return settings
